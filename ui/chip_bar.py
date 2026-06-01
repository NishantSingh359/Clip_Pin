from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QScrollArea, QSizePolicy

from config import MOTION_ENABLED, CHIP_SCROLL_SPEED, CHIP_SCROLL_DURATION_MS


class ChipBar(QScrollArea):
    def __init__(self):
        super().__init__()

        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar { background: transparent; }"
        )

        self._scroll_animation = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(CHIP_SCROLL_DURATION_MS)

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

