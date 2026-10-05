from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
    QSizePolicy,
    QLabel,
    QMenu,
    QGraphicsDropShadowEffect,
    QSystemTrayIcon,
)

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPoint,
    QPropertyAnimation,
    QParallelAnimationGroup,
    QEasingCurve,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QRegion,
    QIcon,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
import ctypes
import ctypes.wintypes
import json
import sys
from pathlib import Path
try:
    import winreg
except ImportError:
    winreg = None

from core.clipboard_manager import ClipboardManager
from core.dragdrop_handler import DragDropHandler
from core.favicon_service import shutdown_favicon_service
from core.paste_controller import PasteController
from ui.chip_bar import ChipBar
from ui.chip_widget import ChipContextMenu, ChipWidget
from ui.settings_dialog import SettingsDialog
from ui.animations import fade, parse_color
from config import (
    APP_NAME,
    APP_STORAGE_DIR,
    CHIP_MIN_WIDTH,
    CHIP_MAX_WIDTH,
    CHIP_WIDTH_MIN_LIMIT,
    CHIP_WIDTH_MAX_LIMIT,
    CHIP_WIDTH_DEFAULTS_VERSION,
    MAX_CHIPS_MIN,
    MAX_CHIPS_MAX,
    COLOR_PREVIEW_ENABLED,
    EMPTY_STATE_FONT_SIZE,
    EMPTY_STATE_FONT_WEIGHT,
    EMPTY_STATE_ICON_COLOR,
    EMPTY_STATE_ICON_ENABLED,
    EMPTY_STATE_ICON_PATH,
    EMPTY_STATE_ICON_SIZE,
    EMPTY_STATE_ICON_SPACING,
    EMPTY_STATE_LEFT_PADDING,
    EMPTY_STATE_PADDING,
    EMPTY_STATE_TEXT,
    EMPTY_STATE_TEXT_COLOR,
    HIDE_DISTANCE,
    HOVER_TRIGGER_HEIGHT,
    HOVER_TRIGGER_WIDTH,
    MAX_CHIPS,
    MOUSE_POLL_MS,
    MOTION_ENABLED,
    CHIP_CONTEXT_MENU_FADE_OUT_MS,
    MOTION_SHELF_MS,
    CHIP_LAYOUT_ANIMATION_MS,
    SHELF_CHIP_REVEAL_ENABLED,
    SHELF_CHIP_REVEAL_MS,
    SHELF_CHIP_REVEAL_STAGGER_MS,
    SHELF_CHIP_REVEAL_OFFSET,
    SHELF_SHOW_ON_HOVER,
    SHELF_HEIGHT,
    SHELF_TOP_MARGIN,
    HIDE_ON_PASTE,
    clip_indexing,
    SHELF_WIDTH_RATIO,
    SHELF_WIDTH_RATIO_MIN,
    SHELF_WIDTH_RATIO_MAX,
    SHELF_BACKGROUND_COLOR,
    SHELF_BORDER_COLOR,
    SHELF_BORDER_WIDTH,
    SHELF_BORDER_RADIUS,
    SHELF_SHADOW_BLUR_RADIUS,
    SHELF_SHADOW_OFFSET,
    SHELF_SHADOW_COLOR,
    SHELF_MARGIN,
    SHELF_PADDING,
    SHELF_SPACING,
    SHELF_AUTO_HIDE_DELAY
)
from utils.app_logging import log_exception, safe_slot


class ShelfContainer(QWidget):
    """Custom container widget with rounded corners."""
    def __init__(self):
        super().__init__()
        self.setObjectName("shelfContainer")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(SHELF_HEIGHT)
        if SHELF_SHADOW_BLUR_RADIUS > 0:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(SHELF_SHADOW_BLUR_RADIUS)
            shadow.setOffset(*SHELF_SHADOW_OFFSET)
            shadow.setColor(parse_color(SHELF_SHADOW_COLOR))
            self.setGraphicsEffect(shadow)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        path = QPainterPath()
        rect = self.rect()
        if SHELF_BORDER_WIDTH > 0:
            margin = SHELF_BORDER_WIDTH / 2.0
            rect_f = rect.toRectF().adjusted(margin, margin, -margin, -margin)
        else:
            rect_f = rect.toRectF()
            
        path.addRoundedRect(rect_f, SHELF_BORDER_RADIUS, SHELF_BORDER_RADIUS)
        
        bg_color = parse_color(SHELF_BACKGROUND_COLOR)
        painter.fillPath(path, bg_color)
        
        if SHELF_BORDER_WIDTH > 0:
            border_color = parse_color(SHELF_BORDER_COLOR)
            pen = painter.pen()
            pen.setColor(border_color)
            pen.setWidth(SHELF_BORDER_WIDTH)
            painter.setPen(pen)
            painter.drawPath(path)
        
        painter.end()
        super().paintEvent(event)



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.is_open = False
        self._target_pos = None
        self.last_target_window = None
        self.chips_by_content = {}
        self.is_shelf_pinned = False
        self._is_hiding = False
        self._hotkey_was_down = False
        self._screen_geometry_cache_key = None
        self._chip_position_animation_group = None
        self._chip_position_targets = {}
        self.show_on_hover_enabled = SHELF_SHOW_ON_HOVER
        self.hide_on_paste_enabled = HIDE_ON_PASTE
        self.clip_indexing_enabled = clip_indexing
        self.color_preview_enabled = COLOR_PREVIEW_ENABLED
        self.close_to_tray_enabled = True
        self.start_with_windows_enabled = False
        self.chip_min_width = CHIP_MIN_WIDTH
        self.chip_max_width = CHIP_MAX_WIDTH
        self.max_chips = MAX_CHIPS
        self.shelf_width_ratio = SHELF_WIDTH_RATIO
        self._next_chip_number = 1
        self._settings_dialog = None
        self._shadow_margin = max(
            0,
            int(SHELF_SHADOW_BLUR_RADIUS * 2 + max(abs(value) for value in SHELF_SHADOW_OFFSET)),
        )
        self._load_context_menu_settings()

        # Refresh an existing Run entry. Older versions used sys.argv[0] for
        # source launches, which can contain launcher arguments (for example
        # `python.exe -m unittest`) and create a startup command that opens an
        # unrelated path or fails to launch correctly.
        if self.start_with_windows_enabled:
            try:
                self._set_windows_startup(True)
            except Exception as exc:
                log_exception(f"Failed to repair Windows startup entry: {exc}")

        self._create_tray_icon()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.paste_controller = PasteController()
        self.dragdrop_handler = DragDropHandler(APP_STORAGE_DIR)
        self.clipboard_manager = ClipboardManager(APP_STORAGE_DIR)
        self.clipboard_manager.text_copied.connect(self.add_clip)
        self.clipboard_manager.image_copied.connect(self.add_clip)
        self.clipboard_manager.path_copied.connect(self.add_clip)

        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(MOTION_SHELF_MS)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.update_screen_geometry()
        self.move(self.hidden_pos)

        self.setup_ui()
        self.refresh_chip_indexes()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide_shelf)
        self._auto_hide_waiting_for_reentry = False

        self.hide_reset_timer = QTimer(self)
        self.hide_reset_timer.setSingleShot(True)
        self.hide_reset_timer.timeout.connect(lambda: setattr(self, "_is_hiding", False))

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_mouse_position)
        self.timer.start(MOUSE_POLL_MS)

        self.hotkey_timer = QTimer()
        self.hotkey_timer.timeout.connect(self.check_toggle_hotkey)
        self.hotkey_timer.start(50)

        # Apply native Windows Acrylic theme
        # from ui.styles import apply_acrylic

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self._shadow_margin,
            self._shadow_margin,
            self._shadow_margin,
            self._shadow_margin,
        )
        main_layout.setSpacing(0)

        self.container = ShelfContainer()
        # Background is drawn in ShelfContainer.paintEvent(), so keep widget background unset
        self.container.setStyleSheet("")

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(*SHELF_PADDING)
        container_layout.setSpacing(SHELF_SPACING)

        self.scroll = ChipBar()
        self.scroll.setFixedHeight(SHELF_HEIGHT - SHELF_PADDING[1] - SHELF_PADDING[3])

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self.chip_layout = QHBoxLayout(scroll_widget)
        self.chip_layout.setContentsMargins(0, 0, 0, 0)
        self.chip_layout.setSpacing(10)

        self.scroll.setWidget(scroll_widget)
        container_layout.addWidget(self.scroll)

        main_layout.addWidget(self.container)
        self.empty_state_widget = QWidget()
        self.empty_state_widget.setStyleSheet("background: transparent;")
        self.empty_state_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.empty_state_layout = QHBoxLayout(self.empty_state_widget)
        self.empty_state_layout.setContentsMargins(
            EMPTY_STATE_LEFT_PADDING,
            0,
            EMPTY_STATE_PADDING[1],
            0,
        )
        self.empty_state_layout.setSpacing(EMPTY_STATE_ICON_SPACING)

        self.empty_state_icon = QLabel()
        self.empty_state_icon.setAlignment(Qt.AlignCenter)
        self.empty_state_icon.setFixedSize(EMPTY_STATE_ICON_SIZE, EMPTY_STATE_ICON_SIZE)
        self.empty_state_icon.setVisible(EMPTY_STATE_ICON_ENABLED)
        if EMPTY_STATE_ICON_ENABLED:
            icon_path = Path(EMPTY_STATE_ICON_PATH)
            if not icon_path.is_absolute():
                icon_path = Path(__file__).resolve().parent.parent / icon_path
            renderer = QSvgRenderer(str(icon_path))
            if renderer.isValid():
                icon_pixmap = QPixmap(EMPTY_STATE_ICON_SIZE, EMPTY_STATE_ICON_SIZE)
                icon_pixmap.fill(Qt.transparent)
                icon_painter = QPainter(icon_pixmap)
                renderer.render(icon_painter)
                icon_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                icon_painter.fillRect(icon_pixmap.rect(), parse_color(EMPTY_STATE_ICON_COLOR))
                icon_painter.end()
                self.empty_state_icon.setPixmap(icon_pixmap)
            else:
                self.empty_state_icon.hide()

        self.empty_state_layout.addWidget(self.empty_state_icon)

        self.empty_label = QLabel(EMPTY_STATE_TEXT)
        self.empty_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.empty_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.empty_label.setStyleSheet(f"""
            QLabel {{
                color: {EMPTY_STATE_TEXT_COLOR};
                font-size: {EMPTY_STATE_FONT_SIZE}px;
                font-weight: {EMPTY_STATE_FONT_WEIGHT};
                padding: {EMPTY_STATE_PADDING[0]}px 0px;
            }}
        """)
        self.empty_state_layout.addWidget(self.empty_label)
        self.chip_layout.addWidget(self.empty_state_widget)
        self.chip_layout.addStretch()
        self.update_empty_state()
        self.update_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "container"):
            self.update_mask()

    def update_mask(self):
        self.clearMask()

    @safe_slot("Failed to add clipboard chip")
    def add_clip(self, content):
        if content in self.chips_by_content:
            return

        self.add_chip(content)

    @safe_slot("Failed to create clipboard chip")
    def add_chip(self, content):
        if content in self.chips_by_content:
            return

        self._finish_chip_position_animation()
        chip = ChipWidget(
            content,
            self.chip_min_width,
            self.chip_max_width,
            color_preview_enabled=self.color_preview_enabled,
        )
        self._assign_chip_number(chip)
        chip.paste_requested.connect(self.paste_clip)
        chip.copy_again_requested.connect(self.copy_again_clip)
        chip.delete_requested.connect(self.remove_clip)
        chip.pin_requested.connect(self.pin_clip)
        chip.clear_all_requested.connect(self.clear_unpinned_clips)
        chip.context_action_triggered.connect(self.keep_shelf_open_after_context_action)
        self.chips_by_content[content] = chip
        self.update_empty_state()
        self.insert_chip(chip)
        self.refresh_chip_indexes()
        chip.show()
        chip._entry_fade_animation = fade(
            chip,
            0.0,
            1.0,
            CHIP_LAYOUT_ANIMATION_MS,
            finished=lambda: self._finish_chip_fade_in(chip),
        )
        self.trim_chips()

    def add_clips(self, contents):
        for content in contents:
            self.add_clip(content)

    @safe_slot("Failed to remove clipboard chip")
    def remove_clip(self, content):
        chip = self.chips_by_content.pop(content, None)
        if not chip:
            return

        try:
            self.clipboard_manager.get_db().delete_by_content(content)
        except Exception:
            log_exception("Failed to delete clipboard item")
        self.remove_chip_widget(chip)

    def remove_chip_widget(self, chip):
        self._remove_chip_widgets([chip])

    def _remove_chip_widgets(self, chips):
        chips = [chip for chip in chips if not getattr(chip, "_is_deleting", False)]
        if not chips:
            return

        self._finish_chip_position_animation()
        start_positions = {chip: chip.pos() for chip in self.chip_widgets()}
        for chip in chips:
            chip._is_deleting = True
            chip.setEnabled(False)
            chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            entry_animation = getattr(chip, "_entry_fade_animation", None)
            if entry_animation is not None:
                entry_animation.stop()
                chip._entry_fade_animation = None
            chip.hide()
            chip.setGraphicsEffect(None)
            self.chip_layout.removeWidget(chip)
            chip.deleteLater()

        self.chip_layout.activate()
        self.update_empty_state()
        self.refresh_chip_indexes()
        self._animate_chip_layout(start_positions, CHIP_LAYOUT_ANIMATION_MS)

    @staticmethod
    def _finish_chip_fade_in(chip):
        chip._entry_fade_animation = None
        if not chip._is_deleting:
            chip.setGraphicsEffect(None)

    def update_empty_state(self):
        if hasattr(self, "empty_label"):
            has_chip_widgets = False
            for index in range(self.chip_layout.count()):
                item = self.chip_layout.itemAt(index)
                widget = item.widget() if item else None
                if widget and widget is not self.empty_state_widget:
                    has_chip_widgets = True
                    break
            self.empty_state_widget.setVisible(not self.chips_by_content and not has_chip_widgets)

    @safe_slot("Failed to clear unpinned clips")
    def clear_unpinned_clips(self):
        chips = [
            chip
            for chip in list(self.chips_by_content.values())
            if not chip.pinned and not getattr(chip, "_is_deleting", False)
        ]

        for chip in chips:
            self.chips_by_content.pop(chip.content, None)
            try:
                self.clipboard_manager.get_db().delete_by_content(chip.content)
            except Exception:
                log_exception("Failed to delete clipboard item during clear")

        self._remove_chip_widgets(chips)

    @safe_slot("Failed to pin clipboard chip")
    def pin_clip(self, content):
        chip = self.chips_by_content.get(content)
        if not chip or getattr(chip, "_is_deleting", False):
            return

        self._finish_chip_position_animation()
        chip._is_reordering = True
        chips = self.chip_widgets()
        start_positions = {item: item.pos() for item in chips}
        self.chip_layout.removeWidget(chip)
        self.insert_chip(chip)
        self.refresh_chip_indexes()

        self._animate_chip_layout(
            start_positions,
            CHIP_LAYOUT_ANIMATION_MS,
            finished=lambda: setattr(chip, "_is_reordering", False),
        )

    def _finish_chip_position_animation(self):
        animation_group = self._chip_position_animation_group
        if animation_group is not None:
            animation_group.stop()
            self._chip_position_animation_group = None
        for chip, target in self._chip_position_targets.items():
            chip.move(target)
        self._chip_position_targets = {}
        self.chip_layout.setEnabled(True)
        self.chip_layout.activate()
        self._clear_chip_reordering_flags()

    def _clear_chip_reordering_flags(self):
        for chip in self.chip_widgets():
            chip._is_reordering = False

    def _animate_chip_layout(self, start_positions, duration, finished=None):
        self.chip_layout.activate()
        target_positions = {
            chip: chip.pos()
            for chip in self.chip_widgets()
            if chip in start_positions
        }
        moving_chips = [
            chip
            for chip, target in target_positions.items()
            if start_positions[chip] != target
        ]

        if not MOTION_ENABLED or duration <= 0 or not moving_chips:
            self.chip_layout.setEnabled(True)
            self.chip_layout.activate()
            self._clear_chip_reordering_flags()
            if finished:
                finished()
            return

        animation_group = QParallelAnimationGroup(self)
        self.chip_layout.setEnabled(False)
        for chip in moving_chips:
            chip.move(start_positions[chip])
            position_animation = QPropertyAnimation(chip, b"pos", animation_group)
            position_animation.setDuration(duration)
            position_animation.setStartValue(start_positions[chip])
            position_animation.setEndValue(target_positions[chip])
            position_animation.setEasingCurve(QEasingCurve.OutCubic)
            animation_group.addAnimation(position_animation)

        def finish_transition():
            self.chip_layout.setEnabled(True)
            self.chip_layout.activate()
            self._chip_position_animation_group = None
            self._chip_position_targets = {}
            self._clear_chip_reordering_flags()
            if finished:
                finished()

        animation_group.finished.connect(finish_transition)
        self._chip_position_animation_group = animation_group
        self._chip_position_targets = target_positions
        self.chip_layout.setEnabled(False)
        animation_group.start()

    def chip_widgets(self):
        chips = []
        for index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(index)
            widget = item.widget() if item else None
            if isinstance(widget, ChipWidget):
                chips.append(widget)
        return chips

    def insert_chip(self, chip):
        insert_at = 0
        for layout_index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(layout_index)
            if not item:
                continue
            widget = item.widget()
            if widget is None:
                break
            if widget is getattr(self, "empty_state_widget", None):
                continue

            if getattr(widget, "pinned", False):
                insert_at = layout_index + 1
                continue

            if chip.pinned:
                break

            existing_number = getattr(widget, "clip_index", None)
            if existing_number is None or chip.clip_index > existing_number:
                insert_at = layout_index
                break
            insert_at = layout_index + 1

        self.chip_layout.insertWidget(insert_at, chip)

    def _assign_chip_number(self, chip):
        chip.set_clip_index(self._next_chip_number, show_index=self.clip_indexing_enabled)
        self._next_chip_number += 1
        self._save_context_menu_settings()

    def refresh_chip_indexes(self):
        chips = []
        for layout_index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(layout_index)
            widget = item.widget() if item else None
            if widget is None or widget is getattr(self, "empty_state_widget", None):
                continue
            if hasattr(widget, "set_clip_index"):
                chips.append(widget)

        for chip in chips:
            if chip.clip_index is None:
                self._assign_chip_number(chip)
            else:
                chip.set_clip_index(chip.clip_index, show_index=self.clip_indexing_enabled)

    @safe_slot("Failed to paste clipboard chip")
    def paste_clip(self, content):
        if self.hide_on_paste_enabled:
            self.hide_shelf()
        chip = self.chips_by_content.get(content)
        if chip and chip.kind == "IMG":
            self.clipboard_manager.set_image_for_paste(content, temporary=True)
        else:
            self.clipboard_manager.set_text_for_paste(content, temporary=True)

        QTimer.singleShot(
            MOTION_SHELF_MS,
            lambda: self.paste_controller.paste_text(content, self.last_target_window)
        )
        QTimer.singleShot(
            MOTION_SHELF_MS + 220,
            self.clipboard_manager.restore_previous_clipboard
        )

    @safe_slot("Failed to copy chip content again")
    def copy_again_clip(self, content):
        chip = self.chips_by_content.get(content)
        if chip and chip.kind == "IMG":
            self.clipboard_manager.set_image_for_paste(content, temporary=False)
        else:
            self.clipboard_manager.set_text_for_paste(content, temporary=False)

    @safe_slot("Failed to trim chips")
    def trim_chips(self):
        chips_to_remove = []
        while len(self.chips_by_content) > self.max_chips:
            chip = self.oldest_unpinned_chip()
            if chip is None:
                break
            self.chips_by_content.pop(chip.content, None)
            chips_to_remove.append(chip)
        self._remove_chip_widgets(chips_to_remove)

    def oldest_unpinned_chip(self):
        for index in range(self.chip_layout.count() - 2, -1, -1):
            item = self.chip_layout.itemAt(index)
            if not item:
                continue
            chip = item.widget()
            if (
                chip
                and chip is not getattr(self, "empty_state_widget", None)
                and not getattr(chip, "pinned", False)
                and not getattr(chip, "_is_deleting", False)
            ):
                return chip
        return None

    @safe_slot("Failed to process drag enter")
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-copypin-chip"):
            event.ignore()
            return
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    @safe_slot("Failed to process drag move")
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-copypin-chip"):
            event.ignore()
            return
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    @safe_slot("Failed to process drop")
    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-copypin-chip"):
            event.ignore()
            return
        items = self.dragdrop_handler.extract_items(event.mimeData())
        if not items:
            event.ignore()
            return

        self.add_clips(items)
        self._set_clipboard_for_drop(items)
        event.acceptProposedAction()

    def _set_clipboard_for_drop(self, items):
        if not items:
            return

        content = items[-1]

        if Path(content).exists() and self.clipboard_manager.set_image_for_paste(content):
            return

        self.clipboard_manager.set_text_for_paste(content)

    # -------------------------
    # HOVER DETECTION
    # -------------------------

    def set_show_on_hover_enabled(self, enabled):
        self.show_on_hover_enabled = bool(enabled)
        self._save_context_menu_settings()

    def set_hide_on_paste_enabled(self, enabled):
        self.hide_on_paste_enabled = bool(enabled)
        self._save_context_menu_settings()

    def set_clip_indexing_enabled(self, enabled):
        self.clip_indexing_enabled = bool(enabled)
        self.refresh_chip_indexes()
        self._save_context_menu_settings()

    def set_color_preview_enabled(self, enabled):
        self.color_preview_enabled = bool(enabled)
        for chip in self.chips_by_content.values():
            chip.set_color_preview_enabled(self.color_preview_enabled)
        self._save_context_menu_settings()

    def _context_menu_settings_path(self):
        settings_path = APP_STORAGE_DIR / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        return settings_path

    def _load_context_menu_settings(self):
        settings_path = self._context_menu_settings_path()
        if not settings_path.exists():
            return

        try:
            with settings_path.open("r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
            needs_sizing_defaults_migration = (
                settings.get("chip_width_defaults_version", 0) < CHIP_WIDTH_DEFAULTS_VERSION
            )
            self.show_on_hover_enabled = bool(settings.get("show_on_hover_enabled", self.show_on_hover_enabled))
            self.hide_on_paste_enabled = bool(settings.get("hide_on_paste_enabled", self.hide_on_paste_enabled))
            self.clip_indexing_enabled = bool(settings.get("clip_indexing_enabled", self.clip_indexing_enabled))
            self.color_preview_enabled = bool(settings.get("color_preview_enabled", self.color_preview_enabled))
            self.close_to_tray_enabled = bool(settings.get("close_to_tray_enabled", self.close_to_tray_enabled))
            self.start_with_windows_enabled = bool(settings.get("start_with_windows_enabled", self.start_with_windows_enabled))
            self.max_chips = max(
                MAX_CHIPS_MIN,
                min(MAX_CHIPS_MAX, int(settings.get("max_chips", self.max_chips))),
            )
            if needs_sizing_defaults_migration:
                self.chip_min_width = CHIP_MIN_WIDTH
                self.chip_max_width = CHIP_MAX_WIDTH
                self.shelf_width_ratio = SHELF_WIDTH_RATIO
            else:
                self.chip_min_width = max(
                    CHIP_WIDTH_MIN_LIMIT,
                    min(CHIP_WIDTH_MAX_LIMIT, int(settings.get("chip_min_width", self.chip_min_width))),
                )
                self.chip_max_width = max(
                    self.chip_min_width,
                    min(CHIP_WIDTH_MAX_LIMIT, int(settings.get("chip_max_width", self.chip_max_width))),
                )
                self.shelf_width_ratio = max(
                    SHELF_WIDTH_RATIO_MIN,
                    min(SHELF_WIDTH_RATIO_MAX, float(settings.get("shelf_width_ratio", self.shelf_width_ratio))),
                )
            if needs_sizing_defaults_migration:
                self._save_context_menu_settings()
        except Exception as exc:
            log_exception(f"Failed to load context menu settings: {exc}")

    def _save_context_menu_settings(self):
        settings_path = self._context_menu_settings_path()
        try:
            with settings_path.open("w", encoding="utf-8") as settings_file:
                json.dump(
                    {
                        "show_on_hover_enabled": self.show_on_hover_enabled,
                        "hide_on_paste_enabled": self.hide_on_paste_enabled,
                        "clip_indexing_enabled": self.clip_indexing_enabled,
                        "color_preview_enabled": self.color_preview_enabled,
                        "close_to_tray_enabled": self.close_to_tray_enabled,
                        "start_with_windows_enabled": self.start_with_windows_enabled,
                        "chip_min_width": self.chip_min_width,
                        "chip_max_width": self.chip_max_width,
                        "max_chips": self.max_chips,
                        "shelf_width_ratio": self.shelf_width_ratio,
                        "chip_width_defaults_version": CHIP_WIDTH_DEFAULTS_VERSION,
                    },
                    settings_file,
                    indent=2,
                )
        except Exception as exc:
            log_exception(f"Failed to save context menu settings: {exc}")

    def _create_tray_icon(self):
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)), self)
        self.tray_icon.setToolTip(APP_NAME)

        tray_menu = QMenu(self)
        tray_menu.addAction("Settings", self.open_settings)
        tray_menu.addSeparator()
        tray_menu.addAction("Exit", self.exit_application)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def toggle_shelf_from_tray(self):
        if self.is_open:
            self.hide_shelf(force=True)
        else:
            self.show_shelf("cursor")

    def exit_application(self, checked=False):
        # Closing normally hides the shelf when close-to-tray is enabled.
        # Tray Exit must bypass that behavior and run the regular shutdown path.
        self.close_to_tray_enabled = False
        self.tray_icon.hide()
        self.close()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_shelf_from_tray()

    def open_settings(self):
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        self._settings_dialog = SettingsDialog(
            show_on_hover=self.show_on_hover_enabled,
            hide_on_paste=self.hide_on_paste_enabled,
            show_clip_indexes=self.clip_indexing_enabled,
            color_preview_enabled=self.color_preview_enabled,
            close_to_tray=self.close_to_tray_enabled,
            start_with_windows=self.start_with_windows_enabled,
            chip_min_width=self.chip_min_width,
            chip_max_width=self.chip_max_width,
            max_chips=self.max_chips,
            shelf_width_ratio=self.shelf_width_ratio,
            on_show_on_hover=self.set_show_on_hover_enabled,
            on_hide_on_paste=self.set_hide_on_paste_enabled,
            on_show_clip_indexes=self.set_clip_indexing_enabled,
            on_color_preview=self.set_color_preview_enabled,
            on_close_to_tray=self.set_close_to_tray_enabled,
            on_start_with_windows=self.set_start_with_windows_enabled,
            on_chip_min_width=self.set_chip_min_width,
            on_chip_max_width=self.set_chip_max_width,
            on_max_chips=self.set_max_chips,
            on_shelf_width_ratio=self.set_shelf_width_ratio,
            parent=None,
        )
        self._settings_dialog.setWindowIcon(self.tray_icon.icon())
        self._settings_dialog.show()

    def set_max_chips(self, max_chips):
        self.max_chips = max(MAX_CHIPS_MIN, min(MAX_CHIPS_MAX, int(max_chips)))
        self.trim_chips()
        self._save_context_menu_settings()

    def set_chip_min_width(self, width):
        self.chip_min_width = max(
            CHIP_WIDTH_MIN_LIMIT,
            min(CHIP_WIDTH_MAX_LIMIT, int(width)),
        )
        if self.chip_min_width > self.chip_max_width:
            self.chip_max_width = self.chip_min_width
            if self._settings_dialog is not None:
                self._settings_dialog.chip_max_width.blockSignals(True)
                self._settings_dialog.chip_max_width.setValue(self.chip_max_width)
                self._settings_dialog.chip_max_width.blockSignals(False)
        self._apply_chip_width_settings()

    def set_chip_max_width(self, width):
        self.chip_max_width = max(
            CHIP_WIDTH_MIN_LIMIT,
            min(CHIP_WIDTH_MAX_LIMIT, int(width)),
        )
        if self.chip_max_width < self.chip_min_width:
            self.chip_min_width = self.chip_max_width
            if self._settings_dialog is not None:
                self._settings_dialog.chip_min_width.blockSignals(True)
                self._settings_dialog.chip_min_width.setValue(self.chip_min_width)
                self._settings_dialog.chip_min_width.blockSignals(False)
        self._apply_chip_width_settings()

    def _apply_chip_width_settings(self):
        for chip in self.chips_by_content.values():
            chip.min_width = self.chip_min_width
            chip.max_width = self.chip_max_width
            chip.update_label()
        self._save_context_menu_settings()

    def set_shelf_width_ratio(self, ratio):
        self.shelf_width_ratio = max(
            SHELF_WIDTH_RATIO_MIN,
            min(SHELF_WIDTH_RATIO_MAX, float(ratio)),
        )
        self._screen_geometry_cache_key = None
        self.update_screen_geometry()
        if self.is_open:
            self.animate_to(self.open_pos)
        else:
            self.move(self.hidden_pos)
        self._save_context_menu_settings()

    def set_close_to_tray_enabled(self, enabled):
        self.close_to_tray_enabled = bool(enabled)
        self._save_context_menu_settings()

    def set_start_with_windows_enabled(self, enabled):
        enabled = bool(enabled)
        try:
            self._set_windows_startup(enabled)
        except Exception as exc:
            log_exception(f"Failed to update Windows startup setting: {exc}")
            if self._settings_dialog is not None:
                self._settings_dialog.start_with_windows.setChecked(not enabled)
            return
        self.start_with_windows_enabled = enabled
        self._save_context_menu_settings()

    @staticmethod
    def _set_windows_startup(enabled):
        if sys.platform != "win32" or winreg is None:
            return

        run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key_path) as run_key:
            if enabled:
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}"'
                else:
                    script_path = Path(__file__).resolve().parents[1] / "main.py"
                    command = f'"{sys.executable}" "{script_path}"'
                winreg.SetValueEx(run_key, "ClipFlow", 0, winreg.REG_SZ, command)
            for value_name in ("Copy Pin", "ClipFlow"):
                if enabled and value_name == "ClipFlow":
                    continue
                try:
                    winreg.DeleteValue(run_key, value_name)
                except FileNotFoundError:
                    pass

    def closeEvent(self, event):
        if self.close_to_tray_enabled:
            event.ignore()
            self.hide_shelf(force=True)
            return
        self.tray_icon.hide()
        event.accept()
        QApplication.quit()

    def _cursor_over_chip_context_menu(self, cursor):
        popup = self._active_chip_context_menu()
        if popup is None or not popup.frameGeometry().contains(cursor):
            return False

        return True

    def _active_chip_context_menu(self):
        popup = QApplication.activePopupWidget()
        if not isinstance(popup, ChipContextMenu):
            return None
        parent = popup.parentWidget()
        while parent is not None and parent is not self:
            parent = parent.parentWidget()
        return popup if parent is self else None

    @safe_slot("Failed to check mouse position")
    def check_mouse_position(self):
        is_dragging = False
        if sys.platform == "win32":
            is_dragging = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        else:
            is_dragging = bool(QApplication.mouseButtons() & Qt.LeftButton)

        if self.is_shelf_pinned or self._is_hiding:
            return

        cursor = QCursor.pos()
        if self._cursor_over_chip_context_menu(cursor):
            if self.auto_hide_timer.isActive():
                self.auto_hide_timer.stop()
            return
            
        if not self.show_on_hover_enabled and not is_dragging and not self.is_open:
            return

        self.update_screen_geometry("cursor")
        mouse_y = cursor.y()

        if self.is_open:
            # Use the same hide margin on both the top and bottom edges so
            # Windows dock/taskbar gaps do not leave the shelf partially visible.
            active_area = self.geometry().adjusted(
                -8,
                -HIDE_DISTANCE,
                8,
                HIDE_DISTANCE,
            )
            if self._auto_hide_waiting_for_reentry:
                if active_area.contains(cursor):
                    self._auto_hide_waiting_for_reentry = False
                else:
                    if self.auto_hide_timer.isActive():
                        self.auto_hide_timer.stop()
                    return

            if not active_area.contains(cursor):
                if not self.auto_hide_timer.isActive():
                    self.auto_hide_timer.start(SHELF_AUTO_HIDE_DELAY)
            else:
                if self.auto_hide_timer.isActive():
                    self.auto_hide_timer.stop()
            return

        edge_geometry = getattr(self, "full_screen_geometry", self.screen_geometry)
        hover_threshold = edge_geometry.top() + max(HOVER_TRIGGER_HEIGHT, 1)
        is_over_top_edge = (
            self.trigger_left <= cursor.x() <= self.trigger_right
            and mouse_y <= hover_threshold
        )
        if is_over_top_edge:
            self.show_shelf("cursor")

    def keep_shelf_open_after_context_action(self):
        self._auto_hide_waiting_for_reentry = True
        if self.auto_hide_timer.isActive():
            self.auto_hide_timer.stop()

    def show_shelf(self, monitor_hint="cursor"):
        self.update_screen_geometry(monitor_hint)
        self.last_target_window = self.paste_controller.foreground_window()
        self._is_hiding = False
        self._auto_hide_waiting_for_reentry = False
        if self.hide_reset_timer.isActive():
            self.hide_reset_timer.stop()

        self.is_open = True

        # Make sure the shelf is raised above the taskbar/dock layer on Windows
        # before animating it into view.
        self.show()
        self.raise_()

        if SHELF_CHIP_REVEAL_ENABLED:
            self.reveal_chips()
        self.animate_to(self.open_pos)

    def hide_shelf(self, force=False):
        if self.is_shelf_pinned and not force:
            return

        popup = self._active_chip_context_menu()
        if popup is not None:
            fade(popup, 1.0, 0.0, CHIP_CONTEXT_MENU_FADE_OUT_MS, finished=popup.close)

        self.is_open = False
        self._is_hiding = True
        if self.hide_reset_timer.isActive():
            self.hide_reset_timer.stop()
        self.hide_reset_timer.start(max(MOTION_SHELF_MS, 120) + 40)

        self.animate_to(self.hidden_pos)

    def reveal_chips(self):
        # Animations removed: ensure all chips are visible immediately
        for index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(index)
            chip = item.widget() if item else None
            if chip is None or chip is getattr(self, "empty_state_widget", None):
                continue
            chip.setVisible(True)
            if hasattr(chip, "_base_width"):
                chip.setMinimumWidth(chip._base_width)
                chip.setMaximumWidth(chip._base_width)

    def toggle_shelf_pin(self):
        self.is_shelf_pinned = not self.is_shelf_pinned
        if self.is_shelf_pinned:
            if self.auto_hide_timer.isActive():
                self.auto_hide_timer.stop()
            self.show_shelf("active")
        else:
            self.hide_shelf(force=True)

    @safe_slot("Failed to check toggle hotkey")
    def check_toggle_hotkey(self):
        is_down = self.is_toggle_hotkey_down()
        if is_down and not self._hotkey_was_down:
            self.toggle_shelf_pin()
        self._hotkey_was_down = is_down

    @safe_slot("Failed to inspect toggle hotkey")
    def is_toggle_hotkey_down(self):
        if sys.platform != "win32":
            return False

        ctrl_pressed = (
            ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000
            or ctypes.windll.user32.GetAsyncKeyState(0xA2) & 0x8000
            or ctypes.windll.user32.GetAsyncKeyState(0xA3) & 0x8000
        )
        win_pressed = (
            ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000
            or ctypes.windll.user32.GetAsyncKeyState(0x5C) & 0x8000
        )
        return bool(ctrl_pressed and win_pressed)

    def animate_to(self, target):
        if self._target_pos == target:
            return

        self._target_pos = target
        if not MOTION_ENABLED:
            self.move(target)
            return

        self.animation.stop()
        self.animation.setStartValue(self.pos())
        self.animation.setEndValue(target)
        self.animation.start()

    def update_screen_geometry(self, monitor_hint="cursor"):
        screen = self.screen_for_hint(monitor_hint)
        geometry = screen.availableGeometry()
        full_geometry = screen.geometry()
        cache_key = (
            screen.name(),
            geometry.left(),
            geometry.top(),
            geometry.width(),
            geometry.height(),
            full_geometry.left(),
            full_geometry.top(),
            full_geometry.width(),
            full_geometry.height(),
        )
        if cache_key == self._screen_geometry_cache_key:
            return

        self._screen_geometry_cache_key = cache_key
        width = max(720, int(geometry.width() * self.shelf_width_ratio))
        width = min(width, geometry.width() - 32)

        window_width = width + self._shadow_margin * 2
        window_height = SHELF_HEIGHT + self._shadow_margin * 2
        if self.width() != window_width or self.height() != window_height:
            self.resize(window_width, window_height)

        x = geometry.left() + (geometry.width() - width) // 2 - self._shadow_margin
        y = geometry.top() + SHELF_TOP_MARGIN - self._shadow_margin
        self.screen_geometry = geometry
        self.full_screen_geometry = full_geometry
        self.open_pos = QPoint(x, y)
        hidden_y = full_geometry.top() - self.height() - 10
        self.hidden_pos = QPoint(x, hidden_y)
        trigger_center = geometry.left() + geometry.width() // 2
        trigger_half_width = HOVER_TRIGGER_WIDTH // 2
        self.trigger_left = trigger_center - trigger_half_width
        self.trigger_right = trigger_center + trigger_half_width

    def screen_for_hint(self, monitor_hint):
        if monitor_hint == "active":
            screen = self.active_window_screen()
            if screen:
                return screen

        return QApplication.screenAt(QCursor.pos()) or self.active_window_screen() or QApplication.primaryScreen()

    def active_window_screen(self):
        if not sys.platform.startswith("win"):
            return None

        hwnd = self.paste_controller.foreground_window()
        if not hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None

        center = QPoint((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        return QApplication.screenAt(center)

    def shutdown(self):
        try:
            self.clipboard_manager.close()
        except Exception:
            log_exception("Failed to shut down clipboard manager")
        try:
            self.clipboard_manager.get_db().clear()
        except Exception:
            log_exception("Failed to clear clipboard history on shutdown")
        try:
            self.clipboard_manager.image_store.clear_thumbnails()
        except Exception:
            log_exception("Failed to clear stored clipboard images on shutdown")
        try:
            shutdown_favicon_service()
        except Exception:
            log_exception("Failed to shut down favicon service")
