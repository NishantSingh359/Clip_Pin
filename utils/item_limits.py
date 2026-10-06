import os
from pathlib import Path

from config import MAX_CLIP_ITEM_SIZE_BYTES


def is_oversized_file(path):
    """Check a file or a folder's combined file size against the clipboard limit."""
    try:
        candidate = Path(path)
        if candidate.is_file():
            return candidate.stat().st_size > MAX_CLIP_ITEM_SIZE_BYTES
        if not candidate.is_dir():
            return False

        total_size = 0
        pending = [candidate]
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                total_size += entry.stat(follow_symlinks=False).st_size
                                if total_size > MAX_CLIP_ITEM_SIZE_BYTES:
                                    return True
                            elif entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                        except OSError:
                            continue
            except OSError:
                continue
        return False
    except OSError:
        return False


def is_oversized_text(text):
    return len(str(text).encode("utf-8")) > MAX_CLIP_ITEM_SIZE_BYTES
