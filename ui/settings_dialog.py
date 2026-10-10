from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from config import (
    CHIP_WIDTH_MAX_LIMIT,
    CHIP_WIDTH_MIN_LIMIT,
    MAX_CHIPS_MIN,
    MAX_CHIPS_MAX,
    SETTINGS_WINDOW_MIN_WIDTH,
    SHELF_WIDTH_RATIO_MAX,
    SHELF_WIDTH_RATIO_MIN,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        *,
        show_on_hover,
        hide_on_paste,
        show_clip_indexes,
        color_preview_enabled,
        text_preview_on_double_click,
        open_images_on_double_click,
        prevent_oversize_items,
        show_oversize_warning,
        close_to_tray,
        start_with_windows,
        chip_min_width,
        chip_max_width,
        max_chips,
        shelf_width_ratio,
        theme_name,
        available_themes,
        history_dates,
        selected_history_date,
        theme,
        on_show_on_hover,
        on_hide_on_paste,
        on_show_clip_indexes,
        on_color_preview,
        on_text_preview_on_double_click,
        on_open_images_on_double_click,
        on_prevent_oversize_items,
        on_oversize_warning,
        on_close_to_tray,
        on_start_with_windows,
        on_chip_min_width,
        on_chip_max_width,
        on_max_chips,
        on_shelf_width_ratio,
        on_history_date,
        on_theme,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme or {"settings": {}}
        self.setWindowTitle(self.theme.get("settings", {}).get("window_title", "DockPaste Settings"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(SETTINGS_WINDOW_MIN_WIDTH)

        layout = QVBoxLayout(self)
        settings_theme = self.theme.get("settings", {})
        layout.setContentsMargins(*settings_theme.get("content_margins", [20, 18, 20, 16]))
        layout.setSpacing(int(settings_theme.get("layout_spacing", 10)))

        heading = QLabel("Preferences")
        heading.setObjectName("settingsHeading")
        layout.addWidget(heading)

        theme_group = QGroupBox("Theme")
        theme_form = QFormLayout(theme_group)
        theme_form.setContentsMargins(12, 10, 12, 10)
        theme_form.setHorizontalSpacing(12)
        theme_form.setVerticalSpacing(8)
        self.theme_combo = QComboBox()
        for theme_id, display_name in available_themes:
            self.theme_combo.addItem(display_name, theme_id)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme_name))
        self.theme_combo.currentIndexChanged.connect(lambda index: on_theme(self.theme_combo.itemData(index)))
        theme_form.addRow("Theme", self.theme_combo)
        layout.addWidget(theme_group)
        layout.addSpacing(int(settings_theme.get("section_spacing", 18)))

        history_group = QGroupBox("Filter History")
        history_form = QFormLayout(history_group)
        history_form.setContentsMargins(12, 10, 12, 10)
        history_form.setHorizontalSpacing(12)
        history_form.setVerticalSpacing(8)
        self.history_date_combo = QComboBox()
        for history_date in history_dates:
            self.history_date_combo.addItem(history_date, history_date)
        selected_index = self.history_date_combo.findData(selected_history_date)
        self.history_date_combo.setCurrentIndex(max(0, selected_index))
        self.history_date_combo.currentIndexChanged.connect(
            lambda index: on_history_date(self.history_date_combo.itemData(index))
        )
        history_form.addRow("Copy date", self.history_date_combo)
        layout.addWidget(history_group)
        layout.addSpacing(int(settings_theme.get("section_spacing", 18)))

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
        self.text_preview_on_double_click = self._add_checkbox(
            layout,
            "Preview text on double-click",
            text_preview_on_double_click,
            on_text_preview_on_double_click,
        )
        self.open_images_on_double_click = self._add_checkbox(
            layout,
            "Open images on double-click",
            open_images_on_double_click,
            on_open_images_on_double_click,
        )
        self.prevent_oversize_items = self._add_checkbox(
            layout, "Prevent items over 5 MB from entering history",
            prevent_oversize_items, on_prevent_oversize_items
        )
        self.oversize_warning = self._add_checkbox(
            layout,
            "Warn when items exceed 5 MB",
            show_oversize_warning,
            on_oversize_warning,
        )
        self.oversize_warning.setEnabled(bool(prevent_oversize_items))
        self.prevent_oversize_items.toggled.connect(self._set_oversize_warning_availability)
        self.close_to_tray = self._add_checkbox(
            layout, "Keep Running When Closed", close_to_tray, on_close_to_tray
        )
        self.close_to_tray.setToolTip(
            "Closing the shelf hides it in the system tray and keeps clipboard monitoring active. "
            "The current history is cleared when the shelf is closed. Use Exit in the tray menu to quit."
        )
        self.start_with_windows = self._add_checkbox(
            layout, "Start with Windows", start_with_windows, on_start_with_windows
        )

        layout.addSpacing(int(settings_theme.get("section_spacing", 18)))
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

        layout.addSpacing(int(settings_theme.get("section_spacing", 18)))
        shelf_group = QGroupBox("Shelf")
        shelf_form = QFormLayout(shelf_group)
        shelf_form.setContentsMargins(12, 10, 12, 10)
        shelf_form.setHorizontalSpacing(12)
        shelf_form.setVerticalSpacing(8)

        self.shelf_width_ratio = QDoubleSpinBox()
        self.shelf_width_ratio.setRange(
            SHELF_WIDTH_RATIO_MIN,
            SHELF_WIDTH_RATIO_MAX,
        )
        self.shelf_width_ratio.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.shelf_width_ratio.setDecimals(2)
        self.shelf_width_ratio.setSingleStep(0.01)
        self.shelf_width_ratio.setValue(shelf_width_ratio)
        self.shelf_width_ratio.valueChanged.connect(on_shelf_width_ratio)
        shelf_form.addRow("Width ratio", self.shelf_width_ratio)
        layout.addWidget(shelf_group)

        self.set_theme(theme)
        primary_screen = QApplication.primaryScreen()
        if primary_screen is not None:
            available_geometry = primary_screen.availableGeometry()
            self.adjustSize()
            self.move(
                available_geometry.center().x() - self.width() // 2,
                available_geometry.center().y() - self.height() // 2,
            )

    def set_theme(self, theme):
        self.theme = theme
        settings = theme.get("settings", {})
        background = settings.get("background", "#202124")
        text_color = settings.get("text", "#c0c0c0")
        disabled_text_color = settings.get("disabled_text", "#777b82")
        heading_color = settings.get("heading", "#c0c0c0")
        button_background = settings.get("button_background", "#34373b")
        button_border = settings.get("button_border", "#45494e")
        button_hover = settings.get("button_hover", "#41454a")
        checkbox_background = settings.get("checkbox_background", "#292b2f")
        checkbox_border = settings.get("checkbox_border", "#666a70")
        checkbox_checked = settings.get("checkbox_checked", "#8F993E")
        self.setWindowTitle(settings.get("window_title", "DockPaste Settings"))
        self.setMinimumWidth(SETTINGS_WINDOW_MIN_WIDTH)
        self.setStyleSheet(f"""
            QDialog {{
                background: {background};
                color: {text_color};
                font-size: {settings.get("font_size", 13)}px;
            }}
            QLabel {{
                color: {text_color};
            }}
            QLabel#settingsHeading {{
                color: {heading_color};
                font-size: {settings.get("heading_font_size", 17)}px;
                font-weight: {settings.get("heading_font_weight", 600)};
                padding-bottom: {settings.get("heading_bottom_padding", 6)}px;
            }}
            QGroupBox {{
                color: {heading_color};
                border: 1px solid {button_border};
                border-radius: {settings.get("button_border_radius", 5)}px;
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
                color: {text_color};
                spacing: {settings.get("checkbox_spacing", 10)}px;
                padding: {settings.get("checkbox_padding", [5, 2])[0]}px {settings.get("checkbox_padding", [5, 2])[1]}px;
            }}
            QCheckBox:disabled {{ color: {disabled_text_color}; }}
            QCheckBox::indicator {{
                width: {settings.get("checkbox_indicator_size", 16)}px;
                height: {settings.get("checkbox_indicator_size", 16)}px;
                border: 1px solid {checkbox_border};
                border-radius: {settings.get("checkbox_border_radius", 4)}px;
                background: {checkbox_background};
            }}
            QCheckBox::indicator:checked {{
                background: {checkbox_checked};
                border-color: {checkbox_checked};
            }}
            QCheckBox::indicator:disabled {{
                background: {background};
                border-color: {disabled_text_color};
            }}
            QPushButton {{
                min-width: {settings.get("button_min_width", 64)}px;
                padding: {settings.get("button_padding", [6, 12])[0]}px {settings.get("button_padding", [6, 12])[1]}px;
                color: {text_color};
                background: {button_background};
                border: 1px solid {button_border};
                border-radius: {settings.get("button_border_radius", 5)}px;
            }}
            QPushButton:hover {{ background: {button_hover}; }}
            QComboBox {{
                color: {text_color};
                background: {checkbox_background};
                border: 1px solid {button_border};
                border-radius: {settings.get("button_border_radius", 5)}px;
                padding: 4px 6px;
            }}
            QComboBox QAbstractItemView {{
                color: {text_color};
                background: {background};
                selection-background-color: {checkbox_checked};
                selection-color: #ffffff;
                border: 1px solid {button_border};
            }}
            QSpinBox, QDoubleSpinBox {{
                min-width: 88px;
                padding: 4px 6px;
                color: {text_color};
                background: {background};
                border: 1px solid {button_border};
                border-radius: {settings.get("button_border_radius", 5)}px;
            }}
        """)

    @staticmethod
    def _add_checkbox(layout, text, checked, callback):
        checkbox = QCheckBox(text)
        checkbox.setChecked(bool(checked))
        checkbox.toggled.connect(callback)
        layout.addWidget(checkbox)
        return checkbox

    def _set_oversize_warning_availability(self, prevention_enabled):
        self.oversize_warning.setEnabled(prevention_enabled)
        if not prevention_enabled and self.oversize_warning.isChecked():
            self.oversize_warning.setChecked(False)
