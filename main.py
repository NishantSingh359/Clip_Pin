import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from config import APP_NAME, APP_STORAGE_DIR
from core.image_store import ImageStore

app = QApplication(sys.argv)
app.setApplicationName(APP_NAME)

ImageStore(APP_STORAGE_DIR).purge_old_thumbnails()

window = MainWindow()
window.show()


sys.exit(app.exec())
