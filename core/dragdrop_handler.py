from pathlib import Path

from PySide6.QtCore import QUrl

from core.image_store import ImageStore
from core.database import ClipboardDatabase
from config import MAX_CLIP_ITEM_SIZE_BYTES
from utils.app_logging import log_exception
from utils.item_limits import is_oversized_file, is_oversized_text



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
        oversized_item_rejected = False

        try:
            if mime_data.hasUrls():
                url_items = self._extract_urls(mime_data.urls())
                accepted_url_items = []

                # store file/folder paths into DB as type='path'
                for it in url_items:
                    # keep only filesystem paths
                    p = Path(it)
                    if p.exists() and (p.is_file() or p.is_dir()):
                        if is_oversized_file(p):
                            oversized_item_rejected = True
                            continue
                        self.db.insert_with_type(it, "path")
                    elif is_oversized_text(it):
                        oversized_item_rejected = True
                        continue
                    accepted_url_items.append(it)
                items.extend(accepted_url_items)

            if mime_data.hasImage():
                image_data = mime_data.imageData()
                source_size_bytes = self.image_store.image_payload_size(image_data, mime_data)
                if source_size_bytes is not None and source_size_bytes > MAX_CLIP_ITEM_SIZE_BYTES:
                    oversized_item_rejected = True
                image_path = self._save_image(image_data, source_size_bytes)
                if image_path:
                    items.append(image_path)

            if not items and not oversized_item_rejected and mime_data.hasText():
                raw_text = mime_data.text()
                if not is_oversized_text(raw_text):
                    text = raw_text.strip()
                    if text:
                        items.append(text)
                else:
                    oversized_item_rejected = True

            if not items and not oversized_item_rejected and mime_data.hasHtml():
                raw_html = mime_data.html()
                if not is_oversized_text(raw_html):
                    html = raw_html.strip()
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

    def _save_image(self, image_data, source_size_bytes=None):
        return self.image_store.save_image(image_data, "drop", source_size_bytes)

    def _unique(self, items):
        seen = set()
        result = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result
