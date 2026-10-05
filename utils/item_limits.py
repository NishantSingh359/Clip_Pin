from pathlib import Path

from config import MAX_CLIP_ITEM_SIZE_BYTES


def is_oversized_file(path):
    try:
        candidate = Path(path)
        return candidate.is_file() and candidate.stat().st_size > MAX_CLIP_ITEM_SIZE_BYTES
    except OSError:
        return False


def is_oversized_text(text):
    return len(str(text).encode("utf-8")) > MAX_CLIP_ITEM_SIZE_BYTES
