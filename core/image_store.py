from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtGui import QImage, QPixmap

from config import THUMBNAILS_DIR, THUMBNAIL_RETENTION_DAYS, THUMBNAIL_PURGE_PREFIXES



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

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.thumbnail_dir / f"{prefix}_{stamp}_{uuid4().hex[:8]}.png"
        if image.save(str(path), "PNG"):
            return str(path)
        return None

    def _as_image(self, image_data):
        if isinstance(image_data, QImage):
            return image_data

        if isinstance(image_data, QPixmap):
            return image_data.toImage()

        return None
