import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from core.dragdrop_handler import DragDropHandler
from core.paste_controller import PasteController
from ui.chip_widget import ChipWidget
from ui.main_window import MainWindow


app = QApplication.instance() or QApplication([])


class RaisingMimeData:
    def hasUrls(self):
        raise RuntimeError("bad mime")


class RaisingUser32:
    def SetForegroundWindow(self, hwnd):
        raise RuntimeError("focus failed")

    def keybd_event(self, *args):
        raise RuntimeError("keyboard failed")

    def GetForegroundWindow(self):
        raise RuntimeError("foreground failed")


class FakeFaviconService:
    def __init__(self):
        self.callback = None

    def request(self, url, callback):
        self.callback = callback


class TestRuntimeSmoke(unittest.TestCase):
    def test_scroll_viewport_uses_rounded_clipping(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        self.assertIn("border-radius", window.scroll.viewport().styleSheet().lower())
        window.deleteLater()

    def test_dragdrop_invalid_data_is_ignored(self):
        handler = DragDropHandler(tempfile.mkdtemp())
        mime = RaisingMimeData()

        self.assertFalse(handler.can_accept(mime))
        self.assertEqual(handler.extract_items(mime), [])

    def test_paste_failures_do_not_raise(self):
        controller = PasteController()
        controller.is_windows = True
        controller.user32 = RaisingUser32()

        self.assertIsNone(controller.foreground_window())
        controller.paste_text("hello", 123)
        controller._send_ctrl_v()

    def test_chip_deleted_before_favicon_delivery_does_not_raise(self):
        service = FakeFaviconService()
        with patch("ui.chip_widget.get_favicon_service", return_value=service):
            chip = ChipWidget("https://example.com")

        chip.mark_destroyed()
        service.callback(b"image bytes over 64 characters........................................")
        chip.deleteLater()


if __name__ == "__main__":
    unittest.main()
