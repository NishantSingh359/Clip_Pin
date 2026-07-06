import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint
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
    def test_hover_does_not_use_dock_area_as_top_edge(self):
        class FakeGeometry:
            def __init__(self, left, top, width, height):
                self._left = left
                self._top = top
                self._width = width
                self._height = height

            def left(self):
                return self._left

            def top(self):
                return self._top

            def width(self):
                return self._width

            def height(self):
                return self._height

        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.is_open = False
        window.is_shelf_pinned = False
        window._is_hiding = False
        window.screen_geometry = FakeGeometry(0, 40, 1600, 900)
        window.full_screen_geometry = FakeGeometry(0, 0, 1600, 1000)
        window.trigger_left = 0
        window.trigger_right = 100

        with patch.object(window, "update_screen_geometry"), \
             patch.object(window, "show_shelf") as show_shelf, \
             patch("ui.main_window.QCursor.pos", return_value=QPoint(50, 30)):
            window.check_mouse_position()

        show_shelf.assert_not_called()
        window.deleteLater()

    def test_hidden_position_uses_full_screen_edge(self):
        class FakeGeometry:
            def __init__(self, left, top, width, height):
                self._left = left
                self._top = top
                self._width = width
                self._height = height

            def left(self):
                return self._left

            def top(self):
                return self._top

            def width(self):
                return self._width

            def height(self):
                return self._height

        class FakeScreen:
            def __init__(self):
                self._available = FakeGeometry(0, 40, 1600, 900)
                self._full = FakeGeometry(0, 0, 1600, 1000)

            def availableGeometry(self):
                return self._available

            def geometry(self):
                return self._full

            def name(self):
                return "fake"

        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        fake_screen = FakeScreen()
        with patch.object(window, "screen_for_hint", return_value=fake_screen):
            window.update_screen_geometry("cursor")

        self.assertEqual(window.hidden_pos.y(), fake_screen.geometry().top() - window.height() - 10)
        window.deleteLater()

    def test_hide_in_progress_prevents_immediate_reopen(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.is_open = False
        window._is_hiding = True
        window.screen_geometry = type("Geom", (), {"top": 0})()
        window.trigger_left = 0
        window.trigger_right = 100

        with patch.object(window, "update_screen_geometry"), \
             patch.object(window, "show_shelf") as show_shelf, \
             patch("ui.main_window.QCursor.pos", return_value=QPoint(50, 0)):
            window.check_mouse_position()

        show_shelf.assert_not_called()
        window.deleteLater()

    def test_show_on_hover_toggle_disables_hover_behavior(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.show_on_hover_enabled = False
        window.is_open = False
        window.is_shelf_pinned = False
        window._is_hiding = False
        window.screen_geometry = type("Geom", (), {"top": 0})()
        window.trigger_left = 0
        window.trigger_right = 100

        with patch.object(window, "update_screen_geometry"), \
             patch.object(window, "show_shelf") as show_shelf, \
             patch("ui.main_window.QCursor.pos", return_value=QPoint(50, 0)):
            window.check_mouse_position()

        show_shelf.assert_not_called()
        window.deleteLater()

    def test_clip_indexing_toggle_updates_state(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        self.assertTrue(window.clip_indexing_enabled)
        window.set_clip_indexing_enabled(False)
        self.assertFalse(window.clip_indexing_enabled)
        window.set_clip_indexing_enabled(True)
        self.assertTrue(window.clip_indexing_enabled)
        window.deleteLater()

    def test_show_shelf_brings_window_to_front(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        with patch.object(window, "update_screen_geometry"), \
             patch.object(window, "reveal_chips"), \
             patch.object(window, "animate_to") as animate_to, \
             patch.object(window, "raise_") as raise_mock:
            window.show_shelf("cursor")

        raise_mock.assert_called_once()
        animate_to.assert_called_once()
        window.deleteLater()

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
