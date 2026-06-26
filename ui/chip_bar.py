from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QScrollArea, QSizePolicy

from config import MOTION_ENABLED, CHIP_SCROLL_SPEED, CHIP_SCROLL_DURATION_MS, SCROLL_VIEWPORT_BORDER_RADIUS, CHIP_OVERSCROLL_LIMIT, CHIP_OVERSCROLL_DRAG_MS, CHIP_OVERSCROLL_BOUNCE_MS


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
        self._scroll_value = value
        scrollbar = self.horizontalScrollBar()
        min_val = scrollbar.minimum()
        max_val = scrollbar.maximum()
        
        if value < min_val:
            scrollbar.setValue(min_val)
            if self.widget():
                self.widget().move(min_val - int(value), self.widget().y())
        elif value > max_val:
            scrollbar.setValue(max_val)
            if self.widget():
                self.widget().move(-max_val - int(value - max_val), self.widget().y())
        else:
            scrollbar.setValue(int(value))
            # QScrollArea automatically positions the widget when scrollbar value changes,
            # but since we might have overridden it during overscroll, we ensure it's correct.
            if self.widget():
                self.widget().move(-int(value), self.widget().y())

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
        
        if not MOTION_ENABLED:
            target = max(min_val, min(max_val, raw_target))
            self.scroll_value = target
            event.accept()
            return

        # Determine if we are overscrolling
        if raw_target < min_val or raw_target > max_val:
            # Allow some overscroll distance but cap it
            if raw_target < min_val:
                bounce_target = max(min_val - CHIP_OVERSCROLL_LIMIT, raw_target)
                final_target = min_val
            else:
                bounce_target = min(max_val + CHIP_OVERSCROLL_LIMIT, raw_target)
                final_target = max_val
                
            self._scroll_animation.stop()
            
            # Disconnect previous finished signal if it exists to avoid multiple connections
            if hasattr(self, '_bounce_back_slot') and self._bounce_back_slot is not None:
                try:
                    self._scroll_animation.finished.disconnect(self._bounce_back_slot)
                except Exception:
                    pass
                self._bounce_back_slot = None
                
            self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._scroll_animation.setDuration(CHIP_OVERSCROLL_DRAG_MS)
            self._scroll_animation.setStartValue(self._scroll_value)
            self._scroll_animation.setEndValue(bounce_target)
            
            def bounce_back():
                if hasattr(self, '_bounce_back_slot') and self._bounce_back_slot is not None:
                    try:
                        self._scroll_animation.finished.disconnect(self._bounce_back_slot)
                    except Exception:
                        pass
                    self._bounce_back_slot = None
                self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
                self._scroll_animation.setDuration(CHIP_OVERSCROLL_BOUNCE_MS)
                self._scroll_animation.setStartValue(self.scroll_value)
                self._scroll_animation.setEndValue(final_target)
                self._scroll_animation.start()
                
            self._bounce_back_slot = bounce_back
            self._scroll_animation.finished.connect(self._bounce_back_slot)
            self._scroll_animation.start()
        else:
            if hasattr(self, '_bounce_back_slot') and self._bounce_back_slot is not None:
                try:
                    self._scroll_animation.finished.disconnect(self._bounce_back_slot)
                except Exception:
                    pass
                self._bounce_back_slot = None
                
            self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
            self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)
            self._scroll_animation.stop()
            self._scroll_animation.setStartValue(self._scroll_value)
            self._scroll_animation.setEndValue(raw_target)
            self._scroll_animation.start()

        event.accept()

