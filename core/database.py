"""
Clipboard history database module.
Manages persistence of clipboard items with SQLite.

Schema:
    id      - INTEGER PRIMARY KEY AUTOINCREMENT (unique, not null)
    type    - TEXT: 'link', 'text', 'path', or 'img'
    content - TEXT: the copied text, link, path, or img file path
"""


import os
import re
import sqlite3
from pathlib import Path


DB_DIR = "data"
DB_NAME = "clips.db"
APP_DATA_DIR = "Copy Pin"


def get_db_path(base_dir=None):
    """Get the full path to the database file."""
    if base_dir:
        base = Path(base_dir)
    else:
        base = Path(__file__).resolve().parent.parent

    db_dir = base / DB_DIR
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / DB_NAME)


def get_user_db_path():
    """Get a writable per-user database path for packaged/renamed installs."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    else:
        root = os.environ.get("XDG_DATA_HOME")

    base = Path(root) if root else Path.home() / ".local" / "share"
    db_dir = base / APP_DATA_DIR / DB_DIR
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / DB_NAME)


def detect_type(content: str) -> str:

    """
    Detect the type of clipboard content.

    Returns:
        'link'  - if content looks like a URL (http/https/ftp)
        'path'  - if content looks like a file/folder path
        'img'   - if content looks like an existing image file path
        'text'  - otherwise

    """
    content = content.strip()

    # URL detection
    url_pattern = re.compile(
        r'^(https?://|ftp://|www\.)[^\s]+$',
        re.IGNORECASE
    )
    if url_pattern.match(content):
        return "link"

    # Path detection (Windows paths)
    path_pattern = re.compile(
        r'^[a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*$'
    )
    if path_pattern.match(content):
        return "path"

    # Path detection (Unix-like paths)
    unix_path_pattern = re.compile(r'^/(?:[^/\0]+/)*[^/\0]*$')
    if unix_path_pattern.match(content):
        return "path"

    # Network share paths
    net_path_pattern = re.compile(r'^\\\\[^\\]+\\[^\\]+')
    if net_path_pattern.match(content):
        return "path"

    # Image path detection
    img_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    if any(content.lower().endswith(suf) for suf in img_suffixes):
        p = Path(content)
        if p.exists() and p.is_file():
            return "img"


    return "text"



class ClipboardDatabase:
    """Database handler for clipboard history."""

    def __init__(self, base_dir=None):
        try:
            self.db_path = get_db_path(base_dir)
            self._init_db()
        except (OSError, sqlite3.OperationalError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and "unable to open database file" not in str(exc).lower():
                raise
            self.db_path = get_user_db_path()
            self._init_db()

    def _get_connection(self):
        """Create and return a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    type    TEXT    NOT NULL,
                    content TEXT    NOT NULL UNIQUE,

                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_clips_type ON clips(type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_clips_created_at ON clips(created_at DESC)
            """)
            conn.commit()
        finally:
            conn.close()

    def insert(self, content: str) -> int | None:
        """
        Insert a clipboard item. Automatically detects type.

        Args:
            content: The clipboard content string.

        Returns:
            The row id of the inserted record, or None if it already exists.
        """
        clip_type = detect_type(content)
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO clips (type, content) VALUES (?, ?)",
                (clip_type, content)
            )
            conn.commit()
            # cursor.rowcount is 0 when INSERT OR IGNORE skips a duplicate
            return cursor.lastrowid if cursor.rowcount > 0 else None
        finally:
            conn.close()

    def insert_with_type(self, content: str, clip_type: str) -> int | None:
        """
        Insert a clipboard item with an explicit type.

        Args:
            content: The clipboard content string.
            clip_type: One of 'link', 'text', 'path'.

        Returns:
            The row id of the inserted record, or None if it already exists.
        """
        if clip_type not in ("link", "text", "path", "img"):
            raise ValueError(
                f"Invalid type '{clip_type}'. Must be 'link', 'text', 'path', or 'img'."
            )



        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO clips (type, content) VALUES (?, ?)",
                (clip_type, content)
            )
            conn.commit()
            # cursor.rowcount is 0 when INSERT OR IGNORE skips a duplicate
            return cursor.lastrowid if cursor.rowcount > 0 else None
        finally:
            conn.close()

    def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Retrieve clipboard history ordered by most recent first.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of dicts with keys: id, type, content, created_at.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, type, content, created_at FROM clips ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_by_type(self, clip_type: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """
        Retrieve clipboard history filtered by type.

        Args:
            clip_type: One of 'link', 'text', 'path'.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of dicts with keys: id, type, content, created_at.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, type, content, created_at FROM clips WHERE type = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (clip_type, limit, offset)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_by_id(self, record_id: int) -> dict | None:
        """
        Retrieve a single clipboard record by its id.

        Args:
            record_id: The id of the record.

        Returns:
            Dict with keys: id, type, content, created_at, or None if not found.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT id, type, content, created_at FROM clips WHERE id = ?",
                (record_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """
        Search clipboard history by content.

        Args:
            query: Search term to match against content.
            limit: Maximum number of records to return.

        Returns:
            List of dicts with keys: id, type, content, created_at.
        """

        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, type, content, created_at FROM clips WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count(self) -> int:
        """Get the total number of clipboard records."""
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) as total FROM clips").fetchone()
            return row["total"]
        finally:
            conn.close()

    def delete(self, record_id: int) -> bool:
        """
        Delete a clipboard record by id.

        Args:
            record_id: The id of the record to delete.

        Returns:
            True if a record was deleted, False otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM clips WHERE id = ?", (record_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_by_content(self, content: str) -> bool:
        """
        Delete a clipboard record by its content.

        Args:
            content: The content to match and delete.

        Returns:
            True if a record was deleted, False otherwise.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM clips WHERE content = ?", (content,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def purge_old_records(self, retention_days: int = 30) -> int:
        """
        Delete clipboard records older than the specified number of days.
        
        Uses the created_at timestamp to determine age. Records whose
        creation date is older than 'retention_days' days are removed.
        
        Args:
            retention_days: Maximum age of records in days (default: 30).
        
        Returns:
            Number of deleted records.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM clips WHERE created_at < datetime('now', 'localtime', ?)",
                (f"-{retention_days} days",)
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def clear(self) -> int:
        """
        Delete all clipboard records.
        
        Returns:
            Number of deleted records.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM clips")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """
        Get statistics about the clipboard history.

        Returns:
            Dict with keys: total, links, texts, paths, imgs.
        """

        conn = self._get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM clips").fetchone()["c"]
            links = conn.execute("SELECT COUNT(*) as c FROM clips WHERE type='link'").fetchone()["c"]
            texts = conn.execute("SELECT COUNT(*) as c FROM clips WHERE type='text'").fetchone()["c"]
            paths = conn.execute("SELECT COUNT(*) as c FROM clips WHERE type='path'").fetchone()["c"]
            return {"total": total, "links": links, "texts": texts, "paths": paths}
        finally:
            conn.close()

    def close(self):
        """No-op for compatibility. Connections are auto-closed."""
        pass
