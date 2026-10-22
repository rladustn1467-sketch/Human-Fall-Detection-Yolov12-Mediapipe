"""Bridge from the old fall API (/api/events, PC dashboard and Android test app) to new web app incidents.

The old API has one shared token and a free-text device_id, so it cannot tell which group's home a fall
belongs to. A fall becomes an incident ONLY when an administrator registered that device_id for a home here.
Unregistered device ids and test events (is_test) never create incidents. The old flow (events.json,
Telegram, report simulation) keeps working unchanged next to this.

Administrator commands (from the server folder, with the server venv; the database is FALL_DB_PATH or
server/fall.db):
  venv\\Scripts\\python.exe legacy_devices.py list
  venv\\Scripts\\python.exe legacy_devices.py add <device_id> <home_id> <location>
  venv\\Scripts\\python.exe legacy_devices.py remove <device_id>
"""
import os
import sys
import time
from pathlib import Path

import db
import incidents
from accounts import AccountError

DEVICE_ID_MAX = 64


def _clean_device_id(value):
    device_id = value.strip() if isinstance(value, str) else ""
    if not device_id or len(device_id) > DEVICE_ID_MAX:
        raise AccountError(400, f"기기 이름을 1~{DEVICE_ID_MAX}자로 입력해 주세요.", "device_id")
    return device_id


def add(conn, device_id, home_id, location, now=None):
    device_id = _clean_device_id(device_id)
    location = incidents.clean_location(location)
    with db.transaction(conn):
        if not conn.execute("SELECT 1 FROM homes WHERE id = ?", (home_id,)).fetchone():
            raise AccountError(404, "집을 찾을 수 없어요.", "home")
        conn.execute("""INSERT INTO legacy_device_homes (device_id, home_id, location, created_at) VALUES (?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET home_id = excluded.home_id, location = excluded.location""",
                     (device_id, home_id, location, time.time() if now is None else now))


def remove(conn, device_id):
    with db.transaction(conn):
        return conn.execute("DELETE FROM legacy_device_homes WHERE device_id = ?", (device_id,)).rowcount


def entries(conn):
    return [dict(r) for r in conn.execute("""SELECT l.device_id, l.home_id, l.location, h.address, h.group_id
                                              FROM legacy_device_homes l JOIN homes h ON h.id = l.home_id
                                              ORDER BY l.device_id""")]


def incident_for_event(conn, device_id, event_id, is_test, now=None):
    """Called by /api/events after the old flow saved the event. Returns the incident id, or None when the
    device is not registered or the event is a test. The same event_id never creates a second incident."""
    if is_test:
        return None
    row = conn.execute("SELECT home_id, location FROM legacy_device_homes WHERE device_id = ?",
                       (device_id,)).fetchone()
    if not row:
        return None
    incident_id, _created = incidents.create(conn, row["home_id"], row["location"], "legacy", source_ref=device_id,
                                             dedupe_key=f"legacy:{event_id}", now=now)
    return incident_id


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
                    print(f"{r['device_id']}\t{r['home_id']}\t{r['location']}\t{r['address'] or '(주소 없음)'}")
                print(f"{len(rows)}개")
            elif argv[:1] == ["add"] and len(argv) == 4:
                add(conn, argv[1], argv[2], argv[3])
                print(f"등록했어요: {argv[1]} → {argv[2]} ({argv[3]})")
            elif argv[:1] == ["remove"] and len(argv) == 2:
                print("삭제했어요" if remove(conn, argv[1]) else "등록되지 않은 기기예요")
            else:
                print(__doc__)
                return 2
        except AccountError as e:
            print(f"오류: {e.message}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
