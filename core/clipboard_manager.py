from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QObject, QBuffer, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QClipboard

from core.image_store import ImageStore
from core.database import ClipboardDatabase
from utils.app_logging import log_exception, safe_slot


class ClipboardManager(QObject):
    text_copied = Signal(str)
    image_copied = Signal(str)
    path_copied = Signal(str)

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

            image_hash = self._hash_image(image)
            if not image_hash:
                return

            with self._image_lock:
                if image_hash == self._last_image_hash or image_hash in self._pending_image_hashes:
                    return
                self._pending_image_hashes.add(image_hash)

            self._last_image_cache_key = cache_key
            self._image_executor.submit(self._process_image, image.copy(), image_hash, True)
            return

        if mime.hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).exists()
            ]
            if paths:
                for path in paths:
                    content = str(path)
                    try:
                        self.db.insert_with_type(content, "path")
                        self.path_copied.emit(content)
                    except Exception:
                        log_exception("Failed to store clipboard path")
                return


        if not mime.hasText():
            return

        text = mime.text().strip()
        if not text or text == self._last_text:
            return

        self._last_text = text
        try:
            if Path(text).exists():
                self.db.insert_with_type(text, "path")
                self.path_copied.emit(text)
            else:
                self.db.insert(text)
                self.text_copied.emit(text)
        except Exception:
            log_exception("Failed to store text clipboard item")

    def _process_image(self, image, image_hash=None, reserved=False):
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

            image_path = self.image_store.save_image(image, "screenshot")
            if not image_path:
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
