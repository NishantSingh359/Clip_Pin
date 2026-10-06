import os
from pathlib import Path


# -----------------------------------------------------------------------------
# Application and storage
# -----------------------------------------------------------------------------

APP_NAME = "DockPaste"
APP_STORAGE_NAME = "Copy Pin"  # Preserve the existing user data and settings path.
BASE_DIR = Path(__file__).resolve().parent
APP_STORAGE_DIR = (
    Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or BASE_DIR)
    / APP_STORAGE_NAME
)

THUMBNAILS_DIR = "thumbnails"
THUMBNAIL_RETENTION_DAYS = 30
THUMBNAIL_PURGE_PREFIXES = ("screenshot_", "drop_")
MAX_STORED_IMAGE_DIMENSION = 1800
MAX_STORED_IMAGE_BYTES = 12 * 1024 * 1024
MAX_CLIP_ITEM_SIZE_BYTES = 5 * 1024 * 1024

DB_BUSY_TIMEOUT_MS = 2000
DB_WRITE_RETRIES = 2
DB_RETRY_DELAY_MS = 80
FAVICON_WORKERS = 2
FAVICON_TIMEOUT_SECONDS = 2.5
FAVICON_CACHE_DIR = "favicons"


# -----------------------------------------------------------------------------
# Window and input behavior
# -----------------------------------------------------------------------------

HOVER_TRIGGER_HEIGHT = 1
HOVER_TRIGGER_WIDTH = 100
HIDE_DISTANCE = 30
SHELF_AUTO_HIDE_DELAY = 50
MOUSE_POLL_MS = 33
SHELF_SHOW_ON_HOVER = True
HIDE_ON_PASTE = True
clip_indexing = True


# -----------------------------------------------------------------------------
# Chip behavior
# -----------------------------------------------------------------------------

CHIP_MIN_WIDTH = 70
CHIP_MAX_WIDTH = 350
CHIP_WIDTH_MIN_LIMIT = 70
CHIP_WIDTH_MAX_LIMIT = 500
MAX_CHIPS = 100
MAX_CHIPS_MIN = 50
MAX_CHIPS_MAX = 500
COLOR_PREVIEW_ENABLED = True
CHIP_WIDTH_DEFAULTS_VERSION = 2


# -----------------------------------------------------------------------------
# Shelf behavior
# -----------------------------------------------------------------------------

SHELF_WIDTH_RATIO = 0.7
SHELF_WIDTH_RATIO_MIN = 0.50
SHELF_WIDTH_RATIO_MAX = 0.98
SETTINGS_WINDOW_MIN_WIDTH = 320
