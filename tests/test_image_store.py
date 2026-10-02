import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from config import MAX_STORED_IMAGE_DIMENSION
from core.clipboard_manager import ClipboardManager
from core.image_store import ImageStore


app = QApplication.instance() or QApplication([])


class TestImageStore(unittest.TestCase):
    def test_screenshots_use_sequential_names(self):
        store = ImageStore(tempfile.mkdtemp())
        image = QImage(24, 24, QImage.Format_ARGB32)
        image.fill(QColor("red"))

        first = Path(store.save_image(image, "screenshot"))
        second = Path(store.save_image(image, "screenshot"))

        self.assertEqual(first.name, "screenshot-1.png")
        self.assertEqual(second.name, "screenshot-2.png")

    def test_large_image_is_bounded_when_saved(self):
        temp_dir = tempfile.mkdtemp()
        store = ImageStore(temp_dir)
        image = QImage(MAX_STORED_IMAGE_DIMENSION + 600, 900, QImage.Format_ARGB32)
        image.fill(QColor("red"))

        path = store.save_image(image, "large")

        self.assertIsNotNone(path)
        saved = QImage(path)
        self.assertLessEqual(max(saved.width(), saved.height()), MAX_STORED_IMAGE_DIMENSION)

    def test_failed_save_returns_none(self):
        temp_dir = tempfile.mkdtemp()
        store = ImageStore(temp_dir)
        store.thumbnail_dir = Path(temp_dir) / "missing" / "nested"
        image = QImage(10, 10, QImage.Format_ARGB32)
        image.fill(QColor("blue"))

        self.assertIsNone(store.save_image(image, "bad"))

    def test_duplicate_image_processing_saves_once(self):
        temp_dir = tempfile.mkdtemp()
        manager = ClipboardManager(temp_dir)
        saved_paths = []
        emitted = []
        image = QImage(20, 20, QImage.Format_ARGB32)
        image.fill(QColor("green"))

        manager.image_store.save_image = lambda *_: str(Path(temp_dir) / "image.png")
        manager.db.insert_with_type = lambda content, clip_type: saved_paths.append((content, clip_type)) or 1
        manager.image_copied.connect(emitted.append)

        manager._process_image(image)
        manager._process_image(image)
        time.sleep(0.05)
        manager.close()

        self.assertEqual(len(saved_paths), 1)
        self.assertEqual(len(emitted), 1)

    def test_clipboard_image_is_processed_after_hash_reservation(self):
        temp_dir = tempfile.mkdtemp()
        manager = ClipboardManager(temp_dir)
        manager.clipboard.dataChanged.disconnect(manager.on_data_changed)
        saved = []
        emitted = []
        image_path = str(Path(temp_dir) / "screenshot.png")
        image = QImage(24, 24, QImage.Format_ARGB32)
        image.fill(QColor("blue"))
        manager.image_store.save_image = lambda *_: image_path
        manager.db.insert_with_type = lambda content, clip_type: saved.append((content, clip_type))
        manager.image_copied.connect(emitted.append)
        manager.clipboard.setImage(image)

        manager.on_data_changed()
        manager._image_executor.shutdown(wait=True)
        app.processEvents()
        manager.close()

        self.assertEqual(saved, [(image_path, "img")])
        self.assertEqual(emitted, [image_path])


if __name__ == "__main__":
    unittest.main()
