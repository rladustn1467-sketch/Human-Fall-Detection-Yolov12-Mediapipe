"""Bridge from the old fall API (/api/events, PC dashboard and Android test app) to new web app incidents.

The old API has one shared token and a free-text device_id, so it cannot tell which group's home a fall
belongs to. A fall becomes an incident ONLY when an administrator registered that device_id for a home here.
Unregistered device ids and test events (is_test) never create incidents and keep the old flow unchanged.

Mode of a registered device:
  incident  only the new incident (main.py hands the old event over: no old timer, no old Telegram alerts
            with buttons, no old report simulation). Telegram gets the incident's alerts through alerts.py
            (text only) for the groups registered with 'telegram add'.
  both      the old flow and the new incident side by side (for comparison; they do not know each other)

Administrator commands (from the server folder, with the server venv; the database is FALL_DB_PATH or
server/fall.db):
  venv\\Scripts\\python.exe legacy_devices.py list
  venv\\Scripts\\python.exe legacy_devices.py add <device_id> <home_id> <location> [incident|both]   (기본 incident)
  venv\\Scripts\\python.exe legacy_devices.py remove <device_id>
  venv\\Scripts\\python.exe legacy_devices.py telegram list
  venv\\Scripts\\python.exe legacy_devices.py telegram add <group_id> <chat_id>
  venv\\Scripts\\python.exe legacy_devices.py telegram remove <group_id> <chat_id>
"""
import os
import sys
import time
from pathlib import Path

import db
import incidents
from accounts import AccountError

DEVICE_ID_MAX = 64
MODES = ("incident", "both")
CHAT_ID_MAX = 64


def _clean_device_id(value):
    device_id = value.strip() if isinstance(value, str) else ""
    if not device_id or len(device_id) > DEVICE_ID_MAX:
        raise AccountError(400, f"기기 이름을 1~{DEVICE_ID_MAX}자로 입력해 주세요.", "device_id")
    return device_id


def add(conn, device_id, home_id, location, mode="incident", now=None):
    device_id = _clean_device_id(device_id)
    location = incidents.clean_location(location)
    if mode not in MODES:
        raise AccountError(400, "처리 방식은 incident 또는 both 예요.", "mode")
    with db.transaction(conn):
        if not conn.execute("SELECT 1 FROM homes WHERE id = ?", (home_id,)).fetchone():
            raise AccountError(404, "집을 찾을 수 없어요.", "home")
        conn.execute("""INSERT INTO legacy_device_homes (device_id, home_id, location, mode, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET home_id = excluded.home_id, location = excluded.location,
                                                            mode = excluded.mode""",
                     (device_id, home_id, location, mode, time.time() if now is None else now))


def remove(conn, device_id):
    with db.transaction(conn):
        return conn.execute("DELETE FROM legacy_device_homes WHERE device_id = ?", (device_id,)).rowcount


def mode_for(conn, device_id):
    """'incident' / 'both' for a registered device, None for an unregistered one (old flow only)."""
    row = conn.execute("SELECT mode FROM legacy_device_homes WHERE device_id = ?", (device_id,)).fetchone()
    return row["mode"] if row else None


def entries(conn):
    return [dict(r) for r in conn.execute("""SELECT l.device_id, l.home_id, l.location, l.mode, h.address, h.group_id
                                              FROM legacy_device_homes l JOIN homes h ON h.id = l.home_id
                                              ORDER BY l.device_id""")]


def incident_for_event(conn, device_id, event_id, is_test, now=None):
    """Called by /api/events. Returns the incident id, or None when the device is not registered or the event
    is a test. The same event_id never creates a second incident."""
    if is_test:
        return None
    row = conn.execute("SELECT home_id, location FROM legacy_device_homes WHERE device_id = ?",
                       (device_id,)).fetchone()
    if not row:
        return None
    incident_id, _created = incidents.create(conn, row["home_id"], row["location"], "legacy", source_ref=device_id,
                                             dedupe_key=f"legacy:{event_id}", now=now)
    return incident_id


# ---- 텔레그램: 그룹의 사고 알림을 받을 대화방 (alerts.py 가 글자 알림만 보냄, 버튼 없음) ----
def _clean_chat_id(value):
    chat_id = value.strip() if isinstance(value, str) else ""
    if not chat_id or len(chat_id) > CHAT_ID_MAX:
        raise AccountError(400, "텔레그램 대화방 id 를 확인해 주세요.", "chat_id")
    return chat_id


def add_telegram(conn, group_id, chat_id, now=None):
    chat_id = _clean_chat_id(chat_id)
    with db.transaction(conn):
        if not conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
            raise AccountError(404, "그룹을 찾을 수 없어요.", "group")
        conn.execute("INSERT OR IGNORE INTO telegram_routes (group_id, chat_id, created_at) VALUES (?, ?, ?)",
                     (group_id, chat_id, time.time() if now is None else now))


def remove_telegram(conn, group_id, chat_id):
    with db.transaction(conn):
        return conn.execute("DELETE FROM telegram_routes WHERE group_id = ? AND chat_id = ?",
                            (group_id, chat_id)).rowcount


def telegram_entries(conn):
    return [dict(r) for r in conn.execute("SELECT group_id, chat_id FROM telegram_routes ORDER BY group_id, chat_id")]


def _main(argv):
    path = Path(os.environ.get("FALL_DB_PATH") or Path(__file__).parent / "fall.db")
    if not path.exists():
        print(f"데이터베이스가 없어요: {path}")
        return 1
    with db.session(path) as conn:
        try:
            if argv[:1] == ["list"] and len(argv) == 1:
                rows = entries(conn)
                for r in rows:
                    print(f"{r['device_id']}\t{r['home_id']}\t{r['location']}\t{r['mode']}\t{r['address'] or '(주소 없음)'}")
                print(f"{len(rows)}개")
            elif argv[:1] == ["add"] and len(argv) in (4, 5):
                mode = argv[4] if len(argv) == 5 else "incident"
                add(conn, argv[1], argv[2], argv[3], mode)
                print(f"등록했어요: {argv[1]} → {argv[2]} ({argv[3]}, {mode})")
            elif argv[:1] == ["remove"] and len(argv) == 2:
                print("삭제했어요" if remove(conn, argv[1]) else "등록되지 않은 기기예요")
            elif argv[:2] == ["telegram", "list"] and len(argv) == 2:
                rows = telegram_entries(conn)
                for r in rows:
                    print(f"{r['group_id']}\t{r['chat_id']}")
                print(f"{len(rows)}개")
            elif argv[:2] == ["telegram", "add"] and len(argv) == 4:
                add_telegram(conn, argv[2], argv[3])
                print(f"등록했어요: 그룹 {argv[2]} → 텔레그램 {argv[3]}")
            elif argv[:2] == ["telegram", "remove"] and len(argv) == 4:
                print("삭제했어요" if remove_telegram(conn, argv[2], argv[3]) else "등록되지 않은 대화방이에요")
            else:
                print(__doc__)
                return 2
        except AccountError as e:
            print(f"오류: {e.message}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
