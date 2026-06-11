from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QScrollArea, QSizePolicy

from config import MOTION_ENABLED, CHIP_SCROLL_SPEED, CHIP_SCROLL_DURATION_MS, SCROLL_VIEWPORT_BORDER_RADIUS


class ChipBar(QScrollArea):
    def __init__(self):
        super().__init__()

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        radius = str(SCROLL_VIEWPORT_BORDER_RADIUS)
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; border-radius: "
            + radius + "px; }"
            "QScrollArea::viewport { background: transparent; border: none; border-radius: "
            + radius + "px; }"
            "QScrollBar { background: transparent; }"
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.viewport().setStyleSheet(
            "background: transparent;"
            "border: none;"
            "border-radius: " + radius + "px;"
        )

        self._scroll_animation = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)

        self._update_viewport_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_viewport_mask()

    def _update_viewport_mask(self):
        viewport = self.viewport()
        if viewport is None:
            return

        rect = viewport.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, SCROLL_VIEWPORT_BORDER_RADIUS, SCROLL_VIEWPORT_BORDER_RADIUS)
        viewport.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            return

        scrollbar = self.horizontalScrollBar()
        target = scrollbar.value() - int(delta * CHIP_SCROLL_SPEED)
        target = max(scrollbar.minimum(), min(scrollbar.maximum(), target))

        if not MOTION_ENABLED:
            scrollbar.setValue(target)
            event.accept()
            return

        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(scrollbar.value())
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.start()

        event.accept()

