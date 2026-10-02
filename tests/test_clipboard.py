import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from config import CHIP_TEXT_FONT_SIZE, CLIP_INDEX_FONT_SIZE, CLIP_INDEX_TEXT_COLOR
from core.clipboard_manager import ClipboardManager
from ui.chip_widget import ChipWidget


app = QApplication.instance() or QApplication([])


class TestChipWidget(unittest.TestCase):
    def test_displays_text_content(self):
        chip = ChipWidget("hello world")
        self.assertEqual(chip.display_text(), "hello world")
        self.assertIn(f"font-size: {CHIP_TEXT_FONT_SIZE}px", chip.title.styleSheet())
        chip.deleteLater()

    def test_transient_paste_restores_previous_clipboard_content(self):
        with TemporaryDirectory() as temp_dir:
            manager = ClipboardManager(temp_dir)
            manager.clipboard.setText("original", QClipboard.Clipboard)

            manager.set_text_for_paste("chip content", temporary=True)
            self.assertEqual(manager.clipboard.text(QClipboard.Clipboard), "chip content")

            manager.restore_previous_clipboard()
            self.assertEqual(manager.clipboard.text(QClipboard.Clipboard), "original")
            manager.close()

    def test_transient_image_paste_restores_previous_clipboard_text(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "test.png"
            from PySide6.QtGui import QImage

            image = QImage(32, 32, QImage.Format_RGB32)
            image.fill(0xff0000)
            image.save(str(image_path), "PNG")

            manager = ClipboardManager(temp_dir)
            manager.clipboard.setText("original", QClipboard.Clipboard)

            result = manager.set_image_for_paste(str(image_path), temporary=True)
            self.assertTrue(result)
            self.assertTrue(manager.clipboard.mimeData().hasImage())

            manager.restore_previous_clipboard()
            self.assertEqual(manager.clipboard.text(QClipboard.Clipboard), "original")
            manager.close()

    def test_displays_clip_index_when_set(self):
        chip = ChipWidget("hello world")
        chip.set_clip_index(3)
        self.assertEqual(chip.index_label.text(), "3")
        self.assertFalse(chip.index_label.isHidden())
        style = chip.index_label.styleSheet()
        self.assertIn(CLIP_INDEX_TEXT_COLOR, style)
        self.assertIn(f"font-size: {CLIP_INDEX_FONT_SIZE}px", style)
        chip.deleteLater()

    def test_image_chip_uses_elided_file_name(self):
        chip = ChipWidget("C:\\missing\\image.png")
        self.assertEqual(chip.kind, "IMG")
        self.assertEqual(chip.display_text(), "image.png")
        self.assertIn("image.png", chip.title.text())
        chip.deleteLater()

    def test_path_chip_selects_folder_or_file_icon(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "folder"
            folder.mkdir()
            file_path = Path(temp_dir) / "document.txt"
            file_path.write_text("content", encoding="utf-8")
            requested_icons = []

            with patch.object(ChipWidget, "_load_icon_pixmap", autospec=True) as load_icon:
                load_icon.side_effect = lambda chip, path, *_args: requested_icons.append((chip.content, path)) or QPixmap(18, 18)
                folder_chip = ChipWidget(str(folder))
                file_chip = ChipWidget(str(file_path))

            self.assertEqual(folder_chip.kind, "PATH")
            self.assertEqual(file_chip.kind, "PATH")
            self.assertTrue(any(path.endswith("folder.svg") for content, path in requested_icons if content == str(folder)))
            self.assertTrue(any(path.endswith("file.svg") for content, path in requested_icons if content == str(file_path)))
            folder_chip.deleteLater()
            file_chip.deleteLater()

    def test_generated_screenshot_stays_an_image_chip(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screenshot-1.png"
            image = QImage(16, 16, QImage.Format_RGB32)
            image.fill(0xff0000)
            image.save(str(image_path))

            chip = ChipWidget(str(image_path))

            self.assertEqual(chip.kind, "IMG")
            self.assertEqual(chip.display_text(), "Screenshot")
            chip.deleteLater()

    def test_existing_copied_image_file_uses_thumbnail(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "photo.png"
            image = QImage(16, 16, QImage.Format_RGB32)
            image.fill(0x00ff00)
            image.save(str(image_path))

            chip = ChipWidget(str(image_path))

            self.assertEqual(chip.kind, "IMG")
            self.assertFalse(chip.icon.pixmap().isNull())
            self.assertEqual(chip.display_text(), "photo.png")
            chip.deleteLater()

    def test_image_drag_payload_contains_image_not_thumbnail_path(self):
        with TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "screenshot-1.png"
            image = QImage(24, 18, QImage.Format_RGB32)
            image.fill(0x3366cc)
            image.save(str(image_path))

            chip = ChipWidget(str(image_path))
            mime_data = chip.create_drag_mime_data()

            self.assertTrue(mime_data.hasImage())
            self.assertIn("image/png", mime_data.formats())
            self.assertIn("<img", mime_data.html())
            self.assertFalse(mime_data.hasUrls())
            self.assertNotEqual(mime_data.text(), str(image_path))
            self.assertEqual(mime_data.imageData().size(), image.size())

            file_mime_data = chip.create_drag_mime_data(include_file_url=True)
            self.assertTrue(file_mime_data.hasImage())
            self.assertTrue(file_mime_data.hasUrls())
            self.assertTrue(file_mime_data.urls()[0].isLocalFile())
            self.assertEqual(Path(file_mime_data.urls()[0].toLocalFile()), image_path)
            chip.deleteLater()

    def test_copied_local_file_url_emits_path(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "document.txt"
            file_path.write_text("content", encoding="utf-8")
            manager = ClipboardManager(temp_dir)
            saved = []
            emitted = []
            manager.db.insert_with_type = lambda content, clip_type: saved.append((content, clip_type))
            manager.path_copied.connect(emitted.append)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(file_path))])
            manager.clipboard.setMimeData(mime, QClipboard.Clipboard)
            app.processEvents()

            self.assertEqual(saved, [(str(file_path), "path")])
            self.assertEqual(emitted, [str(file_path)])
            manager.close()


if __name__ == "__main__":
    unittest.main()
