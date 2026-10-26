"""Detection devices (PC detector program, detection phone) connected to a home from the app.

How a device is connected:
  1. A family member linked to the home asks the app for a pairing code (type + location). 6 characters, 10 minutes, once.
  2. The device sends the code once (POST /api/v2/device/pair) and gets its own device token. Only the token's hash
     is stored (like login sessions); deleting the device in the app makes the token useless at once.
  3. With the token the device sends a status signal every minute (camera OK or not) and its falls with the
     silhouette photo. A fall creates the home's incident directly (the old /api/events flow is not used).

The status shown in the app is computed from the stored times, never stored:
  off           a family member turned detection off (the device is told in the status-signal answer)
  disconnected  no signal yet, no signal for OFFLINE_AFTER_MS, or the device reports the camera is not working
  ok            otherwise
Test falls from a device make no incident and no alert: only the time is shown on the device screen.
The old shared-token API (/api/events) and the admin registration (legacy_devices.py) are unchanged.
"""
import hashlib
import re
import secrets
import time

import accounts
import db
import incidents
from accounts import AccountError

TYPES = ("pc", "phone")
PAIR_MINUTES = 10
PAIR_CODE_LENGTH = 6
PAIR_LIMIT_PER_IP = (10, 15 * 60)       # 틀린 연결 코드 (같은 주소에서 15분에 10번)
HEARTBEAT_SECONDS = 60                  # 기기가 상태 신호를 보내는 간격 (기기에 알려 줌)
OFFLINE_AFTER_MS = 3 * 60 * 1000        # 이보다 오래 신호가 없으면 '연결 끊김'
TOKEN_MAX = 200
APP_VERSION_MAX = 40


def now_ms():
    return int(time.time() * 1000)


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _clean_type(value):
    if value not in TYPES:
        raise AccountError(400, "기기 종류를 골라 주세요.", "type")
    return value


def _linked_home(conn, user_id, home_id, what):
    import people   # people 이 accounts 를 쓰므로 함수 안에서 불러옴 (door_codes.py 와 같은 방식)
    me = people._my_group(conn, user_id)
    home = people._group_home(conn, me, home_id)
    if not people._is_linked(conn, home["id"], user_id):
        raise AccountError(403, f"이 집에 연결된 가족만 기기를 {what}할 수 있어요.", "home")
    return home


def _my_device(conn, user_id, device_id, what):
    """A device of the user's own group (other groups: 404, like a missing one) whose home the user is linked to."""
    import people
    me = people._my_group(conn, user_id)
    row = conn.execute("SELECT * FROM devices WHERE id = ? AND group_id = ?",
                       (str(device_id or ""), me["group_id"])).fetchone()
    if not row:
        raise AccountError(404, "기기를 찾을 수 없어요.", "device")
    _linked_home(conn, user_id, row["home_id"], what)
    return row


# ---- 앱: 연결 코드 · 이름/위치 · 켜기/끄기 · 삭제 ----
def start_pairing(conn, user_id, home_id, type_, location, now=None):
    """New pairing code for a home. Returns {code, expiresAt, type, location}."""
    now = now_ms() if now is None else now
    type_ = _clean_type(type_)
    location = incidents.clean_location(location)
    with db.transaction(conn):
        home = _linked_home(conn, user_id, home_id, "추가")
        conn.execute("DELETE FROM device_pairings WHERE expires_at <= ? OR used_at IS NOT NULL", (now,))
        while True:
            code = "".join(secrets.choice(accounts.INVITE_ALPHABET) for _ in range(PAIR_CODE_LENGTH))
            if not conn.execute("SELECT 1 FROM device_pairings WHERE code = ?", (code,)).fetchone():
                break
        expires = now + PAIR_MINUTES * 60 * 1000
        conn.execute("""INSERT INTO device_pairings (code, home_id, type, location, created_by, created_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""", (code, home["id"], type_, location, user_id, now, expires))
    return {"code": code, "expiresAt": expires, "type": type_, "location": location}


def update(conn, user_id, device_id, location=None, enabled=None, now=None):
    now = now_ms() if now is None else now
    with db.transaction(conn):
        row = _my_device(conn, user_id, device_id, "설정")
        if location is not None:
            conn.execute("UPDATE devices SET location = ? WHERE id = ?", (incidents.clean_location(location), row["id"]))
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise AccountError(400, "감지 켜기/끄기 값을 확인해 주세요.", "enabled")
            if int(enabled) != row["enabled"]:
                conn.execute("UPDATE devices SET enabled = ?, enabled_at = ? WHERE id = ?", (int(enabled), now, row["id"]))


def remove(conn, user_id, device_id):
    """Delete the device: its token stops working at once."""
    with db.transaction(conn):
        row = _my_device(conn, user_id, device_id, "삭제")
        conn.execute("DELETE FROM devices WHERE id = ?", (row["id"],))


# ---- 기기: 연결 · 인증 · 상태 신호 · 낙상 ----
def pair(conn, code, ip, app_version=None, now=None):
    """The device sends the pairing code once. Returns {deviceId, deviceToken, type, location, heartbeatSeconds}."""
    now = now_ms() if now is None else now
    code = re.sub(r"\s+", "", str(code or "")).upper()
    key = f"pair-ip:{ip}"
    accounts._check_limit(conn, key, PAIR_LIMIT_PER_IP, now / 1000,
                          "연결 코드 입력 시도가 너무 많아요. {minutes}분 뒤 다시 시도해 주세요.")
    with db.transaction(conn):
        row = conn.execute("SELECT p.*, h.group_id FROM device_pairings p JOIN homes h ON h.id = p.home_id WHERE p.code = ?",
                           (code,)).fetchone() if code else None
        if not row or row["used_at"] is not None or row["expires_at"] <= now:
            accounts._record_failure(conn, key, now / 1000)
            error = AccountError(400, "만료된 연결 코드예요. 앱에서 새 코드를 받아 주세요." if row else "연결 코드를 확인해 주세요.", "code")
        else:
            error = None
            device_id = f"d_{secrets.token_hex(8)}"
            token = secrets.token_urlsafe(32)
            conn.execute("""INSERT INTO devices (id, group_id, home_id, type, location, enabled, enabled_at, token_hash,
                                                 created_by, created_at, app_version)
                            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
                         (device_id, row["group_id"], row["home_id"], row["type"], row["location"], now,
                          _token_hash(token), row["created_by"], now, _clean_version(app_version)))
            conn.execute("UPDATE device_pairings SET used_at = ?, device_id = ? WHERE code = ?", (now, device_id, code))
    if error:
        raise error
    return {"deviceId": device_id, "deviceToken": token, "type": row["type"], "location": row["location"],
            "heartbeatSeconds": HEARTBEAT_SECONDS}


def _clean_version(value):
    return value.strip()[:APP_VERSION_MAX] if isinstance(value, str) and value.strip() else None


def authenticate(conn, authorization):
    """The device of an 'Authorization: Bearer <device token>' header, else 401."""
    scheme, _, token = str(authorization or "").partition(" ")
    token = token.strip()
    row = None
    if scheme.lower() == "bearer" and 0 < len(token) <= TOKEN_MAX and token.isascii():
        row = conn.execute("SELECT * FROM devices WHERE token_hash = ?", (_token_hash(token),)).fetchone()
    if not row:
        raise AccountError(401, "기기 인증에 실패했어요. 앱에서 기기를 다시 연결해 주세요.")
    return row


def heartbeat(conn, device, camera_ok, app_version=None, now=None):
    """Status signal. Returns what the device must follow: detection on/off, location, signal interval."""
    now = now_ms() if now is None else now
    if not isinstance(camera_ok, bool):
        raise AccountError(400, "카메라 상태 값을 확인해 주세요.", "cameraOk")
    with db.transaction(conn):
        changed = device["camera_ok"] is None or bool(device["camera_ok"]) != camera_ok
        conn.execute("""UPDATE devices SET last_seen_at = ?, camera_ok = ?, camera_changed_at = ?,
                                           app_version = COALESCE(?, app_version) WHERE id = ?""",
                     (now, int(camera_ok), now if changed else device["camera_changed_at"],
                      _clean_version(app_version), device["id"]))
    return {"enabled": bool(device["enabled"]), "location": device["location"], "heartbeatSeconds": HEARTBEAT_SECONDS}


def seen(conn, device, now=None):
    """Any authenticated request is a sign of life."""
    with db.transaction(conn):
        conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (now_ms() if now is None else now, device["id"]))


def record_test(conn, device, now=None):
    now = now_ms() if now is None else now
    with db.transaction(conn):
        conn.execute("UPDATE devices SET last_test_at = ?, last_seen_at = ? WHERE id = ?", (now, now, device["id"]))


def photo_id(device, event_id):
    """Photo file id for a device's fall: fixed per (device, event) so a retry writes the same file, and one device
    can never name (overwrite) another device's photo."""
    return hashlib.sha256(f"{device['id']}:{event_id}".encode()).hexdigest()[:32]


def incident_for_fall(conn, device, event_id, now=None):
    """Incident of a real (not test) fall. The same event_id of the same device never makes a second incident."""
    incident_id, _created = incidents.create(conn, device["home_id"], device["location"], "device",
                                             source_ref=device["id"], dedupe_key=f"device:{device['id']}:{event_id}",
                                             now=now)
    return incident_id


# ---- 화면에 보낼 상태 (store.js 의 device 형식 + 실제 상태 정보) ----
def _view(row, now):
    if not row["enabled"]:
        status, problem, since = "off", None, row["enabled_at"]
    elif row["last_seen_at"] is None:
        status, problem, since = "disconnected", "never", row["created_at"]
    elif now - row["last_seen_at"] > OFFLINE_AFTER_MS:
        status, problem, since = "disconnected", "offline", row["last_seen_at"]
    elif row["camera_ok"] == 0:
        status, problem, since = "disconnected", "camera", row["camera_changed_at"] or row["last_seen_at"]
    else:
        status, problem, since = "ok", None, row["last_seen_at"]
    return {"id": row["id"], "homeId": row["home_id"], "type": row["type"], "location": row["location"],
            "status": status, "problem": problem, "since": since, "createdAt": row["created_at"],
            "lastSeenAt": row["last_seen_at"], "lastTestAt": row["last_test_at"], "live": True}


def state_part(conn, group_id, now=None):
    now = now_ms() if now is None else now
    return [_view(r, now) for r in conn.execute("SELECT * FROM devices WHERE group_id = ? ORDER BY created_at",
                                                (group_id,))]
