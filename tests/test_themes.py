import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from config import (
    CHIP_MAX_WIDTH,
    CHIP_MIN_WIDTH,
    CHIP_WIDTH_MAX_LIMIT,
    CHIP_WIDTH_MIN_LIMIT,
    COLOR_PREVIEW_ENABLED,
    MAX_CHIPS,
    SETTINGS_WINDOW_MIN_WIDTH,
    SHELF_WIDTH_RATIO_MAX,
    SHELF_WIDTH_RATIO_MIN,
)
from ui.main_window import MainWindow
from ui.theme_manager import DEFAULT_THEME, ThemeManager


app = QApplication.instance() or QApplication([])


class TestThemeManager(unittest.TestCase):
    def test_builtin_themes_are_dark_only(self):
        themes = ThemeManager()

        self.assertEqual(themes.available_themes(), [("dark", "Dark")])
        self.assertTrue(themes.is_valid(DEFAULT_THEME))
        self.assertTrue(themes.is_valid("DARK"))
        self.assertFalse(themes.is_valid("light"))

    def test_behavioral_settings_are_not_defined_in_theme(self):
        theme = ThemeManager().get_theme(DEFAULT_THEME)
        chip_theme = theme.get("chip", {})
        settings_theme = theme.get("settings", {})

        self.assertNotIn("min_width", chip_theme)
        self.assertNotIn("max_width", chip_theme)
        self.assertNotIn("max_chips", chip_theme)
        self.assertNotIn("color_preview_enabled", chip_theme)
        self.assertNotIn("chip_width_min_limit", settings_theme)
        self.assertNotIn("chip_width_max_limit", settings_theme)

    def test_behavioral_defaults_are_configured(self):
        self.assertEqual(CHIP_MIN_WIDTH, 120)
        self.assertEqual(CHIP_MAX_WIDTH, 350)
        self.assertEqual(CHIP_WIDTH_MIN_LIMIT, 100)
        self.assertEqual(CHIP_WIDTH_MAX_LIMIT, 500)
        self.assertEqual(MAX_CHIPS, 100)
        self.assertTrue(COLOR_PREVIEW_ENABLED)
        self.assertEqual(SETTINGS_WINDOW_MIN_WIDTH, 320)
        self.assertEqual(SHELF_WIDTH_RATIO_MIN, 0.50)
        self.assertEqual(SHELF_WIDTH_RATIO_MAX, 0.98)

    def test_invalid_theme_falls_back_to_dark(self):
        themes = ThemeManager()

        self.assertEqual(themes.get_theme("missing")["name"], "dark")

    def test_theme_is_loaded_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            with patch("ui.main_window.APP_STORAGE_DIR", Path(temp_dir)), \
                 patch("ui.main_window.ClipboardManager"), \
                 patch("ui.main_window.DragDropHandler"), \
                 patch("ui.main_window.PasteController"), \
                 patch("ui.main_window.QTimer"):
                window = MainWindow()

            saved_settings = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(window.theme_name, "dark")
            self.assertEqual(saved_settings["theme"], "dark")
            self.assertEqual(window.container.background_color, "rgba(20, 20, 20, 1)")
            window.open_settings()
            self.assertEqual(window._settings_dialog.theme_combo.currentData(), "dark")
            window._settings_dialog.close()
            window.tray_icon.hide()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
