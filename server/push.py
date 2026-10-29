"""Push notifications to phones (Firebase Cloud Messaging) at the steps of a fall incident (user decision
2026-10-29; incidents.py decides who):
  detected           the fall is detected: the detection targets of that home ('are you all right?'); the family
                     does not see the incident for its first 60 s, so they are not pushed yet
  family_alert       60 s without answer: the family (members who are not detection targets of that home)
  help               a target asks for help (first request only): the family
  redetected         a new fall while a family member is checking: the family
  checking_reminder  still checking after every 30 minutes: the member who is checking
Once per incident, person, kind and number (push_deliveries UNIQUE(incident_id, user_id, kind, n)).
Members of other groups never get it: the receivers are taken from the incident's group, and when sending, a
person who has left that group meanwhile is skipped.

Phones: the Android app registers its FCM token after login (POST /api/v2/me/push-token). The token is tied to
that login session (push_tokens.session_hash → sessions): logging out or withdrawing deletes the session and the
token with it, and a token whose session has expired is not used. A token belongs to one person at a time (the
phone's current login).

Sending runs in the server's background loop (process_due), never inside the incident's transaction, so a push
that fails can not undo or block the incident, its in-app notifications or SMS. Retries like SMS (3 attempts).

Senders (build_sender):
  FcmSender   the real FCM HTTP v1 API, authenticated with a Google service account key file whose path is in
              FCM_SERVICE_ACCOUNT_FILE (kept outside the project and Git; never logged). OAuth access tokens are
              made from the key (RS256 JWT) and kept in memory only.
  FakeSender  for tests (PUSH_FAKE_URL: a fake FCM server on this computer, or in memory): 'simulated' = nothing
              was sent to a phone.
  None        not configured: deliveries are marked 'skipped' (the incident works as before).

The message shown on the lock screen has no name or address (PUSH_TEXT).
The app opens the incident from the data field incidentId.
"""
import base64
import json
import re
import threading
import time
import urllib.error
import urllib.request

import db
from accounts import AccountError

TITLE = "낙상 지킴이"
BODY = "낙상 사고가 감지됐어요. 확인해 주세요."
# 잠금 화면 문장 (이름·주소 없음)
PUSH_TEXT = {
    "detected": BODY,
    "family_alert": "낙상 후 60초 동안 응답이 없어요. 확인해 주세요.",
    "help": "낙상 후 도움을 요청했어요. 확인해 주세요.",
    "redetected": "확인 중인 사고에서 다시 넘어짐이 감지됐어요. 확인해 주세요.",
    "checking_reminder": "아직 확인 중인 낙상 사고가 있어요. 확인을 마치면 종료해 주세요.",
}
CHANNEL_ID = "fall_alert"                  # 앱(mobile/)의 긴급 알림 채널과 같은 이름
MAX_ATTEMPTS = 3
RETRY_BACKOFF_MS = (30_000, 120_000)
LEASE_MS = 60_000
BATCH = 20
TOKEN_RE = re.compile(r"^[A-Za-z0-9_:\-]{20,4096}$")
MAX_TOKENS_PER_USER = 10
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_API = "https://fcm.googleapis.com"


def now_ms():
    return int(time.time() * 1000)


# ---- 휴대폰 알림 토큰 (로그인한 본인 것만) ----
def register_token(conn, user_id, session_hash, token, platform="android", now=None):
    """Remember this phone's token for the logged-in person and session. The same token registered by another
    account before (the phone's previous login) moves to this person."""
    now = now_ms() if now is None else now
    token = str(token or "").strip()
    if not TOKEN_RE.match(token):
        raise AccountError(400, "알림 토큰을 확인해 주세요.", "token")
    if platform != "android":
        raise AccountError(400, "지원하지 않는 기기예요.", "platform")
    with db.transaction(conn):
        conn.execute("""INSERT INTO push_tokens (token, user_id, session_hash, platform, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(token) DO UPDATE SET user_id = excluded.user_id, session_hash = excluded.session_hash,
                                                         platform = excluded.platform, updated_at = excluded.updated_at""",
                     (token, user_id, session_hash, platform, now, now))
        # 한 사람의 휴대폰이 너무 많으면 오래된 것부터 정리
        conn.execute("""DELETE FROM push_tokens WHERE user_id = ? AND token NOT IN (
                            SELECT token FROM push_tokens WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?)""",
                     (user_id, user_id, MAX_TOKENS_PER_USER))


def unregister_token(conn, user_id, token):
    """Forget this phone's token. Only the person's own token is removed (someone else's is left as it is)."""
    with db.transaction(conn):
        conn.execute("DELETE FROM push_tokens WHERE token = ? AND user_id = ?", (str(token or ""), user_id))


# ---- 사고 단계 → 전달 대기 (사고를 바꾸는 트랜잭션 안에서, incidents.py) ----
def queue(conn, incident_id, group_id, user_ids, kind, now, n=0):
    """One push per person for this step (only members of the incident's group). Never raises (a push problem
    must not stop the incident)."""
    try:
        for user_id in user_ids:
            conn.execute("""INSERT OR IGNORE INTO push_deliveries (incident_id, group_id, user_id, kind, n, status,
                                                                   next_attempt_at, created_at, updated_at)
                            SELECT ?, ?, id, ?, ?, 'pending', ?, ?, ? FROM users WHERE id = ? AND group_id = ?""",
                         (incident_id, group_id, kind, n, now, now, now, user_id, group_id))
    except Exception as e:   # 푸시 표가 없거나 하는 문제는 기록만 (사고는 그대로)
        print(f"[push] 전달 대기 등록 실패: {type(e).__name__}")


# ---- 보내기 ----
class PushError(Exception):
    def __init__(self, message, retryable=True, invalid_token=False):
        super().__init__(message)
        self.retryable = retryable
        self.invalid_token = invalid_token


def message(token, incident_id, dev=False, kind="detected"):
    """FCM HTTP v1 message: shown by Android itself when the app is in the background or closed (channel
    fall_alert, high priority), data incidentId opens the incident when tapped. No personal data."""
    title = ("[개발 시험] " if dev else "") + TITLE
    return {"message": {
        "token": token,
        "notification": {"title": title, "body": PUSH_TEXT.get(kind, BODY)},
        "data": {"incidentId": incident_id, "kind": "fall", "step": kind},
        "android": {
            "priority": "high",
            "ttl": "3600s",
            "notification": {"channel_id": CHANNEL_ID, "tag": incident_id, "visibility": "PUBLIC",
                             "notification_priority": "PRIORITY_MAX", "default_sound": True,
                             "default_vibrate_timings": True},
        },
    }}


class FakeSender:
    """Tests only. Posts the message to a fake FCM server on this computer (url), or keeps it in memory.
    A token that starts with 'bad-' is treated as unregistered, 'down-' as a temporary failure."""
    name = "fake"
    simulated = True

    def __init__(self, url=None):
        self.url = url
        self.sent = []

    def send(self, msg):
        token = msg["message"]["token"]
        if token.startswith("bad-"):
            raise PushError("UNREGISTERED", retryable=False, invalid_token=True)
        if token.startswith("down-"):
            raise PushError("UNAVAILABLE", retryable=True)
        if self.url:
            req = urllib.request.Request(self.url, data=json.dumps(msg).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    r.read()
            except urllib.error.URLError as e:
                raise PushError(f"가짜 푸시 서버에 연결할 수 없어요 ({type(e).__name__})")
        self.sent.append(msg)
        return "fake"


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class FcmSender:
    """The real FCM HTTP v1 API with a service account key (file path from FCM_SERVICE_ACCOUNT_FILE)."""
    name = "fcm"
    simulated = False

    def __init__(self, key, api=FCM_API):
        for field in ("client_email", "private_key", "project_id"):
            if not key.get(field):
                raise ValueError(f"서비스 계정 키에 {field} 가 없어요")
        self.key = key
        self.project = key["project_id"]
        self.token_uri = key.get("token_uri") or "https://oauth2.googleapis.com/token"
        self.api = api.rstrip("/")
        self._access = None
        self._access_until = 0
        self._lock = threading.Lock()

    def _assertion(self, now):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {"iss": self.key["client_email"], "scope": FCM_SCOPE, "aud": self.token_uri,
                  "iat": int(now), "exp": int(now) + 3600}
        signing_input = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(claims).encode())
        private_key = serialization.load_pem_private_key(self.key["private_key"].encode(), password=None)
        signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return signing_input + "." + _b64url(signature)

    def _access_token(self):
        with self._lock:
            now = time.time()
            if self._access and now < self._access_until - 60:
                return self._access
            body = ("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion="
                    + self._assertion(now)).encode("ascii")
            req = urllib.request.Request(self.token_uri, data=body, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise PushError(f"FCM 인증 실패 (HTTP {e.code})", retryable=e.code >= 500)
            except urllib.error.URLError as e:
                raise PushError(f"FCM 인증 서버에 연결할 수 없어요 ({type(e).__name__})")
            self._access = data["access_token"]
            self._access_until = now + int(data.get("expires_in", 3600))
            return self._access

    def send(self, msg):
        url = f"{self.api}/v1/projects/{self.project}/messages:send"
        req = urllib.request.Request(url, data=json.dumps(msg).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8",
                                              "Authorization": "Bearer " + self._access_token()})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("name", "")[-40:]
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read() or b"{}").get("error", {})
            except ValueError:
                err = {}
            codes = {d.get("errorCode") for d in err.get("details", []) if isinstance(d, dict)} | {err.get("status")}
            if e.code == 404 or "UNREGISTERED" in codes:
                raise PushError("UNREGISTERED", retryable=False, invalid_token=True)
            if e.code == 400 and "INVALID_ARGUMENT" in codes:
                raise PushError("INVALID_ARGUMENT", retryable=False, invalid_token=True)
            if e.code in (401, 403):
                with self._lock:
                    self._access = None
                raise PushError(f"FCM 권한 오류 (HTTP {e.code})", retryable=e.code == 401)
            raise PushError(f"FCM 오류 (HTTP {e.code})", retryable=e.code == 429 or e.code >= 500)
        except urllib.error.URLError as e:
            raise PushError(f"FCM 에 연결할 수 없어요 ({type(e).__name__})")


def build_sender(env):
    """FcmSender with FCM_SERVICE_ACCOUNT_FILE, FakeSender with PUSH_FAKE_URL (tests), else None (not configured)."""
    path = (env.get("FCM_SERVICE_ACCOUNT_FILE") or "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                key = json.load(f)
            return FcmSender(key, api=(env.get("FCM_API_URL") or FCM_API).strip())   # FCM_API_URL: 시험 전용
        except (OSError, ValueError) as e:
            print(f"[push] 서비스 계정 키를 읽지 못했어요 ({type(e).__name__}) → 푸시를 보내지 않아요")
            return None
    fake = (env.get("PUSH_FAKE_URL") or "").strip()
    if fake:
        return FakeSender(fake)
    return None


def describe(sender):
    if sender is None:
        return "없음 (FCM_SERVICE_ACCOUNT_FILE 미설정 - 푸시를 보내지 않음)"
    return f"FCM (프로젝트 {sender.project})" if isinstance(sender, FcmSender) else "가짜 전송 (시험용, 휴대폰에 보내지 않음)"


def _tokens(conn, user_id, group_id, now):
    """Tokens of the person's phones with a valid login session, only while the person is still in the group."""
    return [r["token"] for r in conn.execute(
        """SELECT pt.token FROM push_tokens pt JOIN sessions s ON s.token_hash = pt.session_hash
           JOIN users u ON u.id = pt.user_id
           WHERE pt.user_id = ? AND u.group_id = ? AND s.expires_at > ?""", (user_id, group_id, now / 1000))]


def process_due(conn, sender, now=None):
    """Send the pushes that are due. Returns the number of deliveries processed."""
    now = now_ms() if now is None else now
    with db.transaction(conn):
        rows = conn.execute("""SELECT d.*, i.source FROM push_deliveries d JOIN incidents i ON i.id = d.incident_id
                               WHERE d.status IN ('pending', 'retry') AND d.next_attempt_at <= ?
                               ORDER BY d.id LIMIT ?""", (now, BATCH)).fetchall()
        for r in rows:
            conn.execute("UPDATE push_deliveries SET attempts = attempts + 1, next_attempt_at = ?, updated_at = ? WHERE id = ?",
                         (now + LEASE_MS, now, r["id"]))
    for r in rows:
        attempts = r["attempts"] + 1
        tokens = _tokens(conn, r["user_id"], r["group_id"], now)
        sent, invalid, error, retryable = 0, [], None, False
        if sender is None:
            status, error = "skipped", "푸시 설정 없음"
        elif not tokens:
            status = "no_token"
        else:
            for token in tokens:
                try:
                    sender.send(message(token, r["incident_id"], dev=r["source"] == "dev", kind=r["kind"]))
                    sent += 1
                except PushError as e:
                    error = str(e)[:200]
                    if e.invalid_token:
                        invalid.append(token)
                    retryable |= e.retryable
                except Exception as e:   # 보내는 쪽의 예상하지 못한 오류도 다시 시도
                    error, retryable = f"{type(e).__name__}"[:200], True
            if sent:
                status = "simulated" if sender.simulated else "sent"
            elif retryable and attempts < MAX_ATTEMPTS:
                status = "retry"
            else:
                status = "failed"
        next_at = now + RETRY_BACKOFF_MS[min(attempts, len(RETRY_BACKOFF_MS)) - 1] if status == "retry" else None
        with db.transaction(conn):
            for token in invalid:   # 무효가 된 토큰은 지움 (앱을 지웠거나 토큰이 바뀜)
                conn.execute("DELETE FROM push_tokens WHERE token = ?", (token,))
            conn.execute("""UPDATE push_deliveries SET status = ?, provider = ?, sent_count = sent_count + ?, last_error = ?,
                            next_attempt_at = ?, updated_at = ? WHERE id = ?""",
                         (status, sender.name if sender else None, sent, error, next_at, now, r["id"]))
    return len(rows)
