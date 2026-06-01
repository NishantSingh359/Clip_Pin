from PySide6.QtCore import QPoint, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsOpacityEffect

from config import MOTION_ENABLED


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

    effect.setOpacity(start)
    return animate_property(widget, effect, b"opacity", start, end, duration, easing, finished)


def expand_and_fade_in(widget, target_width, duration=140):
    if not MOTION_ENABLED:
        widget.setMinimumWidth(target_width)
        widget.setMaximumWidth(target_width)
        widget.show()
        return

    widget.hide()
    widget.setMinimumWidth(0)
    widget.setMaximumWidth(0)

    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)

    opacity_animation = QPropertyAnimation(effect, b"opacity", widget)
    opacity_animation.setDuration(duration)
    opacity_animation.setStartValue(0.0)
    opacity_animation.setEndValue(1.0)
    opacity_animation.setEasingCurve(QEasingCurve.OutQuad)

    width_animation = QPropertyAnimation(widget, b"maximumWidth", widget)
    width_animation.setDuration(duration)
    width_animation.setStartValue(0)
    width_animation.setEndValue(target_width)
    width_animation.setEasingCurve(QEasingCurve.OutCubic)

    group = QParallelAnimationGroup(widget)
    group.addAnimation(opacity_animation)
    group.addAnimation(width_animation)

    def finish_animation():
        widget.setGraphicsEffect(None)
        widget.setMinimumWidth(target_width)
        widget.setMaximumWidth(target_width)

    group.finished.connect(finish_animation)
    remember_animation(widget, group)
    widget.show()
    group.start()


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
