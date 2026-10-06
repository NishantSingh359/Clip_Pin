import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtTest import QTest

from core.dragdrop_handler import DragDropHandler
from core.paste_controller import PasteController
from ui.chip_bar import ChipBar
from ui.chip_widget import ChipContextMenu, ChipWidget
from ui.main_window import MainWindow
from animation_config import CHIP_LAYOUT_ANIMATION_MS


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
    def test_cursor_over_chip_context_menu_prevents_shelf_autohide(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        menu = ChipContextMenu(window)
        menu.setGeometry(QRect(500, 80, 50, 140))
        window.is_open = True
        window.auto_hide_timer.start()

        with patch("ui.main_window.QApplication.activePopupWidget", return_value=menu), \
             patch("ui.main_window.QCursor.pos", return_value=QPoint(520, 120)), \
             patch.object(window, "update_screen_geometry"):
            window.check_mouse_position()

        window.auto_hide_timer.stop.assert_called()
        menu.close()
        window.tray_icon.hide()
        window.deleteLater()

    def test_hiding_shelf_closes_its_chip_context_menu(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        menu = ChipContextMenu(window)
        menu.show()
        window.is_shelf_pinned = False
        with patch("ui.main_window.QApplication.activePopupWidget", return_value=menu), \
               patch("ui.main_window.fade", side_effect=lambda widget, start, end, duration, finished: finished()), \
             patch.object(window, "animate_to"):
            window.hide_shelf()

        self.assertFalse(menu.isVisible())
        window.tray_icon.hide()
        window.deleteLater()

    def test_hiding_shelf_fades_chip_context_menu_before_close(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        menu = ChipContextMenu(window)
        menu.show()
        with patch("ui.main_window.QApplication.activePopupWidget", return_value=menu), \
             patch("ui.main_window.fade", side_effect=lambda widget, start, end, duration, finished: finished()) as fade_popup, \
             patch.object(window, "animate_to"):
            window.hide_shelf()

        fade_popup.assert_called_once()
        self.assertEqual(fade_popup.call_args.args[:3], (menu, 1.0, 0.0))
        from animation_config import CHIP_CONTEXT_MENU_FADE_OUT_MS

        self.assertEqual(fade_popup.call_args.args[3], CHIP_CONTEXT_MENU_FADE_OUT_MS)
        close_callback = fade_popup.call_args.kwargs["finished"]
        self.assertEqual(close_callback.__self__, menu)
        self.assertTrue(callable(close_callback))
        menu.close()
        window.tray_icon.hide()
        window.deleteLater()

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

    def test_screen_geometry_sets_a_stable_window_size(self):
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

        expected_width = int(fake_screen.availableGeometry().width() * window.shelf_width_ratio)
        expected_height = int(window.theme.get("shelf", {}).get("height", 52))
        self.assertEqual(window.size(), QSize(expected_width + window._shadow_margin * 2, expected_height + window._shadow_margin * 2))
        self.assertEqual(window.minimumSize(), window.size())
        self.assertEqual(window.maximumSize(), window.size())
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
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
             patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        self.assertTrue(window.clip_indexing_enabled)
        window.set_clip_indexing_enabled(False)
        self.assertFalse(window.clip_indexing_enabled)
        window.set_clip_indexing_enabled(True)
        self.assertTrue(window.clip_indexing_enabled)
        window.tray_icon.hide()
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

    def test_tray_icon_has_settings_and_exit_actions(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        self.assertTrue(window.tray_icon.isVisible())
        self.assertEqual(
            [action.text() for action in window.tray_icon.contextMenu().actions() if not action.isSeparator()],
            ["Settings", "Exit"],
        )
        window.tray_icon.hide()
        window.deleteLater()

    def test_close_to_tray_preference_is_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            with patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
                 patch("ui.main_window.ClipboardManager"), \
                 patch("ui.main_window.DragDropHandler"), \
                 patch("ui.main_window.PasteController"), \
                 patch("ui.main_window.QTimer"):
                window = MainWindow()
                window.set_close_to_tray_enabled(False)
                window.set_start_with_windows_enabled(True)

            saved_settings = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertFalse(saved_settings["close_to_tray_enabled"])
            self.assertTrue(saved_settings["start_with_windows_enabled"])
            window.tray_icon.hide()
            window.deleteLater()

    def test_close_hides_to_tray_when_enabled(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.close_to_tray_enabled = True
        event = type("CloseEvent", (), {
            "ignored": False,
            "ignore": lambda self: setattr(self, "ignored", True),
            "accept": lambda self: setattr(self, "ignored", False),
        })()
        with patch.object(window, "hide_shelf") as hide_shelf:
            window.closeEvent(event)

        self.assertTrue(event.ignored)
        hide_shelf.assert_called_once_with(force=True)
        window.tray_icon.hide()
        window.deleteLater()

    def test_settings_dialog_reflects_current_preferences(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.show_on_hover_enabled = False
        window.hide_on_paste_enabled = False
        window.clip_indexing_enabled = False
        window.close_to_tray_enabled = False
        window.start_with_windows_enabled = True
        window.open_settings()

        dialog = window._settings_dialog
        self.assertFalse(dialog.show_on_hover.isChecked())
        self.assertFalse(dialog.hide_on_paste.isChecked())
        self.assertFalse(dialog.show_clip_indexes.isChecked())
        self.assertFalse(dialog.close_to_tray.isChecked())
        self.assertTrue(dialog.start_with_windows.isChecked())
        dialog.close()
        window.tray_icon.hide()
        window.deleteLater()

    def test_settings_dialog_sizing_controls_use_configured_defaults_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
             patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.open_settings()
        dialog = window._settings_dialog
        self.assertEqual((dialog.chip_min_width.value(), dialog.chip_min_width.minimum(), dialog.chip_min_width.maximum()), (120, 100, 500))
        self.assertEqual((dialog.chip_max_width.value(), dialog.chip_max_width.minimum(), dialog.chip_max_width.maximum()), (350, 100, 500))
        self.assertEqual((dialog.max_chips.value(), dialog.max_chips.minimum(), dialog.max_chips.maximum()), (100, 50, 500))
        self.assertEqual((dialog.shelf_width_ratio.value(), dialog.shelf_width_ratio.minimum(), dialog.shelf_width_ratio.maximum()), (0.98, 0.50, 0.98))
        dialog.close()
        window.tray_icon.hide()
        window.deleteLater()

    def test_settings_dialog_max_chips_uses_default_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
             patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.open_settings()
        control = window._settings_dialog.max_chips
        self.assertEqual((control.value(), control.minimum(), control.maximum()), (100, 50, 500))
        window._settings_dialog.close()
        window.tray_icon.hide()
        window.deleteLater()

    def test_old_sizing_preferences_migrate_to_requested_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            settings_file.write_text(
                json.dumps({
                    "chip_min_width": 119,
                    "chip_max_width": 199,
                    "shelf_width_ratio": 0.75,
                }),
                encoding="utf-8",
            )
            with patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
                 patch("ui.main_window.ClipboardManager"), \
                 patch("ui.main_window.DragDropHandler"), \
                 patch("ui.main_window.PasteController"), \
                 patch("ui.main_window.QTimer"):
                window = MainWindow()

            self.assertEqual(
                (window.chip_min_width, window.chip_max_width, window.shelf_width_ratio),
                (120, 350, 0.98),
            )
            migrated_settings = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(migrated_settings["chip_width_defaults_version"], 1)
            window.tray_icon.hide()
            window.deleteLater()

    def test_chip_width_chip_count_and_shelf_ratio_settings_apply_and_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            with patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
                 patch("ui.main_window.ClipboardManager"), \
                 patch("ui.main_window.DragDropHandler"), \
                 patch("ui.main_window.PasteController"), \
                 patch("ui.main_window.QTimer"):
                window = MainWindow()
                window.add_chip("resizable chip")
                chip = window.chips_by_content["resizable chip"]

                window.set_chip_min_width(180)
                self.assertEqual(chip.min_width, 180)
                self.assertGreaterEqual(chip.width(), 180)
                self.assertEqual(window.chip_max_width, 350)

                window.set_chip_max_width(160)
                self.assertEqual(window.chip_max_width, 160)
                self.assertEqual(window.chip_min_width, 160)
                self.assertEqual(chip.min_width, 160)
                self.assertEqual(chip.max_width, 160)
                self.assertEqual(chip.width(), 160)

                window.set_shelf_width_ratio(0.75)
                window.set_max_chips(49)
                self.assertEqual(window.max_chips, 50)
                window.set_max_chips(501)
                self.assertEqual(window.max_chips, 500)
                saved_settings = json.loads(settings_file.read_text(encoding="utf-8"))
                self.assertEqual(saved_settings["chip_min_width"], 160)
                self.assertEqual(saved_settings["chip_max_width"], 160)
                self.assertEqual(saved_settings["max_chips"], 500)
                self.assertEqual(saved_settings["shelf_width_ratio"], 0.75)

            window.tray_icon.hide()
            window.deleteLater()
            chip.deleteLater()

    def test_close_quits_when_close_to_tray_is_disabled(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.close_to_tray_enabled = False
        event = type("CloseEvent", (), {
            "ignored": False,
            "ignore": lambda self: setattr(self, "ignored", True),
            "accept": lambda self: setattr(self, "ignored", False),
        })()
        with patch("ui.main_window.QApplication.quit") as quit_app:
            window.closeEvent(event)

        self.assertFalse(event.ignored)
        self.assertFalse(window.tray_icon.isVisible())
        quit_app.assert_called_once()
        window.deleteLater()

    def test_pin_reorders_chip_without_collapsing_it(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        first = ChipWidget("first item")
        second = ChipWidget("second item")
        window.chips_by_content[first.content] = first
        window.chips_by_content[second.content] = second
        window.insert_chip(first)
        window.insert_chip(second)
        first.show()
        second.show()

        second.pinned = True
        window.pin_clip(second.content)

        self.assertIs(window.chip_layout.itemAt(0).widget(), second)
        self.assertGreater(second.width(), 0)
        window.deleteLater()

    def test_pin_then_unpin_reorders_chip_without_overlap(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        window.show()
        window.add_chip("older item")
        window.add_chip("newer item")
        app.processEvents()
        older = window.chips_by_content["older item"]
        newer = window.chips_by_content["newer item"]

        def wait_for_transition():
            if window._chip_position_animation_group is not None:
                QTest.qWait(window._chip_position_animation_group.duration() + 80)
            app.processEvents()

        wait_for_transition()

        older.pinned = True
        window.pin_clip(older.content)
        self.assertIs(window.chip_layout.itemAt(0).widget(), older)
        wait_for_transition()

        newer.pinned = True
        window.pin_clip(newer.content)
        wait_for_transition()

        older.pinned = False
        window.pin_clip(older.content)
        self.assertIs(window.chip_layout.itemAt(0).widget(), newer)
        wait_for_transition()

        self.assertFalse(older._is_reordering)
        self.assertGreater(older.width(), 0)
        self.assertGreater(newer.width(), 0)
        self.assertFalse(older.geometry().intersects(newer.geometry()))
        window.deleteLater()

    def test_removing_chip_shifts_next_chip_without_width_collapse(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        first = ChipWidget("first item")
        second = ChipWidget("second item")
        window.chips_by_content[first.content] = first
        window.chips_by_content[second.content] = second
        window.insert_chip(first)
        window.insert_chip(second)
        first.show()
        second.show()
        first_width = first.width()
        second_width = second.width()

        window.remove_chip_widget(first)

        self.assertIs(window.chip_layout.itemAt(0).widget(), second)
        self.assertEqual(first.width(), first_width)
        self.assertEqual(second.width(), second_width)
        window.deleteLater()

    def test_internal_chip_drop_is_ignored_by_shelf(self):
        with patch("ui.main_window.ClipboardManager"), \
             patch("ui.main_window.DragDropHandler"), \
             patch("ui.main_window.PasteController"), \
             patch("ui.main_window.QTimer"):
            window = MainWindow()

        mime = ChipWidget("https://example.com").create_drag_mime_data()
        event = type("DropEvent", (), {
            "mimeData": lambda self: mime,
            "ignore": lambda self: setattr(self, "ignored", True),
        })()
        window.dragdrop_handler.extract_items = lambda *_: self.fail("internal drop must not be imported")

        window.dropEvent(event)

        self.assertTrue(event.ignored)
        window.deleteLater()

    def test_scroll_refreshes_hover_for_chip_under_stationary_cursor(self):
        class FakeRect:
            def __init__(self, contains):
                self._contains = contains

            def contains(self, _point):
                return self._contains

        class FakeChip:
            def __init__(self, contains_cursor, hovered):
                self._is_hovered = hovered
                self._contains_cursor = contains_cursor

            def isVisible(self):
                return True

            def rect(self):
                return FakeRect(self._contains_cursor)

            def mapFromGlobal(self, _position):
                return QPoint(0, 0)

            def set_hovered(self, hovered):
                self._is_hovered = hovered

        first = FakeChip(contains_cursor=False, hovered=True)
        second = FakeChip(contains_cursor=True, hovered=False)
        chip_bar = ChipBar.__new__(ChipBar)

        chip_bar._apply_chip_hover([first, second], QPoint(10, 10), True)

        self.assertFalse(first._is_hovered)
        self.assertTrue(second._is_hovered)

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
