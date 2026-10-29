"""db.py: database creation, migrations and settings, on a temporary file (never server/fall.db).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import db


class DbInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "test.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_migration_11_keeps_old_push_rows_as_first_detection(self):
        db.init(self.path, [m for m in db.MIGRATIONS if m[0] <= 10])
        with db.session(self.path) as conn:
            conn.execute("INSERT INTO groups (id, name, created_at) VALUES ('g', 'g', 0)")
            conn.execute("INSERT INTO users (id, name, phone, password_hash, created_at, group_id) VALUES ('u', 'u', '010', 'h', 0, 'g')")
            conn.execute("INSERT INTO homes (id, group_id, created_at, updated_at) VALUES ('h', 'g', 0, 0)")
            conn.execute("""INSERT INTO incidents (id, group_id, home_id, source, location, detected_at, status, updated_at)
                            VALUES ('i', 'g', 'h', 'dev', '거실', 0, 'detected', 0)""")
            conn.execute("""INSERT INTO push_deliveries (incident_id, group_id, user_id, status, attempts, sent_count,
                                                         created_at, updated_at) VALUES ('i', 'g', 'u', 'sent', 1, 1, 5, 6)""")
        self.assertEqual(db.init(self.path), 11)
        with db.session(self.path) as conn:
            row = conn.execute("SELECT * FROM push_deliveries").fetchone()
            self.assertEqual((row["incident_id"], row["user_id"], row["kind"], row["n"], row["status"], row["sent_count"]),
                             ("i", "u", "detected", 0, "sent", 1))
            conn.execute("""INSERT INTO push_deliveries (incident_id, group_id, user_id, kind, n, status, created_at, updated_at)
                            VALUES ('i', 'g', 'u', 'family_alert', 0, 'pending', 7, 7)""")   # 같은 사람, 다른 단계
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("""INSERT INTO push_deliveries (incident_id, group_id, user_id, kind, n, status, created_at, updated_at)
                                VALUES ('i', 'g', 'u', 'family_alert', 0, 'pending', 8, 8)""")   # 같은 단계는 한 번
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'incident_redetections'").fetchone())

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


class ConcurrentInitTest(unittest.TestCase):
    """Several server processes starting at once on the same empty database (each applies migrations itself)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_applied_once(self, path):
        with db.session(path) as conn:
            versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            created = conn.execute("SELECT COUNT(*) FROM app_meta WHERE key = 'created_at'").fetchone()[0]
        self.assertEqual(versions, [m[0] for m in db.MIGRATIONS])   # 모두 한 번씩만 기록
        self.assertEqual(created, 1)

    def test_migration_applied_by_another_process_meanwhile_is_skipped(self):
        # 이미 적용된 목록을 읽은 뒤, 첫 변경의 쓰기 잠금을 잡기 직전에 다른 프로세스가 전부 적용한 경우
        path = self.dir / "race.db"
        original = db.transaction
        raced = []

        def other_process_wins_first(conn):
            if not raced:
                raced.append(True)
                db.transaction = original
                db.init(path)                      # 다른 연결 = 먼저 시작한 다른 서버
            return original(conn)

        db.transaction = other_process_wins_first
        try:
            self.assertEqual(db.init(path), db.MIGRATIONS[-1][0])
        finally:
            db.transaction = original
        self.assertTrue(raced)
        self.assert_applied_once(path)

    def test_processes_starting_at_the_same_moment(self):
        # 실제 프로세스 여러 개를 같은 시각에 시작 (수정 전에는 'table app_meta already exists' 등으로 일부가 실패)
        server_dir = Path(db.__file__).resolve().parent
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import db; "
                "time.sleep(max(0.0, float(sys.argv[3]) - time.time())); print(db.init(sys.argv[2]))")
        for round_no in range(8):
            path = self.dir / f"start{round_no}.db"
            start_at = time.time() + 1.5            # 프로세스가 모두 뜬 뒤 같은 순간에 db.init 시작
            procs = [subprocess.Popen([sys.executable, "-c", code, str(server_dir), str(path), str(start_at)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(4)]
            # 결과를 보기 전에 모두 끝날 때까지 기다림 (실패해도 DB 파일을 잡고 있는 프로세스가 남지 않게)
            finished = [(p.returncode, out, err) for p in procs for out, err in [p.communicate(timeout=60)]]
            for code_, out, err in finished:
                self.assertEqual(code_, 0, f"round {round_no}: {err.strip().splitlines()[-1:]}")
                self.assertEqual(out.strip(), str(db.MIGRATIONS[-1][0]))
            self.assert_applied_once(path)


if __name__ == "__main__":
    unittest.main()
