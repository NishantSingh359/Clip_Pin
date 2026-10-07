import math

from PySide6.QtCore import Qt, QEvent, QPoint, QPropertyAnimation, QEasingCurve, Property, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtGui import QPainterPath, QRegion
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QWidget

from animation_config import MOTION_ENABLED, CHIP_SCROLL_SPEED, CHIP_SCROLL_DURATION_MS
from ui.animations import EdgeFadeOpacityEffect


DEFAULT_EDGE_FADE = {
    "enabled": True,
    "width": 40,
    "alpha_stops": [[0.0, 0.0], [0.35, 0.2], [0.7, 0.7], [1.0, 1.0]],
}


class ChipBar(QScrollArea):
    def __init__(self, theme=None):
        super().__init__()
        self.theme = theme or {"scroll_viewport": {"border_radius": 40}}

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self._apply_theme()

        self._scroll_value = 0.0
        self._target_scroll_value = 0.0
        self._scroll_animation = QPropertyAnimation(self, b"scroll_value", self)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)
        self.horizontalScrollBar().valueChanged.connect(self._refresh_chip_hover)
        self.horizontalScrollBar().rangeChanged.connect(self._refresh_chip_hover)
        self._scroll_animation.finished.connect(self._refresh_chip_hover)
        self._edge_fade_update_pending = False

        self._update_viewport_mask()

    def set_theme(self, theme):
        self.theme = theme or {}
        self._apply_theme()
        self._update_viewport_mask()
        self.refresh_edge_fades()

    def _apply_theme(self):
        viewport_theme = self.theme.get("scroll_viewport", {})
        radius = int(viewport_theme.get("border_radius", 40))
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; border-radius: "
            + str(radius) + "px; }"
            "QScrollArea::viewport { background: transparent; border: none; border-radius: "
            + str(radius) + "px; }"
            "QScrollBar { background: transparent; }"
        )
        self.viewport().setStyleSheet(
            "background: transparent;"
            "border: none;"
            "border-radius: " + str(radius) + "px;"
        )
        self._load_edge_fade_settings(viewport_theme.get("edge_fade", {}))

    def _load_edge_fade_settings(self, settings):
        self._edge_fade_enabled = settings.get("enabled", DEFAULT_EDGE_FADE["enabled"])
        if not isinstance(self._edge_fade_enabled, bool):
            raise ValueError("scroll_viewport.edge_fade.enabled must be a boolean")

        width = settings.get("width", DEFAULT_EDGE_FADE["width"])
        if isinstance(width, bool) or not isinstance(width, int) or width < 0:
            raise ValueError("scroll_viewport.edge_fade.width must be a non-negative integer")
        self._edge_fade_width = width

        raw_stops = settings.get("alpha_stops", DEFAULT_EDGE_FADE["alpha_stops"])
        if not isinstance(raw_stops, list) or len(raw_stops) < 2:
            raise ValueError(
                "scroll_viewport.edge_fade.alpha_stops must contain at least "
                "two [position, alpha] pairs"
            )

        stops = []
        for stop in raw_stops:
            if not isinstance(stop, list) or len(stop) != 2:
                raise ValueError("Each edge-fade alpha stop must be a [position, alpha] pair")
            position, alpha = stop
            if (
                isinstance(position, bool)
                or isinstance(alpha, bool)
                or not isinstance(position, (int, float))
                or not isinstance(alpha, (int, float))
                or not math.isfinite(position)
                or not math.isfinite(alpha)
                or not 0.0 <= position <= 1.0
                or not 0.0 <= alpha <= 1.0
            ):
                raise ValueError("Edge-fade positions and alpha values must be between 0 and 1")
            if stops and position <= stops[-1][0]:
                raise ValueError("Edge-fade alpha-stop positions must be strictly increasing")
            stops.append((float(position), float(alpha)))

        if stops[0][0] != 0.0 or stops[-1][0] != 1.0:
            raise ValueError("Edge-fade alpha stops must start at position 0 and end at position 1")
        self._edge_fade_alpha_stops = tuple(stops)

    def setWidget(self, widget):
        super().setWidget(widget)
        widget.installEventFilter(self)
        self._schedule_edge_fade_update()

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
        self.refresh_edge_fades()

    def eventFilter(self, watched, event):
        if watched is self.widget() and event.type() == QEvent.ChildAdded:
            self._schedule_edge_fade_update()
        elif event.type() in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide):
            self._schedule_edge_fade_update()
        return super().eventFilter(watched, event)

    def _schedule_edge_fade_update(self):
        if self._edge_fade_update_pending:
            return
        self._edge_fade_update_pending = True
        QTimer.singleShot(0, self._run_scheduled_edge_fade_update)

    def _run_scheduled_edge_fade_update(self):
        self._edge_fade_update_pending = False
        self.refresh_edge_fades()

    def refresh_edge_fades(self):
        content_widget = self.widget()
        if content_widget is None:
            return

        viewport_width = self.viewport().width()
        scrollbar = self.horizontalScrollBar()
        scroll_value = scrollbar.value()
        fade_width = min(self._edge_fade_width, viewport_width // 2)
        fade_left = self._edge_fade_enabled and scroll_value > scrollbar.minimum()
        fade_right = self._edge_fade_enabled and scroll_value < scrollbar.maximum()
        if not self._edge_fade_enabled:
            fade_width = 0
        for chip in content_widget.findChildren(QWidget):
            if not callable(getattr(chip, "set_hovered", None)):
                continue

            effect = chip.graphicsEffect()
            if not isinstance(effect, EdgeFadeOpacityEffect):
                effect = EdgeFadeOpacityEffect(chip)
                chip.setGraphicsEffect(effect)

            chip_left = chip.mapTo(self.viewport(), QPoint(0, 0)).x()
            effect.set_edge_fade(
                chip_left,
                viewport_width,
                fade_width,
                fade_left,
                fade_right,
                self._edge_fade_alpha_stops,
            )
            chip.installEventFilter(self)

    def _update_viewport_mask(self):
        viewport = self.viewport()
        if viewport is None:
            return

        rect = viewport.rect()
        radius = int(self.theme.get("scroll_viewport", {}).get("border_radius", 40))
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        viewport.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _refresh_chip_hover(self):
        content_widget = self.widget()
        if content_widget is None:
            return

        self.refresh_edge_fades()
        cursor_position = QCursor.pos()
        viewport_position = self.viewport().mapFromGlobal(cursor_position)
        cursor_in_viewport = self.viewport().rect().contains(viewport_position)
        self._apply_chip_hover(
            content_widget.findChildren(QWidget),
            cursor_position,
            cursor_in_viewport,
        )

    def _apply_chip_hover(self, chips, cursor_position, cursor_in_viewport):
        for chip in chips:
            if not hasattr(chip, "set_hovered"):
                continue
            is_hovered = (
                cursor_in_viewport
                and chip.isVisible()
                and chip.rect().contains(chip.mapFromGlobal(cursor_position))
            )
            chip.set_hovered(is_hovered)


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
