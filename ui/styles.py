import ctypes
import sys
from PySide6.QtGui import QColor

def apply_acrylic(window):
    """Applies Windows acrylic theme to the window."""
    if sys.platform != "win32":
        return

    # Force native window handle creation
    hwnd = int(window.winId())

    # 1. Enable Immersive Dark Mode and set Rounded Corners preference first
    try:
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_mode = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,
            ctypes.byref(dark_mode),
            ctypes.sizeof(dark_mode)
        )
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33
        # DWMWCP_ROUND = 2 (standard round corners)
        corner_preference = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            33,
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference)
        )
    except Exception as e:
        print(f"Failed to set immersive dark mode or corner preference: {e}")

    # 2. Try Windows 11 Acrylic Backdrop (DWMWA_SYSTEMBACKDROP_TYPE = 38)
    # Supported on Windows 11 Build 22621+
    try:
        dwmapi = ctypes.windll.dwmapi
        backdrop_type = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW (Acrylic)
        res = dwmapi.DwmSetWindowAttribute(
            hwnd,
            38,
            ctypes.byref(backdrop_type),
            ctypes.sizeof(backdrop_type)
        )
        if res == 0:
            return  # Successfully applied Windows 11 system backdrop!
    except Exception:
        pass

    # 3. Fallback to SetWindowCompositionAttribute (Windows 10 / earlier Windows 11)
    try:
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_int),
                ("AnimationId", ctypes.c_int),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        # ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        # We use a dark background color in AABBGGRR format:
        # e.g., Alpha=0x90 (144/255 opacity), Blue=0x18, Green=0x18, Red=0x18
        # Value = 0x90181818
        accent = ACCENTPOLICY()
        accent.AccentState = 3  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 2
        #accent.GradientColor = 0x00000000

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except Exception as e:
        print(f"Failed to apply acrylic blur fallback: {e}")
