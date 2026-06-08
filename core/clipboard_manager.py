from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
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

    def __init__(self, base_dir):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.image_store = ImageStore(base_dir)
        self.db = ClipboardDatabase(base_dir)
        self._last_text = ""
        self._last_image_cache_key = None
        self._last_image_hash = None
        self._ignore_next = False
        self._image_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="copypin-image")
        self._image_lock = Lock()
        self.clipboard.dataChanged.connect(self.on_data_changed)

    def get_db(self):
        """Return the database instance for external queries."""
        return self.db

    def set_text_for_paste(self, text):
        self._ignore_next = True
        self._last_text = text
        self.clipboard.setText(text, QClipboard.Clipboard)

    def set_image_for_paste(self, image_path):
        try:
            image = QImage(image_path)
            if image.isNull():
                return False

            self._ignore_next = True
            self._last_image_cache_key = image.cacheKey()
            self.clipboard.setImage(image, QClipboard.Clipboard)
            return True
        except Exception:
            log_exception("Failed to set image for paste")
            return False

    @safe_slot("Failed to process clipboard change")
    def on_data_changed(self):
        if self._ignore_next:
            self._ignore_next = False
            return

        mime = self.clipboard.mimeData()
        if mime.hasImage():
            image = self.clipboard.image()
            if image.isNull():
                return

            cache_key = image.cacheKey()
            if cache_key == self._last_image_cache_key:
                return

            self._last_image_cache_key = cache_key
            self._image_executor.submit(self._process_image, image.copy())
            return


        if not mime.hasText():
            return

        text = mime.text().strip()
        if not text or text == self._last_text:
            return

        self._last_text = text
        try:
            self.db.insert(text)
            self.text_copied.emit(text)
        except Exception:
            log_exception("Failed to store text clipboard item")

    def _process_image(self, image):
        try:
            image_hash = self._hash_image(image)
            if not image_hash:
                return

            with self._image_lock:
                if image_hash == self._last_image_hash:
                    return

            image_path = self.image_store.save_image(image, "screenshot")
            if not image_path:
                return

            self.db.insert_with_type(image_path, "img")
            with self._image_lock:
                self._last_image_hash = image_hash
            self.image_copied.emit(image_path)
        except Exception:
            log_exception("Failed to process clipboard image")

    def _hash_image(self, image):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        if not image.save(buffer, "PNG"):
            return None
        data = bytes(buffer.data())
        return sha256(data).hexdigest()

    def close(self):
        self._image_executor.shutdown(wait=False, cancel_futures=True)
