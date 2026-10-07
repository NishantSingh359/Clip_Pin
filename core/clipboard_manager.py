import base64
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import monotonic

from PySide6.QtCore import QObject, QByteArray, QBuffer, QMimeData, Signal, Slot, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QClipboard

from core.image_store import ImageStore
from core.database import ClipboardDatabase
from config import MAX_CLIP_ITEM_SIZE_BYTES
from utils.app_logging import log_exception, safe_slot
from utils.item_limits import is_oversized_file, is_oversized_text

PASTE_IMAGE_CACHE_MAX_BYTES = 48 * 1024 * 1024
MAX_PERSISTED_RICH_FORMAT_BYTES = 16 * 1024 * 1024


class ClipboardManager(QObject):
    text_copied = Signal(str)
    image_copied = Signal(str)
    path_copied = Signal(str)
    oversized_item_rejected = Signal()

    def __init__(self, base_dir):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.image_store = ImageStore(base_dir)
        self.enforce_size_limit = True
        self.db = ClipboardDatabase(base_dir)
        self._last_text = ""
        self._last_image_cache_key = None
        self._last_image_hash = None
        self._pending_image_hashes = set()
        self._ignored_image_hashes = {}
        self._paste_image_cache = OrderedDict()
        self._paste_image_cache_bytes = 0
        self._ignore_next_count = 0
        self._pending_restore = False
        self._restore_text = None
        self._restore_image = None
        self._restore_image_hash = None
        self._clipboard_image_snapshot = None
        self._clipboard_image_snapshot_hash = None
        self._clipboard_rich_formats_snapshot = {}
        self._restore_rich_formats = {}
        self._rich_formats_by_image_path = {}
        self._image_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="copypin-image")
        self._image_lock = Lock()
        self._clipboard_change_timer = QTimer(self)
        self._clipboard_change_timer.setSingleShot(True)
        self._clipboard_change_timer.setInterval(200)
        self._clipboard_change_timer.timeout.connect(self._process_clipboard_change)
        self.clipboard.dataChanged.connect(self.on_data_changed)

    def get_db(self):
        """Return the database instance for external queries."""
        return self.db

    def set_size_limit_enabled(self, enabled):
        self.enforce_size_limit = bool(enabled)
        self.image_store.set_size_limit_enabled(enabled)

    def ignore_image_capture(self, image_path):
        """Ignore clipboard copies of an image opened by an external viewer.

        Queue registration on the image worker before launching the viewer so
        any clipboard image it publishes is checked against the registered hash.
        """
        self._image_executor.submit(self._register_ignored_image, str(image_path))

    def _register_ignored_image(self, image_path):
        try:
            image = QImage(image_path)
            image_hash = self._hash_image(image) if not image.isNull() else None
            if image_hash:
                expires_at = monotonic() + 30
                self._ignored_image_hashes = {
                    known_hash: expiry
                    for known_hash, expiry in self._ignored_image_hashes.items()
                    if expiry >= monotonic()
                }
                self._ignored_image_hashes[image_hash] = expires_at
        except Exception:
            log_exception("Failed to register image opened in external viewer")

    def set_text_for_paste(self, text, temporary=False):
        self._ignore_next_count += 1
        self._last_text = text
        self._restore_text = self._get_current_clipboard_text()
        self._restore_image = self._clipboard_image_snapshot
        if self._restore_image is None:
            self._restore_image = self._get_current_clipboard_image()
        self._restore_image_hash = self._clipboard_image_snapshot_hash
        self._restore_rich_formats = self._clipboard_rich_formats_snapshot
        self.clipboard.setText(text, QClipboard.Clipboard)
        self._clipboard_image_snapshot = None
        self._clipboard_image_snapshot_hash = None
        self._clipboard_rich_formats_snapshot = {}
        if temporary:
            self._pending_restore = True

    def set_image_for_paste(self, image_path, temporary=False):
        try:
            image, image_hash = self._load_paste_image(image_path)
            if image.isNull():
                return False

            self._ignore_next_count += 1
            self._last_image_cache_key = image.cacheKey()
            self._last_image_hash = image_hash
            self._restore_text = self._get_current_clipboard_text()
            self._restore_image = self._clipboard_image_snapshot
            if self._restore_image is None:
                self._restore_image = self._get_current_clipboard_image()
            self._restore_image_hash = self._clipboard_image_snapshot_hash
            self._restore_rich_formats = self._clipboard_rich_formats_snapshot
            rich_formats = self._load_rich_formats(image_path)
            if rich_formats:
                self.clipboard.setMimeData(self._mime_data_with_image(rich_formats, image))
            else:
                self.clipboard.setImage(image, QClipboard.Clipboard)
            self._clipboard_image_snapshot = image
            self._clipboard_image_snapshot_hash = image_hash
            self._clipboard_rich_formats_snapshot = rich_formats or {}
            if temporary:
                self._pending_restore = True
            return True
        except Exception:
            log_exception("Failed to set image for paste")
            return False

    def restore_previous_clipboard(self):
        if not getattr(self, "_pending_restore", False):
            return

        self._pending_restore = False
        self._ignore_next_count += 1
        previous_text = getattr(self, "_restore_text", None)
        previous_image = getattr(self, "_restore_image", None)
        if previous_image is not None:
            self._last_image_cache_key = previous_image.cacheKey()
            self._last_image_hash = (
                self._restore_image_hash or self._hash_image(previous_image)
            )
            if self._restore_rich_formats:
                self.clipboard.setMimeData(
                    self._mime_data_with_image(self._restore_rich_formats, previous_image)
                )
            else:
                self.clipboard.setImage(previous_image, QClipboard.Clipboard)
            self._clipboard_image_snapshot = previous_image
            self._clipboard_image_snapshot_hash = self._last_image_hash
            self._clipboard_rich_formats_snapshot = self._restore_rich_formats or {}
            return
        if previous_text is not None:
            self._last_text = previous_text
            self.clipboard.setText(previous_text, QClipboard.Clipboard)
            self._clipboard_image_snapshot = None
            self._clipboard_image_snapshot_hash = None
            self._clipboard_rich_formats_snapshot = {}
            return

        self._last_text = ""
        self._last_image_cache_key = None
        self._last_image_hash = None
        self._clipboard_image_snapshot = None
        self._clipboard_image_snapshot_hash = None
        self._clipboard_rich_formats_snapshot = {}
        self.clipboard.clear(QClipboard.Clipboard)

    @Slot()
    @safe_slot("Failed to process clipboard change")
    def on_data_changed(self):
        if getattr(self, "_ignore_next_count", 0) > 0:
            self._ignore_next_count -= 1
            return

        # Design tools often publish several clipboard formats in sequence.
        # Wait for the burst to settle, then inspect the final MIME payload once.
        if self.sender() is self.clipboard:
            self._clipboard_change_timer.start()
            return

        # Keep direct calls useful for integrations and unit-level callers.
        self._process_clipboard_change()

    @safe_slot("Failed to process clipboard change")
    def _process_clipboard_change(self):

        mime = self.clipboard.mimeData()
        if mime.hasImage():
            image = self.clipboard.image()
            if image.isNull():
                self._clipboard_image_snapshot = None
                self._clipboard_image_snapshot_hash = None
                self._clipboard_rich_formats_snapshot = {}
                return
            self._clipboard_image_snapshot = image
            self._clipboard_image_snapshot_hash = None

            cache_key = image.cacheKey()
            if cache_key == self._last_image_cache_key:
                return

            # Image size metadata is O(1); avoid reading every encoded clipboard
            # format on the UI thread. Hashing/encoding happens in the worker.
            source_size_bytes = self.image_store.image_payload_size(image)
            if source_size_bytes is None or (
                self.enforce_size_limit and source_size_bytes > MAX_CLIP_ITEM_SIZE_BYTES
            ):
                # Remember this image so repeated clipboard notifications do not
                # repeatedly inspect and reject the same oversized content.
                self._last_image_cache_key = cache_key
                if self.enforce_size_limit and source_size_bytes is not None:
                    self.oversized_item_rejected.emit()
                return

            # Only copy rich format payloads after deduplication and size checks.
            # Some applications publish large native clipboard formats, and
            # reading them eagerly would add work to every clipboard update.
            rich_formats = self._capture_rich_formats(mime)
            self._clipboard_rich_formats_snapshot = rich_formats

            self._last_image_cache_key = cache_key
            self._image_executor.submit(
                self._process_image,
                image,
                None,
                False,
                source_size_bytes,
                rich_formats,
            )
            return

        if mime.hasUrls():
            self._clipboard_image_snapshot = None
            self._clipboard_image_snapshot_hash = None
            self._clipboard_rich_formats_snapshot = {}
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).exists()
            ]
            rejected_oversized_path = False
            if paths:
                for path in paths:
                    content = str(path)
                    if self.enforce_size_limit and is_oversized_text(content):
                        rejected_oversized_path = True
                        continue
                    if self.enforce_size_limit and is_oversized_file(path):
                        rejected_oversized_path = True
                        continue
                    try:
                        self.db.insert_with_type(content, "path")
                        self.path_copied.emit(content)
                    except Exception:
                        log_exception("Failed to store clipboard path")
                if rejected_oversized_path:
                    self.oversized_item_rejected.emit()
                return


        if not mime.hasText():
            self._clipboard_image_snapshot = None
            self._clipboard_image_snapshot_hash = None
            self._clipboard_rich_formats_snapshot = {}
            if self.enforce_size_limit and mime.hasHtml() and is_oversized_text(mime.html()):
                self.oversized_item_rejected.emit()
            return

        raw_text = mime.text()
        self._clipboard_image_snapshot = None
        self._clipboard_image_snapshot_hash = None
        self._clipboard_rich_formats_snapshot = {}
        if self._is_vector_markup(raw_text, mime):
            self._last_text = raw_text
            return
        if self.enforce_size_limit and (is_oversized_text(raw_text) or (
            mime.hasHtml() and is_oversized_text(mime.html())
        )):
            if raw_text != self._last_text:
                self.oversized_item_rejected.emit()
            self._last_text = raw_text
            return

        text = raw_text.strip()
        if not text or text == self._last_text:
            return

        self._last_text = text
        try:
            path = Path(text)
            if path.exists():
                if self.enforce_size_limit and (is_oversized_text(text) or is_oversized_file(path)):
                    self.oversized_item_rejected.emit()
                    return
                self.db.insert_with_type(text, "path")
                self.path_copied.emit(text)
            else:
                self.db.insert(text)
                self.text_copied.emit(text)
        except Exception:
            log_exception("Failed to store text clipboard item")

    @staticmethod
    def _is_vector_markup(text, mime):
        sample = str(text).lstrip()[:20000].lower()
        formats = " ".join(str(item).lower() for item in mime.formats())
        return (
            (sample.startswith("<?xml") and "<svg" in sample)
            or sample.startswith("<svg")
            or ("svg" in formats and ("<?xml" in sample or "<svg" in sample))
        )

    @staticmethod
    def _capture_rich_formats(mime):
        """Capture non-raster formats needed to round-trip editable objects."""
        formats = {}
        total_bytes = 0
        try:
            for raw_format in mime.formats():
                format_name = str(raw_format)
                normalized = format_name.lower()
                if normalized == "application/x-qt-image" or any(
                    marker in normalized
                    for marker in (
                        'value="cf_dib"',
                        'value="cf_dibv5"',
                        'value="cf_bitmap"',
                    )
                ):
                    continue
                if normalized.startswith("image/") and not any(
                    marker in normalized for marker in ("svg", "emf", "wmf", "metafile")
                ):
                    continue
                payload = bytes(mime.data(raw_format))
                if not payload:
                    continue
                total_bytes += len(payload)
                if total_bytes > MAX_PERSISTED_RICH_FORMAT_BYTES:
                    return {}
                formats[format_name] = payload
        except Exception:
            log_exception("Failed to capture rich clipboard formats")
            return {}
        return formats

    @staticmethod
    def _mime_data_with_image(formats, image):
        mime_data = QMimeData()
        for format_name, payload in formats.items():
            mime_data.setData(format_name, QByteArray(payload))
        mime_data.setImageData(image)
        return mime_data

    @staticmethod
    def _rich_formats_sidecar_path(image_path):
        return Path(f"{image_path}.mime.json")

    def _save_rich_formats(self, image_path, formats):
        if not formats:
            return
        sidecar_path = self._rich_formats_sidecar_path(image_path)
        try:
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            encoded = {
                name: base64.b64encode(payload).decode("ascii")
                for name, payload in formats.items()
            }
            with sidecar_path.open("w", encoding="utf-8") as sidecar:
                json.dump({"version": 1, "formats": encoded}, sidecar)
            self._rich_formats_by_image_path[str(Path(image_path).resolve())] = formats
        except Exception:
            log_exception("Failed to persist rich clipboard formats")

    def _load_rich_formats(self, image_path):
        key = str(Path(image_path).resolve())
        cached = self._rich_formats_by_image_path.get(key)
        if cached is not None:
            return cached
        sidecar_path = self._rich_formats_sidecar_path(image_path)
        try:
            with sidecar_path.open("r", encoding="utf-8") as sidecar:
                stored = json.load(sidecar)
            if stored.get("version") != 1 or not isinstance(stored.get("formats"), dict):
                return {}
            decoded = {
                name: base64.b64decode(payload, validate=True)
                for name, payload in stored["formats"].items()
            }
            self._rich_formats_by_image_path[key] = decoded
            return decoded
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _process_image(
        self, image, image_hash=None, reserved=False, source_size_bytes=None, rich_formats=None
    ):
        try:
            image_cache_key = image.cacheKey()
            image_hash = image_hash or self._hash_image(image)
            if not image_hash:
                return

            ignored_until = self._ignored_image_hashes.get(image_hash)
            if ignored_until is not None:
                if monotonic() <= ignored_until:
                    return
                self._ignored_image_hashes.pop(image_hash, None)

            with self._image_lock:
                if image_hash == self._last_image_hash:
                    self._pending_image_hashes.discard(image_hash)
                    return
                if not reserved and image_hash in self._pending_image_hashes:
                    return
                self._pending_image_hashes.add(image_hash)

            image_path = self.image_store.save_image(
                image,
                "screenshot",
                source_size_bytes,
            )
            if not image_path:
                return

            image_file = Path(image_path)
            if (self.enforce_size_limit and image_file.is_file()
                    and image_file.stat().st_size > MAX_CLIP_ITEM_SIZE_BYTES):
                image_file.unlink(missing_ok=True)
                self.oversized_item_rejected.emit()
                return

            self.db.insert_with_type(image_path, "img")
            if rich_formats:
                self._save_rich_formats(image_path, rich_formats)
            if image_cache_key == self._last_image_cache_key:
                with self._image_lock:
                    self._last_image_hash = image_hash
            snapshot = self._clipboard_image_snapshot
            if snapshot is not None and image_cache_key == snapshot.cacheKey():
                self._clipboard_image_snapshot_hash = image_hash
            self.image_copied.emit(image_path)
        except Exception:
            log_exception("Failed to process clipboard image")
        finally:
            if image_hash:
                with self._image_lock:
                    self._pending_image_hashes.discard(image_hash)

    def _hash_image(self, image):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        if not image.save(buffer, "PNG"):
            return None
        data = bytes(buffer.data())
        return sha256(data).hexdigest()

    def _load_paste_image(self, image_path):
        """Load and hash a saved image once, reusing recent decoded images."""
        path = Path(image_path)
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None

        key = str(path.resolve())
        cached = self._paste_image_cache.get(key)
        if cached is not None and cached[0] == signature:
            self._paste_image_cache.move_to_end(key)
            return cached[1], cached[2]
        if cached is not None:
            self._paste_image_cache_bytes -= cached[3]
            del self._paste_image_cache[key]

        image = QImage(str(path))
        if image.isNull():
            return image, None
        image_hash = self._hash_image(image)
        image_bytes = max(0, int(image.sizeInBytes()))
        if signature is not None and image_hash and image_bytes <= PASTE_IMAGE_CACHE_MAX_BYTES:
            self._paste_image_cache[key] = (signature, image, image_hash, image_bytes)
            self._paste_image_cache_bytes += image_bytes
            while (
                self._paste_image_cache_bytes > PASTE_IMAGE_CACHE_MAX_BYTES
                and len(self._paste_image_cache) > 1
            ):
                _, evicted = self._paste_image_cache.popitem(last=False)
                self._paste_image_cache_bytes -= evicted[3]
        return image, image_hash

    def _get_current_clipboard_text(self):
        mime = self.clipboard.mimeData()
        if mime and mime.hasText():
            return mime.text()
        return None

    def _get_current_clipboard_image(self):
        mime = self.clipboard.mimeData()
        if mime and mime.hasImage():
            image = self.clipboard.image()
            if not image.isNull():
                return image
        return None

    def close(self):
        self._clipboard_change_timer.stop()
        try:
            self.clipboard.dataChanged.disconnect(self.on_data_changed)
        except (RuntimeError, TypeError):
            pass
        self._image_executor.shutdown(wait=True, cancel_futures=True)
