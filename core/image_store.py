from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from config import (
    MAX_STORED_IMAGE_BYTES,
    MAX_STORED_IMAGE_DIMENSION,
    THUMBNAILS_DIR,
    THUMBNAIL_RETENTION_DAYS,
    THUMBNAIL_PURGE_PREFIXES,
)
from utils.app_logging import log_exception



class ImageStore:
    def __init__(self, base_dir):
        self.thumbnail_dir = Path(base_dir) / THUMBNAILS_DIR
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

    def purge_old_thumbnails(self, retention_days: int = THUMBNAIL_RETENTION_DAYS) -> int:
        """Delete thumbnail image files older than retention_days.

        Only deletes files whose name starts with one of THUMBNAIL_PURGE_PREFIXES.
        """
        if not self.thumbnail_dir.exists():
            return 0

        now_ts = datetime.now().timestamp()
        cutoff_ts = now_ts - (retention_days * 24 * 60 * 60)

        deleted = 0
        for p in self.thumbnail_dir.glob("*.png"):
            name = p.name
            if not any(name.startswith(prefix) for prefix in THUMBNAIL_PURGE_PREFIXES):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff_ts:
                try:
                    p.unlink(missing_ok=True)  # type: ignore[arg-type]
                    deleted += 1
                except OSError:
                    pass
        return deleted

    def save_image(self, image_data, prefix="image"):

        image = self._as_image(image_data)
        if image is None or image.isNull():
            return None

        image = self._bounded_image(image)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.thumbnail_dir / f"{prefix}_{stamp}_{uuid4().hex[:8]}.png"
        try:
            if image.save(str(path), "PNG"):
                return str(path)
        except Exception:
            log_exception("Failed to save image thumbnail")
        return None

    def _as_image(self, image_data):
        if isinstance(image_data, QImage):
            return image_data

        if isinstance(image_data, QPixmap):
            return image_data.toImage()

        return None

    def _bounded_image(self, image):
        max_dimension = max(1, MAX_STORED_IMAGE_DIMENSION)
        if image.width() > max_dimension or image.height() > max_dimension:
            image = image.scaled(max_dimension, max_dimension, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        size_in_bytes = self._size_in_bytes(image)
        if size_in_bytes <= MAX_STORED_IMAGE_BYTES:
            return image

        ratio = (MAX_STORED_IMAGE_BYTES / size_in_bytes) ** 0.5
        target_width = max(1, int(image.width() * ratio))
        target_height = max(1, int(image.height() * ratio))
        return image.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _size_in_bytes(self, image):
        if hasattr(image, "sizeInBytes"):
            return image.sizeInBytes()
        return image.bytesPerLine() * image.height()
