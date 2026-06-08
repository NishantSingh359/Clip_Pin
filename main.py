import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from config import APP_NAME, APP_STORAGE_DIR
from core.image_store import ImageStore
from utils.app_logging import log_exception, safe_call, setup_logging

setup_logging(APP_STORAGE_DIR)
app = QApplication(sys.argv)
app.setApplicationName(APP_NAME)

safe_call("Failed to purge old thumbnails", ImageStore(APP_STORAGE_DIR).purge_old_thumbnails)

try:
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
except Exception:
    log_exception("Failed to start main window")
    raise


sys.exit(app.exec())
