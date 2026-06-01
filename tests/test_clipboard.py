import unittest

from PySide6.QtWidgets import QApplication

from ui.chip_widget import ChipWidget


app = QApplication.instance() or QApplication([])


class TestChipWidget(unittest.TestCase):
    def test_displays_text_content(self):
        chip = ChipWidget("hello world")
        self.assertEqual(chip.display_text(), "hello world")
        chip.deleteLater()


if __name__ == "__main__":
    unittest.main()
