import math
import re
from hashlib import sha256

from PySide6.QtCore import QObject, QBuffer, QByteArray, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QClipboard

from core.image_store import ImageStore
from core.database import ClipboardDatabase, detect_type


def is_sensitive_text(text):
    value = text.strip()
    lowered = value.lower()

    if not value:
        return False

    if detect_type(value) in ("link", "path", "img"):
        return False

    if re.fullmatch(r"\d{4,32}", value):
        return True

    sensitive_words = (
        "otp",
        "one-time",
        "one time",
        "verification code",
        "security code",
        "password",
        "passcode",
        "passwd",
        "pwd",
        "secret",
        "token",
    )
    if any(word in lowered for word in sensitive_words):
        return True

    if re.search(r"\s", value):
        return False

    if 8 <= len(value) <= 128:
        has_letter = any(ch.isalpha() for ch in value)
        has_digit = any(ch.isdigit() for ch in value)
        has_symbol = any(not ch.isalnum() for ch in value)
        category_count = sum((has_letter, has_digit, has_symbol))

        if category_count >= 2:
            return True

        if value.isalpha() and len(set(value.lower())) >= 5:
            return True

        if has_letter and len(value) >= 14 and text_entropy(value) >= 3.0:
            return True

    return False


def text_entropy(text):
    counts = {ch: text.count(ch) for ch in set(text)}
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


class ClipboardManager(QObject):
    text_copied = Signal(str)
    sensitive_text_copied = Signal(str)
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
        self.clipboard.dataChanged.connect(self.on_data_changed)

    def get_db(self):
        """Return the database instance for external queries."""
        return self.db

    def set_text_for_paste(self, text):
        self._ignore_next = True
        self._last_text = text
        self.clipboard.setText(text, QClipboard.Clipboard)

    def set_image_for_paste(self, image_path):
        image = QImage(image_path)
        if image.isNull():
            return False

        self._ignore_next = True
        self._last_image_cache_key = image.cacheKey()
        self.clipboard.setImage(image, QClipboard.Clipboard)
        return True

    def on_data_changed(self):
        if self._ignore_next:
            self._ignore_next = False
            return

        mime = self.clipboard.mimeData()
        if mime.hasImage():
            image = self.clipboard.image()
            if image.isNull():
                return

            image_hash = self._hash_image(image)
            cache_key = image.cacheKey()
            if image_hash and image_hash != self._last_image_hash:
                self._last_image_hash = image_hash
                self._last_image_cache_key = cache_key
                image_path = self.image_store.save_image(image, "screenshot")
                if image_path:
                    # store in DB as type='img' (content column holds image path)
                    self.db.insert_with_type(image_path, "img")
                    self.image_copied.emit(image_path)
            return


        if not mime.hasText():
            return

        text = mime.text().strip()
        if not text or text == self._last_text:
            return

        self._last_text = text
        if is_sensitive_text(text):
            self.db.delete_by_content(text)
            self.sensitive_text_copied.emit(text)
            return

        self.db.insert(text)
        self.text_copied.emit(text)

    def _hash_image(self, image):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        if not image.save(buffer, "PNG"):
            return None
        data = bytes(buffer.data())
        return sha256(data).hexdigest()
