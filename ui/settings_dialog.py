from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QVBoxLayout

from config import (
    SETTINGS_WINDOW_BACKGROUND_COLOR,
    SETTINGS_WINDOW_BUTTON_BACKGROUND_COLOR,
    SETTINGS_WINDOW_BUTTON_BORDER_COLOR,
    SETTINGS_WINDOW_BUTTON_BORDER_RADIUS,
    SETTINGS_WINDOW_BUTTON_HOVER_COLOR,
    SETTINGS_WINDOW_BUTTON_MIN_WIDTH,
    SETTINGS_WINDOW_BUTTON_PADDING,
    SETTINGS_WINDOW_CHECKBOX_BACKGROUND_COLOR,
    SETTINGS_WINDOW_CHECKBOX_BORDER_COLOR,
    SETTINGS_WINDOW_CHECKBOX_BORDER_RADIUS,
    SETTINGS_WINDOW_CHECKBOX_CHECKED_COLOR,
    SETTINGS_WINDOW_CHECKBOX_INDICATOR_SIZE,
    SETTINGS_WINDOW_CHECKBOX_PADDING,
    SETTINGS_WINDOW_CHECKBOX_SPACING,
    SETTINGS_WINDOW_CONTENT_MARGINS,
    SETTINGS_WINDOW_FONT_SIZE,
    SETTINGS_WINDOW_HEADING_BOTTOM_PADDING,
    SETTINGS_WINDOW_HEADING_COLOR,
    SETTINGS_WINDOW_HEADING_FONT_SIZE,
    SETTINGS_WINDOW_HEADING_FONT_WEIGHT,
    SETTINGS_WINDOW_LAYOUT_SPACING,
    SETTINGS_WINDOW_MIN_WIDTH,
    SETTINGS_WINDOW_TEXT_COLOR,
    SETTINGS_WINDOW_TITLE,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        *,
        show_on_hover,
        hide_on_paste,
        show_clip_indexes,
        close_to_tray,
        start_with_windows,
        on_show_on_hover,
        on_hide_on_paste,
        on_show_clip_indexes,
        on_close_to_tray,
        on_start_with_windows,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(SETTINGS_WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(SETTINGS_WINDOW_MIN_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*SETTINGS_WINDOW_CONTENT_MARGINS)
        layout.setSpacing(SETTINGS_WINDOW_LAYOUT_SPACING)

        heading = QLabel("Preferences")
        heading.setObjectName("settingsHeading")
        layout.addWidget(heading)

        self.show_on_hover = self._add_checkbox(
            layout, "Show shelf on hover", show_on_hover, on_show_on_hover
        )
        self.hide_on_paste = self._add_checkbox(
            layout, "Hide shelf after paste", hide_on_paste, on_hide_on_paste
        )
        self.show_clip_indexes = self._add_checkbox(
            layout, "Show clip indexes", show_clip_indexes, on_show_clip_indexes
        )
        self.close_to_tray = self._add_checkbox(
            layout, "Keep running when closed", close_to_tray, on_close_to_tray
        )
        self.start_with_windows = self._add_checkbox(
            layout, "Start with Windows", start_with_windows, on_start_with_windows
        )

        self.setStyleSheet(f"""
            QDialog {{
                background: {SETTINGS_WINDOW_BACKGROUND_COLOR};
                color: {SETTINGS_WINDOW_TEXT_COLOR};
                font-size: {SETTINGS_WINDOW_FONT_SIZE}px;
            }}
            QLabel#settingsHeading {{
                color: {SETTINGS_WINDOW_HEADING_COLOR};
                font-size: {SETTINGS_WINDOW_HEADING_FONT_SIZE}px;
                font-weight: {SETTINGS_WINDOW_HEADING_FONT_WEIGHT};
                padding-bottom: {SETTINGS_WINDOW_HEADING_BOTTOM_PADDING}px;
            }}
            QCheckBox {{
                spacing: {SETTINGS_WINDOW_CHECKBOX_SPACING}px;
                padding: {SETTINGS_WINDOW_CHECKBOX_PADDING[0]}px {SETTINGS_WINDOW_CHECKBOX_PADDING[1]}px;
            }}
            QCheckBox::indicator {{
                width: {SETTINGS_WINDOW_CHECKBOX_INDICATOR_SIZE}px;
                height: {SETTINGS_WINDOW_CHECKBOX_INDICATOR_SIZE}px;
                border: 1px solid {SETTINGS_WINDOW_CHECKBOX_BORDER_COLOR};
                border-radius: {SETTINGS_WINDOW_CHECKBOX_BORDER_RADIUS}px;
                background: {SETTINGS_WINDOW_CHECKBOX_BACKGROUND_COLOR};
            }}
            QCheckBox::indicator:checked {{
                background: {SETTINGS_WINDOW_CHECKBOX_CHECKED_COLOR};
                border-color: {SETTINGS_WINDOW_CHECKBOX_CHECKED_COLOR};
            }}
            QPushButton {{
                min-width: {SETTINGS_WINDOW_BUTTON_MIN_WIDTH}px;
                padding: {SETTINGS_WINDOW_BUTTON_PADDING[0]}px {SETTINGS_WINDOW_BUTTON_PADDING[1]}px;
                color: {SETTINGS_WINDOW_TEXT_COLOR};
                background: {SETTINGS_WINDOW_BUTTON_BACKGROUND_COLOR};
                border: 1px solid {SETTINGS_WINDOW_BUTTON_BORDER_COLOR};
                border-radius: {SETTINGS_WINDOW_BUTTON_BORDER_RADIUS}px;
            }}
            QPushButton:hover {{ background: {SETTINGS_WINDOW_BUTTON_HOVER_COLOR}; }}
        """)

    @staticmethod
    def _add_checkbox(layout, text, checked, callback):
        checkbox = QCheckBox(text)
        checkbox.setChecked(bool(checked))
        checkbox.toggled.connect(callback)
        layout.addWidget(checkbox)
        return checkbox