"""db.py: database creation, migrations and settings, on a temporary file (never server/fall.db).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import db


class DbInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "test.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_file_and_applies_migrations(self):
        version = db.init(self.path)
        self.assertTrue(self.path.is_file())
        self.assertEqual(version, db.MIGRATIONS[-1][0])
        with db.session(self.path) as conn:
            self.assertEqual(db.schema_version(conn), version)
            created = conn.execute("SELECT value FROM app_meta WHERE key = 'created_at'").fetchone()
            self.assertIsNotNone(created)

    def test_running_again_changes_nothing(self):
        db.init(self.path)
        with db.session(self.path) as conn:
            before = conn.execute("SELECT * FROM schema_migrations").fetchall()
            meta_before = conn.execute("SELECT * FROM app_meta").fetchall()
        self.assertEqual(db.init(self.path), db.MIGRATIONS[-1][0])
        with db.session(self.path) as conn:
            self.assertEqual([tuple(r) for r in conn.execute("SELECT * FROM schema_migrations")], [tuple(r) for r in before])
            self.assertEqual([tuple(r) for r in conn.execute("SELECT * FROM app_meta")], [tuple(r) for r in meta_before])

    def test_settings(self):
        db.init(self.path)
        with db.session(self.path) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], db.BUSY_TIMEOUT_MS)

    def test_failed_migration_is_rolled_back(self):
        broken = db.MIGRATIONS + [(99, "broken", ["CREATE TABLE ok_table (x INTEGER)", "THIS IS NOT SQL"])]
        with self.assertRaises(sqlite3.Error):
            db.init(self.path, broken)
        with db.session(self.path) as conn:
            self.assertEqual(db.schema_version(conn), db.MIGRATIONS[-1][0])
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertNotIn("ok_table", tables)

    def test_new_migration_is_applied_later(self):
        db.init(self.path)
        extended = db.MIGRATIONS + [(db.MIGRATIONS[-1][0] + 1, "extra", ["CREATE TABLE extra (x INTEGER)"])]
        self.assertEqual(db.init(self.path, extended), db.MIGRATIONS[-1][0] + 1)

    def test_versions_must_increase(self):
        with self.assertRaises(ValueError):
            db.init(self.path, [(2, "b", []), (1, "a", [])])

    def test_health(self):
        db.init(self.path)
        self.assertEqual(db.health(self.path), (True, db.MIGRATIONS[-1][0]))


if __name__ == "__main__":
    unittest.main()
