import json
from pathlib import Path
from typing import Any

from config import BASE_DIR


THEME_DIR = BASE_DIR / "themes"
DEFAULT_THEME = "dark"


class ThemeManager:
    """Loads built-in theme definitions and exposes their selected values."""

    def __init__(self, theme_dir=THEME_DIR):
        self.theme_dir = Path(theme_dir)
        self._themes = {}
        self._load_themes()

    def _load_themes(self):
        self._themes = {}
        if not self.theme_dir.is_dir():
            return

        for theme_file in sorted(self.theme_dir.glob("*.json")):
            try:
                with theme_file.open("r", encoding="utf-8") as source:
                    theme = json.load(source)
                name = str(theme.get("name", theme_file.stem)).lower()
                if name and isinstance(theme.get("display_name"), str):
                    self._themes[name] = theme
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue

    def available_themes(self):
        return [
            (name, theme.get("display_name", name.title()))
            for name, theme in sorted(self._themes.items())
        ]

    def get_theme(self, name):
        theme_name = str(name or DEFAULT_THEME).lower()
        if theme_name not in self._themes:
            theme_name = DEFAULT_THEME
        theme = self._themes.get(theme_name, self._themes[DEFAULT_THEME])
        return {**theme, "name": theme_name}

    def is_valid(self, name):
        return str(name or "").lower() in self._themes

    def get(self, theme, section, key, default=None):
        value = self.get_theme(theme).get(section, {}).get(key, default)
        return value

    @staticmethod
    def theme_values(theme):
        """Return the current theme's palette values for the UI modules."""
        return theme


THEME_MANAGER = ThemeManager()
THEME_MANAGER.active_theme = DEFAULT_THEME


def get_theme_value(theme, section, key, default=None):
    return theme.get(section, {}).get(key, default)


def set_active_theme(name):
    theme = THEME_MANAGER.get_theme(name)
    THEME_MANAGER.active_theme = theme["name"]
    return theme
