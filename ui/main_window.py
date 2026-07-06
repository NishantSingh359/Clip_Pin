from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
    QSizePolicy,
    QLabel,
    QMenu,
)

from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QRegion,
)
import ctypes
import ctypes.wintypes
import sys
from pathlib import Path

from core.clipboard_manager import ClipboardManager
from core.dragdrop_handler import DragDropHandler
from core.favicon_service import shutdown_favicon_service
from core.paste_controller import PasteController
from ui.chip_bar import ChipBar
from ui.chip_widget import ChipWidget
from ui.animations import parse_color
from config import (
    APP_NAME,
    APP_STORAGE_DIR,
    CONTEXT_MENU_FONT_SIZE,
    CONTEXT_MENU_BACKGROUND_COLOR,
    CONTEXT_MENU_BORDER_COLOR,
    CONTEXT_MENU_BORDER_RADIUS,
    CONTEXT_MENU_HOVER_BORDER_RADIUS,
    CONTEXT_MENU_HOVER_COLOR,
    CONTEXT_MENU_ITEM_PADDING,
    CONTEXT_MENU_TEXT_COLOR,
    CONTEXT_MENU_TEXT_FONT_WEIGHT,
    CONTEXT_MENU_BORDER_WIDTH,
    EMPTY_STATE_FONT_SIZE,
    EMPTY_STATE_FONT_WEIGHT,
    EMPTY_STATE_PADDING,
    EMPTY_STATE_TEXT,
    EMPTY_STATE_TEXT_COLOR,
    HIDE_DISTANCE,
    HOVER_TRIGGER_HEIGHT,
    HOVER_TRIGGER_WIDTH,
    MAX_CHIPS,
    MOUSE_POLL_MS,
    MOTION_ENABLED,
    MOTION_SHELF_MS,
    SHELF_CHIP_REVEAL_ENABLED,
    SHELF_CHIP_REVEAL_MS,
    SHELF_CHIP_REVEAL_STAGGER_MS,
    SHELF_CHIP_REVEAL_OFFSET,
    SHELF_SHOW_ON_HOVER,
    SHELF_HEIGHT,
    SHELF_TOP_MARGIN,
    clip_indexing,
    SHELF_WIDTH_RATIO,
    SHELF_BACKGROUND_COLOR,
    SHELF_BORDER_COLOR,
    SHELF_BORDER_WIDTH,
    SHELF_BORDER_RADIUS,
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
        self.setMaximumHeight(SHELF_HEIGHT)
    
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
        self.show_on_hover_enabled = SHELF_SHOW_ON_HOVER
        self.clip_indexing_enabled = clip_indexing

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

        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(MOTION_SHELF_MS)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.update_screen_geometry()
        self.move(self.hidden_pos)

        self.setup_ui()

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide_shelf)

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
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.container = ShelfContainer()
        # Background is drawn in ShelfContainer.paintEvent(), so keep widget background unset
        self.container.setStyleSheet("")
        self.container.setContextMenuPolicy(Qt.CustomContextMenu)
        self.container.customContextMenuRequested.connect(self.show_shelf_context_menu)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_shelf_context_menu)

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
        self.empty_label = QLabel(EMPTY_STATE_TEXT)
        self.empty_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.empty_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.empty_label.setStyleSheet(f"""
            QLabel {{
                color: {EMPTY_STATE_TEXT_COLOR};
                font-size: {EMPTY_STATE_FONT_SIZE}px;
                font-weight: {EMPTY_STATE_FONT_WEIGHT};
                padding: {EMPTY_STATE_PADDING[0]}px {EMPTY_STATE_PADDING[1]}px;
            }}
        """)
        self.chip_layout.addWidget(self.empty_label)
        self.chip_layout.addStretch()
        self.update_empty_state()
        self.update_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "container"):
            self.update_mask()

    def update_mask(self):
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, SHELF_BORDER_RADIUS, SHELF_BORDER_RADIUS)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    @safe_slot("Failed to add clipboard chip")
    def add_clip(self, content):
        if content in self.chips_by_content:
            return

        self.add_chip(content)

    @safe_slot("Failed to create clipboard chip")
    def add_chip(self, content):
        if content in self.chips_by_content:
            return

        chip = ChipWidget(content)
        chip.paste_requested.connect(self.paste_clip)
        chip.copy_again_requested.connect(self.copy_again_clip)
        chip.delete_requested.connect(self.remove_clip)
        chip.pin_requested.connect(self.pin_clip)
        chip.clear_all_requested.connect(self.clear_unpinned_clips)
        self.chips_by_content[content] = chip
        self.update_empty_state()
        self.insert_chip(chip)
        self.refresh_chip_indexes()
        # Animations removed: immediately ensure chip is visible at its base width
        chip.setMinimumWidth(chip._base_width)
        chip.setMaximumWidth(chip._base_width)
        chip.show()
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
        # Remove from layout and schedule deletion (prevents stale widgets in UI)
        # Animations removed: remove immediately
        self.chip_layout.removeWidget(chip)
        chip.deleteLater()
        self.update_empty_state()
        self.refresh_chip_indexes()

    def update_empty_state(self):
        if hasattr(self, "empty_label"):
            has_chip_widgets = False
            for index in range(self.chip_layout.count()):
                item = self.chip_layout.itemAt(index)
                widget = item.widget() if item else None
                if widget and widget is not self.empty_label:
                    has_chip_widgets = True
                    break
            self.empty_label.setVisible(not self.chips_by_content and not has_chip_widgets)

    @safe_slot("Failed to clear unpinned clips")
    def clear_unpinned_clips(self):
        chips = [
            chip
            for chip in list(self.chips_by_content.values())
            if not chip.pinned and not getattr(chip, "_is_deleting", False)
        ]

        db = self.clipboard_manager.get_db()
        for chip in chips:
            self.chips_by_content.pop(chip.content, None)
            try:
                db.delete_by_content(chip.content)
            except Exception:
                log_exception("Failed to delete clipboard item during clear")
            self.remove_chip_widget(chip)
        self.refresh_chip_indexes()

    @safe_slot("Failed to pin clipboard chip")
    def pin_clip(self, content):
        chip = self.chips_by_content.get(content)
        if not chip:
            return

        self.chip_layout.removeWidget(chip)
        self.insert_chip(chip)
        self.refresh_chip_indexes()

    def insert_chip(self, chip):
        pinned_count = 0
        for index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(index)
            if not item:
                continue
            widget = item.widget()
            if widget is None:
                continue
            if widget is getattr(self, "empty_label", None):
                continue
            if getattr(widget, "pinned", False):
                pinned_count += 1
            else:
                break
        self.chip_layout.insertWidget(pinned_count, chip)

    def refresh_chip_indexes(self):
        chips = []
        for layout_index in range(self.chip_layout.count()):
            item = self.chip_layout.itemAt(layout_index)
            widget = item.widget() if item else None
            if widget is None or widget is getattr(self, "empty_label", None):
                continue
            if hasattr(widget, "set_clip_index"):
                chips.append(widget)

        index = len(chips)
        for chip in chips:
            chip.set_clip_index(index, show_index=self.clip_indexing_enabled)
            index -= 1

    @safe_slot("Failed to paste clipboard chip")
    def paste_clip(self, content):
        from config import HIDE_ON_PASTE
        if HIDE_ON_PASTE:
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
        while len(self.chips_by_content) > MAX_CHIPS:
            chip = self.oldest_unpinned_chip()
            if chip is None:
                return
            self.chips_by_content.pop(chip.content, None)
            self.remove_chip_widget(chip)

    def oldest_unpinned_chip(self):
        for index in range(self.chip_layout.count() - 2, -1, -1):
            item = self.chip_layout.itemAt(index)
            if not item:
                continue
            chip = item.widget()
            if (
                chip
                and chip is not getattr(self, "empty_label", None)
                and not getattr(chip, "pinned", False)
                and not getattr(chip, "_is_deleting", False)
            ):
                return chip
        return None

    @safe_slot("Failed to process drag enter")
    def dragEnterEvent(self, event):
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    @safe_slot("Failed to process drag move")
    def dragMoveEvent(self, event):
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    @safe_slot("Failed to process drop")
    def dropEvent(self, event):
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

    def set_clip_indexing_enabled(self, enabled):
        self.clip_indexing_enabled = bool(enabled)
        self.refresh_chip_indexes()

    def show_shelf_context_menu(self, pos):
        menu = QMenu(self)
        hover_action = QAction("Show on Hover", self, checkable=True)
        hover_action.setChecked(self.show_on_hover_enabled)
        index_action = QAction("Show Clip Indexes", self, checkable=True)
        index_action.setChecked(self.clip_indexing_enabled)

        menu.addAction(hover_action)
        menu.addAction(index_action)

        menu.setStyleSheet(f'''
            QMenu {{
                font-size: {CONTEXT_MENU_FONT_SIZE}px;
                font-weight: {CONTEXT_MENU_TEXT_FONT_WEIGHT};
                background-color: {CONTEXT_MENU_BACKGROUND_COLOR};
                color: {CONTEXT_MENU_TEXT_COLOR};
                border: {CONTEXT_MENU_BORDER_WIDTH}px solid {CONTEXT_MENU_BORDER_COLOR};
                border-radius: {CONTEXT_MENU_BORDER_RADIUS}px;
                padding: {CONTEXT_MENU_ITEM_PADDING[0]}px {CONTEXT_MENU_ITEM_PADDING[1]}px;
            }}
            QMenu::item {{
                padding: {CONTEXT_MENU_ITEM_PADDING[0]}px {CONTEXT_MENU_ITEM_PADDING[1]}px;
            }}
            QMenu::item:selected {{
                background-color: {CONTEXT_MENU_HOVER_COLOR};
                border-radius: {CONTEXT_MENU_HOVER_BORDER_RADIUS}px;
            }}
        ''')

        selected_action = menu.exec(
            self.mapToGlobal(pos)
        )
        if selected_action is hover_action:
            self.set_show_on_hover_enabled(hover_action.isChecked())
        elif selected_action is index_action:
            self.set_clip_indexing_enabled(index_action.isChecked())

    @safe_slot("Failed to check mouse position")
    def check_mouse_position(self):
        if self.is_shelf_pinned or self._is_hiding or not self.show_on_hover_enabled:
            return

        self.update_screen_geometry("cursor")
        cursor = QCursor.pos()
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

    def show_shelf(self, monitor_hint="cursor"):
        self.update_screen_geometry(monitor_hint)
        self.last_target_window = self.paste_controller.foreground_window()
        self._is_hiding = False
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
            if chip is None or chip is getattr(self, "empty_label", None):
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
        space_pressed = ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000
        return bool(ctrl_pressed and space_pressed)

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
        width = max(720, int(geometry.width() * SHELF_WIDTH_RATIO))
        width = min(width, geometry.width() - 32)

        if self.width() != width or self.height() != SHELF_HEIGHT:
            self.resize(width, SHELF_HEIGHT)

        x = geometry.left() + (geometry.width() - self.width()) // 2
        y = geometry.top() + SHELF_TOP_MARGIN
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
            shutdown_favicon_service()
        except Exception:
            log_exception("Failed to shut down favicon service")
