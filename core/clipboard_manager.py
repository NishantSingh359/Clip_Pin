from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QObject, QBuffer, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QClipboard

from core.image_store import ImageStore
from core.database import ClipboardDatabase
from config import MAX_CLIP_ITEM_SIZE_BYTES
from utils.app_logging import log_exception, safe_slot
from utils.item_limits import is_oversized_file, is_oversized_text


class ClipboardManager(QObject):
    text_copied = Signal(str)
    image_copied = Signal(str)
    path_copied = Signal(str)
    oversized_item_rejected = Signal()

    def __init__(self, base_dir):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.image_store = ImageStore(base_dir)
        self.db = ClipboardDatabase(base_dir)
        self._last_text = ""
        self._last_image_cache_key = None
        self._last_image_hash = None
        self._pending_image_hashes = set()
        self._ignore_next_count = 0
        self._pending_restore = False
        self._restore_text = None
        self._restore_image = None
        self._image_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="copypin-image")
        self._image_lock = Lock()
        self.clipboard.dataChanged.connect(self.on_data_changed)

    def get_db(self):
        """Return the database instance for external queries."""
        return self.db

    def set_text_for_paste(self, text, temporary=False):
        self._ignore_next_count += 1
        self._last_text = text
        self._restore_text = self._get_current_clipboard_text()
        self._restore_image = self._get_current_clipboard_image()
        self.clipboard.setText(text, QClipboard.Clipboard)
        if temporary:
            self._pending_restore = True

    def set_image_for_paste(self, image_path, temporary=False):
        try:
            image = QImage(image_path)
            if image.isNull():
                return False

            self._ignore_next_count += 1
            self._last_image_cache_key = image.cacheKey()
            self._last_image_hash = self._hash_image(image)
            self._restore_text = self._get_current_clipboard_text()
            self._restore_image = self._get_current_clipboard_image()
            self.clipboard.setImage(image, QClipboard.Clipboard)
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
            self._last_image_hash = self._hash_image(previous_image)
            self.clipboard.setImage(previous_image, QClipboard.Clipboard)
            return
        if previous_text is not None:
            self._last_text = previous_text
            self.clipboard.setText(previous_text, QClipboard.Clipboard)
            return

        self._last_text = ""
        self._last_image_cache_key = None
        self._last_image_hash = None
        self.clipboard.clear(QClipboard.Clipboard)

    @safe_slot("Failed to process clipboard change")
    def on_data_changed(self):
        if getattr(self, "_ignore_next_count", 0) > 0:
            self._ignore_next_count -= 1
            return

        mime = self.clipboard.mimeData()
        if mime.hasImage():
            image = self.clipboard.image()
            if image.isNull():
                return

            cache_key = image.cacheKey()
            if cache_key == self._last_image_cache_key:
                return

            # Image size metadata is O(1); avoid reading every encoded clipboard
            # format on the UI thread. Hashing/encoding happens in the worker.
            source_size_bytes = self.image_store.image_payload_size(image)
            if source_size_bytes is None or source_size_bytes > MAX_CLIP_ITEM_SIZE_BYTES:
                # Remember this image so repeated clipboard notifications do not
                # repeatedly inspect and reject the same oversized content.
                self._last_image_cache_key = cache_key
                if source_size_bytes is not None:
                    self.oversized_item_rejected.emit()
                return

            self._last_image_cache_key = cache_key
            self._image_executor.submit(
                self._process_image,
                image,
                None,
                False,
                source_size_bytes,
            )
            return

        if mime.hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).exists()
            ]
            rejected_oversized_path = False
            if paths:
                for path in paths:
                    content = str(path)
                    if is_oversized_text(content):
                        rejected_oversized_path = True
                        continue
                    if is_oversized_file(path):
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
            if mime.hasHtml() and is_oversized_text(mime.html()):
                self.oversized_item_rejected.emit()
            return

        raw_text = mime.text()
        if is_oversized_text(raw_text) or (
            mime.hasHtml() and is_oversized_text(mime.html())
        ):
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
                if is_oversized_text(text) or is_oversized_file(path):
                    self.oversized_item_rejected.emit()
                    return
                self.db.insert_with_type(text, "path")
                self.path_copied.emit(text)
            else:
                self.db.insert(text)
                self.text_copied.emit(text)
        except Exception:
            log_exception("Failed to store text clipboard item")

    def _process_image(self, image, image_hash=None, reserved=False, source_size_bytes=None):
        try:
            image_hash = image_hash or self._hash_image(image)
            if not image_hash:
                return

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
            if image_file.is_file() and image_file.stat().st_size > MAX_CLIP_ITEM_SIZE_BYTES:
                image_file.unlink(missing_ok=True)
                self.oversized_item_rejected.emit()
                return

            self.db.insert_with_type(image_path, "img")
            with self._image_lock:
                self._last_image_hash = image_hash
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
        try:
            self.clipboard.dataChanged.disconnect(self.on_data_changed)
        except (RuntimeError, TypeError):
            pass
        self._image_executor.shutdown(wait=True, cancel_futures=True)
