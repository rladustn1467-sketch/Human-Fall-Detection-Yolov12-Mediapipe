"""SQLite storage for the family web app (/app/next).

Stage A only prepares the database: connection settings and schema versioning.
Existing data is NOT stored here yet and is not touched by this module:
events.json, residents.json, access_token.txt, telegram_state.json, .env.
Later stages add their tables as new migrations (B: users/sessions/groups, C: people/homes, ...).

The database file defaults to server/fall.db; set FALL_DB_PATH to use another file
(test copies of the server use their own file, so test data never mixes with real data).
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

# 스키마 변경 목록: (버전, 설명, [SQL 문장, ...]).
# 한 번 배포한 항목은 고치지 말고, 바꿀 일이 있으면 새 버전을 뒤에 추가합니다.
MIGRATIONS = [
    (1, "기본 정보 테이블", [
        """CREATE TABLE app_meta (
               key   TEXT PRIMARY KEY,
               value TEXT NOT NULL
           )""",
        "INSERT INTO app_meta (key, value) VALUES ('created_at', strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))",
    ]),
]

BUSY_TIMEOUT_MS = 10_000  # 다른 스레드가 쓰는 중이면 이 시간까지 기다림


def connect(path):
    """Open a connection: foreign keys on, rows as dict-like objects, explicit transactions (autocommit mode)."""
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def session(path):
    """One connection per request or task (sqlite3 connections are not shared between threads)."""
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn):
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def init(path, migrations=None):
    """Create the database file if needed and apply pending migrations in order.

    Safe to call on every server start. Each migration runs in its own transaction, so a
    failed migration leaves the database at the previous version. Returns the schema version.
    """
    migrations = MIGRATIONS if migrations is None else migrations
    versions = [m[0] for m in migrations]
    if versions != sorted(set(versions)):
        raise ValueError("migration versions must be unique and increasing")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with session(path) as conn:
        # 여러 스레드가 읽고 쓰는 서버에 맞는 저장 방식 (파일 옆에 -wal, -shm 파일이 생김)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                            version     INTEGER PRIMARY KEY,
                            description TEXT NOT NULL,
                            applied_at  TEXT NOT NULL
                        )""")
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, description, statements in migrations:
            if version in done:
                continue
            with transaction(conn):
                for sql in statements:
                    conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                             (version, description, time.strftime("%Y-%m-%d %H:%M:%S")))
        return schema_version(conn)


def health(path):
    """Quick check for the health API: the database opens and answers. Returns (ok, schema_version)."""
    try:
        with session(path) as conn:
            return True, schema_version(conn)
    except sqlite3.Error:
        return False, None
