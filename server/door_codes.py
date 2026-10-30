"""Door codes (중앙 현관 / 집 현관 비밀번호) of family homes, stored ENCRYPTED. Stage H.

Security rules (see also db.py migration 4):
  - AES-256-GCM (cryptography). A new random nonce for every save, and the ciphertext is bound to its home and
    kind (associated data), so a ciphertext copied to another home or kind does not decrypt.
  - The key is DOOR_CODE_KEY in server/.env (never in the database, code, logs or docs). Without a valid key
    nothing is saved: the request fails with 503. There is no plain-text fallback.
  - Nobody can read a code back through the API. Screens only get "registered or not". reveal() exists for a
    future emergency-report flow inside the server only (stage D/E) and is not connected to any endpoint.
  - Only people linked to a home of their own group may set, change or delete its codes (same rule as the
    address, people.py). Another group's home is answered like a missing one (404).
  - The code value never appears in errors, logs or the work record (home_events keeps who/when/what only).

Make a key:  server\\venv\\Scripts\\python.exe door_codes.py genkey   (prints a new key once; keep a safe copy)
"""
import base64
import hashlib
import re
import secrets
import sys
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import db
from accounts import AccountError

KINDS = {"central": "중앙 현관 비밀번호", "door": "집 현관 비밀번호"}
# 현관 출입 방식 (db.py 5번 변경). '없음'은 현관마다 다른 값: 중앙현관 없음 = absent, 집 현관 잠금장치 없음 = unlocked
METHODS = {"central": ("code", "key", "absent"), "door": ("code", "key", "unlocked")}
NOT_CODE = "이 현관의 출입 방식이 비밀번호가 아니에요. 출입 방식을 비밀번호로 바꾼 뒤 등록해 주세요."
CODE_RE = re.compile(r"^[0-9*#]{3,20}$")      # 숫자, *, # 만 3~20자
CODE_RULE = "현관 비밀번호는 숫자와 *, # 만 써서 3~20자로 입력해 주세요."
NO_KEY = "지금은 현관 비밀번호를 저장할 수 없어요. 서버 관리자에게 암호화 키 설정을 확인해 달라고 해 주세요."
KEY_BYTES = 32                                 # AES-256


class DoorCodeKeyError(Exception):
    """The configured key cannot decrypt a stored code (missing key or a different key)."""


class Key:
    def __init__(self, raw):
        self.aead = AESGCM(raw)
        # 어떤 키로 저장했는지 구분하는 표시 (키 해시의 앞부분이라 키를 알아낼 수 없음)
        self.key_id = hashlib.sha256(b"fd-door-code-key-id|" + raw).hexdigest()[:12]


def generate_key():
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def parse_key(value):
    """Return (Key or None, problem). problem: '' / 'missing' / 'invalid'. Never echoes the value."""
    text = (value or "").strip()
    if not text:
        return None, "missing"
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        return None, "invalid"
    if len(raw) != KEY_BYTES:
        return None, "invalid"
    return Key(raw), ""


# 서버가 켜질 때 main.py 가 configure() 로 한 번 설정
_key, _problem = None, "missing"


def configure(value):
    """Set the server key from DOOR_CODE_KEY. Returns a status line safe to print (no key material)."""
    global _key, _problem
    _key, _problem = parse_key(value)
    if _key:
        return f"켜짐 (키 표시 {_key.key_id})"
    if _problem == "missing":
        return "꺼짐 - server/.env 에 DOOR_CODE_KEY 가 없음 (등록 요청은 503, 평문 저장 안 함)"
    return "꺼짐 - DOOR_CODE_KEY 형식 오류 (32바이트 base64 키가 아님, 평문 저장 안 함)"


def current_key():
    return _key


# ---- 입력값 ----
def clean_kind(kind):
    if kind not in KINDS:
        raise AccountError(404, "알 수 없는 비밀번호 종류예요.")
    return kind


def clean_method(kind, value):
    if value not in METHODS[kind]:
        raise AccountError(400, "출입 방식을 다시 선택해 주세요.", "method")
    return value


def clean_code(value):
    # 값은 오류 메시지에 넣지 않음
    code = value if isinstance(value, str) else ""
    if not CODE_RE.match(code):
        raise AccountError(400, CODE_RULE, "code")
    return code


# ---- 암호화 ----
def _aad(home_id, kind):
    return f"fd-door-code|v1|{home_id}|{kind}".encode("utf-8")


def encrypt(key, home_id, kind, code):
    nonce = secrets.token_bytes(12)
    return nonce, key.aead.encrypt(nonce, code.encode("ascii"), _aad(home_id, kind))


def decrypt(key, home_id, kind, nonce, ciphertext):
    try:
        return key.aead.decrypt(nonce, ciphertext, _aad(home_id, kind)).decode("ascii")
    except InvalidTag:
        raise DoorCodeKeyError("decrypt failed")


# ---- 권한 (people.py 의 집 주소 수정과 같은 규칙) ----
def _linked_home(conn, user_id, home_id):
    """The home if the user is its administrator (현관 출입 방식·비밀번호는 집 관리자만, 사용자 결정 2026-10-30)."""
    import people   # people.finish_setup 이 이 모듈을 쓰므로 서로 불러올 때 순서 문제를 피함
    return people.admin_home(conn, user_id, home_id, "이 집의 관리자만 현관 정보를 바꿀 수 있어요.")


def _record(conn, home_id, actor_id, action, kind, now):
    conn.execute("INSERT INTO home_events (home_id, actor_id, action, kind, at) VALUES (?, ?, ?, ?, ?)",
                 (home_id, actor_id, action, kind, now))


def method_of(conn, home_id, kind):
    row = conn.execute("SELECT method FROM home_entrances WHERE home_id = ? AND kind = ?", (home_id, kind)).fetchone()
    return row["method"] if row else None


def set_method_in_transaction(conn, user_id, home_id, kind, method, now):
    """Save the entrance method inside the caller's transaction. Any other method than 'code' deletes this
    entrance's code only (the other entrance is not touched). Returns True if a code was deleted."""
    before = method_of(conn, home_id, kind)
    if before != method:
        conn.execute("""INSERT INTO home_entrances (home_id, kind, method, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (home_id, kind) DO UPDATE SET method = excluded.method,
                            updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                     (home_id, kind, method, user_id, now))
        _record(conn, home_id, user_id, f"entrance_{method}", kind, now)   # 방식만 기록 (값 없음)
    if method != "code":
        if conn.execute("DELETE FROM home_door_codes WHERE home_id = ? AND kind = ?", (home_id, kind)).rowcount:
            _record(conn, home_id, user_id, "door_code_deleted", kind, now)
            return True
    return False


def store_in_transaction(conn, user_id, home_id, kind, code, key, now):
    """Encrypt and save inside the caller's transaction (permission already checked by the caller).
    Only for an entrance whose method is 'code' (an unset method becomes 'code')."""
    if key is None:
        raise AccountError(503, NO_KEY)
    method = method_of(conn, home_id, kind)
    if method not in (None, "code"):
        raise AccountError(409, NOT_CODE, "method")
    if method is None:
        set_method_in_transaction(conn, user_id, home_id, kind, "code", now)
    existed = conn.execute("SELECT 1 FROM home_door_codes WHERE home_id = ? AND kind = ?", (home_id, kind)).fetchone()
    nonce, ciphertext = encrypt(key, home_id, kind, code)
    conn.execute("""INSERT INTO home_door_codes (home_id, kind, ciphertext, nonce, key_id, updated_by, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (home_id, kind) DO UPDATE SET ciphertext = excluded.ciphertext, nonce = excluded.nonce,
                        key_id = excluded.key_id, updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                 (home_id, kind, ciphertext, nonce, key.key_id, user_id, now))
    _record(conn, home_id, user_id, "door_code_changed" if existed else "door_code_set", kind, now)


def put(conn, user_id, home_id, kind, code, key=None, now=None):
    """Register or change a door code. Raises AccountError (400 rule, 403/404 permission, 503 no key)."""
    now = time.time() if now is None else now
    key = key if key is not None else current_key()
    kind = clean_kind(kind)
    code = clean_code(code)
    if key is None:
        raise AccountError(503, NO_KEY)
    with db.transaction(conn):
        home = _linked_home(conn, user_id, home_id)
        store_in_transaction(conn, user_id, home["id"], kind, code, key, now)


def set_entrance(conn, user_id, home_id, kind, method, code=None, key=None, now=None):
    """Set one entrance's method, and with method 'code' optionally its code, in ONE transaction.

    - method 'code' with no code: the registered code (if any) stays as it is
    - any other method: this entrance's code is deleted (the screen asks first); the other entrance is kept
    Raises AccountError (400 rule, 403/404 permission, 503 code given without a key).
    """
    now = time.time() if now is None else now
    key = key if key is not None else current_key()
    kind = clean_kind(kind)
    method = clean_method(kind, method)
    code = clean_code(code) if method == "code" and code not in (None, "") else None
    if code is not None and key is None:
        raise AccountError(503, NO_KEY)
    with db.transaction(conn):
        home = _linked_home(conn, user_id, home_id)
        set_method_in_transaction(conn, user_id, home["id"], kind, method, now)
        if code is not None:
            store_in_transaction(conn, user_id, home["id"], kind, code, key, now)


def clean_entrances(value, key):
    """Check {"central": {"method", "code"}, "door": {...}} for first setup before its transaction.
    Returns {kind: (method, code or None)} for the entrances that were sent."""
    value = value if isinstance(value, dict) else {}
    out = {}
    for kind in KINDS:
        item = value.get(kind)
        if item is None:
            continue
        if not isinstance(item, dict):
            raise AccountError(400, "출입 방식을 다시 선택해 주세요.", "method")
        method = clean_method(kind, item.get("method"))
        code = clean_code(item.get("code")) if method == "code" and item.get("code") not in (None, "") else None
        out[kind] = (method, code)
    if key is None and any(code for _, code in out.values()):
        raise AccountError(503, NO_KEY)
    return out


def apply_entrances_in_transaction(conn, user_id, home_id, entrances, key, now):
    """Save checked entrances (from clean_entrances) inside the first-setup transaction."""
    for kind, (method, code) in entrances.items():
        set_method_in_transaction(conn, user_id, home_id, kind, method, now)
        if code is not None:
            store_in_transaction(conn, user_id, home_id, kind, code, key, now)


def methods(conn, home_ids):
    """{home_id: {"central": method or None, "door": method or None}} (None = 미설정)."""
    out = {h: {"central": None, "door": None} for h in home_ids}
    if home_ids:
        marks = ",".join("?" * len(home_ids))
        for row in conn.execute(f"SELECT home_id, kind, method FROM home_entrances WHERE home_id IN ({marks})", list(home_ids)):
            out[row["home_id"]][row["kind"]] = row["method"]
    return out


def delete(conn, user_id, home_id, kind, now=None):
    """Delete a door code (no key needed). Raises AccountError (403/404)."""
    now = time.time() if now is None else now
    kind = clean_kind(kind)
    with db.transaction(conn):
        home = _linked_home(conn, user_id, home_id)
        gone = conn.execute("DELETE FROM home_door_codes WHERE home_id = ? AND kind = ?", (home["id"], kind)).rowcount
        if not gone:
            raise AccountError(404, "등록된 현관 비밀번호가 없어요.")
        _record(conn, home["id"], user_id, "door_code_deleted", kind, now)


def registered(conn, home_ids):
    """{home_id: {"central": bool, "door": bool}} - only whether a code exists, never the value."""
    out = {h: {"central": False, "door": False} for h in home_ids}
    if home_ids:
        marks = ",".join("?" * len(home_ids))
        for row in conn.execute(f"SELECT home_id, kind FROM home_door_codes WHERE home_id IN ({marks})", list(home_ids)):
            out[row["home_id"]][row["kind"]] = True
    return out


def reveal(conn, home_id, kind, key=None):
    """Decrypt one code for server-internal use only (future emergency report). Not exposed by any endpoint.
    Returns None if not registered. Raises DoorCodeKeyError with a missing or different key."""
    key = key if key is not None else current_key()
    row = conn.execute("SELECT * FROM home_door_codes WHERE home_id = ? AND kind = ?", (home_id, clean_kind(kind))).fetchone()
    if row is None:
        return None
    if key is None or row["key_id"] != key.key_id:
        raise DoorCodeKeyError("key missing or different from the one used to save")
    return decrypt(key, home_id, kind, row["nonce"], row["ciphertext"])


if __name__ == "__main__":
    if sys.argv[1:] == ["genkey"]:
        print("새 DOOR_CODE_KEY (server/.env 에 한 줄로 넣고, 안전한 곳에 따로 보관하세요. 잃어버리면 저장된 비밀번호를 풀 수 없어요):")
        print(generate_key())
    else:
        print("사용: python door_codes.py genkey")
