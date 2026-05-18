from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from config import (
    PREVIEW_BACKGROUND_COLOR,
    PREVIEW_BORDER_COLOR,
    PREVIEW_BORDER_RADIUS,
    PREVIEW_PADDING,
    PREVIEW_TEXT_COLOR,
)


class PreviewPanel(QLabel):
    def __init__(self):
        super().__init__()

        self.setText("Hover a chip to preview it")
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setWordWrap(True)
        self.setMinimumHeight(66)

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {PREVIEW_BACKGROUND_COLOR};
                color: {PREVIEW_TEXT_COLOR};
                border: 1px solid {PREVIEW_BORDER_COLOR};
                border-radius: {PREVIEW_BORDER_RADIUS}px;
                padding: {PREVIEW_PADDING[0]}px {PREVIEW_PADDING[1]}px;
                font-size: 13px;
            }}
        """)

    def update_preview(self, content):
        if len(content) > 320:
            content = f"{content[:320]}..."
        self.setText(content)
