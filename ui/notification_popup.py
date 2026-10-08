from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class OversizedItemPopup(QWidget):
    """A non-modal, theme-colored notice for clipboard items above the size limit."""

    def __init__(self):
        super().__init__(
            None,
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("oversizedItemCard")
        outer_layout.addWidget(self.card)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 12, 16, 12)
        card_layout.setSpacing(12)

        self.accent = QWidget(self.card)
        self.accent.setFixedWidth(4)
        card_layout.addWidget(self.accent)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        self.title = QLabel("Item exceeds 5 MB", self.card)
        self.title.setObjectName("oversizedItemTitle")
        self.message = QLabel(
            "Large files, folders, images, and text are skipped.", self.card
        )
        self.message.setObjectName("oversizedItemMessage")
        self.message.setWordWrap(True)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.message)
        card_layout.addLayout(text_layout, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_notice(self, theme):
        notification = theme.get("notification", {})
        background = notification.get("background", "#282a2e")
        text = notification.get("text", "#f1f1f1")
        muted_text = notification.get("muted_text", text)
        border = notification.get("border", "rgba(255, 255, 255, 0.14)")
        accent = notification.get("accent", "#d7df78")
        radius = int(notification.get("border_radius", 12))
        padding = notification.get("padding", [12, 16])
        width = int(notification.get("width", 360))

        self.card.setStyleSheet(f"""
            QFrame#oversizedItemCard {{
                background: {background};
                color: {text};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
            QLabel#oversizedItemTitle {{
                color: {text};
                font-size: 14px;
                font-weight: 600;
                border: none;
            }}
            QLabel#oversizedItemMessage {{
                color: {muted_text};
                font-size: 12px;
                border: none;
            }}
        """)
        self.accent.setStyleSheet(f"background: {accent}; border: none; border-radius: 2px;")
        layout = self.card.layout()
        layout.setContentsMargins(padding[1], padding[0], padding[1], padding[0])
        self.setFixedWidth(width)
        self.adjustSize()

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.move(
                QPoint(
                    available.right() - self.width() - 20,
                    available.bottom() - self.height() - 20,
                )
            )

        self.show()
        self.raise_()
        self._timer.start(max(1000, int(notification.get("duration_ms", 4500))))
