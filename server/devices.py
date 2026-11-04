"""Detection devices (PC detector program, detection phone) connected to a home from the app.

How a device is connected:
  1. A family member linked to the home asks the app for a pairing code (type + location). 6 characters, 10 minutes, once.
  2. The device sends the code once (POST /api/v2/device/pair) and gets its own device token. Only the token's hash
     is stored (like login sessions); deleting the device in the app makes the token useless at once.
  3. With the token the device sends a status signal every minute (camera OK or not) and its falls with the
     silhouette photo. A fall creates the home's incident directly (the old /api/events flow is not used).

The status shown in the app is computed from the stored times, never stored:
  off           detection was turned off on the device itself (never remotely: the app can not change it)
  disconnected  no signal yet, no signal for OFFLINE_AFTER_MS, or the device reports the camera is not working
  ok            otherwise
Test falls from a device make no incident and no alert: only the time is shown on the device screen.
Device types: "phone" (this phone or a spare phone, the Android app) is the product device. "pc" (the PC detector
program) is a developer tool: pairing codes for it are issued only when the server runs with FD_DEV_DEVICES=1
(copy/test servers; never in the production .env). PC devices that are already connected keep working.
The old shared-token API (/api/events) and the admin registration (legacy_devices.py) are unchanged.
"""
import hashlib
import os
import re
import secrets
import time

import accounts
import alerts
import db
import incidents
from accounts import AccountError

TYPES = ("pc", "phone")                 # 저장되는 기기 종류 (DB CHECK 와 같음)
PRODUCT_TYPES = ("phone",)              # 사용자에게 제공하는 기기
DEV_TYPES = ("pc",)                     # 개발·시험 도구 (FD_DEV_DEVICES=1 인 서버에서만 연결 코드 발급)
PAIR_MINUTES = 10
PAIR_CODE_LENGTH = 6
PAIR_LIMIT_PER_IP = (10, 15 * 60)       # 틀린 연결 코드 (같은 주소에서 15분에 10번)
HEARTBEAT_SECONDS = 60                  # 기기가 상태 신호를 보내는 간격 (기기에 알려 줌)
OFFLINE_AFTER_MS = 3 * 60 * 1000        # 이보다 오래 신호가 없으면 '연결 끊김'
ALERT_AFTER_MS = 5 * 60 * 1000          # 문제가 이만큼 이어지면 가족에게 알림 (기기의 자동 복구 시간을 줌)
LOW_BATTERY_PERCENT = 15                # 충전 중이 아니고 이 이하면 가족에게 알림
BATTERY_OK_PERCENT = 25                 # 이만큼 회복하면 다시 알릴 수 있음 (경계에서 알림이 반복되지 않게)
TOKEN_MAX = 200
APP_VERSION_MAX = 40


def now_ms():
    return int(time.time() * 1000)


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def dev_devices():
    """True only on servers started with FD_DEV_DEVICES=1 (copy/test servers)."""
    return os.environ.get("FD_DEV_DEVICES", "").strip() == "1"


def pairing_types():
    return PRODUCT_TYPES + (DEV_TYPES if dev_devices() else ())


def _clean_type(value):
    if value not in pairing_types():
        raise AccountError(400, "기기 종류를 골라 주세요.", "type")
    return value


def _linked_home(conn, user_id, home_id, what):
    """The home if the user is its administrator (기기 추가·이름 변경·삭제는 집 관리자만, 사용자 결정 2026-10-30)."""
    import people   # people 이 accounts 를 쓰므로 함수 안에서 불러옴 (door_codes.py 와 같은 방식)
    return people.admin_home(conn, user_id, home_id, f"이 집의 관리자만 기기를 {what}할 수 있어요.")


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
def start_pairing(conn, user_id, home_id, type_, location, now=None, own_phone=False):
    """New pairing code for a home. Returns {code, expiresAt, type, location}. Administrators add any device. own_phone:
    a linked member connects the phone in their hand (사용자 결정 2026-11-04); that code only works for 'this phone'."""
    now = now_ms() if now is None else now
    type_ = _clean_type(type_)
    location = incidents.clean_location(location)
    with db.transaction(conn):
        home = _linked_member_home(conn, user_id, home_id) if own_phone else _linked_home(conn, user_id, home_id, "추가")
        return _new_code(conn, home["id"], type_, location, user_id, now, own_phone=own_phone)


def _linked_member_home(conn, user_id, home_id):
    import people   # people 이 accounts 를 쓰므로 함수 안에서 불러옴
    me = people._my_group(conn, user_id)
    home = people._group_home(conn, me, home_id)
    if not people._is_linked(conn, home["id"], user_id):
        raise AccountError(403, "이 집에 연결한 뒤 감지를 켤 수 있어요.", "home")
    return home


def _new_code(conn, home_id, type_, location, created_by, now, own_phone=False):
    """Inside a transaction: a new one-time pairing code (PAIR_MINUTES) for a home."""
    conn.execute("DELETE FROM device_pairings WHERE expires_at <= ? OR used_at IS NOT NULL", (now,))
    while True:
        code = "".join(secrets.choice(accounts.INVITE_ALPHABET) for _ in range(PAIR_CODE_LENGTH))
        if not conn.execute("SELECT 1 FROM device_pairings WHERE code = ?", (code,)).fetchone():
            break
    expires = now + PAIR_MINUTES * 60 * 1000
    conn.execute("""INSERT INTO device_pairings (code, home_id, type, location, created_by, created_at, expires_at, own_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (code, home_id, type_, location, created_by, now, expires, int(own_phone)))
    return {"code": code, "expiresAt": expires, "type": type_, "location": location}


def admin_pairing(conn, home_id, type_, location, now=None):
    """The server's administrator (command line on the server PC, legacy_devices.py pc-code): a pairing code for a
    home without the app. Used to move the old PC detection program (developer tool) to the device API on a server
    where the app does not offer PC devices (FD_DEV_DEVICES off)."""
    now = now_ms() if now is None else now
    if type_ not in PRODUCT_TYPES + DEV_TYPES:
        raise AccountError(400, "기기 종류를 골라 주세요.", "type")
    location = incidents.clean_location(location)
    with db.transaction(conn):
        if not conn.execute("SELECT 1 FROM homes WHERE id = ?", (home_id,)).fetchone():
            raise AccountError(404, "집을 찾을 수 없어요.", "home")
        return _new_code(conn, home_id, type_, location, None, now)


def update(conn, user_id, device_id, location=None, enabled=None, now=None):
    """From the app: only the location name. Detection on/off is never changed remotely (the device's own screen
    turns it on/off, set_enabled_by_device); a request that tries to is refused as a whole."""
    with db.transaction(conn):
        row = _my_device(conn, user_id, device_id, "설정")
        if enabled is not None:
            raise AccountError(403, "감지 켜기·끄기는 그 감지 기기에서 직접 할 수 있어요.", "enabled")
        if location is not None:
            conn.execute("UPDATE devices SET location = ? WHERE id = ?", (incidents.clean_location(location), row["id"]))


def remove(conn, user_id, device_id):
    """Delete the device: its token stops working at once."""
    with db.transaction(conn):
        row = _my_device(conn, user_id, device_id, "삭제")
        conn.execute("DELETE FROM devices WHERE id = ?", (row["id"],))
        alerts.tell_home(conn, row["home_id"], user_id, "감지 기기를 삭제했어요", now_ms())


# ---- 기기: 연결 · 인증 · 상태 신호 · 낙상 ----
def pair(conn, code, ip, app_version=None, now=None, mode=None):
    """The device sends the pairing code once. Returns {deviceId, deviceToken, type, location, heartbeatSeconds}.
    mode 'self' = the person's own phone ('이 휴대폰으로 감지'), which goes when that person is removed from the group."""
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
        elif row["own_phone"] and mode != "self":
            error = AccountError(400, "이 코드는 앱의 '이 휴대폰으로 감지하기'에서만 쓸 수 있어요.", "code")
        else:
            error = None
            device_id = f"d_{secrets.token_hex(8)}"
            token = secrets.token_urlsafe(32)
            conn.execute("""INSERT INTO devices (id, group_id, home_id, type, location, enabled, enabled_at, token_hash,
                                                 created_by, created_at, app_version, self_user_id)
                            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                         (device_id, row["group_id"], row["home_id"], row["type"], row["location"], now,
                          _token_hash(token), row["created_by"], now, _clean_version(app_version),
                          row["created_by"] if mode == "self" else None))
            conn.execute("UPDATE device_pairings SET used_at = ?, device_id = ? WHERE code = ?", (now, device_id, code))
            alerts.tell_home(conn, row["home_id"], row["created_by"], "감지 기기를 추가했어요", now)
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


def _clean_health(health):
    """Battery and heat as sent by the device. Unknown or wrong values are None: they must not stop the signal."""
    health = health or {}
    battery = health.get("battery")
    if not isinstance(battery, int) or isinstance(battery, bool) or not 0 <= battery <= 100:
        battery = None
    flag = lambda value: int(value) if isinstance(value, bool) else None
    return battery, flag(health.get("charging")), flag(health.get("hot"))


def heartbeat(conn, device, camera_ok, app_version=None, now=None, health=None):
    """Status signal. Returns what the device must follow: detection on/off, location, signal interval."""
    now = now_ms() if now is None else now
    if not isinstance(camera_ok, bool):
        raise AccountError(400, "카메라 상태 값을 확인해 주세요.", "cameraOk")
    battery, charging, hot = _clean_health(health)
    with db.transaction(conn):
        changed = device["camera_ok"] is None or bool(device["camera_ok"]) != camera_ok
        conn.execute("""UPDATE devices SET last_seen_at = ?, camera_ok = ?, camera_changed_at = ?,
                                           app_version = COALESCE(?, app_version),
                                           battery_percent = ?, charging = ?, hot = ? WHERE id = ?""",
                     (now, int(camera_ok), now if changed else device["camera_changed_at"],
                      _clean_version(app_version), battery, charging, hot, device["id"]))
    return {"enabled": bool(device["enabled"]), "location": device["location"], "heartbeatSeconds": HEARTBEAT_SECONDS}


def set_enabled_by_device(conn, device, enabled, now=None):
    """The device itself turns detection on/off (its own screen, or logout/withdrawal on that phone). This is the
    only way the flag changes; the app shows it (status 'off'). Returns the same answer as a status signal."""
    now = now_ms() if now is None else now
    if not isinstance(enabled, bool):
        raise AccountError(400, "감지 켜기/끄기 값을 확인해 주세요.", "enabled")
    with db.transaction(conn):
        if int(enabled) != device["enabled"]:
            conn.execute("UPDATE devices SET enabled = ?, enabled_at = ?, last_seen_at = ? WHERE id = ?",
                         (int(enabled), now, now, device["id"]))
        else:
            conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (now, device["id"]))
    return {"enabled": enabled, "location": device["location"], "heartbeatSeconds": HEARTBEAT_SECONDS}


def unpair_by_device(conn, device):
    """The device removes itself (its owner withdrew from the service on that phone): its token stops working."""
    with db.transaction(conn):
        conn.execute("DELETE FROM devices WHERE id = ?", (device["id"],))


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


def incident_for_fall(conn, device, event_id, now=None, age_ms=None):
    """Incident of a real (not test) fall. The same event_id of the same device never makes a second incident.
    age_ms: how long ago the phone saw it, when it could only send it later. At most the 60 s answer time counts: the
    family is then alerted at once and still has their full time, instead of an automatic report on arrival."""
    now = now_ms() if now is None else now
    late = age_ms if isinstance(age_ms, int) and not isinstance(age_ms, bool) and age_ms > 0 else 0
    incident_id, _created = incidents.create(conn, device["home_id"], device["location"], "device",
                                             source_ref=device["id"], dedupe_key=f"device:{device['id']}:{event_id}",
                                             now=now, detected_at=now - min(late, incidents.SELF_WINDOW_MS))
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
            "lastSeenAt": row["last_seen_at"], "lastTestAt": row["last_test_at"], "live": True,
            "battery": row["battery_percent"],
            "charging": None if row["charging"] is None else bool(row["charging"]),
            "hot": None if row["hot"] is None else bool(row["hot"])}


def watch(conn, server_started_at, now=None):
    """Background step: tell the family when a device that was working stops, and when it is back (setting 'device').
    A device turned off on purpose or never connected is no problem. The time counts from the server's start too:
    while the server was off no device could send signals, so it must not look as if they all stopped."""
    now = now_ms() if now is None else now
    for row in conn.execute("SELECT * FROM devices WHERE last_seen_at IS NOT NULL").fetchall():
        try:
            with db.transaction(conn):
                _watch_one(conn, row, server_started_at, now)
        except Exception as e:   # 기기 하나의 오류가 다른 기기를 막지 않게
            print(f"[device] 기기 {row['id']} 상태 확인 오류: {type(e).__name__}: {e}")


def _watch_one(conn, row, server_started_at, now):
    view = _view(row, now)
    problem = view["problem"] in ("offline", "camera")
    if problem and row["alerted_at"] is None:
        if now - max(view["since"], server_started_at) >= ALERT_AFTER_MS:
            conn.execute("UPDATE devices SET alerted_at = ? WHERE id = ?", (now, row["id"]))
            _tell_family(conn, row, "device_problem", now)
    elif not problem and row["alerted_at"] is not None:
        conn.execute("UPDATE devices SET alerted_at = NULL WHERE id = ?", (row["id"],))
        if view["status"] == "ok":   # 일부러 끈 것이면 더 알리지 않음
            _tell_family(conn, row, "device_back", now)
    _watch_battery(conn, row, view, now)


def _watch_battery(conn, row, view, now):
    if view["status"] != "ok" or row["battery_percent"] is None or row["charging"] is None:
        return
    if row["low_battery_alerted_at"] is None:
        if row["battery_percent"] <= LOW_BATTERY_PERCENT and not row["charging"]:
            conn.execute("UPDATE devices SET low_battery_alerted_at = ? WHERE id = ?", (now, row["id"]))
            _tell_family(conn, row, "device_low_battery", now)
    elif row["charging"] or row["battery_percent"] >= BATTERY_OK_PERCENT:
        conn.execute("UPDATE devices SET low_battery_alerted_at = NULL WHERE id = ?", (row["id"],))


def _tell_family(conn, row, kind, now):
    import push   # 보내기는 서버의 백그라운드 작업이 따로 (push.py)
    members = [r["id"] for r in conn.execute("SELECT id FROM users WHERE group_id = ?", (row["group_id"],))]
    users = alerts.wanting(conn, members, "device")
    alerts.record_place(conn, row["group_id"], users, kind, row["home_id"], row["location"], None, now)
    push.queue(conn, None, row["group_id"], users, kind, now)


def state_part(conn, group_id, now=None):
    now = now_ms() if now is None else now
    return [_view(r, now) for r in conn.execute("SELECT * FROM devices WHERE group_id = ? ORDER BY created_at",
                                                (group_id,))]
