"""SQLite storage for the family web app (/app/next).

Stage A only prepares the database: connection settings and schema versioning.
Existing data is NOT stored here yet and is not touched by this module:
events.json, residents.json, access_token.txt, telegram_state.json, .env.
Later stages add their tables as new migrations (B: users/sessions/groups, C: people/homes, ...).
events.json and residents.json are still not moved here (stage C leaves residents.json as it is).

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
    (2, "계정·로그인·그룹·초대 (accounts.py)", [
        """CREATE TABLE groups (
               id          TEXT PRIMARY KEY,
               name        TEXT NOT NULL,
               created_by  TEXT,
               created_at  REAL NOT NULL
           )""",
        """CREATE TABLE users (
               id            TEXT PRIMARY KEY,
               name          TEXT NOT NULL,
               phone         TEXT NOT NULL UNIQUE,      -- 숫자만 (01012345678)
               password_hash TEXT NOT NULL,             -- scrypt$n$r$p$salt$hash (원문 없음)
               group_id      TEXT REFERENCES groups(id) ON DELETE SET NULL,
               onboarded     INTEGER NOT NULL DEFAULT 0,
               created_at    REAL NOT NULL
           )""",
        "CREATE INDEX users_group ON users(group_id)",
        """CREATE TABLE invites (
               group_id    TEXT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,  -- 그룹마다 유효한 코드 1개
               code        TEXT NOT NULL UNIQUE,
               created_by  TEXT,
               created_at  REAL NOT NULL,
               expires_at  REAL NOT NULL
           )""",
        """CREATE TABLE sessions (
               token_hash  TEXT PRIMARY KEY,            -- 쿠키 값의 SHA-256 (쿠키 값 자체는 저장 안 함)
               user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               created_at  REAL NOT NULL,
               expires_at  REAL NOT NULL
           )""",
        "CREATE INDEX sessions_user ON sessions(user_id)",
        """CREATE TABLE auth_failures (
               id   INTEGER PRIMARY KEY,
               key  TEXT NOT NULL,                      -- 예: login-phone:01012345678, login-ip:1.2.3.4
               at   REAL NOT NULL
           )""",
        "CREATE INDEX auth_failures_key ON auth_failures(key, at)",
    ]),
    (3, "가족 구성원 정보·집 (people.py)", [
        # 감지 대상자와 건강 정보 (그룹 가족에게만 보임). 목록은 JSON 문자열, NULL = 아직 입력 안 함, '[]' = 없음
        "ALTER TABLE users ADD COLUMN is_target INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN birth TEXT",
        "ALTER TABLE users ADD COLUMN conditions TEXT",
        "ALTER TABLE users ADD COLUMN medications TEXT",
        # 알림 받기 설정 {"device": true, "member": true, "home": true} (실제 알림은 G단계)
        "ALTER TABLE users ADD COLUMN prefs TEXT",
        # 현관 비밀번호는 H단계 (암호화 설계 후). 여기에는 저장하지 않음
        """CREATE TABLE homes (
               id          TEXT PRIMARY KEY,
               group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
               address     TEXT NOT NULL DEFAULT '',
               created_by  TEXT,
               created_at  REAL NOT NULL,
               updated_at  REAL NOT NULL
           )""",
        "CREATE INDEX homes_group ON homes(group_id)",
        """CREATE TABLE home_members (
               home_id     TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               linked_at   REAL NOT NULL,
               PRIMARY KEY (home_id, user_id)
           )""",
        "CREATE INDEX home_members_user ON home_members(user_id)",
    ]),
    (4, "현관 비밀번호 암호화 저장·작업 기록 (door_codes.py)", [
        # 값은 AES-256-GCM 암호문만 저장 (키는 server/.env 의 DOOR_CODE_KEY, DB 와 분리). 평문 칸 없음
        """CREATE TABLE home_door_codes (
               home_id     TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               kind        TEXT NOT NULL CHECK (kind IN ('central', 'door')),   -- 중앙(공동) 현관 / 집 현관
               ciphertext  BLOB NOT NULL,
               nonce       BLOB NOT NULL,
               key_id      TEXT NOT NULL,          -- 어떤 키로 암호화했는지 (키의 해시 앞부분, 키 자체 아님)
               updated_by  TEXT,
               updated_at  REAL NOT NULL,
               PRIMARY KEY (home_id, kind)
           )""",
        # 집 정보 작업 기록: 누가 언제 무엇을 했는지만 (비밀번호 값은 남기지 않음)
        """CREATE TABLE home_events (
               id        INTEGER PRIMARY KEY,
               home_id   TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               actor_id  TEXT,
               action    TEXT NOT NULL,             -- door_code_set / door_code_changed / door_code_deleted
               kind      TEXT,
               at        REAL NOT NULL
           )""",
        "CREATE INDEX home_events_home ON home_events(home_id, at)",
    ]),
    (5, "현관 출입 방식 (door_codes.py)", [
        # 집·현관마다 출입 방식 하나. 줄이 없으면 '미설정'.
        # '없음'은 현관마다 다른 값으로 저장해 섞이지 않게 함: 중앙현관 없음 = absent, 집 현관 잠금장치 없음 = unlocked
        """CREATE TABLE home_entrances (
               home_id     TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               kind        TEXT NOT NULL CHECK (kind IN ('central', 'door')),
               method      TEXT NOT NULL,
               updated_by  TEXT,
               updated_at  REAL NOT NULL,
               PRIMARY KEY (home_id, kind),
               CHECK ((kind = 'central' AND method IN ('code', 'key', 'absent'))
                   OR (kind = 'door' AND method IN ('code', 'key', 'unlocked')))
           )""",
        # 기존 데이터 보존: 이미 등록된 비밀번호는 '비밀번호' 방식으로 (비밀번호는 그대로 둠)
        """INSERT INTO home_entrances (home_id, kind, method, updated_by, updated_at)
           SELECT home_id, kind, 'code', updated_by, updated_at FROM home_door_codes""",
        # 안전장치: 출입 방식이 비밀번호가 아닌 현관에는 비밀번호를 저장할 수 없음 (프로그램 실수가 있어도 DB 가 막음)
        """CREATE TRIGGER home_door_codes_need_code_insert BEFORE INSERT ON home_door_codes
           WHEN EXISTS (SELECT 1 FROM home_entrances WHERE home_id = NEW.home_id AND kind = NEW.kind AND method != 'code')
           BEGIN SELECT RAISE(ABORT, 'entrance method is not code'); END""",
        """CREATE TRIGGER home_door_codes_need_code_update BEFORE UPDATE ON home_door_codes
           WHEN EXISTS (SELECT 1 FROM home_entrances WHERE home_id = NEW.home_id AND kind = NEW.kind AND method != 'code')
           BEGIN SELECT RAISE(ABORT, 'entrance method is not code'); END""",
    ]),
    (6, "낙상 사고·진행 기록·알림·문자 발송 기록·옛 감지 기기 연결 (incidents.py, alerts.py, legacy_devices.py)", [
        # 시각은 웹앱 화면과 같은 밀리초 정수(ms). 사람 이름·건강 정보는 저장하지 않고 사용자 id 만 (문장은 화면에 보낼 때 만듦)
        # 상태: detected → no_response | help → checking → closed | reported (store.js 의 사고 모델과 같음)
        """CREATE TABLE incidents (
               id                 TEXT PRIMARY KEY,
               group_id           TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
               home_id            TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               source             TEXT NOT NULL CHECK (source IN ('device', 'legacy', 'dev')),
               source_ref         TEXT,
               dedupe_key         TEXT UNIQUE,
               location           TEXT NOT NULL,
               detected_at        INTEGER NOT NULL,
               status             TEXT NOT NULL CHECK (status IN ('detected', 'no_response', 'help', 'checking', 'closed', 'reported')),
               response           TEXT CHECK (response IN ('within60', 'after60', 'none')),
               family_notified_at INTEGER,
               auto_report_at     INTEGER,
               checked_by         TEXT,
               checked_at         INTEGER,
               closed_at          INTEGER,
               closed_by          TEXT,
               result             TEXT CHECK (result IN ('self', 'family', 'reported', 'auto_reported')),
               reported_by        TEXT,
               reported_at        INTEGER,
               report_kind        TEXT CHECK (report_kind IS NULL OR report_kind = 'simulation'),
               recognized_id      TEXT,
               updated_at         INTEGER NOT NULL,
               CHECK ((status IN ('closed', 'reported')) = (closed_at IS NOT NULL)),
               CHECK ((status = 'reported') = (COALESCE(report_kind, '') = 'simulation'))
           )""",
        "CREATE INDEX incidents_group_time ON incidents (group_id, detected_at)",
        # 한 집에 진행 중인 사고는 하나만 (같은 집에서 다시 감지되면 기존 사고에 기록만 더함)
        "CREATE UNIQUE INDEX incidents_one_open_per_home ON incidents (home_id) WHERE status NOT IN ('closed', 'reported')",
        """CREATE TABLE incident_help (
               incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
               at          INTEGER NOT NULL,
               user_id     TEXT
           )""",
        # 진행 기록: 동작 종류와 사람 id 만 (문장은 화면에 보낼 때 만듦 → 탈퇴한 사람 이름이 남지 않음)
        """CREATE TABLE incident_log (
               id          INTEGER PRIMARY KEY AUTOINCREMENT,
               incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
               at          INTEGER NOT NULL,
               action      TEXT NOT NULL,
               user_id     TEXT,
               n           INTEGER,
               late        INTEGER NOT NULL DEFAULT 0
           )""",
        """CREATE TABLE incident_targets (
               incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
               user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               PRIMARY KEY (incident_id, user_id)
           )""",
        """CREATE TABLE incident_dismissals (
               incident_id TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
               user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               at          INTEGER NOT NULL,
               PRIMARY KEY (incident_id, user_id)
           )""",
        # 알림 기록 (앱 알림센터). 실제 전달 여부는 아래 notification_deliveries 에 따로 기록
        """CREATE TABLE notifications (
               id          TEXT PRIMARY KEY,
               group_id    TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
               user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               incident_id TEXT REFERENCES incidents(id) ON DELETE CASCADE,
               kind        TEXT NOT NULL,
               actor_id    TEXT,
               n           INTEGER NOT NULL DEFAULT 0,
               created_at  INTEGER NOT NULL,
               read_at     INTEGER,
               UNIQUE (incident_id, user_id, kind, n)
           )""",
        "CREATE INDEX notifications_user ON notifications (user_id, created_at)",
        # 채널별 전달 시도 (지금은 문자 'sms' 만, 모의 발송). simulated = 실제로 보내지 않음
        """CREATE TABLE notification_deliveries (
               id              INTEGER PRIMARY KEY AUTOINCREMENT,
               notification_id TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
               channel         TEXT NOT NULL CHECK (channel IN ('sms')),
               status          TEXT NOT NULL CHECK (status IN ('pending', 'retry', 'simulated', 'sent', 'failed')),
               provider        TEXT,
               body            TEXT NOT NULL,
               attempts        INTEGER NOT NULL DEFAULT 0,
               next_attempt_at INTEGER,
               last_error      TEXT,
               provider_ref    TEXT,
               created_at      INTEGER NOT NULL,
               updated_at      INTEGER NOT NULL,
               UNIQUE (notification_id, channel)
           )""",
        "CREATE INDEX notification_deliveries_due ON notification_deliveries (status, next_attempt_at)",
        # 옛 감지 프로그램(/api/events 의 device_id)을 집에 연결: 관리자가 legacy_devices.py 로 등록한 것만
        """CREATE TABLE legacy_device_homes (
               device_id  TEXT PRIMARY KEY,
               home_id    TEXT NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
               location   TEXT NOT NULL,
               created_at REAL NOT NULL
           )""",
    ]),
    (7, "옛 감지 기기 처리 방식·텔레그램을 새 사고의 알림 수단으로 (legacy_devices.py, alerts.py)", [
        # incident = 새 사고만 (옛 타이머·텔레그램 버튼 알림·옛 모의 신고는 시작하지 않음), both = 두 흐름 모두.
        # 이미 등록된 줄은 지금 동작(두 흐름)을 그대로 두도록 both, 새 등록의 기본값은 legacy_devices.py 가 incident 로 정함
        """ALTER TABLE legacy_device_homes ADD COLUMN mode TEXT NOT NULL DEFAULT 'both'
           CHECK (mode IN ('incident', 'both'))""",
        # 어느 그룹의 사고 알림을 어느 텔레그램 대화방에 보낼지 (관리자가 legacy_devices.py 로 등록)
        """CREATE TABLE telegram_routes (
               group_id   TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
               chat_id    TEXT NOT NULL,
               created_at REAL NOT NULL,
               PRIMARY KEY (group_id, chat_id)
           )""",
        # 사고 알림의 텔레그램 전달 (사고·대화방·종류·회차마다 한 번). simulated = 가짜 발송기 (실제로 보내지 않음)
        """CREATE TABLE telegram_deliveries (
               id              INTEGER PRIMARY KEY AUTOINCREMENT,
               incident_id     TEXT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
               chat_id         TEXT NOT NULL,
               kind            TEXT NOT NULL,
               n               INTEGER NOT NULL DEFAULT 0,
               status          TEXT NOT NULL CHECK (status IN ('pending', 'retry', 'simulated', 'sent', 'failed')),
               body            TEXT NOT NULL,
               attempts        INTEGER NOT NULL DEFAULT 0,
               next_attempt_at INTEGER,
               last_error      TEXT,
               created_at      INTEGER NOT NULL,
               updated_at      INTEGER NOT NULL,
               UNIQUE (incident_id, chat_id, kind, n)
           )""",
        "CREATE INDEX telegram_deliveries_due ON telegram_deliveries (status, next_attempt_at)",
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


def _use_wal(conn):
    """Switch to WAL once. The switch needs the whole database for a moment and SQLite does not wait for it
    (busy_timeout does not apply), so when another server process is starting at the same time, retry briefly."""
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000
    while True:
        try:
            if conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                conn.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


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
        _use_wal(conn)
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
                # 위에서 목록을 읽은 뒤 다른 서버 프로세스가 먼저 적용했을 수 있으므로,
                # 쓰기 잠금(BEGIN IMMEDIATE)을 잡은 뒤 다시 확인하고 아직일 때만 적용
                if conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone():
                    continue
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
