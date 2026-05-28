import unittest

from PySide6.QtWidgets import QApplication

from core.clipboard_manager import is_sensitive_text
from ui.chip_widget import ChipWidget


app = QApplication.instance() or QApplication([])


class TestSensitiveClipboardDetection(unittest.TestCase):
    def test_detects_numeric_otp(self):
        self.assertTrue(is_sensitive_text("123456"))

    def test_detects_long_numeric_password(self):
        self.assertTrue(is_sensitive_text("1234567890"))

    def test_detects_labeled_password(self):
        self.assertTrue(is_sensitive_text("password: hunter2"))

    def test_detects_labeled_otp(self):
        self.assertTrue(is_sensitive_text("Your OTP is 493201"))

    def test_detects_high_entropy_secret(self):
        self.assertTrue(is_sensitive_text("A9$vQ2!pL8#z"))

    def test_detects_short_mixed_password(self):
        self.assertTrue(is_sensitive_text("Ej3fo&_d3?"))

    def test_detects_generated_word_password(self):
        self.assertTrue(is_sensitive_text("vuhuhernrevnaonf"))

    def test_detects_short_generated_word_passwords(self):
        self.assertTrue(is_sensitive_text("yegdbour"))
        self.assertTrue(is_sensitive_text("ueydgboe"))

    def test_allows_regular_text(self):
        self.assertFalse(is_sensitive_text("remember to buy milk"))

    def test_allows_regular_url(self):
        self.assertFalse(is_sensitive_text("https://example.com/page-123"))


class TestSensitiveChipDisplay(unittest.TestCase):
    def test_masks_match_sensitive_content_length(self):
        chip = ChipWidget("1234567890", sensitive=True)
        self.assertEqual(chip.display_text(), "••••••••••")
        chip.deleteLater()


if __name__ == "__main__":
    unittest.main()
