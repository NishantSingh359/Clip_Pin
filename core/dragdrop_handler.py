from pathlib import Path

from PySide6.QtCore import QUrl

from core.image_store import ImageStore
from core.database import ClipboardDatabase
from utils.app_logging import log_exception



class DragDropHandler:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.image_store = ImageStore(self.base_dir)
        self.db = ClipboardDatabase(self.base_dir)


    def can_accept(self, mime_data):
        try:
            return (
                mime_data.hasUrls()
                or mime_data.hasImage()
                or mime_data.hasText()
                or mime_data.hasHtml()
            )
        except Exception:
            log_exception("Failed to inspect drag data")
            return False

    def extract_items(self, mime_data):
        items = []

        try:
            if mime_data.hasUrls():
                items.extend(self._extract_urls(mime_data.urls()))

                # store file/folder paths into DB as type='path'
                for it in items:
                    # keep only filesystem paths
                    p = Path(it)
                    if p.exists() and (p.is_file() or p.is_dir()):
                        self.db.insert_with_type(it, "path")

            if mime_data.hasImage():
                image_path = self._save_image(mime_data.imageData())
                if image_path:
                    items.append(image_path)

            if not items and mime_data.hasText():
                text = mime_data.text().strip()
                if text:
                    items.append(text)

            if not items and mime_data.hasHtml():
                html = mime_data.html().strip()
                if html:
                    items.append(html)
        except Exception:
            log_exception("Failed to extract drag/drop items")
            return []

        return self._unique(items)

    def _extract_urls(self, urls):
        items = []
        for url in urls:
            if url.isLocalFile():
                items.append(url.toLocalFile())
            else:
                items.append(url.toString())

        return items

    def _save_image(self, image_data):
        return self.image_store.save_image(image_data, "drop")

    def _unique(self, items):
        seen = set()
        result = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result
