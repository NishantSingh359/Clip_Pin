import os
import re
import sys
from base64 import b64encode
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal, QPoint, QSize, QRectF, QMimeData, QBuffer, QIODevice, QTimer
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
    QRegion,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QHBoxLayout,
    QMenu,
    QWidget,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QToolButton,
    QWidgetAction,
)

from ui.theme_manager import get_theme_value
from config import (
    CHIP_MAX_WIDTH,
    CHIP_MIN_WIDTH,
    COLOR_PREVIEW_ENABLED,
    clip_indexing,
)
from core.favicon_service import get_favicon_service
from utils.app_logging import log_exception, safe_slot
from ui.animations import (
    color_to_rgba,
    parse_color,
)


class ChipContextMenu(QMenu):
    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        self.theme = theme or {"context_menu": {}}

    def _effective_corner_radius(self):
        radius = float(self.theme.get("context_menu", {}).get("border_radius", 50))
        if self.width() <= 0 or self.height() <= 0:
            return radius
        return min(radius, self.width() / 2, self.height() / 2)

    def _apply_menu_shape(self):
        if self.width() <= 0 or self.height() <= 0:
            return
        radius = self._effective_corner_radius()
        menu_theme = self.theme.get("context_menu", {})
        self.setStyleSheet(f'''
            QMenu {{
                background: {menu_theme.get('background', 'rgba(20, 20, 20, 1)')};
                color: {menu_theme.get('text', 'rgba(200, 200, 200, 1)')};
                border: none;
                padding: {menu_theme.get('padding', 6)}px;
            }}
        ''')

        path = QPainterPath()
        path.addRoundedRect(self.rect(), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event):
        if self.width() <= 0 or self.height() <= 0:
            super().paintEvent(event)
            return

        menu_theme = self.theme.get("context_menu", {})
        outer_radius = self._effective_corner_radius()
        background_path = QPainterPath()
        background_path.addRoundedRect(self.rect(), outer_radius, outer_radius)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(parse_color(menu_theme.get("background", "rgba(20, 20, 20, 1)")))
        painter.drawPath(background_path)
        painter.end()

        super().paintEvent(event)

        border_width = float(menu_theme.get("border_width", 1.2))
        if border_width <= 0:
            return

        inset = border_width / 2
        border_rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        border_path = QPainterPath()
        border_path.addRoundedRect(
            border_rect,
            max(0, outer_radius - inset),
            max(0, outer_radius - inset),
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(parse_color(menu_theme.get("border", "rgba(200, 200, 200, 0.09)")), border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(border_path)
        painter.end()

    def set_theme(self, theme):
        self.theme = theme
        self._apply_menu_shape()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_menu_shape()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_menu_shape()


class ChipWidget(QWidget):
    paste_requested = Signal(str)
    copy_again_requested = Signal(str)
    delete_requested = Signal(str)
    pin_requested = Signal(str)
    clear_all_requested = Signal()
    context_action_triggered = Signal()
    image_opening = Signal(str)
    favicon_loaded = Signal(bytes)

    def __init__(
        self,
        content,
        min_width=None,
        max_width=None,
        color_preview_enabled=None,
        theme=None,
    ):
        super().__init__()

        self.content = content
        self.theme = theme or {"chip": {}}
        self.min_width = int(min_width) if min_width is not None else CHIP_MIN_WIDTH
        self.max_width = int(max_width) if max_width is not None else CHIP_MAX_WIDTH
        self.max_width = max(self.max_width, self.min_width)
        self.color_preview_enabled = bool(color_preview_enabled) if color_preview_enabled is not None else COLOR_PREVIEW_ENABLED
        self.clip_index = None
        self.kind = self.detect_kind()
        self.pinned = False
        self.network = None
        self._destroyed = False
        self._is_hovered = False
        self._is_deleting = False
        self._drag_start_position = None
        self._dragging = False
        self._suppress_next_release = False
        self._image_click_timer = QTimer(self)
        self._image_click_timer.setSingleShot(True)
        # Keep the single-click paste pending until Qt has time to recognize a
        # double-click, with a small margin for queued UI events.
        self._image_click_timer.setInterval(QApplication.doubleClickInterval() + 50)
        self._image_click_timer.timeout.connect(lambda: self.paste_requested.emit(self.content))
        self._favicon_pixmap = QPixmap()
        self.setObjectName("chip")

        chip_theme = self.theme.get("chip", {})
        self._chip_height = int(chip_theme.get("height", 32))
        self.setFixedHeight(self._chip_height)
        self.setMinimumWidth(self.min_width)
        self.setMaximumWidth(self.max_width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self._base_width = self.min_width
        self._base_height = self._chip_height

        self.setup_ui()
        self.apply_style()
        self.update_label()
        self.destroyed.connect(self.mark_destroyed)
        self.favicon_loaded.connect(self.on_favicon_data_loaded)

        if self.kind == "LINK":
            self.load_favicon()

    def mark_destroyed(self):
        self._destroyed = True

    def sizeHint(self):
        return QSize(self._base_width, self._base_height)

    def setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        chip_theme = self.theme.get("chip", {})

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(*chip_theme.get("padding", [10, 0, 10, 0]))
        self.layout.setSpacing(int(chip_theme.get("spacing", 8)))

        self.index_label = QLabel()
        self.index_label.setAlignment(Qt.AlignCenter)
        self.index_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.index_label.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("index", "rgba(150, 150, 150, 0.7)")};
                font-size: {chip_theme.get("index_font_size", 11)}px;
                font-weight: {chip_theme.get("index_font_weight", 700)};
            }}
        """)
        self.index_label.hide()

        self.icon = QLabel()
        icon_size = int(chip_theme.get("icon_size", 18))
        self.icon.setFixedSize(icon_size, icon_size)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("icon_color", "rgba(200, 200, 200, 1)")};
                font-size: {chip_theme.get("icon_font_size", 11)}px;
                font-weight: 800;
            }}
        """)
        thumbnail = chip_theme.get("thumbnail", {})
        if int(thumbnail.get("shadow_blur_radius", 3)) > 0:
            thumbnail_shadow = QGraphicsDropShadowEffect(self.icon)
            thumbnail_shadow.setBlurRadius(int(thumbnail.get("shadow_blur_radius", 3)))
            thumbnail_shadow.setOffset(*thumbnail.get("shadow_offset", [0, 1]))
            thumbnail_shadow.setColor(parse_color(thumbnail.get("shadow_color", "rgba(0, 0, 0, 0.45)")))
            self.icon.setGraphicsEffect(thumbnail_shadow)

        self.title = QLabel()
        self.title.setAlignment(Qt.AlignVCenter)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("text", "rgba(200, 200, 200, 1)")};
                font-size: {chip_theme.get("font_size", 15)}px;
                font-weight: {chip_theme.get("font_weight", 600)};
            }}
        """)

        self.open_icon = QLabel()
        open_icon_size = int(chip_theme.get("open_icon_size", 18))
        self.open_icon.setFixedSize(open_icon_size, open_icon_size)
        self.open_icon.setAlignment(Qt.AlignCenter)
        self.open_icon.setCursor(Qt.PointingHandCursor)
        self.open_icon.setPixmap(self.load_open_icon_pixmap())
        self.open_icon.mousePressEvent = self.open_link
        self.open_icon.setVisible(self.kind == "LINK")

        self.layout.addWidget(self.index_label)
        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.open_icon)

    def apply_style(self):
        chip_theme = self.theme.get("chip", {})
        border_color = chip_theme.get("border", "rgba(200, 200, 200, 0.09)")
        if self.pinned:
            border_color = chip_theme.get("pinned_border", border_color)
        elif self._is_hovered:
            border_color = chip_theme.get("hover_border", border_color)
        background_color = chip_theme.get(
            "pinned" if self.pinned else "hover" if self._is_hovered else "default",
            "rgba(45, 45, 45, 1)" if self.pinned else "rgba(40, 40, 40, 1)" if self._is_hovered else "rgba(35, 35, 35, 1)",
        )
        self.setStyleSheet(f"""
            #chip {{
                background-color: {color_to_rgba(background_color)};
                border: {chip_theme.get("border_width", 1)}px solid {border_color};
                border-radius: {chip_theme.get("border_radius", 15)}px;
            }}
        """)

    def set_theme(self, theme):
        self.theme = theme
        self.apply_style()
        chip_theme = theme.get("chip", {})
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("text", "rgba(200, 200, 200, 1)")};
                font-size: {chip_theme.get("font_size", 15)}px;
                font-weight: {chip_theme.get("font_weight", 600)};
            }}
        """)
        self.index_label.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("index", "rgba(150, 150, 150, 0.7)")};
                font-size: {chip_theme.get("index_font_size", 11)}px;
                font-weight: {chip_theme.get("index_font_weight", 700)};
            }}
        """)
        self.icon.setStyleSheet(f"""
            QLabel {{
                color: {chip_theme.get("icon_color", "rgba(200, 200, 200, 1)")};
                font-size: {chip_theme.get("icon_font_size", 11)}px;
                font-weight: 800;
            }}
        """)
        self.apply_style()

    def set_hovered(self, hovered):
        hovered = bool(hovered)
        if self._is_hovered == hovered:
            return
        self._is_hovered = hovered
        if not self._is_deleting:
            self.apply_style()

    def set_clip_index(self, index, show_index=True):
        self.clip_index = index
        self.index_label.setText(str(index))
        self.index_label.setVisible(bool(show_index))
        self.update_label()

    def detect_kind(self):
        content = self.content.strip()

        if content.startswith(("http://", "https://")):
            return "LINK"

        if self.color_preview_enabled and self.parse_color_code(content) is not None:
            return "COLOR"

        if Path(content).name.lower().startswith("screenshot") and content.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return "IMG"

        if content.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return "IMG"

        if os.path.exists(content):
            return "PATH"

        return "TEXT"

    def update_label(self):
        text = self.display_text()
        metrics = QFontMetrics(self.title.font())
        chip_theme = self.theme.get("chip", {})
        if self.kind == "IMG":
            self.icon.show()
            self.set_image_thumb()
        elif self.kind == "COLOR":
            self.icon.show()
            self.set_color_swatch()
        elif self.kind == "LINK":
            self.icon.show()
            self.icon.setText("")
            if self._favicon_pixmap.isNull():
                self.icon.setPixmap(self.logo_fallback_pixmap())
            else:
                self.icon.setPixmap(self._favicon_pixmap)
        elif self.kind == "PATH":
            self.icon.show()
            icon_size = int(chip_theme.get("folder_icon_size", 22))
            self.icon.setFixedSize(icon_size, icon_size)
            self.icon.setPixmap(self.load_path_icon_pixmap())
        else:
            self.icon.hide()

        visible_widgets = [
            widget for widget in (self.index_label, self.icon, self.title, self.open_icon)
            if not widget.isHidden()
        ]
        margins = self.layout.contentsMargins()
        fixed_width = margins.left() + margins.right() + 2 * int(chip_theme.get("border_width", 1))
        fixed_width += int(chip_theme.get("spacing", 8)) * max(0, len(visible_widgets) - 1)
        fixed_width += sum(
            widget.sizeHint().width()
            for widget in visible_widgets
            if widget is not self.title
        )
        natural_width = fixed_width + metrics.horizontalAdvance(text)
        width = max(self.min_width, min(natural_width, self.max_width))
        title_width = max(0, width - fixed_width)
        self.title.setText(metrics.elidedText(text, Qt.ElideRight, title_width))
        self._base_width = width
        self.setFixedWidth(width)
        self.setFixedHeight(self._base_height)

    def set_color_preview_enabled(self, enabled):
        enabled = bool(enabled)
        if self.color_preview_enabled == enabled:
            return
        self.color_preview_enabled = enabled
        self.kind = self.detect_kind()
        self.update_label()

    @staticmethod
    def parse_color_code(text):
        value = text.strip()
        hex_match = re.fullmatch(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value)
        if hex_match:
            digits = hex_match.group(1)
            if len(digits) in (3, 4):
                channels = [int(char * 2, 16) for char in digits]
            else:
                channels = [int(digits[index:index + 2], 16) for index in range(0, len(digits), 2)]
            if len(channels) == 3:
                channels.append(255)
            elif len(channels) == 4 and len(digits) == 8:
                channels = channels[:3] + [channels[3]]
            return QColor(*channels)

        rgb_match = re.fullmatch(
            r"rgba?\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
            r"\s*(?:,\s*(\d+(?:\.\d+)?)\s*)?\)",
            value,
            re.IGNORECASE,
        )
        if not rgb_match:
            return None

        red, green, blue = (int(rgb_match.group(index)) for index in (1, 2, 3))
        if any(channel > 255 for channel in (red, green, blue)):
            return None

        alpha_text = rgb_match.group(4)
        alpha = 255
        if alpha_text is not None:
            alpha_value = float(alpha_text)
            if 0 <= alpha_value <= 1:
                alpha = round(alpha_value * 255)
            elif alpha_value <= 255 and alpha_value.is_integer():
                alpha = int(alpha_value)
            else:
                return None
        return QColor(red, green, blue, alpha)

    def set_color_swatch(self):
        color = self.parse_color_code(self.content)
        if color is None:
            return

        chip_theme = self.theme.get("chip", {})
        size = max(1, int(chip_theme.get("color_preview_size", 22)))
        border_width = max(0, int(chip_theme.get("color_preview_border_width", 1)))
        self.icon.setFixedSize(size, size)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(pixmap.rect()).adjusted(
            border_width / 2,
            border_width / 2,
            -border_width / 2,
            -border_width / 2,
        )
        if border_width:
            painter.setPen(QPen(parse_color(chip_theme.get("color_preview_border_color", "rgba(255, 255, 255, 0.25)")), border_width))
        else:
            painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(rect)
        painter.end()
        self.icon.setPixmap(pixmap)

    def display_text(self):
        content = self.content.strip()
        if self.kind == "COLOR":
            return content
        if self.kind == "LINK":
            domain = urlparse(content).netloc
            return domain.removeprefix("www.") or content

        if self.kind == "IMG":
            return "Screenshot" if Path(content).name.lower().startswith("screenshot") else os.path.basename(content)

        if self.kind == "PATH":
            return os.path.basename(content.rstrip("\\/")) or content

        return content.replace("\n", " ")

    def set_image_thumb(self):
        pixmap = QPixmap(self.content)
        if pixmap.isNull():
            self.icon.setText("I")
            return

        chip_theme = self.theme.get("chip", {})
        thumbnail = chip_theme.get("thumbnail", {})
        thumb_size = QSize(
            int(thumbnail.get("width", 26)),
            int(thumbnail.get("height", 22)),
        )
        scaled = pixmap.scaled(thumb_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rounded = QPixmap(thumb_size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(
            0,
            0,
            thumb_size.width(),
            thumb_size.height(),
            int(thumbnail.get("border_radius", 4)),
            int(thumbnail.get("border_radius", 4)),
        )
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        self.icon.setFixedSize(thumb_size)
        self.icon.setPixmap(rounded)

    def domain(self):
        return urlparse(self.content).netloc.removeprefix("www.").lower()

    def logo_fallback_pixmap(self):
        domain = self.domain()
        size = 18
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        if "youtube." in domain:
            painter.setBrush(QColor("#ff0033"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(1, 4, 16, 10, 3, 3)
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(QPolygon([
                self._point(7, 6),
                self._point(7, 12),
                self._point(12, 9),
            ]))
        elif "chatgpt." in domain or "openai." in domain:
            painter.setBrush(QColor("#f5f1e8"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 14, 14)
            painter.setPen(QPen(QColor("#16171a"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawEllipse(5, 5, 8, 8)
            painter.drawLine(9, 3, 9, 7)
            painter.drawLine(9, 11, 9, 15)
        elif "brave." in domain:
            painter.setBrush(QColor("#fb542b"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(2, 2, 14, 14, 4, 4)
            painter.setPen(QPen(QColor("#ffffff"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(6, 5, 6, 13)
            painter.drawLine(6, 5, 11, 5)
            painter.drawLine(6, 9, 11, 9)
            painter.drawLine(6, 13, 11, 13)
        elif "amazon." in domain:
            painter.setBrush(QColor("#f7f7f2"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 14, 14)
            painter.setPen(QPen(QColor("#17191d"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawText(5, 12, "a")
            painter.setPen(QPen(QColor("#ff9900"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawArc(5, 8, 8, 5, 205 * 16, 120 * 16)
        elif "github." in domain:
            painter.setBrush(QColor("#f7f7f2"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 14, 14)
            painter.setPen(QPen(QColor("#17191d"), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawEllipse(5, 5, 8, 7)
            painter.drawLine(6, 5, 5, 3)
            painter.drawLine(12, 5, 13, 3)
        elif "google." in domain:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 14, 14)
            painter.setPen(QPen(QColor("#4285f4"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawArc(5, 5, 8, 8, -40 * 16, 230 * 16)
            painter.drawLine(10, 9, 14, 9)
        elif "figma." in domain:
            colors = ["#f24e1e", "#ff7262", "#a259ff", "#1abcfe", "#0acf83"]
            positions = [(5, 2), (9, 2), (5, 6), (9, 6), (5, 10)]
            painter.setPen(Qt.NoPen)
            for color, (x, y) in zip(colors, positions):
                painter.setBrush(QColor(color))
                painter.drawEllipse(x, y, 4, 4)
        elif "iconscout." in domain:
            self.draw_letter_badge(painter, size, "i", QColor("#7c3aed"), QColor("#ffffff"))
        elif "icons8." in domain:
            self.draw_letter_badge(painter, size, "8", QColor("#1fb141"), QColor("#ffffff"))
        elif "ui-layouts." in domain:
            painter.setBrush(QColor("#f4f2ee"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(2, 2, 14, 14, 4, 4)
            painter.setPen(QPen(QColor("#191b20"), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawRect(5, 5, 8, 8)
            painter.drawLine(5, 8, 13, 8)
            painter.drawLine(8, 8, 8, 13)
        elif "lucide." in domain:
            painter.setBrush(QColor("#f4f2ee"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 14, 14)
            painter.setPen(QPen(QColor("#18191d"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(7, 5, 7, 12)
            painter.drawLine(7, 12, 12, 12)
        else:
            self.draw_letter_badge(
                painter,
                size,
                domain[:1].upper() or "?",
                QColor("#3b3b44"),
                QColor("#f4f2ee"),
            )

        painter.end()
        return pixmap

    def draw_letter_badge(self, painter, size, text, background, foreground):
        painter.setBrush(background)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)

        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(foreground)
        painter.drawText(0, 0, size, size - 1, Qt.AlignCenter, text[:1])

    def _point(self, x, y):
        from PySide6.QtCore import QPoint

        return QPoint(x, y)

    def load_favicon(self):
        try:
            get_favicon_service().request(self.content, self._emit_favicon_loaded)
        except Exception:
            log_exception("Failed to request favicon")

    def _emit_favicon_loaded(self, data):
        if self._destroyed:
            return
        try:
            self.favicon_loaded.emit(data)
        except RuntimeError:
            return

    @safe_slot("Failed to apply favicon data")
    def on_favicon_data_loaded(self, data):
        if self._destroyed:
            return

        pixmap = QPixmap()
        chip_theme = self.theme.get("chip", {})
        favicon_size = int(chip_theme.get("favicon_size", 22))
        if pixmap.loadFromData(data) and not pixmap.isNull():
            self._favicon_pixmap = pixmap.scaled(
                favicon_size,
                favicon_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.icon.setText("")
            self.icon.setFixedSize(favicon_size, favicon_size)
            self.icon.setPixmap(self._favicon_pixmap)

    def external_link_icon(self, color):
        chip_theme = self.theme.get("chip", {})
        size = int(chip_theme.get("open_icon_size", 18))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        # draw a small external-link glyph scaled to pixmap
        w = pixmap.width()
        h = pixmap.height()
        painter.drawLine(w*0.25, h*0.9, w*0.25, h*0.45)
        painter.drawLine(w*0.25, h*0.9, w*0.6, h*0.9)
        painter.drawLine(w*0.45, h*0.25, w*0.85, h*0.25)
        painter.drawLine(w*0.85, h*0.25, w*0.85, h*0.55)
        painter.drawLine(w*0.4, h*0.6, w*0.85, h*0.25)
        painter.end()

        return pixmap

    def _resolve_icon_path(self, cfg_path):
        p = Path(cfg_path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[1] / cfg_path
        return p

    def parse_css_color(self, color_string):
        if isinstance(color_string, QColor):
            return color_string
        try:
            color = QColor(color_string)
            if color.isValid() and (color.red() or color.green() or color.blue() or color.alpha()):
                return color
        except Exception:
            pass

        if isinstance(color_string, str):
            value = color_string.strip()
            if value.startswith("rgba(") or value.startswith("rgb("):
                body = value[value.find("(") + 1:value.rfind(")")]
                parts = [p.strip() for p in body.split(",")]
                if len(parts) in (3, 4):
                    r = int(parts[0])
                    g = int(parts[1])
                    b = int(parts[2])
                    a = 255
                    if len(parts) == 4:
                            alpha = parts[3]
                            try:
                                a_val = float(alpha)
                            except Exception:
                                a_val = 1.0
                            if a_val <= 1.0:
                                a = int(max(0, min(1.0, a_val)) * 255)
                            else:
                                a = int(max(0, min(255, int(a_val))))
                    return QColor(r, g, b, a)
        return QColor()

    def _load_icon_pixmap(self, path, size, color):
        path = self._resolve_icon_path(path)
        if not path.exists():
            return QPixmap()

        color = QColor(color)
        if path.suffix.lower() == ".svg":
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            renderer = QSvgRenderer(str(path))
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
        else:
            loaded = QPixmap(str(path))
            if loaded.isNull():
                return QPixmap()
            pix = loaded.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if pix.isNull():
            return QPixmap()

        tinted = QPixmap(pix.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, pix)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def load_open_icon_pixmap(self):
        chip_theme = self.theme.get("chip", {})
        icon_path = chip_theme.get("open_icon_path", "assets/icons/open_link.svg")
        icon_size = int(chip_theme.get("open_icon_size", 18))
        icon_color = self.parse_css_color(chip_theme.get("open_icon_color", "rgba(150, 150, 150, 1)"))
        pix = self._load_icon_pixmap(icon_path, icon_size, icon_color)
        if not pix.isNull():
            return pix
        return self.external_link_icon(icon_color)

    def load_folder_icon_pixmap(self):
        chip_theme = self.theme.get("chip", {})
        icon_path = chip_theme.get("folder_icon_path", "assets/icons/folder.svg")
        icon_size = int(chip_theme.get("folder_icon_size", 22))
        icon_color = self.parse_css_color(chip_theme.get("folder_icon_color", "rgba(200, 200, 200, 1)"))
        pix = self._load_icon_pixmap(icon_path, icon_size, icon_color)
        if not pix.isNull():
            return pix

        # draw a simple folder glyph
        size = icon_size
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        brush = self.parse_css_color(FOLDER_ICON_COLOR)
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)
        r = size
        # folder base
        painter.drawRoundedRect(0, int(size*0.25), r, int(size*0.65), 3, 3)
        # folder tab
        painter.drawRect(int(size*0.1), 0, int(size*0.5), int(size*0.35))
        painter.end()
        return pixmap

    def load_path_icon_pixmap(self):
        chip_theme = self.theme.get("chip", {})
        icon_size = int(chip_theme.get("folder_icon_size", 22))
        icon_color = self.parse_css_color(chip_theme.get("folder_icon_color", "rgba(200, 200, 200, 1)"))
        folder_path = chip_theme.get("folder_icon_path", "assets/icons/folder.svg")
        file_path = chip_theme.get("file_icon_path", "assets/icons/file.svg")
        icon_path = folder_path if os.path.isdir(self.content) else file_path
        pix = self._load_icon_pixmap(icon_path, icon_size, icon_color)
        if not pix.isNull():
            return pix
        return self._load_icon_pixmap(folder_path, icon_size, icon_color)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_position = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() & Qt.LeftButton
            and self._drag_start_position is not None
            and not self._dragging
        ):
            distance = (event.pos() - self._drag_start_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._image_click_timer.stop()
                self._dragging = True
                self._start_drag()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.kind == "IMG":
            self._image_click_timer.stop()
            self._suppress_next_release = True
            image_path = Path(self.content)
            if image_path.is_file():
                self.image_opening.emit(str(image_path))
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path.resolve())))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._suppress_next_release:
                self._suppress_next_release = False
            elif not self._dragging and not self._is_deleting:
                if self.kind == "IMG":
                    self._image_click_timer.start()
                else:
                    self.paste_requested.emit(self.content)
            self._drag_start_position = None
            self._dragging = False
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.set_hovered(False)
        super().leaveEvent(event)

    def show_context_menu(self, position):
        menu = ChipContextMenu(self, self.theme)
        menu.setWindowFlags(
            menu.windowFlags()
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
        )
        menu.setAttribute(Qt.WA_TranslucentBackground)
        menu_theme = self.theme.get("context_menu", {})

        def make_menu_icon(paths, color):
            icon_size = max(1, int(menu_theme.get("icon_size", 18)))
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{icon_size}" '
                f'height="{icon_size}" viewBox="0 0 24 24">'
                f'<g fill="none" stroke="{color}" stroke-width="{menu_theme.get("icon_stroke_width", 1)}" '
                f'stroke-linecap="round" stroke-linejoin="round">{paths}</g></svg>'
            )
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            pixmap = QPixmap(icon_size, icon_size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)

        normal_icon_color = parse_color(menu_theme.get("icon_color", "rgba(200, 200, 200, 1)")).name()
        destructive_icon_color = menu_theme.get("destructive_icon_color", "#e58a83")
        pin_icon = menu_theme.get("unpin_icon", menu_theme.get("pin_icon", "")) if self.pinned else menu_theme.get("pin_icon", "")

        def add_icon_action(icon, callback):
            action = QWidgetAction(menu)

            item_size = int(menu_theme.get("item_size", 16))
            item_padding = int(menu_theme.get("item_padding", 5))
            item_margin = int(menu_theme.get("item_margin", 2))
            row_size = item_size + 2 * item_padding
            button = QToolButton(menu)
            button.setFixedSize(
                row_size + 2 * item_margin,
                row_size + 2 * item_margin,
            )
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setIcon(icon)
            button.setIconSize(QSize(int(menu_theme.get("icon_size", 18)), int(menu_theme.get("icon_size", 18))))
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(f'''
                QToolButton {{
                    background: transparent;
                    border: none;
                    margin: {item_margin}px;
                    border-radius: {menu_theme.get("item_border_radius", 7)}px;
                }}
                QToolButton:hover, QToolButton:focus {{
                    background-color: {menu_theme.get("hover", "rgba(40, 40, 40, 0.9)")};
                }}
            ''')
            action.setDefaultWidget(button)

            def trigger_action(checked=False):
                self.context_action_triggered.emit()
                callback()
                menu.close()

            action.triggered.connect(trigger_action)
            button.clicked.connect(action.trigger)
            menu.addAction(action)
            return action

        def toggle_pin():
            self.pinned = not self.pinned
            self.apply_style()
            self.pin_requested.emit(self.content)

        pin_action = add_icon_action(make_menu_icon(pin_icon, normal_icon_color), toggle_pin)
        copy_again_action = add_icon_action(
            make_menu_icon(menu_theme.get("copy_icon", ""), normal_icon_color),
            lambda: self.copy_again_requested.emit(self.content),
        )
        delete_action = add_icon_action(
            make_menu_icon(menu_theme.get("delete_icon", ""), destructive_icon_color),
            lambda: self.delete_requested.emit(self.content),
        )
        clear_all_action = add_icon_action(
            make_menu_icon(menu_theme.get("clear_icon", ""), destructive_icon_color),
            lambda: self.clear_all_requested.emit(),
        )

        menu.exec(self.mapToGlobal(position))

    def _start_drag(self):
        drag = QDrag(self)
        include_file_url = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        mime_data = self.create_drag_mime_data(include_file_url=include_file_url)
        drag.setMimeData(mime_data)
        drag.setPixmap(self.grab())
        drag.exec(Qt.CopyAction | Qt.MoveAction)

    def create_drag_mime_data(self, include_file_url=False):
        mime_data = QMimeData()
        mime_data.setData("application/x-copypin-chip", b"1")
        if self.kind == "IMG":
            image = QImage(self.content)
            if not image.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG")
                png_data = bytes(buffer.data())
                buffer.close()

                mime_data.setImageData(image)
                mime_data.setData("image/png", png_data)
                encoded_image = b64encode(png_data).decode("ascii")
                mime_data.setHtml(f'<img src="data:image/png;base64,{encoded_image}">')
                if include_file_url and Path(self.content).exists():
                    image_url = QUrl.fromLocalFile(self.content)
                    mime_data.setUrls([image_url])
                    mime_data.setData("text/uri-list", image_url.toString().encode("utf-8"))
                return mime_data

        mime_data.setText(self.content)
        mime_data.setData("text/plain", self.content.encode("utf-8"))
        mime_data.setData("text/plain;charset=utf-8", self.content.encode("utf-8"))
        mime_data.setHtml(self._html_preview())
        mime_data.setData("text/html", self._html_preview().encode("utf-8"))

        if sys.platform.startswith("win"):
            utf16 = self.content.encode("utf-16le")
            mime_data.setData("Text", utf16)
            mime_data.setData("UnicodeText", utf16)
            mime_data.setData("application/x-qt-windows-mime;value=\"Text\"", utf16)
            mime_data.setData("application/x-qt-windows-mime;value=\"UnicodeText\"", utf16)

        if self.kind == "LINK":
            mime_data.setUrls([QUrl(self.content)])
            mime_data.setData("text/uri-list", self.content.encode("utf-8"))
        elif self.kind == "PATH":
            mime_data.setUrls([QUrl.fromLocalFile(self.content)])
            mime_data.setData("text/uri-list", QUrl.fromLocalFile(self.content).toString().encode("utf-8"))
        elif self.kind == "IMG" and Path(self.content).exists():
            mime_data.setUrls([QUrl.fromLocalFile(self.content)])
            mime_data.setData("text/uri-list", QUrl.fromLocalFile(self.content).toString().encode("utf-8"))

        return mime_data

    def _html_preview(self):
        if self.kind == "LINK":
            return f"<a href=\"{self.content}\">{self.content}</a>"

        lines = self.content.splitlines()
        if len(lines) > 1:
            return "<br>".join([self._escape_html(line) for line in lines])
        return self._escape_html(self.content)

    def _escape_html(self, text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
        )

    def open_link(self, event):
        if event.button() == Qt.LeftButton and self.kind == "LINK":
            QDesktopServices.openUrl(QUrl(self.content))
            event.accept()
            return
        event.ignore()
