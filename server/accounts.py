"""Accounts for the family web app (/app/next): sign-up, log-in sessions, family groups and invite codes.

Stage B. Uses the SQLite database from db.py (tables added by migration 2). Nothing here touches the
older system (events.json, residents.json, access_token.txt, Telegram); detectors, the PC dashboard
and the Android app keep using the shared access token.

Security choices
  - passwords: hashlib.scrypt with a random salt per user; the plain password is never stored or logged
  - sessions: random token in an HttpOnly cookie; only its SHA-256 hash is stored, so a copy of the
    database cannot be used to log in
  - brute force: failed log-ins are limited per phone number and per IP address; failed invite codes
    per user; sign-ups per IP address
  - groups: every group operation uses the group of the logged-in user (from the session), never a
    group id sent by the browser, so one family cannot read or change another family's group
SMS verification and password reset are not part of this stage.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

import db

# ---- 조정 가능한 설정값 ----
SESSION_DAYS = 30                  # 로그인 유지 기간
INVITE_HOURS = 24                  # 초대 코드 유효 시간
PASSWORD_MIN, PASSWORD_MAX = 8, 64
NAME_MIN, NAME_MAX = 2, 20
# 실패 횟수 제한: (최대 실패 횟수, 기간(초))
LOGIN_LIMIT_PER_PHONE = (5, 15 * 60)
LOGIN_LIMIT_PER_IP = (30, 15 * 60)
JOIN_LIMIT_PER_USER = (10, 15 * 60)
SIGNUP_LIMIT_PER_IP = (20, 60 * 60)
# scrypt 강도 (n=2^14, r=8 은 약 16MB 메모리를 씀)
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 14, 8, 1, 32
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 0/O, 1/I 제외 (젠스파크 화면과 같음)
INVITE_LENGTH = 6



class AccountError(Exception):
    """A request the user can fix (or must wait for). message is shown to the user as is."""

    def __init__(self, status, message, field=None, retry_after=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.field = field
        self.retry_after = retry_after


# ---- 입력값 ----
def normalize_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if re.fullmatch(r"01\d{8,9}", digits) else None


def format_phone(digits):
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def password_problem(password):
    """'' if the password follows the rule, else the message (same rule as the sign-up screen)."""
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자로 입력해 주세요."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "비밀번호에 영문과 숫자를 모두 넣어 주세요."
    return ""


# ---- 비밀번호 해시 ----
def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# 없는 번호로 로그인할 때도 비슷한 시간이 걸리게 해서 가입 여부를 응답 시간으로 알 수 없게 함
_DUMMY_HASH = hash_password("dummy-password-1")


# ---- 실패 횟수 제한 ----
def _retry_after(conn, key, limit, now):
    """Seconds to wait if key already failed `limit` times in the window, else 0."""
    count, window = limit
    rows = conn.execute("SELECT at FROM auth_failures WHERE key = ? AND at > ? ORDER BY at",
                        (key, now - window)).fetchall()
    if len(rows) < count:
        return 0
    return max(1, int(rows[-count][0] + window - now) + 1)


def _record_failure(conn, key, now):
    conn.execute("INSERT INTO auth_failures (key, at) VALUES (?, ?)", (key, now))


def _clear_failures(conn, key):
    conn.execute("DELETE FROM auth_failures WHERE key = ?", (key,))


def _check_limit(conn, key, limit, now, message):
    wait = _retry_after(conn, key, limit, now)
    if wait:
        minutes = max(1, (wait + 59) // 60)
        raise AccountError(429, message.format(minutes=minutes), retry_after=wait)


def _new_id(prefix):
    return f"{prefix}_{secrets.token_hex(8)}"


def _transaction(conn):
    return db.transaction(conn)


# ---- 가입 · 로그인 · 로그아웃 ----
def signup(conn, name, phone, password, ip, now=None):
    """Create an account. Returns the new user id. Raises AccountError for invalid input."""
    now = time.time() if now is None else now
    name = (name or "").strip()
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise AccountError(400, "이름을 2~20자로 입력해 주세요.", "name")
    digits = normalize_phone(phone)
    if not digits:
        raise AccountError(400, "휴대전화 번호를 정확히 입력해 주세요.", "phone")
    problem = password_problem(password)
    if problem:
        raise AccountError(400, problem, "password")
    with _transaction(conn):
        _check_limit(conn, f"signup-ip:{ip}", SIGNUP_LIMIT_PER_IP, now,
                     "가입 시도가 너무 많아요. {minutes}분 뒤 다시 시도해 주세요.")
        if conn.execute("SELECT 1 FROM users WHERE phone = ?", (digits,)).fetchone():
            raise AccountError(409, "이미 가입된 휴대전화 번호예요. 로그인해 주세요.", "phone")
        user_id = _new_id("u")
        conn.execute("INSERT INTO users (id, name, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, name, digits, hash_password(password), now))
        # 가입도 횟수에 넣어 한 곳에서 계정을 대량으로 만들지 못하게 함
        _record_failure(conn, f"signup-ip:{ip}", now)
    return user_id


def authenticate(conn, phone, password, ip, now=None):
    """Check phone + password. Returns the user id. Raises AccountError (401 wrong, 429 too many tries)."""
    now = time.time() if now is None else now
    digits = normalize_phone(phone) or ""
    phone_key, ip_key = f"login-phone:{digits}", f"login-ip:{ip}"
    wait_message = "로그인 시도가 너무 많아요. {minutes}분 뒤 다시 시도해 주세요."
    _check_limit(conn, phone_key, LOGIN_LIMIT_PER_PHONE, now, wait_message)
    _check_limit(conn, ip_key, LOGIN_LIMIT_PER_IP, now, wait_message)
    row = conn.execute("SELECT id, password_hash FROM users WHERE phone = ?", (digits,)).fetchone() if digits else None
    ok = verify_password(password or "", row["password_hash"] if row else _DUMMY_HASH) and row is not None
    with _transaction(conn):
        if not ok:
            _record_failure(conn, phone_key, now)
            _record_failure(conn, ip_key, now)
        else:
            _clear_failures(conn, phone_key)
    if not ok:
        raise AccountError(401, "휴대전화 번호 또는 비밀번호가 맞지 않아요.", "password")
    return row["id"]


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(conn, user_id, now=None):
    """Start a log-in session. Returns the cookie value (only its hash is stored)."""
    now = time.time() if now is None else now
    token = secrets.token_urlsafe(32)
    with _transaction(conn):
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (_token_hash(token), user_id, now, now + SESSION_DAYS * 86400))
    return token


def session_user(conn, token, now=None):
    """User id of a valid session cookie, else None."""
    if not token or len(token) > 200:
        return None
    now = time.time() if now is None else now
    row = conn.execute("SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                       (_token_hash(token), now)).fetchone()
    return row["user_id"] if row else None


def end_session(conn, token):
    if token and len(token) <= 200:
        with _transaction(conn):
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ---- 그룹 · 초대 ----
def _user(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise AccountError(401, "다시 로그인해 주세요.")
    return row


def _new_invite_code(conn):
    while True:
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))
        if not conn.execute("SELECT 1 FROM invites WHERE code = ?", (code,)).fetchone():
            return code


def _issue_invite(conn, group_id, user_id, now):
    # 그룹마다 코드 1개: 새로 만들면 예전 코드는 바로 쓸 수 없게 됨
    conn.execute("DELETE FROM invites WHERE group_id = ?", (group_id,))
    conn.execute("INSERT INTO invites (group_id, code, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                 (group_id, _new_invite_code(conn), user_id, now, now + INVITE_HOURS * 3600))


def create_group(conn, user_id, now=None):
    now = time.time() if now is None else now
    with _transaction(conn):
        me = _user(conn, user_id)
        if me["group_id"]:
            raise AccountError(409, "이미 가족 그룹에 속해 있어요.")
        group_id = _new_id("g")
        conn.execute("INSERT INTO groups (id, name, created_by, created_at) VALUES (?, ?, ?, ?)",
                     (group_id, f"{me['name']}님의 가족", user_id, now))
        conn.execute("UPDATE users SET group_id = ? WHERE id = ?", (group_id, user_id))
        _issue_invite(conn, group_id, user_id, now)
    return group_id


def regenerate_invite(conn, user_id, now=None):
    now = time.time() if now is None else now
    with _transaction(conn):
        me = _user(conn, user_id)
        if not me["group_id"]:
            raise AccountError(409, "먼저 가족 그룹을 만들거나 참여해 주세요.")
        _issue_invite(conn, me["group_id"], user_id, now)


def join_group(conn, user_id, code, now=None):
    """Join the group of a valid invite code. Raises AccountError (400 bad/expired code, 429 too many tries)."""
    now = time.time() if now is None else now
    code = re.sub(r"\s+", "", str(code or "")).upper()
    key = f"join-user:{user_id}"
    _check_limit(conn, key, JOIN_LIMIT_PER_USER, now, "코드 입력 시도가 너무 많아요. {minutes}분 뒤 다시 시도해 주세요.")
    with _transaction(conn):
        me = _user(conn, user_id)
        if me["group_id"]:
            raise AccountError(409, "이미 가족 그룹에 속해 있어요. 다른 그룹에 참여하려면 먼저 그룹에서 나가 주세요.")
        invite = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone() if code else None
        if not invite or invite["expires_at"] <= now:
            _record_failure(conn, key, now)
            message = "만료된 초대 코드예요. 새 코드를 요청해 주세요." if invite else "초대 코드를 확인해 주세요."
            error = AccountError(400, message, "code")
        else:
            conn.execute("UPDATE users SET group_id = ?, onboarded = 0 WHERE id = ?", (invite["group_id"], user_id))
            _clear_failures(conn, key)
            error = None
    if error:
        raise error
    return invite["group_id"]


def _delete_group_if_empty(conn, group_id):
    # 아무도 남지 않은 그룹은 초대 코드·집과 함께 지움 (invites, homes 는 ON DELETE CASCADE)
    if group_id and not conn.execute("SELECT 1 FROM users WHERE group_id = ?", (group_id,)).fetchone():
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))


def leave_group(conn, user_id):
    """Leave the group. Like the Genspark design, the group-shared profile goes with it: detection-target
    flag, health information and home links. If nobody is left, the group and its homes are deleted."""
    with _transaction(conn):
        me = _user(conn, user_id)
        group_id = me["group_id"]
        if not group_id:
            return
        conn.execute("DELETE FROM home_members WHERE user_id = ?", (user_id,))
        conn.execute("""UPDATE users SET group_id = NULL, onboarded = 0, is_target = 0,
                        birth = NULL, conditions = NULL, medications = NULL WHERE id = ?""", (user_id,))
        _delete_group_if_empty(conn, group_id)


def withdraw(conn, user_id, password, ip, now=None):
    """Delete the account after checking the password again. All or nothing (one transaction).

    Deleted: the user row (profile, health info, password hash), its sessions and home links (ON DELETE
    CASCADE), and failure/count records that contain the phone number or user id. If the user was the last member,
    the group, its invite and its homes are deleted too; otherwise the group, homes and other members stay.
    The new database has no incident/report records yet (stage D); events.json is not linked to accounts.
    """
    now = time.time() if now is None else now
    me = _user(conn, user_id)
    phone_key = f"login-phone:{me['phone']}"
    wait_message = "비밀번호 확인 시도가 너무 많아요. {minutes}분 뒤 다시 시도해 주세요."
    _check_limit(conn, phone_key, LOGIN_LIMIT_PER_PHONE, now, wait_message)
    if not verify_password(password or "", me["password_hash"]):
        with _transaction(conn):
            _record_failure(conn, phone_key, now)
        raise AccountError(401, "비밀번호가 맞지 않아요.", "password")
    with _transaction(conn):
        me = _user(conn, user_id)
        group_id = me["group_id"]
        conn.execute("DELETE FROM auth_failures WHERE key IN (?, ?, ?)",
                     (phone_key, f"join-user:{user_id}", f"address-user:{user_id}"))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        _delete_group_if_empty(conn, group_id)


def set_onboarded(conn, user_id, onboarded):
    with _transaction(conn):
        _user(conn, user_id)
        conn.execute("UPDATE users SET onboarded = ? WHERE id = ?", (1 if onboarded else 0, user_id))


# ---- 화면에 보낼 상태 (젠스파크 store.js 형식) ----
DEFAULT_PREFS = {"device": True, "member": True, "home": True}


def _json_list(text):
    # NULL = 아직 입력 안 함(None), '[]' = 없음
    if text is None:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def _prefs(text):
    prefs = dict(DEFAULT_PREFS)
    try:
        saved = json.loads(text) if text else {}
    except ValueError:
        saved = {}
    if isinstance(saved, dict):
        prefs.update({k: bool(v) for k, v in saved.items() if k in DEFAULT_PREFS})
    return prefs


def _person(row, home_ids=()):
    # phoneCamera(내 폰 카메라 감지)는 카메라 단계에서 저장. 지금은 항상 꺼짐
    return {
        "id": row["id"], "name": row["name"], "phone": format_phone(row["phone"]), "email": "",
        "groupId": row["group_id"], "onboarded": bool(row["onboarded"]),
        "isTarget": bool(row["is_target"]), "birth": row["birth"],
        "conditions": _json_list(row["conditions"]), "medications": _json_list(row["medications"]),
        "homeIds": list(home_ids), "phoneCamera": False, "prefs": _prefs(row["prefs"]),
    }


def _home(row):
    # centralPw/doorPw: 현관 비밀번호 등록 여부. 저장 기능은 H단계라 지금은 항상 '미등록'
    return {"id": row["id"], "groupId": row["group_id"], "address": row["address"],
            "centralPw": False, "doorPw": False}


def empty_state(now=None):
    now_ms = int((time.time() if now is None else now) * 1000)
    return {
        "version": 2, "live": True, "anchoredAt": now_ms,
        "clock": {"realBase": now_ms, "virtBase": now_ms, "speed": 1},
        "groups": [], "people": [], "homes": [], "devices": [],
        "incidents": [], "history": [], "notifs": [],
    }


def state_for(conn, user_id, now=None):
    """Only the logged-in user's own record and, if any, their own group, its members and its homes."""
    state = empty_state(now)
    me = _user(conn, user_id)
    if not me["group_id"]:
        state["people"] = [_person(me)]
        return state
    group = conn.execute("SELECT * FROM groups WHERE id = ?", (me["group_id"],)).fetchone()
    invite = conn.execute("SELECT * FROM invites WHERE group_id = ?", (me["group_id"],)).fetchone()
    members = conn.execute("SELECT * FROM users WHERE group_id = ? ORDER BY created_at", (me["group_id"],)).fetchall()
    state["groups"] = [{
        "id": group["id"], "name": group["name"],
        "invite": None if not invite else {
            "code": invite["code"], "createdAt": int(invite["created_at"] * 1000),
            "expiresAt": int(invite["expires_at"] * 1000), "createdBy": invite["created_by"],
        },
    }]
    homes = conn.execute("SELECT * FROM homes WHERE group_id = ? ORDER BY created_at", (me["group_id"],)).fetchall()
    links = {}
    for row in conn.execute("""SELECT hm.user_id, hm.home_id FROM home_members hm JOIN homes h ON h.id = hm.home_id
                               WHERE h.group_id = ? ORDER BY hm.linked_at""", (me["group_id"],)):
        links.setdefault(row["user_id"], []).append(row["home_id"])
    state["people"] = [_person(m, links.get(m["id"], ())) for m in members]
    state["homes"] = [_home(h) for h in homes]
    return state
