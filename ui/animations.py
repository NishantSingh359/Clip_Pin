from PySide6.QtCore import QPoint, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QBrush, QColor, QLinearGradient
from PySide6.QtWidgets import QGraphicsOpacityEffect

from animation_config import MOTION_ENABLED


class EdgeFadeOpacityEffect(QGraphicsOpacityEffect):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_opacity = 1.0
        self._fade_geometry = None
        super().setOpacity(1.0)

    @Property(float)
    def base_opacity(self):
        return self._base_opacity

    @base_opacity.setter
    def base_opacity(self, opacity):
        self._base_opacity = max(0.0, min(1.0, float(opacity)))
        super().setOpacity(self._base_opacity)

    def set_edge_fade(
        self,
        chip_left,
        viewport_width,
        fade_width,
        fade_left,
        fade_right,
        alpha_stops,
    ):
        geometry = (
            int(chip_left),
            int(viewport_width),
            int(fade_width),
            bool(fade_left),
            bool(fade_right),
            tuple((float(position), float(alpha)) for position, alpha in alpha_stops),
        )
        if geometry == self._fade_geometry:
            return
        self._fade_geometry = geometry

        _, viewport_width, fade_width, fade_left, fade_right, alpha_stops = geometry
        if viewport_width <= 0 or fade_width <= 0:
            self.setOpacityMask(QBrush(QColor(0, 0, 0, 255)))
            return

        gradient = QLinearGradient(-geometry[0], 0, viewport_width - geometry[0], 0)
        stops = {
            0.0: alpha_stops[0][1] if fade_left else 1.0,
            1.0: alpha_stops[0][1] if fade_right else 1.0,
        }
        if fade_left:
            for position, alpha in alpha_stops:
                stops[position * fade_width / viewport_width] = alpha
        if fade_right:
            for position, alpha in alpha_stops:
                stops[1.0 - position * fade_width / viewport_width] = alpha

        for position, alpha in sorted(stops.items()):
            gradient.setColorAt(position, QColor(0, 0, 0, round(alpha * 255)))
        self.setOpacityMask(QBrush(gradient))


def remember_animation(widget, animation):
    if not hasattr(widget, "_active_animations"):
        widget._active_animations = []

    widget._active_animations.append(animation)
    animation.finished.connect(lambda: widget._active_animations.remove(animation))
    return animation


def parse_color(value):
    if isinstance(value, QColor):
        return QColor(value)

    color = QColor(value)
    if color.isValid():
        return color

    if isinstance(value, str) and value.strip().startswith(("rgb(", "rgba(")):
        body = value[value.find("(") + 1:value.rfind(")")]
        parts = [part.strip() for part in body.split(",")]
        if len(parts) in (3, 4):
            red, green, blue = (int(parts[index]) for index in range(3))
            alpha = 255
            if len(parts) == 4:
                raw_alpha = float(parts[3])
                alpha = int(raw_alpha * 255) if raw_alpha <= 1 else int(raw_alpha)
            return QColor(red, green, blue, max(0, min(255, alpha)))

    return QColor(0, 0, 0, 255)


def color_to_rgba(color):
    color = parse_color(color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alphaF():.3f})"


def animate_property(
    widget,
    target,
    prop,
    start,
    end,
    duration,
    easing=QEasingCurve.OutCubic,
    finished=None,
):
    if not MOTION_ENABLED or duration <= 0:
        target.setProperty(prop.decode() if isinstance(prop, bytes) else prop, end)
        if finished:
            finished()
        return None

    animation = QPropertyAnimation(target, prop, widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(easing)
    if finished:
        animation.finished.connect(finished)
    remember_animation(widget, animation)
    animation.start()
    return animation


def fade(widget, start, end, duration, easing=QEasingCurve.OutQuad, finished=None):
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    opacity_property = b"opacity"
    if isinstance(effect, EdgeFadeOpacityEffect):
        effect.base_opacity = start
        opacity_property = b"base_opacity"
    else:
        effect.setOpacity(start)
    return animate_property(widget, effect, opacity_property, start, end, duration, easing, finished)


def expand_and_fade_in(widget, target_width, duration=140):
    target_width = max(widget.minimumWidth(), min(target_width, widget.maximumWidth()))
    widget.resize(target_width, widget.height())
    widget.show()

    if not MOTION_ENABLED:
        return

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)

    opacity_animation = QPropertyAnimation(effect, b"opacity", widget)
    opacity_animation.setDuration(duration)
    opacity_animation.setStartValue(0.0)
    opacity_animation.setEndValue(1.0)
    opacity_animation.setEasingCurve(QEasingCurve.OutQuad)

    def finish_animation():
        widget.setGraphicsEffect(None)

    opacity_animation.finished.connect(finish_animation)
    remember_animation(widget, opacity_animation)
    opacity_animation.start()


def fade_and_collapse(widget, width, duration=140, finished=None):
    if not MOTION_ENABLED:
        if finished:
            finished()
        return

    widget.setMinimumWidth(0)
    widget.setMaximumWidth(width)

    group = QParallelAnimationGroup(widget)

    width_animation = QPropertyAnimation(widget, b"maximumWidth", group)
    width_animation.setDuration(duration)
    width_animation.setStartValue(width)
    width_animation.setEndValue(0)
    width_animation.setEasingCurve(QEasingCurve.InCubic)

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    opacity_animation = QPropertyAnimation(effect, b"opacity", group)
    opacity_animation.setDuration(duration)
    opacity_animation.setStartValue(1.0)
    opacity_animation.setEndValue(0.0)
    opacity_animation.setEasingCurve(QEasingCurve.InQuad)

    group.addAnimation(width_animation)
    group.addAnimation(opacity_animation)
    if finished:
        group.finished.connect(finished)
    remember_animation(widget, group)
    group.start()


def animate_widget_positions(widgets, start_positions, duration):
    if not MOTION_ENABLED or duration <= 0:
        return []

    animations = []
    for widget in widgets:
        start = start_positions.get(widget)
        end = widget.pos()
        if start is None or start == end:
            continue

        animation = QPropertyAnimation(widget, b"pos", widget)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        remember_animation(widget, animation)
        widget.move(start)
        animation.start()
        animations.append(animation)

    return animations
