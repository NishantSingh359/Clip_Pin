from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QVBoxLayout

from config import APP_NAME


class TextPreviewDialog(QDialog):
    """A read-only, theme-aware window sized to fit a text clipboard item."""

    def __init__(self, text, theme, available_geometry=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.preview.setPlainText(text)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        self._layout = layout
        self.set_theme(theme)

        available_geometry = available_geometry or self._primary_available_geometry()
        max_width = max(360, int(available_geometry.width() * 0.85))
        max_height = max(240, int(available_geometry.height() * 0.85))
        metrics = QFontMetrics(self.preview.font())
        sample = text[:20000]
        longest_sample_line = max((len(line) for line in sample.splitlines()), default=0)
        columns = max(40, min(longest_sample_line, 100))
        line_count = max(1, text.count("\n") + 1)
        desired_width = metrics.horizontalAdvance("M" * columns) + 72
        desired_height = (min(line_count, 100) * metrics.lineSpacing()) + 100
        width = min(max_width, max(420, desired_width))
        height = min(max_height, max(190, desired_height))
        self.resize(width, height)
        self.move(
            available_geometry.center().x() - width // 2,
            available_geometry.center().y() - height // 2,
        )

    def set_theme(self, theme):
        settings = (theme or {}).get("settings", {})
        preview_theme = (theme or {}).get("text_preview", {})
        background = preview_theme.get("background", settings.get("background", "#202124"))
        foreground = preview_theme.get("text", settings.get("text", "#e5e7eb"))
        accent = preview_theme.get("selection", settings.get("checkbox_checked", "#5677c8"))
        font_size = int(preview_theme.get("font_size", settings.get("font_size", 13)))
        font_family = preview_theme.get("font_family", "Segoe UI")
        self._layout.setContentsMargins(*preview_theme.get("padding", [12, 12, 12, 12]))
        self.preview.setFont(QFont(font_family, font_size))
        self.setStyleSheet(f"""
            QDialog {{ background: {background}; color: {foreground}; }}
            QPlainTextEdit {{
                background: {background};
                color: {foreground};
                border: none;
                selection-background-color: {accent};
                padding: {int(preview_theme.get("text_padding", 8))}px;
            }}
        """)

    @staticmethod
    def _primary_available_geometry():
        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen.availableGeometry()
        return QRect(0, 0, 1024, 768)
