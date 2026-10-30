"""Family members' profiles and homes for the family web app (/app/next). Stage C.

Uses the tables of db.py migration 3. Every function takes the logged-in user's id (from the session) and
checks permissions here on the server; ids sent by the browser are only looked up inside that user's group:
  - profile, health information, notification settings: only your own
  - homes: only homes of your own group; you can link yourself to any home of your group (Genspark design),
    and only people linked to a home can change it; a home of another group is answered as "not found"
Door codes are in door_codes.py (finish_setup saves them in its transaction). Not in this stage: devices (stage F),
notifications to other members (stage G),
phone number change (needs SMS verification). residents.json is not read or changed here.
"""
import json
import re
import secrets
import time
from datetime import date, datetime

import accounts
import db
from accounts import AccountError

LIST_MAX_ITEMS = 20       # 지병·복용약 항목 수
LIST_ITEM_MAX = 30        # 항목 하나의 글자 수
ADDRESS_MAX = 200
BIRTH_MIN = date(1900, 1, 1)


# ---- 입력값 검사 ----
def clean_name(value):
    name = (value or "").strip() if isinstance(value, str) else ""
    if not accounts.NAME_MIN <= len(name) <= accounts.NAME_MAX:
        raise AccountError(400, "이름을 2~20자로 입력해 주세요.", "name")
    return name


def clean_birth(value, today=None):
    """None (not entered) or 'YYYY-MM-DD' between 1900-01-01 and today."""
    if value is None or value == "":
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date() if isinstance(value, str) else None
    except ValueError:
        day = None
    if day is None or not BIRTH_MIN <= day <= (today or date.today()):
        raise AccountError(400, "생년월일을 정확히 입력해 주세요.", "birth")
    return day.isoformat()


def clean_list(value, field):
    """None (not entered), [] (none) or a list of short texts, without duplicates."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > LIST_MAX_ITEMS:
        raise AccountError(400, f"항목은 {LIST_MAX_ITEMS}개까지 입력할 수 있어요.", field)
    items = []
    for item in value:
        text = re.sub(r"\s+", " ", item).strip() if isinstance(item, str) else ""
        if not 1 <= len(text) <= LIST_ITEM_MAX:
            raise AccountError(400, f"항목은 1~{LIST_ITEM_MAX}자로 입력해 주세요.", field)
        if text not in items:
            items.append(text)
    return items


def clean_address(value, required):
    """Address typed by the user. Later a road-name address search (stage H) fills the same field."""
    address = re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""
    if len(address) > ADDRESS_MAX:
        raise AccountError(400, f"주소는 {ADDRESS_MAX}자 이내로 입력해 주세요.", "address")
    if required and not address:
        raise AccountError(400, "주소를 입력해 주세요.", "address")
    return address


def _dump(items):
    return None if items is None else json.dumps(items, ensure_ascii=False)


def _new_id(prefix):
    return f"{prefix}_{secrets.token_hex(8)}"


# ---- 권한 ----
def _me(conn, user_id):
    return accounts._user(conn, user_id)


def _my_group(conn, user_id):
    me = _me(conn, user_id)
    if not me["group_id"]:
        raise AccountError(409, "먼저 가족 그룹을 만들거나 참여해 주세요.")
    return me


def _group_home(conn, me, home_id):
    """A home of the user's own group. Another group's home is answered exactly like a missing one."""
    row = conn.execute("SELECT * FROM homes WHERE id = ? AND group_id = ?",
                       (str(home_id or ""), me["group_id"])).fetchone()
    if not row:
        raise AccountError(404, "집을 찾을 수 없어요.", "home")
    return row


def _is_linked(conn, home_id, user_id):
    return conn.execute("SELECT 1 FROM home_members WHERE home_id = ? AND user_id = ?",
                        (home_id, user_id)).fetchone() is not None


def is_admin(conn, home_id, user_id):
    """Administrator of that home (사용자 결정 2026-10-30: 현관·기기 수정은 관리자만)."""
    return conn.execute("SELECT 1 FROM home_members WHERE home_id = ? AND user_id = ? AND role = 'admin'",
                        (home_id, user_id)).fetchone() is not None


def _has_admin(conn, home_id):
    return conn.execute("SELECT 1 FROM home_members WHERE home_id = ? AND role = 'admin'", (home_id,)).fetchone() is not None


def _link(conn, home_id, user_id, now):
    # 관리자가 없는 집(새 집 포함)에 처음 연결하는 사람이 관리자, 그 뒤로는 구성원
    role = "member" if _has_admin(conn, home_id) else "admin"
    conn.execute("INSERT OR IGNORE INTO home_members (home_id, user_id, linked_at, role) VALUES (?, ?, ?, ?)",
                 (home_id, user_id, now, role))


def ensure_admin(conn, home_id):
    """Inside a transaction, after someone left the home: if linked members remain but no administrator, the
    longest-linked member becomes one."""
    if _has_admin(conn, home_id):
        return
    row = conn.execute("SELECT user_id FROM home_members WHERE home_id = ? ORDER BY linked_at, user_id LIMIT 1",
                       (home_id,)).fetchone()
    if row:
        conn.execute("UPDATE home_members SET role = 'admin' WHERE home_id = ? AND user_id = ?", (home_id, row["user_id"]))


def admin_home(conn, user_id, home_id, message):
    """The home (of the user's group) if the user is its administrator, else 403 with the message."""
    me = _my_group(conn, user_id)
    home = _group_home(conn, me, home_id)
    if not is_admin(conn, home["id"], user_id):
        raise AccountError(403, message, "home")
    return home


def set_admin(conn, user_id, home_id, member_id, admin):
    """An administrator makes another linked member an administrator or takes it back (one must stay)."""
    with db.transaction(conn):
        home = admin_home(conn, user_id, home_id, "이 집의 관리자만 관리자를 정할 수 있어요.")
        if not conn.execute("SELECT 1 FROM users WHERE id = ? AND group_id = ?", (member_id, home["group_id"])).fetchone():
            raise AccountError(404, "구성원을 찾을 수 없어요.")
        if not _is_linked(conn, home["id"], member_id):
            raise AccountError(409, "이 집에 연결된 가족만 관리자가 될 수 있어요.")
        if not admin and is_admin(conn, home["id"], member_id):
            admins = conn.execute("SELECT COUNT(*) FROM home_members WHERE home_id = ? AND role = 'admin'",
                                  (home["id"],)).fetchone()[0]
            if admins <= 1:
                raise AccountError(409, "관리자는 한 명 이상 있어야 해요. 다른 가족을 먼저 관리자로 정해 주세요.")
        conn.execute("UPDATE home_members SET role = ? WHERE home_id = ? AND user_id = ?",
                     ("admin" if admin else "member", home["id"], member_id))


def _create_home(conn, me, address, now):
    home_id = _new_id("h")
    conn.execute("INSERT INTO homes (id, group_id, address, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (home_id, me["group_id"], address, me["id"], now, now))
    return home_id


# ---- 내 정보 ----
def update_profile(conn, user_id, name, health=None, today=None):
    """Change your own name and, if you are a detection target, your health information.

    health: None to leave it, or a dict with any of birth / conditions / medications.
    """
    name = clean_name(name)
    values = {}
    if health:
        if "birth" in health:
            values["birth"] = clean_birth(health["birth"], today)
        for key in ("conditions", "medications"):
            if key in health:
                values[key] = _dump(clean_list(health[key], key))
    with db.transaction(conn):
        me = _me(conn, user_id)
        if values and not me["is_target"]:
            raise AccountError(409, "낙상 감지를 켠 뒤 건강 정보를 입력할 수 있어요.")
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
        for key, value in values.items():
            conn.execute(f"UPDATE users SET {key} = ? WHERE id = ?", (value, user_id))  # key 는 위 고정 목록


def set_pref(conn, user_id, key, value):
    if key not in accounts.DEFAULT_PREFS:
        raise AccountError(400, "알 수 없는 알림 설정이에요.")
    with db.transaction(conn):
        me = _me(conn, user_id)
        prefs = accounts._prefs(me["prefs"])
        prefs[key] = bool(value)
        conn.execute("UPDATE users SET prefs = ? WHERE id = ?", (json.dumps(prefs), user_id))


# ---- 집 ----
def link_home(conn, user_id, home_id, now=None):
    now = time.time() if now is None else now
    with db.transaction(conn):
        me = _my_group(conn, user_id)
        home = _group_home(conn, me, home_id)
        # 집 연결 = 그 집에 사는 감지 대상. 알림만 받는 가족이 연결해 현관 정보 수정 권한을 얻지 않도록 막음
        # (처음 설정의 '같은 집' 선택은 finish_setup 이 감지 대상으로 바꾸면서 연결)
        if not me["is_target"]:
            raise AccountError(409, "낙상 감지를 켠 뒤 집에 연결할 수 있어요.", "home")
        _link(conn, home["id"], user_id, now)


def unlink_home(conn, user_id, home_id):
    """Remove your own link only. The home stays in the group (other members may still use it)."""
    with db.transaction(conn):
        me = _my_group(conn, user_id)
        home = _group_home(conn, me, home_id)
        if not _is_linked(conn, home["id"], user_id):
            raise AccountError(409, "이 집에 연결되어 있지 않아요.", "home")
        conn.execute("DELETE FROM home_members WHERE home_id = ? AND user_id = ?", (home["id"], user_id))
        ensure_admin(conn, home["id"])


def update_home_address(conn, user_id, home_id, address, now=None):
    now = time.time() if now is None else now
    address = clean_address(address, required=True)
    with db.transaction(conn):
        me = _my_group(conn, user_id)
        home = _group_home(conn, me, home_id)
        if not _is_linked(conn, home["id"], user_id):
            raise AccountError(403, "이 집에 연결된 가족만 정보를 수정할 수 있어요.", "home")
        conn.execute("UPDATE homes SET address = ?, updated_at = ? WHERE id = ?", (address, now, home["id"]))


# ---- 처음 설정 완료 (감지 대상 켜기) ----
def finish_setup(conn, user_id, info, home, now=None, today=None, doors=None, key=None, entrances=None):
    """Finish the 'detection target' setup in ONE transaction: all saved, or nothing saved.

    info: {birth, conditions, medications} (None = not entered)
    home: {"mode": "existing", "id": ...} to link a home of your group, or {"mode": "new", "address": ...}
          (address may be empty when the user skipped it)
    entrances: {"central": {"method", "code"}, "door": {...}} - entrance methods and, for 'code', the codes the
           user entered (stage H, door_codes.py). Entrances not sent are left as they are.
    doors: older form {"central": code, "door": code}, treated as method 'code'.
           Codes are encrypted in the same transaction; without a valid key the whole setup fails (503).
    Devices are not part of this stage.
    """
    import door_codes   # door_codes 도 이 모듈을 쓰므로 함수 안에서 불러옴
    now = time.time() if now is None else now
    info = info if isinstance(info, dict) else {}
    home = home if isinstance(home, dict) else {}
    birth = clean_birth(info.get("birth"), today)
    conditions = _dump(clean_list(info.get("conditions"), "conditions"))
    medications = _dump(clean_list(info.get("medications"), "medications"))
    mode = home.get("mode")
    if mode not in ("existing", "new"):
        raise AccountError(400, "집 정보를 다시 선택해 주세요.", "home")
    address = clean_address(home.get("address"), required=False) if mode == "new" else None
    key = key if key is not None else door_codes.current_key()
    merged = dict(entrances) if isinstance(entrances, dict) else {}
    if isinstance(doors, dict):   # 예전 형식: 입력한 비밀번호 = '비밀번호' 방식
        for kind in door_codes.KINDS:
            if kind not in merged and doors.get(kind) not in (None, ""):
                merged[kind] = {"method": "code", "code": doors[kind]}
    checked = door_codes.clean_entrances(merged, key)   # 트랜잭션 전에 모두 검사 (틀리면 아무것도 저장 안 함)
    with db.transaction(conn):
        me = _my_group(conn, user_id)
        # 순서: 건강 정보 → 집. 집 단계에서 오류가 나도 위 변경까지 함께 취소됨 (db.transaction 의 ROLLBACK)
        conn.execute("""UPDATE users SET is_target = 1, birth = ?, conditions = ?, medications = ?, onboarded = 1
                        WHERE id = ?""", (birth, conditions, medications, user_id))
        if mode == "existing":
            home_id = _group_home(conn, me, home.get("id"))["id"]
            if checked and _has_admin(conn, home_id) and not is_admin(conn, home_id, user_id):
                raise AccountError(403, "현관 정보는 이 집의 관리자만 바꿀 수 있어요.", "home")
        else:
            home_id = _create_home(conn, me, address, now)
        _link(conn, home_id, user_id, now)
        # 현관 출입 방식·비밀번호: 연결이 끝난 뒤 (이 사람은 이제 이 집에 연결된 가족) 같은 트랜잭션으로 저장
        door_codes.apply_entrances_in_transaction(conn, user_id, home_id, checked, key, now)
    return home_id
