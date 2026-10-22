"""Notifications for the new web app: the in-app notification center and the SMS delivery queue (D stage).

Two different things are recorded separately:
  notifications            what the family should know (the app's notification center). A row means
                           "recorded for this person", not "delivered to the phone".
  notification_deliveries  each attempt to deliver it through a channel. Only SMS for now, and only through
                           MockSmsSender: status 'simulated' means nothing was sent. 'sent' is reserved for a real
                           SMS company, which is connected later (G stage) by implementing SmsSender.

No real SMS, call or 119 request is made anywhere in this module.
"""
import secrets

import db

MAX_ATTEMPTS = 3
RETRY_BACKOFF_MS = (30_000, 120_000)   # 실패 후 다시 시도까지 (1번째 실패, 2번째 실패)
LEASE_MS = 60_000                      # 보내는 중 서버가 멈추면 이 시간 뒤 다시 시도
BATCH = 20

# 알림센터 문장 ({home}: 받는 사람 기준 집 이름)
NOTIF_TEXT = {
    "family_alert": "{home} · {loc}: 낙상 후 60초 동안 응답이 없어요",
    "help": "{home} · {loc}: {name}님이 도움을 요청했어요 ({n}번째)",
    "self_ok": "{home} · {loc}: {name}님이 괜찮다고 응답했어요",
    "checked": "{home} · {loc}: {name}님이 확인하고 있어요",
    "closed": "{home} · {loc}: {name}님이 괜찮은 것을 확인하고 종료했어요",
    "reported": "{home} · {loc}: {name}님이 119 신고를 기록했어요 (모의 신고)",
    "auto_reported": "{home} · {loc}: 자동 119 신고가 기록됐어요 (모의 신고)",
}
# 문자 문장 (이름·건강 정보·주소는 넣지 않음)
SMS_TEXT = {
    "family_alert": "[지킴이] {home} {loc}에서 낙상이 감지됐는데 응답이 없어요. 앱에서 확인해 주세요.",
    "help": "[지킴이] {home} {loc}에서 낙상 후 도움을 요청했어요. 앱에서 확인해 주세요.",
    "reported": "[지킴이] {home} {loc} 낙상: 119 신고가 기록됐어요(모의 신고, 실제 119에는 연락되지 않았어요). 앱에서 확인해 주세요.",
    "auto_reported": "[지킴이] {home} {loc} 낙상: 아무도 확인하지 않아 자동 119 신고가 기록됐어요(모의 신고, 실제 119에는 연락되지 않았어요). 앱에서 확인해 주세요.",
}


# ---- 문자 발송 모듈 ----
class SmsError(Exception):
    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


class SmsSender:
    """Interface for an SMS company. send() returns the company's message id or raises SmsError.
    simulated=True means the sender never contacts anyone (its successes are recorded as 'simulated')."""
    name = "base"
    simulated = True

    def send(self, phone, body):
        raise NotImplementedError


class MockSmsSender(SmsSender):
    """Records what would have been sent. Never uses the network. For tests: fail_plan is a list of SmsError
    (or None for success) used in order for the next sends."""
    name = "mock"
    simulated = True

    def __init__(self, fail_plan=None, keep=100):
        self.sent = []
        self.fail_plan = list(fail_plan or [])
        self.keep = keep

    def send(self, phone, body):
        if self.fail_plan:
            error = self.fail_plan.pop(0)
            if error is not None:
                raise error
        ref = f"mock_{secrets.token_hex(6)}"
        self.sent.append({"phone": phone, "body": body, "ref": ref})
        del self.sent[:-self.keep]
        return ref


def build_sender(env):
    """Only the mock sender exists. A real company is added in G stage (SMS_PROVIDER, API key, sender number)."""
    provider = (env.get("SMS_PROVIDER") or "mock").strip().lower()
    if provider != "mock":
        print(f"[sms] SMS_PROVIDER={provider!r} 는 아직 연결되지 않았어요 → 모의 발송만 합니다 (실제 문자 없음)")
    return MockSmsSender()


# ---- 기록 ----
def _home_name(conn, home_id, viewer_id, names):
    """Same rule as Sel.homeName: my home = '우리 집', otherwise the targets' (or linked people's) names."""
    linked = conn.execute("""SELECT u.id, u.is_target FROM users u JOIN home_members hm ON hm.user_id = u.id
                             WHERE hm.home_id = ? ORDER BY hm.linked_at""", (home_id,)).fetchall()
    if any(r["id"] == viewer_id for r in linked):
        return "우리 집"
    people = [r["id"] for r in linked if r["is_target"]] or [r["id"] for r in linked]
    shown = [names[p] for p in people if p in names]
    return "·".join(shown) + "님 댁" if shown else "등록된 집"


def record(conn, group_id, incident_id, user_ids, kind, actor_id, now, n=0, sms=False):
    """Record a notification for each person (once per incident/person/kind/n) and, if sms, queue an SMS.
    Called inside the incident's transaction, so it is saved together with the change it describes."""
    if not user_ids:
        return
    inc = conn.execute("SELECT home_id, location FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM users WHERE group_id = ?", (group_id,))}
    for uid in dict.fromkeys(user_ids):
        nid = f"n_{secrets.token_hex(8)}"
        cur = conn.execute("""INSERT OR IGNORE INTO notifications (id, group_id, user_id, incident_id, kind, actor_id, n,
                                                                  created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                           (nid, group_id, uid, incident_id, kind, actor_id, n, now))
        if cur.rowcount and sms and kind in SMS_TEXT:
            body = SMS_TEXT[kind].format(home=_home_name(conn, inc["home_id"], uid, names), loc=inc["location"])
            conn.execute("""INSERT INTO notification_deliveries (notification_id, channel, status, body, next_attempt_at,
                                                                 created_at, updated_at)
                            VALUES (?, 'sms', 'pending', ?, ?, ?, ?)""", (nid, body, now, now, now))


def for_user(conn, user_id, group_id, names, limit):
    rows = conn.execute("""SELECT n.*, i.home_id, i.location FROM notifications n LEFT JOIN incidents i ON i.id = n.incident_id
                           WHERE n.user_id = ? AND n.group_id = ? ORDER BY n.created_at DESC LIMIT ?""",
                        (user_id, group_id, limit)).fetchall()
    out = []
    for r in reversed(rows):
        home = _home_name(conn, r["home_id"], user_id, names) if r["home_id"] else "집"
        text = NOTIF_TEXT.get(r["kind"], r["kind"]).format(home=home, loc=r["location"] or "",
                                                            name=names.get(r["actor_id"], "가족"), n=r["n"] or 1)
        out.append({"id": r["id"], "groupId": r["group_id"], "to": [user_id], "text": text, "at": r["created_at"],
                    "kind": r["kind"], "incidentId": r["incident_id"], "read": r["read_at"] is not None})
    return out


def mark_read(conn, user_id, now):
    with db.transaction(conn):
        conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (now, user_id))


# ---- 문자 발송 처리 (서버 감시 작업이 1초마다 부름) ----
def process_due(conn, sender, now):
    """Send the SMS deliveries that are due. Returns the number processed.

    Claims rows first (attempts + 1, next try after LEASE_MS) in a transaction, then sends outside it, so a
    crash while sending only delays a retry and the same delivery is never sent by two workers at once."""
    with db.transaction(conn):
        rows = conn.execute("""SELECT d.*, u.phone FROM notification_deliveries d
                               JOIN notifications n ON n.id = d.notification_id JOIN users u ON u.id = n.user_id
                               WHERE d.status IN ('pending', 'retry') AND d.next_attempt_at <= ?
                               ORDER BY d.id LIMIT ?""", (now, BATCH)).fetchall()
        for r in rows:
            conn.execute("UPDATE notification_deliveries SET attempts = attempts + 1, next_attempt_at = ?, updated_at = ? "
                         "WHERE id = ?", (now + LEASE_MS, now, r["id"]))
    for r in rows:
        attempts = r["attempts"] + 1
        try:
            ref = sender.send(r["phone"], r["body"])
            status, error, next_at = ("simulated" if sender.simulated else "sent"), None, None
        except SmsError as e:
            ref, error = None, str(e)[:200]
            if e.retryable and attempts < MAX_ATTEMPTS:
                status, next_at = "retry", now + RETRY_BACKOFF_MS[min(attempts, len(RETRY_BACKOFF_MS)) - 1]
            else:
                status, next_at = "failed", None
        except Exception as e:   # 발송 모듈의 예상하지 못한 오류도 다시 시도
            ref, error = None, f"{type(e).__name__}: {e}"[:200]
            status, next_at = ("retry", now + RETRY_BACKOFF_MS[0]) if attempts < MAX_ATTEMPTS else ("failed", None)
        with db.transaction(conn):
            conn.execute("""UPDATE notification_deliveries SET status = ?, provider = ?, provider_ref = ?, last_error = ?,
                            next_attempt_at = ?, updated_at = ? WHERE id = ?""",
                         (status, sender.name, ref, error, next_at, now, r["id"]))
    return len(rows)
