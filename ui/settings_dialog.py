from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from config import (
    MAX_CHIPS_MIN,
    MAX_CHIPS_MAX,
    CHIP_WIDTH_MIN_LIMIT,
    CHIP_WIDTH_MAX_LIMIT,
    SETTINGS_WINDOW_SECTION_SPACING,
    SHELF_WIDTH_RATIO_MIN,
    SHELF_WIDTH_RATIO_MAX,
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
        color_preview_enabled,
        close_to_tray,
        start_with_windows,
        chip_min_width,
        chip_max_width,
        max_chips,
        shelf_width_ratio,
        on_show_on_hover,
        on_hide_on_paste,
        on_show_clip_indexes,
        on_color_preview,
        on_close_to_tray,
        on_start_with_windows,
        on_chip_min_width,
        on_chip_max_width,
        on_max_chips,
        on_shelf_width_ratio,
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
            layout, "Show shelf on Hover", show_on_hover, on_show_on_hover
        )
        self.hide_on_paste = self._add_checkbox(
            layout, "Hide Shelf After Paste", hide_on_paste, on_hide_on_paste
        )
        self.show_clip_indexes = self._add_checkbox(
            layout, "Show Clip Indexes", show_clip_indexes, on_show_clip_indexes
        )
        self.color_preview = self._add_checkbox(
            layout, "Show Color Preview", color_preview_enabled, on_color_preview
        )
        self.close_to_tray = self._add_checkbox(
            layout, "Keep Running When Closed", close_to_tray, on_close_to_tray
        )
        self.start_with_windows = self._add_checkbox(
            layout, "Start with Windows", start_with_windows, on_start_with_windows
        )

        layout.addSpacing(SETTINGS_WINDOW_SECTION_SPACING)
        chip_group = QGroupBox("Chip")
        chip_form = QFormLayout(chip_group)
        chip_form.setContentsMargins(12, 10, 12, 10)
        chip_form.setHorizontalSpacing(12)
        chip_form.setVerticalSpacing(8)

        self.chip_min_width = QSpinBox()
        self.chip_min_width.setRange(CHIP_WIDTH_MIN_LIMIT, CHIP_WIDTH_MAX_LIMIT)
        self.chip_min_width.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.chip_min_width.setSuffix(" px")
        self.chip_min_width.setValue(chip_min_width)
        self.chip_min_width.valueChanged.connect(on_chip_min_width)
        chip_form.addRow("Minimum width", self.chip_min_width)

        self.chip_max_width = QSpinBox()
        self.chip_max_width.setRange(CHIP_WIDTH_MIN_LIMIT, CHIP_WIDTH_MAX_LIMIT)
        self.chip_max_width.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.chip_max_width.setSuffix(" px")
        self.chip_max_width.setValue(chip_max_width)
        self.chip_max_width.valueChanged.connect(on_chip_max_width)
        chip_form.addRow("Maximum width", self.chip_max_width)

        self.max_chips = QSpinBox()
        self.max_chips.setRange(MAX_CHIPS_MIN, MAX_CHIPS_MAX)
        self.max_chips.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.max_chips.setValue(max_chips)
        self.max_chips.valueChanged.connect(on_max_chips)
        chip_form.addRow("Maximum chips", self.max_chips)
        layout.addWidget(chip_group)

        layout.addSpacing(SETTINGS_WINDOW_SECTION_SPACING)
        shelf_group = QGroupBox("Shelf")
        shelf_form = QFormLayout(shelf_group)
        shelf_form.setContentsMargins(12, 10, 12, 10)
        shelf_form.setHorizontalSpacing(12)
        shelf_form.setVerticalSpacing(8)

        self.shelf_width_ratio = QDoubleSpinBox()
        self.shelf_width_ratio.setRange(SHELF_WIDTH_RATIO_MIN, SHELF_WIDTH_RATIO_MAX)
        self.shelf_width_ratio.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.shelf_width_ratio.setDecimals(2)
        self.shelf_width_ratio.setSingleStep(0.01)
        self.shelf_width_ratio.setValue(shelf_width_ratio)
        self.shelf_width_ratio.valueChanged.connect(on_shelf_width_ratio)
        shelf_form.addRow("Width ratio", self.shelf_width_ratio)
        layout.addWidget(shelf_group)

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
            QGroupBox {{
                color: {SETTINGS_WINDOW_HEADING_COLOR};
                border: 1px solid {SETTINGS_WINDOW_BUTTON_BORDER_COLOR};
                border-radius: {SETTINGS_WINDOW_BUTTON_BORDER_RADIUS}px;
                margin-top: 8px;
                padding-top: 5px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
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
            QSpinBox, QDoubleSpinBox {{
                min-width: 88px;
                padding: 4px 6px;
                color: {SETTINGS_WINDOW_TEXT_COLOR};
                background: {SETTINGS_WINDOW_BACKGROUND_COLOR};
                border: 1px solid {SETTINGS_WINDOW_BUTTON_BORDER_COLOR};
                border-radius: {SETTINGS_WINDOW_BUTTON_BORDER_RADIUS}px;
            }}
        """)

    @staticmethod
    def _add_checkbox(layout, text, checked, callback):
        checkbox = QCheckBox(text)
        checkbox.setChecked(bool(checked))
        checkbox.toggled.connect(callback)
        layout.addWidget(checkbox)
        return checkbox
