import logging
import sys
import tempfile
import traceback
from functools import wraps
from pathlib import Path


LOGGER_NAME = "copypin"


def setup_logging(base_dir):
    log_dir = Path(base_dir) / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path(tempfile.gettempdir()) / "Copy Pin" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "copypin.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)

    def excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error(
            "Unhandled exception\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )

    sys.excepthook = excepthook
    return logger


def get_logger():
    return logging.getLogger(LOGGER_NAME)


def log_exception(message, *args):
    get_logger().exception(message, *args)


def safe_call(message, callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except Exception:
        log_exception(message)
        return None


def safe_slot(message):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                log_exception(message)
                return None

        return wrapper

    return decorator
