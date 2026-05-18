import sys
import ctypes

from PySide6.QtCore import QObject, QTimer


class PasteController(QObject):
    def __init__(self):
        super().__init__()
        self.is_windows = sys.platform.startswith("win")
        self.user32 = ctypes.windll.user32 if self.is_windows else None

    def foreground_window(self):
        if not self.is_windows:
            return None
        return self.user32.GetForegroundWindow()

    def paste_text(self, text, target_window=None):
        if not self.is_windows:
            return

        if target_window:
            self.user32.SetForegroundWindow(target_window)

        QTimer.singleShot(90, self._send_ctrl_v)

    def _send_ctrl_v(self):
        if not self.is_windows:
            return

        ctrl = 0x11
        v_key = 0x56
        key_up = 0x0002

        self.user32.keybd_event(ctrl, 0, 0, 0)
        self.user32.keybd_event(v_key, 0, 0, 0)
        self.user32.keybd_event(v_key, 0, key_up, 0)
        self.user32.keybd_event(ctrl, 0, key_up, 0)
