import os
import re
import threading
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from PySide6.QtCore import Property, Qt, QUrl, Signal, QPoint, QSize
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QHBoxLayout, QMenu, QWidget, QSizePolicy

from config import (
    CHIP_BORDER_RADIUS,
    CHIP_BORDER_WIDTH,
    CHIP_BORDER_COLOR,
    CHIP_DEFAULT_BACKGROUND,
    CHIP_HOVER_BACKGROUND,
    CHIP_PINNED_BACKGROUND,
    CHIP_PADDING,
    CHIP_PRESSED_BACKGROUND,
    CHIP_SPACING,
    CHIP_TEXT_COLOR,
    CHIP_MAX_WIDTH,
    CHIP_MIN_WIDTH,
    CHIP_HEIGHT,
    CONTEXT_MENU_BACKGROUND_COLOR,
    CONTEXT_MENU_TEXT_COLOR,
    CONTEXT_MENU_BORDER_COLOR,
    CONTEXT_MENU_HOVER_COLOR,
    CONTEXT_MENU_BORDER_RADIUS,
    CONTEXT_MENU_ITEM_PADDING,
    OPEN_ICON_PATH,
    FOLDER_ICON_PATH,
    OPEN_ICON_SIZE,
    FOLDER_ICON_SIZE,
    OPEN_ICON_COLOR,
    FOLDER_ICON_COLOR,
    THUMBNAIL_BORDER_RADIUS,
    MOTION_BASE_MS,
    MOTION_FAST_MS,
    MOTION_HOVER_MS,
)
from ui.animations import (
    color_to_rgba,
    parse_color,
)


class ChipWidget(QWidget):
    paste_requested = Signal(str)
    delete_requested = Signal(str)
    pin_requested = Signal(str)
    clear_all_requested = Signal()
    favicon_loaded = Signal(bytes)

    def __init__(self, content):
        super().__init__()

        self.content = content
        self.kind = self.detect_kind()
        self.pinned = False
        self.network = None
        self._favicon_thread = None
        self._favicon_urls = []
        self._favicon_index = 0
        self._destroyed = False
        self._background_color = parse_color(CHIP_DEFAULT_BACKGROUND)
        self._is_hovered = False
        self._is_deleting = False
        self.setObjectName("chip")

        self.setFixedHeight(CHIP_HEIGHT)
        self.setMinimumWidth(CHIP_MIN_WIDTH)
        self.setMaximumWidth(CHIP_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self._base_width = CHIP_MIN_WIDTH
        self._base_height = CHIP_HEIGHT

        self.setup_ui()
        self.apply_style()
        self.update_label()
        self.destroyed.connect(self.mark_destroyed)
        self.favicon_loaded.connect(self.on_favicon_data_loaded)

        if self.kind == "LINK":
            self.load_favicon()

    def get_background_color(self):
        return self._background_color

    def mark_destroyed(self):
        self._destroyed = True

    def set_background_color(self, color):
        self._background_color = parse_color(color)
        self.apply_style()

    backgroundColor = Property(QColor, get_background_color, set_background_color)

    def setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(*CHIP_PADDING)
        self.layout.setSpacing(CHIP_SPACING)

        self.icon = QLabel()
        self.icon.setFixedSize(18, 18)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"""
            QLabel {{
                color: {CHIP_TEXT_COLOR};
                font-size: 11px;
                font-weight: 800;
            }}
        """)

        self.title = QLabel()
        self.title.setAlignment(Qt.AlignVCenter)
        self.title.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {CHIP_TEXT_COLOR};
                font-size: 13px;
                font-weight: 600;
            }}
        """)

        self.open_icon = QLabel()
        self.open_icon.setFixedSize(OPEN_ICON_SIZE, OPEN_ICON_SIZE)
        self.open_icon.setAlignment(Qt.AlignCenter)
        self.open_icon.setCursor(Qt.PointingHandCursor)
        self.open_icon.setPixmap(self.load_open_icon_pixmap())
        self.open_icon.mousePressEvent = self.open_link
        self.open_icon.setVisible(self.kind == "LINK")

        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.open_icon)

    def apply_style(self):
        self.setStyleSheet(f"""
            #chip {{
                background-color: {color_to_rgba(self._background_color)};
                border: {CHIP_BORDER_WIDTH}px solid {CHIP_BORDER_COLOR};
                border-radius: {CHIP_BORDER_RADIUS}px;
            }}
        """)

    def state_background(self):
        if self.pinned:
            return parse_color(CHIP_PINNED_BACKGROUND)
        if self._is_hovered:
            return parse_color(CHIP_HOVER_BACKGROUND)
        return parse_color(CHIP_DEFAULT_BACKGROUND)

    def animate_background_to(self, color, duration=MOTION_HOVER_MS):
        # Animations removed: immediately apply background color
        self._background_color = parse_color(color)
        self.apply_style()

    def animate_entry(self, duration=MOTION_BASE_MS):
        # Animations removed: immediately set to base width and show
        self.setMinimumWidth(self._base_width)
        self.setMaximumWidth(self._base_width)
        self.show()

    def animate_delete(self, finished=None):
        # Animations removed: immediately call finished (or delete)
        if self._is_deleting:
            return
        self._is_deleting = True
        if finished:
            finished()
        else:
            self.deleteLater()

    def animate_press(self):
        self.animate_background_to(CHIP_PRESSED_BACKGROUND, MOTION_FAST_MS)

    def detect_kind(self):
        content = self.content.strip()

        if content.startswith(("http://", "https://")):
            return "LINK"

        if content.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return "IMG"

        if os.path.exists(content):
            return "PATH"

        return "TEXT"

    def update_label(self):
        text = self.display_text()
        metrics = QFontMetrics(self.title.font())
        title_width = CHIP_MAX_WIDTH - 68 if self.kind == "LINK" else CHIP_MAX_WIDTH - 42
        self.title.setText(metrics.elidedText(text, Qt.ElideRight, title_width))

        if self.kind == "IMG":
            self.icon.show()
            self.set_image_thumb()
            self.title.setText("Screenshot")
            return

        if self.kind == "LINK":
            self.icon.show()
            self.icon.setText("")
            self.icon.setPixmap(self.logo_fallback_pixmap())
        elif self.kind == "PATH":
            self.icon.show()
            self.icon.setFixedSize(FOLDER_ICON_SIZE, FOLDER_ICON_SIZE)
            self.icon.setPixmap(self.load_folder_icon_pixmap())
        else:
            self.icon.hide()

        self.adjustSize()
        width = max(CHIP_MIN_WIDTH, min(self.sizeHint().width(), CHIP_MAX_WIDTH))
        self._base_width = width
        self.setFixedWidth(width)
        self.setFixedHeight(self._base_height)

    def display_text(self):
        content = self.content.strip()
        if self.kind == "LINK":
            domain = urlparse(content).netloc
            return domain.removeprefix("www.") or content

        if self.kind == "IMG":
            return "Screenshot"

        if self.kind == "PATH":
            return os.path.basename(content.rstrip("\\/")) or content

        return content.replace("\n", " ")

    def set_image_thumb(self):
        pixmap = QPixmap(self.content)
        if pixmap.isNull():
            self.icon.setText("I")
            return

        thumb_size = QSize(26, 22)
        scaled = pixmap.scaled(thumb_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        rounded = QPixmap(thumb_size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, thumb_size.width(), thumb_size.height(), THUMBNAIL_BORDER_RADIUS, THUMBNAIL_BORDER_RADIUS)
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
        domain = urlparse(self.content).netloc
        if not domain:
            return

        self._favicon_thread = threading.Thread(
            target=self.fetch_favicon_bytes,
            args=(self.content, domain),
            daemon=True,
        )
        self._favicon_thread.start()

    def fetch_favicon_bytes(self, url, domain):
        for favicon_url in self.favicon_candidates(url, domain):
            if self._destroyed:
                return
            data = self.download_favicon(favicon_url)
            if data:
                if self._destroyed:
                    return
                try:
                    self.favicon_loaded.emit(data)
                except RuntimeError:
                    return
                return

    def favicon_candidates(self, url, domain):
        quoted_url = quote(url, safe="")
        candidates = [
            f"https://www.google.com/s2/favicons?domain_url={quoted_url}&sz=64",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=64",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
            f"https://{domain}/favicon.ico",
            f"http://{domain}/favicon.ico",
        ]

        page_icons = self.discover_page_icons(f"https://{domain}")
        if not page_icons:
            page_icons = self.discover_page_icons(f"http://{domain}")

        return page_icons + candidates

    def discover_page_icons(self, page_url):
        try:
            request = Request(
                page_url,
                headers={"User-Agent": "Mozilla/5.0 CopyPin/1.0"},
            )
            with urlopen(request, timeout=4) as response:
                html = response.read(180_000).decode("utf-8", errors="ignore")
        except Exception:
            return []

        icon_urls = []
        for match in re.finditer(r"<link\b[^>]*>", html, flags=re.IGNORECASE):
            tag = match.group(0)
            rel = re.search(r"""rel=["']?([^"'>\s]+)["']?""", tag, flags=re.IGNORECASE)
            href = re.search(r"""href=["']?([^"'>\s]+)["']?""", tag, flags=re.IGNORECASE)
            if not rel or not href:
                continue
            if "icon" not in rel.group(1).lower():
                continue
            icon_urls.append(urljoin(page_url, href.group(1)))

        return icon_urls[:4]

    def download_favicon(self, favicon_url):
        try:
            request = Request(
                favicon_url,
                headers={"User-Agent": "Mozilla/5.0 CopyPin/1.0"},
            )
            with urlopen(request, timeout=5) as response:
                content_type = response.headers.get("content-type", "").lower()
                data = response.read(300_000)
        except Exception:
            return None

        looks_like_image = (
            "image/" in content_type
            or favicon_url.lower().split("?")[0].endswith((".ico", ".png", ".jpg", ".jpeg", ".webp", ".gif"))
        )
        if len(data) > 64 and looks_like_image:
            return data
        return None

    def on_favicon_data_loaded(self, data):
        if self._destroyed:
            return

        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            self.icon.setText("")
            self.icon.setPixmap(
                pixmap.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def external_link_icon(self, color):
        size = OPEN_ICON_SIZE if 'OPEN_ICON_SIZE' in globals() else 20
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
        pix = self._load_icon_pixmap(OPEN_ICON_PATH, OPEN_ICON_SIZE, self.parse_css_color(OPEN_ICON_COLOR))
        if not pix.isNull():
            return pix
        return self.external_link_icon(self.parse_css_color(OPEN_ICON_COLOR))

    def load_folder_icon_pixmap(self):
        pix = self._load_icon_pixmap(FOLDER_ICON_PATH, FOLDER_ICON_SIZE, self.parse_css_color(FOLDER_ICON_COLOR))
        if not pix.isNull():
            return pix

        # draw a simple folder glyph
        size = FOLDER_ICON_SIZE
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.animate_press()
            self.paste_requested.emit(self.content)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_deleting:
            self.animate_background_to(self.state_background(), MOTION_FAST_MS)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._is_hovered = True
        if not self._is_deleting:
            self.animate_background_to(self.state_background(), MOTION_HOVER_MS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if not self._is_deleting:
            self.animate_background_to(self.state_background(), MOTION_HOVER_MS)
        super().leaveEvent(event)

    def show_context_menu(self, position):
        menu = QMenu(self)
        pin_label = "unpin" if self.pinned else "pin"
        pin_action = QAction(pin_label, self)
        delete_action = QAction("delete", self)
        clear_all_action = QAction("clear all", self)

        menu.addAction(pin_action)
        menu.addAction(delete_action)
        menu.addAction(clear_all_action)

        menu.setStyleSheet(f'''
            QMenu {{
                background-color: {CONTEXT_MENU_BACKGROUND_COLOR};
                color: {CONTEXT_MENU_TEXT_COLOR};
                border: 1px solid {CONTEXT_MENU_BORDER_COLOR};
                border-radius: {CONTEXT_MENU_BORDER_RADIUS}px;
                padding: {CONTEXT_MENU_ITEM_PADDING[0]}px {CONTEXT_MENU_ITEM_PADDING[1]}px;
            }}
            QMenu::item {{
                padding: {CONTEXT_MENU_ITEM_PADDING[0]}px {CONTEXT_MENU_ITEM_PADDING[1]}px;
            }}
            QMenu::item:selected {{
                background-color: {CONTEXT_MENU_HOVER_COLOR};
            }}
        ''')

        action = menu.exec(self.mapToGlobal(position))

        if action == pin_action:
            self.pinned = not self.pinned
            self.animate_background_to(self.state_background(), MOTION_BASE_MS)
            self.pin_requested.emit(self.content)
        elif action == delete_action:
            self.delete_requested.emit(self.content)
        elif action == clear_all_action:
            self.clear_all_requested.emit()

    def open_link(self, event):
        if event.button() == Qt.LeftButton and self.kind == "LINK":
            QDesktopServices.openUrl(QUrl(self.content))
            event.accept()
            return
        event.ignore()
