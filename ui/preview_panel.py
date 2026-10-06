from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class PreviewPanel(QLabel):
    def __init__(self, theme=None):
        super().__init__()
        self.theme = theme or {"preview": {}}

        self.setText("Hover a chip to preview it")
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setWordWrap(True)
        self.setMinimumHeight(66)
        self.apply_theme()

    def apply_theme(self):
        preview = self.theme.get("preview", {})
        padding = preview.get("padding", [10, 12])
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {preview.get("background", "rgba(255, 255, 255, 0.08)")};
                color: {preview.get("text", "rgba(200, 200, 200, 1)")};
                border: 1px solid {preview.get("border", "rgba(255, 255, 255, 0.12)")};
                border-radius: {preview.get("border_radius", 12)}px;
                padding: {padding[0]}px {padding[1]}px;
                font-size: {preview.get("font_size", 13)}px;
            }}
        """)

    def set_theme(self, theme):
        self.theme = theme
        self.apply_theme()

    def update_preview(self, content):
        if len(content) > 320:
            content = f"{content[:320]}..."
        self.setText(content)
