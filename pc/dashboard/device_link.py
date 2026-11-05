"""Connection between this PC detector and the app (server devices API, stage 2b). Standard library only, no Qt.

Not paired (default): the dashboard keeps the old way (/api/events with the shared access token), unchanged.
Paired: the family member gets a 6-character pairing code in the app ('기기 추가'), the code is entered here once,
and the server gives this PC its own device token. From then on:
  - falls (and their silhouette photo) go to /api/v2/device/events with 'Authorization: Bearer <device token>'
  - a status signal goes to /api/v2/device/heartbeat every minute (camera working or not); its answer gives the
    location name. Detection on/off is decided only on this PC (Start/Stop): the app can not change it, and this
    program never starts or stops the camera because of the server; it tells the server its own state instead
  - if the family deletes the device in the app, the server answers 401: the token is forgotten here and the
    dashboard shows that it must be connected again

The device token is saved OUTSIDE the project folder (never in Git): %LOCALAPPDATA%\\FallDetection\\device_link.json
(FD_DEVICE_STATE overrides the path, for tests). One entry per server address, so a token of a test server is
never sent to another server.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

APP_VERSION = "pc-dashboard-2b"
SEND_RETRY_DELAYS = (1, 2, 4)        # 낙상 재시도 간격 (기존 /api/events 전송과 같음)
DEFAULT_HEARTBEAT_SECONDS = 60
REQUEST_TIMEOUT = 5


def default_state_path():
    if os.environ.get("FD_DEVICE_STATE"):
        return os.environ["FD_DEVICE_STATE"]
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "FallDetection", "device_link.json")


def server_base(events_url):
    """'http://127.0.0.1:8000/api/events' → 'http://127.0.0.1:8000'."""
    u = urlparse(events_url)
    return f"{u.scheme}://{u.netloc}"


class DeviceRevoked(Exception):
    """The server no longer knows this device's token (deleted in the app)."""


class DeviceLink:
    def __init__(self, events_url, state_path=None, heartbeat_override=None):
        self.base = server_base(events_url)
        self.state_path = state_path or default_state_path()
        # 시험용: 서버가 알려 준 간격 대신 짧은 간격 (FD_DEVICE_HEARTBEAT 초)
        env = os.environ.get("FD_DEVICE_HEARTBEAT")
        self.heartbeat_override = heartbeat_override or (float(env) if env else None)
        self._lock = threading.Lock()
        self._entry = self._load()
        self.local_on = None             # 이 PC 에서 감지가 켜져 있는지 (Start/Stop, 대시보드가 알려 줌)
        self.server_on = None            # 서버에 기록된 켜짐/꺼짐 (표시·맞춤용, 카메라는 따르지 않음)
        # 앱에서 기기를 삭제해 토큰이 거절됨 (프로그램을 다시 켜도 유지: 예전 경로로 몰래 보내지 않게)
        self.revoked = bool((self._read_all().get(self.base) or {}).get("revoked"))
        self.last_ok_at = None           # 서버와 마지막으로 통신에 성공한 시각
        self.last_error = None
        self._stop = threading.Event()
        self._wake = threading.Event()

    # ---- 저장 (프로젝트 밖) ----
    def _read_all(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _load(self):
        entry = self._read_all().get(self.base)
        return entry if isinstance(entry, dict) and entry.get("deviceToken") else None

    def _save(self, entry):
        data = self._read_all()
        if entry:
            data[self.base] = entry
        else:
            data.pop(self.base, None)
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    @property
    def paired(self):
        return self._entry is not None

    @property
    def info(self):
        """What can be shown (never the token)."""
        e = self._entry or {}
        return {"deviceId": e.get("deviceId"), "type": e.get("type"), "location": e.get("location")}

    # ---- 요청 ----
    def _call(self, path, body, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read() or b"{}")
            except ValueError:
                data = {}
            return e.code, data

    def _revoked(self):
        with self._lock:
            self._entry = None
            self.revoked = True
            self.server_on = None
        self._save({"revoked": True, "revokedAt": int(time.time())})   # 토큰은 지우고 '해제됨' 표시만

    # ---- 연결 · 해제 ----
    def pair(self, code):
        """Send the pairing code once. Returns (ok, message for the person)."""
        code = "".join(str(code or "").split()).upper()
        if not code:
            return False, "연결 코드를 입력해 주세요."
        try:
            status, data = self._call("/api/v2/device/pair", {"code": code, "appVersion": APP_VERSION})
        except Exception:
            return False, "서버에 연결할 수 없어요. 서버 주소와 네트워크를 확인해 주세요."
        if status != 200 or not data.get("deviceToken"):
            return False, data.get("message") or f"연결하지 못했어요 (HTTP {status})."
        entry = {"deviceId": data["deviceId"], "deviceToken": data["deviceToken"], "type": data.get("type"),
                 "location": data.get("location"), "pairedAt": int(time.time())}
        self._save(entry)
        with self._lock:
            self._entry, self.revoked, self.server_on = entry, False, None
        self._wake.set()                 # 바로 첫 상태 신호
        return True, f"앱과 연결했어요 ({entry['location']})."

    def forget(self):
        """Forget the token on this PC only (the device stays in the app until it is deleted there)."""
        with self._lock:
            self._entry, self.revoked, self.server_on = None, False, None
        self._save(None)

    # ---- 상태 신호 ----
    def heartbeat(self, camera_ok):
        """One status signal. Returns the next interval in seconds. Never raises."""
        entry = self._entry
        if not entry:
            return DEFAULT_HEARTBEAT_SECONDS
        try:
            status, data = self._call("/api/v2/device/heartbeat", {"cameraOk": bool(camera_ok), "appVersion": APP_VERSION},
                                      entry["deviceToken"])
        except Exception as e:
            self.last_error = f"서버에 연결할 수 없어요 ({type(e).__name__})"
            return self.heartbeat_override or 10          # 끊겼으면 조금 자주 다시 시도
        if status == 401:
            self._revoked()
            self.last_error = "앱에서 기기 연결이 해제됐어요"
            return DEFAULT_HEARTBEAT_SECONDS
        if status != 200:
            self.last_error = data.get("message") or f"HTTP {status}"
            return self.heartbeat_override or 10
        with self._lock:
            self.server_on = bool(data.get("enabled", True))
            if self._entry and data.get("location") and data["location"] != self._entry.get("location"):
                self._entry = dict(self._entry, location=data["location"])
                self._save(self._entry)
        self.last_ok_at, self.last_error = time.time(), None
        if self.local_on is not None and self.server_on != self.local_on:
            self._send_enabled(self.local_on)            # 서버를 이 PC 의 상태에 맞춤
        return self.heartbeat_override or data.get("heartbeatSeconds") or DEFAULT_HEARTBEAT_SECONDS

    def set_local(self, on):
        """The dashboard tells whether detection runs on this PC (Start/Stop). Sent with the next status signal."""
        on = bool(on)
        if on != self.local_on:
            self.local_on = on
            self.nudge()

    def _send_enabled(self, on):
        entry = self._entry
        if not entry:
            return
        try:
            status, data = self._call("/api/v2/device/enabled", {"enabled": bool(on)}, entry["deviceToken"])
        except Exception as e:
            self.last_error = f"서버에 연결할 수 없어요 ({type(e).__name__})"
            return
        if status == 401:
            self._revoked()
            return
        if status == 200:
            self.server_on = bool(data.get("enabled", on))

    def start(self, camera_ok_fn):
        """Status signals in a background thread while the program runs."""
        def loop():
            while not self._stop.is_set():
                interval = self.heartbeat(camera_ok_fn()) if self.paired else 5
                self._wake.wait(interval)
                self._wake.clear()
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def nudge(self):
        """Send the next status signal now (e.g. right after the camera started or stopped)."""
        self._wake.set()

    # ---- 낙상 ----
    def send_fall(self, event_id, fall_type, is_test, image_b64=None, log=print):
        """Send one fall (same event_id on every retry, so the server makes one incident).
        Returns the server answer. Raises DeviceRevoked (401: not retried) or RuntimeError after the retries."""
        entry = self._entry
        if not entry:
            raise DeviceRevoked("not paired")
        body = {"event_id": event_id, "fall_type": fall_type, "is_test": bool(is_test)}
        if image_b64:
            body["image_jpeg_base64"] = image_b64
        error = None
        for attempt in range(len(SEND_RETRY_DELAYS) + 1):
            if attempt:
                time.sleep(SEND_RETRY_DELAYS[attempt - 1])
                log(f"[device] 재시도 {attempt}/{len(SEND_RETRY_DELAYS)} (event {event_id[:8]})")
            try:
                status, data = self._call("/api/v2/device/events", body, entry["deviceToken"])
            except Exception as e:
                error = str(e)                          # 서버 꺼짐·네트워크 오류: 재시도
                continue
            if status == 401:
                self._revoked()
                raise DeviceRevoked(data.get("message") or "401")
            if status >= 500:
                error = f"HTTP {status}"
                continue
            if status != 200 or not data.get("ok"):
                raise RuntimeError(data.get("message") or f"HTTP {status}")   # 잘못된 요청: 다시 보내도 같음
            self.last_ok_at = time.time()
            return data
        raise RuntimeError(error or "전송 실패")
