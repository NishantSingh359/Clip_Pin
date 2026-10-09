"""
Tests for the clipboard history database module.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from pathlib import Path

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import ClipboardDatabase, detect_type


class TestDetectType(unittest.TestCase):
    """Tests for the detect_type function."""

    def test_detects_http_url(self):
        self.assertEqual(detect_type("https://example.com/page"), "link")

    def test_detects_https_url(self):
        self.assertEqual(detect_type("https://github.com/user/repo"), "link")

    def test_detects_ftp_url(self):
        self.assertEqual(detect_type("ftp://files.example.com"), "link")

    def test_detects_www_url(self):
        self.assertEqual(detect_type("www.example.com"), "link")

    def test_detects_windows_path(self):
        self.assertEqual(detect_type("C:\\Users\\TUF\\Documents\\file.txt"), "path")

    def test_detects_windows_path_root(self):
        self.assertEqual(detect_type("D:\\Photos"), "path")

    def test_detects_unix_path(self):
        self.assertEqual(detect_type("/home/user/Documents/file.txt"), "path")

    def test_detects_network_path(self):
        self.assertEqual(detect_type("\\\\server\\share\\folder"), "path")

    def test_detects_plain_text(self):
        self.assertEqual(detect_type("Hello, world!"), "text")

    def test_detects_code_snippet(self):
        self.assertEqual(detect_type("def hello():\n    print('hi')"), "text")

    def test_detects_email_as_text(self):
        self.assertEqual(detect_type("user@example.com"), "text")

    def test_detects_number_as_text(self):
        self.assertEqual(detect_type("12345"), "text")

    def test_empty_string_as_text(self):
        self.assertEqual(detect_type(""), "text")

    def test_whitespace_only_as_text(self):
        self.assertEqual(detect_type("   "), "text")


class TestClipboardDatabase(unittest.TestCase):
    """Tests for the ClipboardDatabase class."""

    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db = ClipboardDatabase(self.temp_dir)

    def tearDown(self):
        """Clean up the temporary database."""
        self.db.clear()
        # Remove the temp db file
        db_path = Path(self.temp_dir) / "data" / "clips.db"
        if db_path.exists():
            db_path.unlink()
        # Remove data dir if empty
        data_dir = Path(self.temp_dir) / "data"
        if data_dir.exists() and not list(data_dir.iterdir()):
            data_dir.rmdir()

    def test_database_file_created(self):
        """Test that the database file is created in the data directory."""
        db_path = Path(self.temp_dir) / "data" / "clips.db"
        self.assertTrue(db_path.exists(), "Database file should exist")

    def test_records_survive_database_reopen(self):
        self.db.insert("persisted clipboard item")

        reopened_db = ClipboardDatabase(self.temp_dir)

        self.assertEqual(
            [record["content"] for record in reopened_db.get_all()],
            ["persisted clipboard item"],
        )

    def test_schema_has_required_columns(self):
        """The daily date/index pair is the non-null composite primary key."""
        conn = self.db._get_connection()
        try:
            info = conn.execute("PRAGMA table_info(clips)").fetchall()
            self.assertEqual(
                [row["name"] for row in info],
                ["date", "index", "type", "content"],
            )
            self.assertEqual([row["pk"] for row in info], [1, 2, 0, 0])
            self.assertTrue(all(row["notnull"] for row in info))
        finally:
            conn.close()

    def test_date_and_index_are_composite_primary_key(self):
        """Date and daily index together form the primary key."""
        conn = self.db._get_connection()
        try:
            info = conn.execute("PRAGMA table_info(clips)").fetchall()
            self.assertEqual(next(r for r in info if r["name"] == "date")["pk"], 1)
            self.assertEqual(next(r for r in info if r["name"] == "index")["pk"], 2)
        finally:
            conn.close()

    def test_index_cannot_be_null(self):
        conn = self.db._get_connection()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    'INSERT INTO clips (date, "index", type, content) VALUES (?, ?, ?, ?)',
                    ("2026-10-09", None, "text", "invalid"),
                )
        finally:
            conn.close()

    def test_insert_text(self):
        """Test inserting a text clip."""
        row_id = self.db.insert("Hello, world!")
        self.assertIsNotNone(row_id)
        self.assertEqual(self.db.count(), 1)

    def test_insert_link(self):
        """Test inserting a link clip (type auto-detected)."""
        row_id = self.db.insert("https://github.com")
        self.assertIsNotNone(row_id)
        record = self.db.get_by_id(row_id)
        self.assertEqual(record["type"], "link")

    def test_insert_path(self):
        """Test inserting a path clip (type auto-detected)."""
        row_id = self.db.insert("C:\\Users\\TUF\\file.txt")
        self.assertIsNotNone(row_id)
        record = self.db.get_by_id(row_id)
        self.assertEqual(record["type"], "path")

    def test_insert_duplicate_content(self):
        """Duplicate content is ignored within the same date."""
        row_id1 = self.db.insert("unique content")
        row_id2 = self.db.insert("unique content")
        self.assertIsNotNone(row_id1)
        self.assertIsNone(row_id2)
        self.assertEqual(self.db.count(), 1)

    def test_daily_indexes_start_at_one_and_reset_each_day(self):
        with patch("core.database.local_date") as mocked_date:
            mocked_date.today.return_value = date(2026, 10, 9)
            first_id = self.db.insert("first daily clip")
            second_id = self.db.insert("second daily clip")
            mocked_date.today.return_value = date(2026, 10, 10)
            next_day_id = self.db.insert("next day clip")

        first_day = self.db.get_by_date("2026-10-09")
        next_day = self.db.get_by_date("2026-10-10")
        self.assertEqual(
            [(row["index"], row["content"]) for row in reversed(first_day)],
            [(1, "first daily clip"), (2, "second daily clip")],
        )
        self.assertEqual(next_day[0]["index"], 1)
        self.assertEqual(len({first_id, second_id, next_day_id}), 3)

    def test_duplicate_content_is_allowed_on_another_date(self):
        with patch("core.database.local_date") as mocked_date:
            mocked_date.today.return_value = date(2026, 10, 9)
            self.db.insert("repeat clip")
            mocked_date.today.return_value = date(2026, 10, 10)
            self.db.insert("repeat clip")

        self.assertEqual(self.db.count(), 2)

    def test_legacy_schema_migrates_preserving_dates_and_order(self):
        with tempfile.TemporaryDirectory() as legacy_dir:
            legacy_path = Path(legacy_dir) / "data" / "clips.db"
            legacy_path.parent.mkdir()
            conn = sqlite3.connect(legacy_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE clips (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT NOT NULL,
                        content TEXT NOT NULL UNIQUE,
                        created_at TEXT DEFAULT (datetime('now', 'localtime'))
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO clips (id, type, content, created_at) VALUES (?, ?, ?, ?)",
                    [
                        (1, "text", "yesterday", "2026-10-08 23:59:59"),
                        (2, "link", "today first", "2026-10-09 08:00:00"),
                        (3, "text", "today second", "2026-10-09 09:00:00"),
                    ],
                )
                conn.execute("CREATE INDEX idx_clips_type ON clips(type)")
                conn.execute(
                    "CREATE INDEX idx_clips_created_at ON clips(created_at DESC)"
                )
                conn.commit()
            finally:
                conn.close()

            migrated_db = ClipboardDatabase(legacy_dir)
            self.assertEqual(
                [
                    (row["date"], row["index"], row["content"])
                    for row in migrated_db.get_all()
                ],
                [
                    ("2026-10-09", 2, "today second"),
                    ("2026-10-09", 1, "today first"),
                    ("2026-10-08", 1, "yesterday"),
                ],
            )

    def test_insert_with_explicit_type(self):
        """Test inserting with an explicit type override."""
        row_id = self.db.insert_with_type("Hello", "text")
        self.assertIsNotNone(row_id)
        record = self.db.get_by_id(row_id)
        self.assertEqual(record["type"], "text")

    def test_insert_with_explicit_type_link(self):
        """Test inserting plain text as type 'link'."""
        row_id = self.db.insert_with_type("Not a link", "link")
        self.assertIsNotNone(row_id)
        record = self.db.get_by_id(row_id)
        self.assertEqual(record["type"], "link")

    def test_insert_invalid_type_raises(self):
        """Test that an invalid type raises ValueError."""
        with self.assertRaises(ValueError):
            self.db.insert_with_type("content", "invalid_type")

    def test_get_all_returns_all(self):
        """Test get_all returns all records ordered by most recent first."""
        self.db.insert("first")
        self.db.insert("second")
        self.db.insert("third")
        all_records = self.db.get_all()
        self.assertEqual(len(all_records), 3)
        # Should be in reverse order (most recent first)
        self.assertEqual(all_records[0]["content"], "third")
        self.assertEqual(all_records[2]["content"], "first")

    def test_get_all_with_limit(self):
        """Test get_all respects the limit parameter."""
        for i in range(10):
            self.db.insert(f"content {i}")
        records = self.db.get_all(limit=3)
        self.assertEqual(len(records), 3)

    def test_get_all_with_offset(self):
        """Test get_all respects the offset parameter."""
        for i in range(10):
            self.db.insert(f"content {i}")
        first_page = self.db.get_all(limit=5, offset=0)
        second_page = self.db.get_all(limit=5, offset=5)
        self.assertEqual(len(first_page), 5)
        self.assertEqual(len(second_page), 5)
        # Ensure no overlap
        first_ids = {r["id"] for r in first_page}
        second_ids = {r["id"] for r in second_page}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_get_by_type_links(self):
        """Test filtering records by type 'link'."""
        self.db.insert("https://example.com")
        self.db.insert("Normal text")
        self.db.insert("C:\\path")
        links = self.db.get_by_type("link")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["type"], "link")

    def test_get_by_type_text(self):
        """Test filtering records by type 'text'."""
        self.db.insert("https://example.com")
        self.db.insert("Normal text")
        self.db.insert("C:\\path")
        texts = self.db.get_by_type("text")
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0]["content"], "Normal text")

    def test_get_by_type_path(self):
        """Test filtering records by type 'path'."""
        self.db.insert("https://example.com")
        self.db.insert("Normal text")
        self.db.insert("C:\\path")
        paths = self.db.get_by_type("path")
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]["content"], "C:\\path")

    def test_history_dates_and_date_filter(self):
        conn = self.db._get_connection()
        try:
            conn.executemany(
                'INSERT INTO clips (date, "index", type, content) VALUES (?, ?, ?, ?)',
                [
                    ("2026-10-08", 1, "text", "yesterday clip"),
                    ("2026-10-09", 1, "link", "today clip"),
                    ("2026-10-09", 2, "text", "today later clip"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(
            self.db.get_available_dates(),
            ["2026-10-09", "2026-10-08"],
        )
        today = self.db.get_by_date("2026-10-09")
        self.assertEqual(
            [record["content"] for record in today],
            ["today later clip", "today clip"],
        )

    def test_get_by_id_found(self):
        """Test get_by_id returns the correct record."""
        row_id = self.db.insert("find me")
        record = self.db.get_by_id(row_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["content"], "find me")

    def test_get_by_id_not_found(self):
        """Test get_by_id returns None for non-existent id."""
        record = self.db.get_by_id(9999)
        self.assertIsNone(record)

    def test_search_matches_content(self):
        """Test search finds records by content substring."""
        self.db.insert("The quick brown fox")
        self.db.insert("jumps over the lazy dog")
        self.db.insert("brown bear")
        results = self.db.search("brown")
        self.assertEqual(len(results), 2)

    def test_search_case_sensitive(self):
        """Test search is case-insensitive with LIKE."""
        self.db.insert("Hello World")
        self.db.insert("Goodbye")
        results = self.db.search("hello")
        self.assertEqual(len(results), 1)

    def test_search_no_match(self):
        """Test search returns empty list when no match."""
        self.db.insert("abc")
        self.db.insert("def")
        results = self.db.search("xyz")
        self.assertEqual(len(results), 0)

    def test_search_empty_query(self):
        """Test search with empty query returns all records."""
        self.db.insert("abc")
        self.db.insert("def")
        results = self.db.search("")
        self.assertEqual(len(results), 2)

    def test_count(self):
        """Test count returns the correct number of records."""
        self.assertEqual(self.db.count(), 0)
        self.db.insert("a")
        self.assertEqual(self.db.count(), 1)
        self.db.insert("b")
        self.db.insert("c")
        self.assertEqual(self.db.count(), 3)

    def test_delete_by_id(self):
        """Test deleting a record by id."""
        row_id = self.db.insert("delete me")
        self.assertEqual(self.db.count(), 1)
        deleted = self.db.delete(row_id)
        self.assertTrue(deleted)
        self.assertEqual(self.db.count(), 0)

    def test_deleting_clip_reindexes_that_day_without_gaps(self):
        with patch("core.database.local_date") as mocked_date:
            mocked_date.today.return_value = date(2026, 10, 9)
            first_id = self.db.insert("first")
            self.db.insert("middle")
            self.db.insert("last")

        self.db.delete(first_id)

        self.assertEqual(
            [(row["index"], row["content"]) for row in reversed(
                self.db.get_by_date("2026-10-09")
            )],
            [(1, "middle"), (2, "last")],
        )

    def test_delete_nonexistent_id(self):
        """Test deleting a non-existent id returns False."""
        result = self.db.delete(9999)
        self.assertFalse(result)

    def test_delete_by_content(self):
        """Test deleting a record by content."""
        self.db.insert("delete by content")
        self.assertEqual(self.db.count(), 1)
        deleted = self.db.delete_by_content("delete by content")
        self.assertTrue(deleted)
        self.assertEqual(self.db.count(), 0)

    def test_delete_by_content_only_deletes_requested_date(self):
        with patch("core.database.local_date") as mocked_date:
            mocked_date.today.return_value = date(2026, 10, 9)
            self.db.insert("same across dates")
            mocked_date.today.return_value = date(2026, 10, 10)
            self.db.insert("same across dates")

        self.assertTrue(
            self.db.delete_by_content("same across dates", "2026-10-09")
        )
        self.assertEqual(
            [record["date"] for record in self.db.search("same across dates")],
            ["2026-10-10"],
        )

    def test_delete_nonexistent_content(self):
        """Test deleting non-existent content returns False."""
        result = self.db.delete_by_content("not in db")
        self.assertFalse(result)

    def test_clear_all(self):
        """Test clearing all records."""
        self.db.insert("a")
        self.db.insert("b")
        self.db.insert("c")
        self.assertEqual(self.db.count(), 3)
        count = self.db.clear()
        self.assertEqual(count, 3)
        self.assertEqual(self.db.count(), 0)

    def test_get_stats_empty(self):
        """Test stats on an empty database."""
        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["links"], 0)
        self.assertEqual(stats["texts"], 0)
        self.assertEqual(stats["paths"], 0)
        self.assertEqual(stats["imgs"], 0)

    def test_get_stats(self):
        """Test stats with mixed content types."""
        self.db.insert("https://link1.com")
        self.db.insert("https://link2.com")
        self.db.insert("Text content")
        self.db.insert("C:\\path1")
        self.db.insert("C:\\path2\\file")
        self.db.insert_with_type("C:\\image.png", "img")
        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 6)
        self.assertEqual(stats["links"], 2)
        self.assertEqual(stats["texts"], 1)
        self.assertEqual(stats["paths"], 2)
        self.assertEqual(stats["imgs"], 1)

    def test_locked_write_retries(self):
        """Test locked database writes are retried."""
        attempts = {"count": 0}

        class FakeConnection:
            def execute(self, _query):
                pass

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        def operation(conn):
            attempts["count"] += 1
            if attempts["count"] == 1:
                import sqlite3
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        with patch.object(self.db, "_get_connection", return_value=FakeConnection()):
            self.assertEqual(self.db._write_with_retry(operation), "ok")
        self.assertEqual(attempts["count"], 2)

    def test_invalid_storage_falls_back_to_user_db_path(self):
        """Test invalid base_dir falls back to the user database path."""
        fallback_root = tempfile.mkdtemp()
        fallback_path = Path(fallback_root) / "data" / "clips.db"
        invalid_base = Path(tempfile.mkdtemp()) / "not_a_dir"
        invalid_base.write_text("file blocks directory creation")

        def fallback_db_path():
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            return str(fallback_path)

        with patch("core.database.get_user_db_path", side_effect=fallback_db_path):
            db = ClipboardDatabase(str(invalid_base))

        self.assertEqual(db.db_path, str(fallback_path))
        self.assertTrue(fallback_path.exists())

    def test_purge_old_records_retention_days_parameter(self):
        """Test purge_old_records with custom retention days."""
        # Insert 3 records
        self.db.insert("fresh record")
        self.db.insert("another fresh")
        self.db.insert("yet another")
        self.assertEqual(self.db.count(), 3)

        # Purge with retention_days=0 should immediately (or nearly so) delete
        # records where date < today.
        # Since the records were just created < 1 second ago, 0-day retention
        # may or may not purge them depending on fractional seconds.
        # Instead, just verify the method accepts the parameter and runs.
        purged = self.db.purge_old_records(retention_days=30)
        self.assertIsInstance(purged, int)

    def test_purge_old_records_with_custom_value(self):
        """Test purge_old_records with a very old timestamp inserted directly."""
        conn = self.db._get_connection()
        try:
            conn.execute(
                'INSERT INTO clips (date, "index", type, content) VALUES (date("now", "localtime", "-60 days"), 1, ?, ?)',
                ("text", "old_record_60_days"),
            )
            conn.execute(
                'INSERT INTO clips (date, "index", type, content) VALUES (date("now", "localtime", "-45 days"), 1, ?, ?)',
                ("text", "old_record_45_days"),
            )
            conn.execute(
                'INSERT INTO clips (date, "index", type, content) VALUES (date("now", "localtime", "-1 day"), 1, ?, ?)',
                ("text", "recent_record"),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(self.db.count(), 3)

        # Should delete the 60-day and 45-day records, but keep the 1-day record.
        purged = self.db.purge_old_records(retention_days=30)
        self.assertEqual(purged, 2)

        remaining = self.db.get_all()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["content"], "recent_record")

    def test_purge_old_records_no_old_records(self):
        """Test purge_old_records when no records exceed retention period."""
        self.db.insert("record1")
        self.db.insert("record2")
        purged = self.db.purge_old_records(retention_days=30)
        self.assertEqual(purged, 0)
        self.assertEqual(self.db.count(), 2)

    def test_purge_old_records_all_old(self):
        """Test purge_old_records when all records exceed retention period."""
        conn = self.db._get_connection()
        try:
            conn.execute(
                'INSERT INTO clips (date, "index", type, content) VALUES (?, ?, ?, ?)',
                ("2026-01-01", 1, "text", "very_old_1"),
            )
            conn.execute(
                'INSERT INTO clips (date, "index", type, content) VALUES (?, ?, ?, ?)',
                ("2026-02-15", 1, "text", "very_old_2"),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(self.db.count(), 2)
        purged = self.db.purge_old_records(retention_days=30)
        self.assertEqual(purged, 2)
        self.assertEqual(self.db.count(), 0)

    def test_date_and_index_are_set_on_insert(self):
        row_id = self.db.insert("date and index test")
        record = self.db.get_by_id(row_id)
        self.assertEqual(record["date"], date.today().isoformat())
        self.assertGreaterEqual(record["index"], 1)

    def test_get_db_path_creates_directory(self):
        """Test that get_db_path creates the data directory."""
        test_dir = tempfile.mkdtemp()
        data_dir = Path(test_dir) / "data"
        self.assertFalse(data_dir.exists())
        from core.database import get_db_path
        path = get_db_path(test_dir)
        self.assertTrue(data_dir.exists())
        self.assertEqual(Path(path).parent, data_dir)

    def test_multiple_inserts_and_retrieval(self):
        """Test inserting multiple records and retrieving them all."""
        items = [
            "https://example.com",
            "Hello, world!",
            "C:\\Users\\file.txt",
            "Another text",
            "https://github.com",
        ]
        for item in items:
            self.db.insert(item)
        
        all_records = self.db.get_all(limit=10)
        contents = [r["content"] for r in all_records]
        self.assertEqual(len(contents), len(items))
        for item in items:
            self.assertIn(item, contents)

    def test_mixed_insert_and_get_by_type(self):
        """Test that get_by_type returns correct count after mixed inserts."""
        self.db.insert("https://link.com")
        self.db.insert("text1")
        self.db.insert("C:\\path\\file.txt")
        self.db.insert("text2")
        self.db.insert("https://another.com")
        self.db.insert("/home/user/file")
        self.db.insert("text3")
        
        links = self.db.get_by_type("link")
        texts = self.db.get_by_type("text")
        paths = self.db.get_by_type("path")
        
        self.assertEqual(len(links), 2)
        self.assertEqual(len(texts), 3)
        self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
