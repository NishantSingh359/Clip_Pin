from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
    QSizePolicy,
    QLabel,
)

from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
)
import ctypes
import ctypes.wintypes
import sys

from core.clipboard_manager import ClipboardManager
from core.dragdrop_handler import DragDropHandler
from core.paste_controller import PasteController
from ui.chip_bar import ChipBar
from ui.chip_widget import ChipWidget
from config import (
    APP_NAME,
    APP_STORAGE_DIR,
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
    SHELF_HEIGHT,
    SHELF_TOP_MARGIN,
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
        path.addRoundedRect(self.rect(), SHELF_BORDER_RADIUS, SHELF_BORDER_RADIUS)
        
        bg_color = QColor(SHELF_BACKGROUND_COLOR)
        painter.fillPath(path, bg_color)
        
        if SHELF_BORDER_WIDTH > 0:
            border_color = QColor(SHELF_BORDER_COLOR)
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
        self._hotkey_was_down = False

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
        self.clipboard_manager.sensitive_text_copied.connect(self.add_sensitive_clip)
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

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_mouse_position)
        self.timer.start(MOUSE_POLL_MS)

        self.hotkey_timer = QTimer()
        self.hotkey_timer.timeout.connect(self.check_toggle_hotkey)
        self.hotkey_timer.start(50)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SHELF_MARGIN[0], SHELF_MARGIN[1], SHELF_MARGIN[2], 0)
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

    def add_clip(self, content):
        if content in self.chips_by_content:
            return

        self.add_chip(content)

    def add_sensitive_clip(self, content):
        self.remove_clip(content)
        self.add_chip(content, sensitive=True)
        QTimer.singleShot(10 * 60 * 1000, lambda content=content: self.remove_clip(content))

    def add_chip(self, content, sensitive=False):
        if content in self.chips_by_content:
            return

        chip = ChipWidget(content, sensitive=sensitive)
        chip.paste_requested.connect(self.paste_clip)
        chip.delete_requested.connect(self.remove_clip)
        chip.pin_requested.connect(self.pin_clip)
        chip.clear_all_requested.connect(self.clear_unpinned_clips)
        self.chips_by_content[content] = chip
        self.update_empty_state()
        self.insert_chip(chip)
        QTimer.singleShot(0, chip.animate_entry)
        self.trim_chips()

    def add_clips(self, contents):
        for content in contents:
            self.add_clip(content)

    def remove_clip(self, content):
        chip = self.chips_by_content.pop(content, None)
        if not chip:
            return

        self.clipboard_manager.get_db().delete_by_content(content)
        self.remove_chip_widget(chip)

    def remove_chip_widget(self, chip):
        # Remove from layout and schedule deletion (prevents stale widgets in UI)
        chip.animate_delete(
            lambda chip=chip: (
                self.chip_layout.removeWidget(chip),
                chip.deleteLater(),
                self.update_empty_state(),
            )
        )

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

    def clear_unpinned_clips(self):
        chips = [
            chip
            for chip in list(self.chips_by_content.values())
            if not chip.pinned and not getattr(chip, "_is_deleting", False)
        ]

        db = self.clipboard_manager.get_db()
        for chip in chips:
            self.chips_by_content.pop(chip.content, None)
            db.delete_by_content(chip.content)
            self.remove_chip_widget(chip)

    def pin_clip(self, content):
        chip = self.chips_by_content.get(content)
        if not chip:
            return

        self.chip_layout.removeWidget(chip)
        self.insert_chip(chip)

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

    def paste_clip(self, content):
        self.hide_shelf()
        chip = self.chips_by_content.get(content)
        if chip and chip.kind == "IMG":
            self.clipboard_manager.set_image_for_paste(content)
        else:
            self.clipboard_manager.set_text_for_paste(content)

        QTimer.singleShot(
            MOTION_SHELF_MS,
            lambda: self.paste_controller.paste_text(content, self.last_target_window)
        )

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

    def dragEnterEvent(self, event):
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.dragdrop_handler.can_accept(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        items = self.dragdrop_handler.extract_items(event.mimeData())
        if not items:
            event.ignore()
            return

        self.add_clips(items)
        event.acceptProposedAction()

    # -------------------------
    # HOVER DETECTION
    # -------------------------

    def check_mouse_position(self):
        if self.is_shelf_pinned:
            return

        self.update_screen_geometry("cursor")
        cursor = QCursor.pos()
        mouse_y = cursor.y()

        if self.is_open:
            active_area = self.geometry().adjusted(-8, -8, 8, HIDE_DISTANCE)
            if not active_area.contains(cursor):
                if not self.auto_hide_timer.isActive():
                    self.auto_hide_timer.start(SHELF_AUTO_HIDE_DELAY)
            else:
                if self.auto_hide_timer.isActive():
                    self.auto_hide_timer.stop()
            return

        is_over_top_edge = (
            self.trigger_left <= cursor.x() <= self.trigger_right
            and mouse_y <= self.screen_geometry.top() + HOVER_TRIGGER_HEIGHT
        )
        if is_over_top_edge:
            self.show_shelf("cursor")

    def show_shelf(self, monitor_hint="cursor"):
        self.update_screen_geometry(monitor_hint)
        self.last_target_window = self.paste_controller.foreground_window()
        self.is_open = True
        self.animate_to(self.open_pos)

    def hide_shelf(self, force=False):
        if self.is_shelf_pinned and not force:
            return

        self.is_open = False
        self.animate_to(self.hidden_pos)

    def toggle_shelf_pin(self):
        self.is_shelf_pinned = not self.is_shelf_pinned
        if self.is_shelf_pinned:
            if self.auto_hide_timer.isActive():
                self.auto_hide_timer.stop()
            self.show_shelf("active")
        else:
            self.hide_shelf(force=True)

    def check_toggle_hotkey(self):
        is_down = self.is_toggle_hotkey_down()
        if is_down and not self._hotkey_was_down:
            self.toggle_shelf_pin()
        self._hotkey_was_down = is_down

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
        width = max(720, int(geometry.width() * SHELF_WIDTH_RATIO))
        width = min(width, geometry.width() - 32)

        if self.width() != width or self.height() != SHELF_HEIGHT:
            self.resize(width, SHELF_HEIGHT)

        x = geometry.left() + (geometry.width() - self.width()) // 2
        y = geometry.top() + SHELF_TOP_MARGIN
        self.screen_geometry = geometry
        self.open_pos = QPoint(x, y)
        self.hidden_pos = QPoint(x, y - self.height() - 10)
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
