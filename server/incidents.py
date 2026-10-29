"""Fall incidents of the new web app (/app/next), handled by the server (D stage).

The model is the one store.js used in test mode (Genspark design), now kept in SQLite (db.py migration 6):
  detected     a fall was detected; only the detection targets of that home see it (60 s to answer)
  no_response  nobody answered in 60 s -> the family is alerted, automatic report 180 s later
  help         a target asked for help -> the family is alerted, automatic report 180 s after the first request
  checking     a family member took over ('확인했어요, 제가 처리할게요') -> automatic report stopped
  closed       the target said '괜찮아요' (result self) or the checking member closed it (result family)
  reported     119 report SIMULATION (result reported / auto_reported). Nothing is ever sent to 119.

Every way a fall can come in uses create(): the device API (F stage), the old /api/events bridge
(legacy_devices.py, only for devices an administrator registered) and the developer fall (copy servers only).
Times are server milliseconds; the state holds only reference times and the screen computes remaining time.
Actions run inside BEGIN IMMEDIATE and re-read the incident, so when several family members press at once
the first valid press wins and the others get 409 with the current state.
Names are not stored: logs and notifications keep user ids and the sentences are made when the state is sent.
"""
import secrets
import time

import alerts
import db
from accounts import AccountError

SELF_WINDOW_MS = 60_000     # 낙상자 응답 대기
AUTO_REPORT_MS = 180_000    # 가족 알림(무응답·도움 요청) 후 자동 신고(모의)까지
LATE_MS = 5_000             # 예정 시각보다 이만큼 넘게 늦게 처리되면 (서버가 꺼져 있었음 등) 기록에 표시
TERMINAL = ("closed", "reported")
OPEN_STATUSES = ("detected", "no_response", "help", "checking")
LOCATION_MAX = 20
STATE_INCIDENT_LIMIT = 200  # 화면에 보내는 사고 수 (진행 중 + 최근 것)
STATE_NOTIF_LIMIT = 60
REPORT_KIND = "simulation"  # 실제 119 신고 기능은 없음


def now_ms():
    return int(time.time() * 1000)


def _new_id():
    return f"inc_{secrets.token_hex(8)}"


def clean_location(value):
    location = " ".join(value.split()) if isinstance(value, str) else ""
    if not location or len(location) > LOCATION_MAX:
        raise AccountError(400, f"위치 이름을 1~{LOCATION_MAX}자로 입력해 주세요.", "location")
    return location


# ---- 사람 ----
def _victims(conn, home_id):
    """Detection targets linked to the home (the people the screen calls 'victim')."""
    return [r["id"] for r in conn.execute(
        """SELECT u.id FROM users u JOIN home_members hm ON hm.user_id = u.id
           WHERE hm.home_id = ? AND u.is_target = 1 ORDER BY hm.linked_at""", (home_id,))]


def _members(conn, group_id):
    return [r["id"] for r in conn.execute("SELECT id FROM users WHERE group_id = ? ORDER BY created_at", (group_id,))]


def _log(conn, incident_id, at, action, user_id=None, n=None, late=False):
    conn.execute("INSERT INTO incident_log (incident_id, at, action, user_id, n, late) VALUES (?, ?, ?, ?, ?, ?)",
                 (incident_id, at, action, user_id, n, 1 if late else 0))


def _touch(conn, incident_id, now):
    conn.execute("UPDATE incidents SET updated_at = ? WHERE id = ?", (now, incident_id))


# ---- 사고 만들기 (모든 경로 공통) ----
def create(conn, home_id, location, source, source_ref=None, dedupe_key=None, now=None, detected_at=None):
    """Create a fall incident for a home, or return the one already open there.

    Returns (incident_id, created). The same dedupe_key (e.g. a retried event) never makes a second incident,
    and a home has at most one open incident: a new detection while one is open is only logged on it.
    """
    now = now_ms() if now is None else now
    detected_at = now if detected_at is None else detected_at
    location = clean_location(location)
    with db.transaction(conn):
        home = conn.execute("SELECT id, group_id FROM homes WHERE id = ?", (home_id,)).fetchone()
        if not home:
            raise AccountError(404, "집을 찾을 수 없어요.", "home")
        if dedupe_key:
            row = conn.execute("SELECT id FROM incidents WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
            if row:
                return row["id"], False
        open_row = conn.execute(f"SELECT id FROM incidents WHERE home_id = ? AND status IN ({_marks(OPEN_STATUSES)})",
                                (home_id, *OPEN_STATUSES)).fetchone()
        if open_row:
            _log(conn, open_row["id"], now, "redetected")
            _touch(conn, open_row["id"], now)
            return open_row["id"], False
        incident_id = _new_id()
        conn.execute("""INSERT INTO incidents (id, group_id, home_id, source, source_ref, dedupe_key, location,
                                               detected_at, status, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'detected', ?)""",
                     (incident_id, home["group_id"], home_id, source, source_ref, dedupe_key, location, detected_at, now))
        _log(conn, incident_id, detected_at, "detected")
        import push   # 그룹 구성원 모두에게 푸시 (보내기는 서버의 백그라운드 작업이 따로, push.py)
        push.queue_for_incident(conn, incident_id, home["group_id"], now)
        return incident_id, True


def add_photo(conn, incident_id, photo_id, now=None):
    """Link a saved silhouette photo (images/{photo_id}.jpg) to an incident. A retried event links it only once."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        conn.execute("INSERT OR IGNORE INTO incident_photos (photo_id, incident_id, at) VALUES (?, ?, ?)",
                     (photo_id, incident_id, now))


PHOTO_KEEP_MS = 14 * 24 * 3600 * 1000   # 끝난 사고의 사진 보관 기간 (사용자 결정 2026-10-29)


def expire_photos(conn, now=None, keep_ms=PHOTO_KEEP_MS):
    """Unlink the photos of incidents that ended (closed or reported) at least keep_ms ago and return their ids,
    so the caller can delete the files. Open incidents keep their photos, also while a family member is checking
    ('checking'): only ended incidents have closed_at. The incident record itself stays."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        ids = [r["photo_id"] for r in conn.execute(
            """SELECT p.photo_id FROM incident_photos p JOIN incidents i ON i.id = p.incident_id
               WHERE i.closed_at IS NOT NULL AND i.closed_at + ? <= ? ORDER BY p.at""", (keep_ms, now))]
        conn.executemany("DELETE FROM incident_photos WHERE photo_id = ?", [(i,) for i in ids])
    return ids


def check_photo(conn, user_id, incident_id, photo_id):
    """Raise 404 unless the photo belongs to an incident of the user's own group (other groups: same as missing)."""
    _load(conn, user_id, incident_id)
    if not conn.execute("SELECT 1 FROM incident_photos WHERE photo_id = ? AND incident_id = ?",
                        (str(photo_id or ""), incident_id)).fetchone():
        raise AccountError(404, "사진을 찾을 수 없어요.")


def _marks(values):
    return ",".join("?" * len(values))


# ---- 시간 경과 (서버 감시 작업이 1초마다 부름) ----
def tick(conn, now=None):
    """Apply the time-based steps that are due: 60 s without answer, automatic report (simulation).
    Uses the stored reference times, so after a restart the steps happen with their original times."""
    now = now_ms() if now is None else now
    changed = 0
    due = conn.execute(
        """SELECT id FROM incidents
           WHERE (status = 'detected' AND detected_at + ? <= ?)
              OR (status IN ('no_response', 'help') AND auto_report_at IS NOT NULL AND auto_report_at <= ?)""",
        (SELF_WINDOW_MS, now, now)).fetchall()
    for row in due:
        with db.transaction(conn):
            inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (row["id"],)).fetchone()
            if inc is None or inc["status"] in TERMINAL:
                continue
            if inc["status"] == "detected" and inc["detected_at"] + SELF_WINDOW_MS <= now:
                notified = inc["detected_at"] + SELF_WINDOW_MS
                conn.execute("""UPDATE incidents SET status = 'no_response', family_notified_at = ?, auto_report_at = ?,
                                updated_at = ? WHERE id = ?""", (notified, notified + AUTO_REPORT_MS, now, inc["id"]))
                _log(conn, inc["id"], notified, "no_response", late=now - notified > LATE_MS)
                _notify_family(conn, inc, "family_alert", None, now, sms=True)
                changed += 1
                inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (row["id"],)).fetchone()
            if inc["status"] in ("no_response", "help") and inc["auto_report_at"] and inc["auto_report_at"] <= now:
                at = inc["auto_report_at"]
                _report(conn, inc, "auto", at, _victims(conn, inc["home_id"]), "auto_reported", late=now - at > LATE_MS)
                _notify(conn, inc, _members(conn, inc["group_id"]), "auto_reported", None, now, sms=True)
                changed += 1
    return changed


# ---- 사람이 누르는 동작 ----
def _load(conn, user_id, incident_id):
    me = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not me:
        raise AccountError(401, "로그인이 필요해요. 다시 로그인해 주세요.")
    inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (str(incident_id or ""),)).fetchone()
    # 다른 그룹의 사고는 없는 사고와 똑같이 답함
    if not inc or not me["group_id"] or inc["group_id"] != me["group_id"]:
        raise AccountError(404, "사고를 찾을 수 없어요.")
    return me, inc


def _ended(inc):
    if inc["status"] in TERMINAL:
        raise AccountError(409, "이미 신고되었거나 종료된 사고예요.")


def _response_for(inc, now):
    if inc["response"]:
        return inc["response"]
    return "within60" if now - inc["detected_at"] < SELF_WINDOW_MS else "after60"


def _terminate(conn, inc, status, result, by, at, response):
    conn.execute("""UPDATE incidents SET status = ?, result = ?, closed_at = ?, closed_by = ?, auto_report_at = NULL,
                    response = ?, report_kind = ?, updated_at = ? WHERE id = ?""",
                 (status, result, at, by, response or "none", REPORT_KIND if status == "reported" else None,
                  max(at, now_ms()), inc["id"]))


def _report(conn, inc, by, at, target_ids, result, late=False):
    conn.execute("DELETE FROM incident_targets WHERE incident_id = ?", (inc["id"],))
    conn.executemany("INSERT INTO incident_targets (incident_id, user_id) VALUES (?, ?)",
                     [(inc["id"], uid) for uid in target_ids])
    conn.execute("UPDATE incidents SET reported_by = ?, reported_at = ? WHERE id = ?", (by, at, inc["id"]))
    _terminate(conn, inc, "reported", result, by, at, inc["response"])
    _log(conn, inc["id"], at, result, None if by == "auto" else by, late=late)


def self_ok(conn, user_id, incident_id, now=None):
    """E-01 '괜찮아요' (only a detection target of that home)."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        if me["id"] not in _victims(conn, inc["home_id"]):
            raise AccountError(403, "이 집의 감지 대상자만 응답할 수 있어요.")
        _ended(inc)
        _terminate(conn, inc, "closed", "self", me["id"], now, _response_for(inc, now))
        _log(conn, inc["id"], now, "self_ok", me["id"])
        if inc["family_notified_at"]:
            _notify_family(conn, inc, "self_ok", me["id"], now)


def self_help(conn, user_id, incident_id, now=None):
    """E-01 '도움이 필요해요'. Pressing again keeps the first deadline (180 s from the first request)."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        if me["id"] not in _victims(conn, inc["home_id"]):
            raise AccountError(403, "이 집의 감지 대상자만 응답할 수 있어요.")
        _ended(inc)
        if inc["status"] == "checking":
            raise AccountError(409, "가족이 이미 확인하고 있어요.")
        conn.execute("INSERT INTO incident_help (incident_id, at, user_id) VALUES (?, ?, ?)", (inc["id"], now, me["id"]))
        n = conn.execute("SELECT COUNT(*) FROM incident_help WHERE incident_id = ?", (inc["id"],)).fetchone()[0]
        first_alert = inc["status"] == "detected"
        if first_alert:
            conn.execute("""UPDATE incidents SET status = 'help', family_notified_at = ?, auto_report_at = ?
                            WHERE id = ?""", (now, now + AUTO_REPORT_MS, inc["id"]))
        else:
            conn.execute("UPDATE incidents SET status = 'help' WHERE id = ?", (inc["id"],))
        conn.execute("UPDATE incidents SET response = ?, updated_at = ? WHERE id = ?",
                     (_response_for(inc, now), now, inc["id"]))
        _log(conn, inc["id"], now, "help", me["id"], n)
        # 문자는 가족에게 처음 알릴 때만 (무응답 알림을 이미 보냈으면 앱 알림만)
        _notify_family(conn, inc, "help", me["id"], now, n=n, sms=first_alert)
        return n


def take_over(conn, user_id, incident_id, now=None):
    """E-02/E-03 '확인했어요, 제가 처리할게요' (a family member). Stops the automatic report."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        if me["id"] in _victims(conn, inc["home_id"]):
            raise AccountError(403, "낙상 대상자는 '괜찮아요' 또는 '도움이 필요해요'로 응답해 주세요.")
        _ended(inc)
        if inc["status"] == "checking":
            raise AccountError(409, "이미 다른 가족이 확인하고 있어요.")
        if inc["status"] == "detected":
            raise AccountError(409, "아직 가족 알림 전이에요.")
        conn.execute("""UPDATE incidents SET status = 'checking', checked_by = ?, checked_at = ?, auto_report_at = NULL,
                        updated_at = ? WHERE id = ?""", (me["id"], now, now, inc["id"]))
        _log(conn, inc["id"], now, "checked", me["id"])
        _notify(conn, inc, [u for u in _members(conn, inc["group_id"]) if u != me["id"]], "checked", me["id"], now)


def close_checked(conn, user_id, incident_id, now=None):
    """E-06 '괜찮은 걸 확인했어요 (종료)' (only the member who is checking)."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        _ended(inc)
        if inc["status"] != "checking" or inc["checked_by"] != me["id"]:
            raise AccountError(409, "확인 중인 가족만 종료할 수 있어요.")
        _terminate(conn, inc, "closed", "family", me["id"], now, inc["response"])
        _log(conn, inc["id"], now, "closed", me["id"])
        _notify(conn, inc, [u for u in _members(conn, inc["group_id"]) if u != me["id"]], "closed", me["id"], now)


def report(conn, user_id, incident_id, target_ids=None, now=None):
    """E-05 '전송': record a 119 report SIMULATION. target_ids: detection targets of that home (empty = all)."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        _ended(inc)
        victims = _victims(conn, inc["home_id"])
        chosen = [str(t) for t in (target_ids or [])] if isinstance(target_ids, (list, tuple)) else []
        if any(t not in victims for t in chosen):
            raise AccountError(400, "낙상 대상자를 다시 선택해 주세요.", "targets")
        targets = list(dict.fromkeys(chosen)) or victims
        _report(conn, inc, me["id"], now, targets, "reported")
        _notify(conn, inc, [u for u in _members(conn, inc["group_id"]) if u != me["id"]], "reported", me["id"], now,
                sms=True)


def dismiss(conn, user_id, incident_id, now=None):
    """E-07 '확인': hide an ended incident from my emergency screen."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        me, inc = _load(conn, user_id, incident_id)
        conn.execute("INSERT OR IGNORE INTO incident_dismissals (incident_id, user_id, at) VALUES (?, ?, ?)",
                     (inc["id"], me["id"], now))


# ---- 알림 ----
def _notify(conn, inc, user_ids, kind, actor_id, now, n=0, sms=False):
    alerts.record(conn, inc["group_id"], inc["id"], user_ids, kind, actor_id, now, n=n, sms=sms)
    # 그룹에 연결된 텔레그램 대화방에도 같은 알림을 한 번 (글자만, 버튼 없음)
    alerts.queue_telegram(conn, inc["group_id"], inc["id"], kind, actor_id, now, n=n)


def _notify_family(conn, inc, kind, actor_id, now, n=0, sms=False):
    """Family = group members who are not detection targets of that home (they see the emergency screen as 'family')."""
    victims = set(_victims(conn, inc["home_id"]))
    _notify(conn, inc, [u for u in _members(conn, inc["group_id"]) if u not in victims], kind, actor_id, now, n=n, sms=sms)


# ---- 화면에 보낼 상태 (store.js 의 incident / notif 형식) ----
LOG_TEXT = {
    "detected": "낙상이 감지됐어요",
    "redetected": "같은 집에서 다시 감지됐어요",
    "no_response": "60초 동안 응답이 없어 가족에게 알렸어요",
    "self_ok": "{name}님이 괜찮다고 응답했어요",
    "help": "{name}님이 도움이 필요하다고 응답했어요 ({n}번째)",
    "checked": "{name}님이 확인했어요",
    "closed": "{name}님이 괜찮은 것을 확인하고 종료했어요",
    "reported": "{name}님이 119 신고를 기록했어요 (모의 신고 · 실제 119에는 연락하지 않았어요)",
    "auto_reported": "아무도 확인하지 않아 자동 119 신고를 기록했어요 (모의 신고 · 실제 119에는 연락하지 않았어요)",
}
LATE_SUFFIX = " (서버가 늦게 처리했어요)"


def _names(conn, group_id):
    return {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM users WHERE group_id = ?", (group_id,))}


def log_text(action, name, n=None, late=False):
    return LOG_TEXT.get(action, action).format(name=name or "가족", n=n or 1) + (LATE_SUFFIX if late else "")


def _incident_dict(conn, inc, names):
    helps = [r["at"] for r in conn.execute("SELECT at FROM incident_help WHERE incident_id = ? ORDER BY at", (inc["id"],))]
    targets = [r["user_id"] for r in conn.execute("SELECT user_id FROM incident_targets WHERE incident_id = ?", (inc["id"],))]
    dismissed = {r["user_id"]: True for r in conn.execute("SELECT user_id FROM incident_dismissals WHERE incident_id = ?",
                                                          (inc["id"],))}
    log = [{"at": r["at"], "text": log_text(r["action"], names.get(r["user_id"]), r["n"], r["late"])}
           for r in conn.execute("SELECT * FROM incident_log WHERE incident_id = ? ORDER BY at, id", (inc["id"],))]
    photos = [{"id": r["photo_id"], "at": r["at"]} for r in conn.execute(
        "SELECT photo_id, at FROM incident_photos WHERE incident_id = ? ORDER BY at, photo_id", (inc["id"],))]
    return {
        "id": inc["id"], "groupId": inc["group_id"], "homeId": inc["home_id"], "location": inc["location"],
        "detectedAt": inc["detected_at"], "status": inc["status"], "response": inc["response"],
        "familyNotifiedAt": inc["family_notified_at"], "helpTimes": helps, "autoReportAt": inc["auto_report_at"],
        "checkedBy": inc["checked_by"], "checkedAt": inc["checked_at"],
        "closedAt": inc["closed_at"], "closedBy": inc["closed_by"], "result": inc["result"],
        "reportedBy": inc["reported_by"], "reportedAt": inc["reported_at"], "reportedTargetIds": targets,
        "reportKind": inc["report_kind"], "recognizedId": inc["recognized_id"],
        "source": inc["source"], "dismissed": dismissed, "log": log, "photos": photos,
    }


def state_part(conn, user_id, group_id):
    """(incidents, notifs) for the logged-in user's own group only."""
    if not group_id:
        return [], []
    names = _names(conn, group_id)
    rows = conn.execute("""SELECT * FROM incidents WHERE group_id = ?
                           ORDER BY (status IN ('closed', 'reported')), detected_at DESC LIMIT ?""",
                        (group_id, STATE_INCIDENT_LIMIT)).fetchall()
    incidents = [_incident_dict(conn, r, names) for r in rows]
    notifs = alerts.for_user(conn, user_id, group_id, names, STATE_NOTIF_LIMIT)
    return incidents, notifs
