import unittest
from tempfile import TemporaryDirectory

from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from config import CLIP_INDEX_FONT_SIZE, CLIP_INDEX_TEXT_COLOR
from core.clipboard_manager import ClipboardManager
from ui.chip_widget import ChipWidget


app = QApplication.instance() or QApplication([])


class TestChipWidget(unittest.TestCase):
    def test_displays_text_content(self):
        chip = ChipWidget("hello world")
        self.assertEqual(chip.display_text(), "hello world")
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

    def test_displays_clip_index_when_set(self):
        chip = ChipWidget("hello world")
        chip.set_clip_index(3)
        self.assertEqual(chip.index_label.text(), "3")
        self.assertFalse(chip.index_label.isHidden())
        style = chip.index_label.styleSheet()
        self.assertIn(CLIP_INDEX_TEXT_COLOR, style)
        self.assertIn(f"font-size: {CLIP_INDEX_FONT_SIZE}px", style)
        chip.deleteLater()

    def test_image_chip_uses_elided_screenshot_label(self):
        chip = ChipWidget("C:\\missing\\image.png")
        self.assertEqual(chip.kind, "IMG")
        self.assertEqual(chip.display_text(), "Screenshot")
        self.assertIn("Screenshot", chip.title.text())
        chip.deleteLater()


if __name__ == "__main__":
    unittest.main()
