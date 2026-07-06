from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
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

        self._scroll_value = 0.0
        self._target_scroll_value = 0.0
        self._scroll_animation = QPropertyAnimation(self, b"scroll_value", self)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)

        self._update_viewport_mask()

    @Property(float)
    def scroll_value(self):
        return self._scroll_value

    @scroll_value.setter
    def scroll_value(self, value):
        scrollbar = self.horizontalScrollBar()
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        clamped_value = max(min_val, min(max_val, int(value)))
        self._scroll_value = clamped_value
        scrollbar.setValue(clamped_value)

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
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        
        # Calculate raw target without bounds
        # If currently animating, accumulate from the target to preserve momentum
        from PySide6.QtCore import QAbstractAnimation
        if self._scroll_animation.state() == QAbstractAnimation.Running:
            base_value = self._target_scroll_value
        else:
            base_value = self._scroll_value
            
        raw_target = base_value - (delta * CHIP_SCROLL_SPEED)
        self._target_scroll_value = raw_target
        
        target = max(min_val, min(max_val, raw_target))
        self._target_scroll_value = target

        if not MOTION_ENABLED:
            self.scroll_value = target
            event.accept()
            return

        current_scroll = scrollbar.value()
        if hasattr(self, '_bounce_back_slot') and self._bounce_back_slot is not None:
            try:
                self._scroll_animation.finished.disconnect(self._bounce_back_slot)
            except Exception:
                pass
            self._bounce_back_slot = None

        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(current_scroll)
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.start()

        event.accept()

