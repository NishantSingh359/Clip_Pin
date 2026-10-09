"""
Clipboard history database module.
Manages persistence of clipboard items with SQLite.

Schema:
    date    - TEXT: local calendar date of the copied item
    index   - INTEGER: 1-based order within the date
    type    - TEXT: 'link', 'text', 'path', or 'img'
    content - TEXT: the copied text, link, path, or img file path
"""


import os
import re
import sqlite3
import time
from datetime import date as local_date
from pathlib import Path

from config import DB_BUSY_TIMEOUT_MS, DB_RETRY_DELAY_MS, DB_WRITE_RETRIES


DB_DIR = "data"
DB_NAME = "clips.db"
APP_DATA_DIR = "DockPaste"


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
        conn = sqlite3.connect(self.db_path, timeout=DB_BUSY_TIMEOUT_MS / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _is_locked_error(self, exc):
        message = str(exc).lower()
        return "locked" in message or "busy" in message

    def _write_with_retry(self, operation):
        for attempt in range(DB_WRITE_RETRIES + 1):
            conn = None
            try:
                conn = self._get_connection()
                conn.execute("BEGIN IMMEDIATE")
                result = operation(conn)
                conn.commit()
                return result
            except sqlite3.OperationalError as exc:
                if conn is not None:
                    try:
                        conn.rollback()
                    except sqlite3.Error:
                        pass
                if not self._is_locked_error(exc) or attempt >= DB_WRITE_RETRIES:
                    raise
                time.sleep(DB_RETRY_DELAY_MS / 1000)
            finally:
                if conn is not None:
                    conn.close()
        return None

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        try:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(clips)").fetchall()
            }
            if not columns:
                self._create_clips_table(conn)
            elif {"date", "index", "type", "content"} - columns:
                self._migrate_legacy_table(conn)
            self._create_clips_indexes(conn)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _create_clips_table(conn, table_name="clips"):
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                date TEXT NOT NULL,
                "index" INTEGER NOT NULL CHECK ("index" >= 1),
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY (date, "index"),
                UNIQUE (date, content)
            )
            """
        )

    @staticmethod
    def _create_clips_indexes(conn):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_type ON clips(type)")
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_clips_date_index ON clips(date DESC, "index" DESC)'
        )

    def _migrate_legacy_table(self, conn):
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(clips)").fetchall()
        }
        if not {"id", "type", "content", "created_at"}.issubset(columns):
            raise sqlite3.DatabaseError(
                "Clipboard history table has an unsupported schema; refusing to replace it"
            )

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ALTER TABLE clips RENAME TO clips_legacy")
        self._create_clips_table(conn)
        records = conn.execute(
            """
            SELECT id, type, content, created_at
            FROM clips_legacy
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        next_index_by_date = {}
        for record in records:
            clip_date = str(record["created_at"])[:10]
            try:
                local_date.fromisoformat(clip_date)
            except ValueError as exc:
                raise sqlite3.DatabaseError(
                    f"Clipboard record {record['id']} has an invalid creation date"
                ) from exc
            clip_index = next_index_by_date.get(clip_date, 0) + 1
            next_index_by_date[clip_date] = clip_index
            conn.execute(
                """
                INSERT INTO clips (rowid, date, "index", type, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    clip_date,
                    clip_index,
                    record["type"],
                    record["content"],
                ),
            )
        conn.execute("DROP TABLE clips_legacy")

    def insert(self, content: str) -> int | None:
        """
        Insert a clipboard item. Automatically detects type.

        Args:
            content: The clipboard content string.

        Returns:
            The row id of the inserted record, or None if it already exists.
        """
        return self.insert_with_type(content, detect_type(content))

    @staticmethod
    def _insert_for_today(conn, content, clip_type):
        clip_date = local_date.today().isoformat()
        existing = conn.execute(
            'SELECT rowid FROM clips WHERE date = ? AND content = ?',
            (clip_date, content),
        ).fetchone()
        if existing:
            return None
        next_index = conn.execute(
            'SELECT COALESCE(MAX("index"), 0) + 1 FROM clips WHERE date = ?',
            (clip_date,),
        ).fetchone()[0]
        cursor = conn.execute(
            'INSERT INTO clips (date, "index", type, content) VALUES (?, ?, ?, ?)',
            (clip_date, next_index, clip_type, content),
        )
        return cursor.lastrowid

    def insert_with_type(self, content: str, clip_type: str) -> int | None:
        """
        Insert an item with an explicit type and assign its next daily index.

        Returns the compatibility row handle, or None for a duplicate on
        today's date.
        """
        if clip_type not in ("link", "text", "path", "img"):
            raise ValueError(
                f"Invalid type '{clip_type}'. Must be 'link', 'text', 'path', or 'img'."
            )

        def operation(conn):
            return self._insert_for_today(conn, content, clip_type)

        return self._write_with_retry(operation)

    def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Retrieve clipboard history ordered by most recent first.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of dicts with keys: id, date, index, type, content.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT rowid AS id, date, "index", type, content
                FROM clips
                ORDER BY date DESC, "index" DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_available_dates(self) -> list[str]:
        """Return local calendar dates with stored clips, newest first."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT date AS clip_date
                FROM clips
                GROUP BY date
                ORDER BY date DESC
                """
            ).fetchall()
            return [row["clip_date"] for row in rows]
        finally:
            conn.close()

    def get_by_date(self, clip_date: str) -> list[dict]:
        """Retrieve all clips created on a local calendar date, newest first."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT rowid AS id, date, "index", type, content
                FROM clips
                WHERE date = ?
                ORDER BY "index" DESC
                """,
                (clip_date,),
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
            List of dicts with keys: id, date, index, type, content.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT rowid AS id, date, "index", type, content
                FROM clips
                WHERE type = ?
                ORDER BY date DESC, "index" DESC
                LIMIT ? OFFSET ?
                """,
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
                """
                SELECT rowid AS id, date, "index", type, content
                FROM clips
                WHERE rowid = ?
                """,
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
            List of dicts with keys: id, date, index, type, content.
        """

        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT rowid AS id, date, "index", type, content
                FROM clips
                WHERE content LIKE ?
                ORDER BY date DESC, "index" DESC
                LIMIT ?
                """,
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
        def operation(conn):
            record = conn.execute(
                "SELECT date FROM clips WHERE rowid = ?", (record_id,)
            ).fetchone()
            cursor = conn.execute("DELETE FROM clips WHERE rowid = ?", (record_id,))
            if record and cursor.rowcount:
                self._reindex_date(conn, record["date"])
            return cursor.rowcount > 0

        return self._write_with_retry(operation)

    def update_content(self, record_id: int, content: str) -> bool:
        """Update a record's content while preserving its date and daily index."""
        def operation(conn):
            cursor = conn.execute(
                "UPDATE clips SET content = ? WHERE rowid = ?",
                (content, record_id),
            )
            return cursor.rowcount > 0

        return self._write_with_retry(operation)

    @staticmethod
    def _reindex_date(conn, clip_date):
        rows = conn.execute(
            'SELECT rowid FROM clips WHERE date = ? ORDER BY "index"',
            (clip_date,),
        ).fetchall()
        if not rows:
            return

        offset = len(rows) + conn.execute(
            'SELECT COALESCE(MAX("index"), 0) FROM clips WHERE date = ?',
            (clip_date,),
        ).fetchone()[0]
        conn.execute(
            'UPDATE clips SET "index" = "index" + ? WHERE date = ?',
            (offset, clip_date),
        )
        for new_index, row in enumerate(rows, start=1):
            conn.execute(
                'UPDATE clips SET "index" = ? WHERE rowid = ?',
                (new_index, row["rowid"]),
            )

    def delete_by_content(self, content: str, clip_date: str | None = None) -> bool:
        """
        Delete a clipboard record by its content.

        Args:
            content:             The content to match and delete, optionally on a specific date.

        Returns:
            True if a record was deleted, False otherwise.
        """
        def operation(conn):
            if clip_date is None:
                record = conn.execute(
                    """
                    SELECT rowid, date FROM clips
                    WHERE content = ?
                    ORDER BY date DESC, "index" DESC
                    LIMIT 1
                    """,
                    (content,),
                ).fetchone()
                if record is None:
                    return False
                cursor = conn.execute(
                    "DELETE FROM clips WHERE rowid = ?", (record["rowid"],)
                )
                if cursor.rowcount:
                    self._reindex_date(conn, record["date"])
            else:
                cursor = conn.execute(
                    'DELETE FROM clips WHERE date = ? AND content = ?',
                    (clip_date, content),
                )
                if cursor.rowcount:
                    self._reindex_date(conn, clip_date)
            return cursor.rowcount > 0

        return self._write_with_retry(operation)

    def purge_old_records(self, retention_days: int = 30) -> int:
        """
        Delete clipboard records older than the specified number of days.
        
        Uses the local calendar date to determine age. Records whose
        creation date is older than 'retention_days' days are removed.
        
        Args:
            retention_days: Maximum age of records in days (default: 30).
        
        Returns:
            Number of deleted records.
        """
        def operation(conn):
            cursor = conn.execute(
                """
                DELETE FROM clips
                WHERE date < date('now', 'localtime', ?)
                """,
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

        return self._write_with_retry(operation)

    def clear(self) -> int:
        """
        Delete all clipboard records.
        
        Returns:
            Number of deleted records.
        """
        def operation(conn):
            cursor = conn.execute("DELETE FROM clips")
            return cursor.rowcount

        return self._write_with_retry(operation)

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
            imgs = conn.execute("SELECT COUNT(*) as c FROM clips WHERE type='img'").fetchone()["c"]
            return {"total": total, "links": links, "texts": texts, "paths": paths, "imgs": imgs}
        finally:
            conn.close()

    def close(self):
        """No-op for compatibility. Connections are auto-closed."""
        pass
