import base64
import binascii
import html
import json
import os
import re
import secrets
import socket
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

import notify_rules
from notifiers import NotificationDispatcher, build_notifiers

ENV_FILE = Path(__file__).parent / ".env"


def _load_env_file(path):
    """Read KEY=VALUE lines from server/.env into os.environ (values already in the environment win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


# 비밀 설정(텔레그램 토큰 등)은 server/.env 에 둠 (GitHub에 올라가지 않음, 예시: .env.example)
_load_env_file(ENV_FILE)

# ---- 조정 가능한 설정값 ----
# 낙상 후 사용자 응답을 기다리는 시간(초). 환경변수 FALL_RESPONSE_TIMEOUT으로도 변경 가능
RESPONSE_TIMEOUT_SECONDS = int(os.environ.get("FALL_RESPONSE_TIMEOUT", "60"))
# 직전 '도움 요청' 알림 후 이 시간(초) 안에 온 도움 요청은 중복(두 번 누름·재시도)으로 보고 알림을 보내지 않음
HELP_ALERT_COOLDOWN = float(os.environ.get("HELP_ALERT_COOLDOWN", "10"))
MAX_IMAGE_BYTES = 1_000_000  # 디코딩 후 최대 1MB
COOKIE_MAX_AGE = 30 * 24 * 3600  # 로그인 쿠키 유지 기간(초)
SERVER_PORT = 8000  # 접속 주소 안내용 (실행 포트와 맞출 것)
TIMEOUT_CHECK_INTERVAL = 1  # 응답 시간 초과를 검사하는 주기(초)

BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "images"
EVENTS_FILE = BASE_DIR / "events.json"
TOKEN_FILE = BASE_DIR / "access_token.txt"
CONFIRM_PAGE = BASE_DIR / "static" / "confirm.html"
IMAGE_DIR.mkdir(exist_ok=True)

COOKIE_NAME = "fall_access"
TOKEN_HEADER = "X-Access-Token"
EVENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")

STATUS_LABELS = {
    "detected": "낙상 감지",
    "awaiting_response": "응답 대기",
    "safe": "안전 확인",
    "help_needed": "도움 요청",
    "timeout": "응답 시간 초과",
}
LATE_PREFIX = "시간 초과 후 "  # 제한 시간이 지난 뒤 누른 응답의 표시 앞말

# ---- 알림 (규칙: notify_rules.py, 전송: notifiers.py) ----
dispatcher = NotificationDispatcher(build_notifiers(os.environ))


def _timeout_watcher(stop):
    """Mark overdue events as timed out every second, so timeout alerts go out even when nobody is viewing a page."""
    while not stop.wait(TIMEOUT_CHECK_INTERVAL):
        try:
            with _lock:
                _refresh_timeouts()
        except Exception as e:  # 감시 작업이 멈추지 않도록 오류는 기록만 함
            print(f"[server] 시간 초과 검사 오류: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app):
    dispatcher.start()
    stop = threading.Event()
    threading.Thread(target=_timeout_watcher, args=(stop,), name="timeout-watcher", daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Fall Detection Server", lifespan=lifespan)


# ---- 접근 토큰 ----
def _load_or_create_token():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


ACCESS_TOKEN = _load_or_create_token()


def _lan_ip():
    # 실제 패킷은 보내지 않고, 외부로 나가는 인터페이스의 IP만 확인
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


print("=" * 60)
print("낙상 감지 서버 접속 주소 (처음 한 번 이 주소로 접속하면 로그인됩니다)")
print(f"  이 컴퓨터 : http://127.0.0.1:{SERVER_PORT}/login?token={ACCESS_TOKEN}")
print(f"  같은 Wi-Fi: http://{_lan_ip()}:{SERVER_PORT}/login?token={ACCESS_TOKEN}")
print("  (토큰은 server/access_token.txt 에 저장되어 있습니다. 외부에 공유하지 마세요)")
print("=" * 60)


def _is_authorized(request: Request):
    supplied = request.headers.get(TOKEN_HEADER) or request.cookies.get(COOKIE_NAME) or ""
    return secrets.compare_digest(supplied.encode(), ACCESS_TOKEN.encode())


def require_auth(request: Request):
    if not _is_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


UNAUTHORIZED_PAGE = """
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>접근 권한 없음</title></head>
<body style="font-family: sans-serif; padding: 24px">
<h2>접근 권한이 없습니다</h2>
<p>서버 콘솔에 표시된 <b>/login?token=...</b> 주소로 먼저 접속해 주세요.</p>
</body></html>
"""


def _page_or_401(request: Request):
    return None if _is_authorized(request) else HTMLResponse(UNAUTHORIZED_PAGE, status_code=401)


# ---- 이벤트 저장소 (메모리 + events.json) ----
_lock = threading.Lock()
events = {}  # event_id -> event dict (삽입 순서 = 발생 순서)


def _now_str(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time()).strftime("%Y-%m-%d %H:%M:%S")


def _load_events():
    if not EVENTS_FILE.exists():
        return
    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        for ev in data:
            events[ev["event_id"]] = ev
    except (ValueError, KeyError, OSError) as e:
        print(f"[server] events.json 읽기 실패 (빈 기록으로 시작): {e}")


def _save_events():
    # 임시 파일에 쓴 뒤 교체해 저장 도중 꺼져도 파일이 깨지지 않게 함
    tmp = EVENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(list(events.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, EVENTS_FILE)


def _add_history(ev, status, ts=None, note=None):
    entry = {"status": status, "time": _now_str(ts)}
    if note:
        entry["note"] = note
    ev["history"].append(entry)


def _notify(ev, trigger, previous_response=None):
    """Ask the rules whether this change needs an alert; if so, record it and hand it to the dispatcher."""
    now = time.time()
    notification = notify_rules.decide(ev, trigger, RESPONSE_TIMEOUT_SECONDS, previous_response,
                                       help_cooldown=HELP_ALERT_COOLDOWN, now=now)
    if notification is None:
        if trigger == "help_needed":
            print(f"[notify] help 알림 생략 - 직전 도움 요청 알림 후 {HELP_ALERT_COOLDOWN:g}초 이내 (event {ev['event_id'][:8]})")
        return
    # 보내기 전에 먼저 기록해 같은 알림이 두 번 나가지 않게 함 (규칙은 이 기록으로 횟수·간격을 판단)
    ev["last_alert"] = notification.kind
    ev["alerts"].append({"kind": notification.kind, "time": _now_str(now), "ts": now,
                         "channels": dispatcher.channel_names})
    channels = ", ".join(dispatcher.channel_names) or "채널 없음 - 전송 안 함"
    print(f"[notify] {notification.kind} 알림 (event {ev['event_id'][:8]}, {channels})")
    dispatcher.notify(notification)


def _apply_timeout(ev, now=None):
    """Switch an unanswered event to timeout once its deadline has passed. Returns True if changed."""
    now = now if now is not None else time.time()
    if ev["status"] == "awaiting_response" and now > ev["deadline"]:
        ev["status"] = "timeout"
        _add_history(ev, "timeout", ev["deadline"])
        _notify(ev, "timeout")
        return True
    return False


def _refresh_timeouts():
    changed = False
    for ev in events.values():
        changed |= _apply_timeout(ev)
    if changed:
        _save_events()


def _detected_ts(ev):
    """Detection time as a timestamp (events saved before detected_ts existed use the time string)."""
    if ev.get("detected_ts") is not None:
        return ev["detected_ts"]
    return datetime.strptime(ev["time"], "%Y-%m-%d %H:%M:%S").timestamp()


def _public(ev):
    """Event as returned to clients, with labels and remaining time."""
    out = dict(ev)
    out["status_label"] = STATUS_LABELS.get(ev["status"], ev["status"])
    if ev.get("late_response") and ev["status"] in ("safe", "help_needed"):
        out["status_label"] = LATE_PREFIX + out["status_label"]
    out["remaining_seconds"] = (max(0, int(ev["deadline"] - time.time()))
                                if ev["status"] == "awaiting_response" else 0)
    return out


_load_events()


# ---- API ----
class FallEvent(BaseModel):
    device_id: str
    fall_type: str = "unknown"
    is_test: bool = False
    # 대시보드가 만든 고유 ID (재시도 시 같은 값을 보내 중복 기록 방지). 없으면 서버가 생성
    event_id: Optional[str] = Field(None, pattern=r"^[0-9a-f]{32}$")
    # 실루엣 처리된 JPEG (base64). 없으면 이미지 없이 기록만 저장
    image_jpeg_base64: Optional[str] = Field(None, max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)


class UserResponse(BaseModel):
    response: Literal["safe", "help_needed"]


def _decode_jpeg(data):
    """Return JPEG bytes if data is a valid base64 JPEG within the size limit, else None."""
    try:
        image = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(image) > MAX_IMAGE_BYTES or not image.startswith(b"\xff\xd8\xff"):
        return None
    return image


@app.post("/api/events", dependencies=[Depends(require_auth)])
def add_event(event: FallEvent):
    event_id = event.event_id or uuid.uuid4().hex
    with _lock:
        # 재시도로 같은 이벤트가 다시 오면 새로 만들지 않고 기존 기록을 돌려줌
        if event_id in events:
            ev = events[event_id]
            return {"ok": True, "event_id": event_id, "image_saved": ev["image"] is not None, "duplicate": True}

        now = time.time()
        ev = {
            "event_id": event_id,
            "device_id": event.device_id,
            "fall_type": event.fall_type,
            "is_test": event.is_test,
            "time": _now_str(now),
            "detected_ts": now,
            "deadline": now + RESPONSE_TIMEOUT_SECONDS,
            "status": "detected",
            "image": None,
            "response": None,
            "responded_at": None,
            "response_seconds": None,  # 낙상 감지부터 (마지막) 응답까지 걸린 시간
            "late_response": False,    # 응답 제한 시간이 지난 뒤 응답했는지
            "last_alert": None,        # 마지막으로 보낸 알림 종류 (중복 알림 방지)
            "alerts": [],              # 보낸 알림 기록
            "history": [],
        }
        _add_history(ev, "detected", now)

        # 이미지가 잘못되어도 낙상 기록 자체는 저장함
        if event.image_jpeg_base64:
            image = _decode_jpeg(event.image_jpeg_base64)
            if image:
                (IMAGE_DIR / f"{event_id}.jpg").write_bytes(image)
                ev["image"] = f"/images/{event_id}.jpg"

        ev["status"] = "awaiting_response"
        _add_history(ev, "awaiting_response", now)
        events[event_id] = ev
        _save_events()
    return {"ok": True, "event_id": event_id, "image_saved": ev["image"] is not None, "count": len(events)}


@app.get("/api/events", dependencies=[Depends(require_auth)])
def list_events(limit: int = 50):
    with _lock:
        _refresh_timeouts()
        return [_public(ev) for ev in reversed(list(events.values()))][:max(1, min(limit, 500))]


@app.get("/api/events/{event_id}", dependencies=[Depends(require_auth)])
def get_event(event_id: str):
    with _lock:
        ev = events.get(event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        if _apply_timeout(ev):
            _save_events()
        return _public(ev)


@app.post("/api/events/{event_id}/response", dependencies=[Depends(require_auth)])
def respond(event_id: str, body: UserResponse):
    with _lock:
        ev = events.get(event_id)
        if not ev:
            raise HTTPException(status_code=404, detail="Event not found")
        now = time.time()
        _apply_timeout(ev, now)

        # 버튼을 누른 시각과 낙상 감지 시각의 차이로 제한 시간 초과 여부를 판단
        elapsed = now - _detected_ts(ev)
        late = elapsed > RESPONSE_TIMEOUT_SECONDS

        notes = []
        if late:
            notes.append("시간 초과 후 응답")
        if ev["response"] and ev["response"] != body.response:
            notes.append(f"응답 변경 ({STATUS_LABELS[ev['response']]} → {STATUS_LABELS[body.response]})")

        previous_response = ev["response"]
        ev["status"] = body.response
        ev["response"] = body.response
        ev["responded_at"] = _now_str(now)
        ev["response_seconds"] = round(elapsed, 1)
        ev["late_response"] = late
        _add_history(ev, body.response, now, ", ".join(notes) or None)
        _notify(ev, body.response, previous_response)
        _save_events()
        return _public(ev)


@app.get("/images/{event_id}.jpg", dependencies=[Depends(require_auth)])
def get_image(event_id: str):
    if not EVENT_ID_RE.match(event_id):
        raise HTTPException(status_code=404, detail="Image not found")
    path = IMAGE_DIR / f"{event_id}.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---- 페이지 ----
@app.get("/login")
def login(token: str = ""):
    if not secrets.compare_digest(token.encode(), ACCESS_TOKEN.encode()):
        return HTMLResponse(UNAUTHORIZED_PAGE, status_code=401)
    response = RedirectResponse("/confirm", status_code=303)
    response.set_cookie(COOKIE_NAME, ACCESS_TOKEN, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return response


@app.get("/confirm", response_class=HTMLResponse)
def confirm_page(request: Request):
    denied = _page_or_401(request)
    if denied:
        return denied
    return HTMLResponse(CONFIRM_PAGE.read_text(encoding="utf-8"))


def _image_cell(e):
    if not e.get("image"):
        return "<td>-</td>"
    src = html.escape(e["image"])
    return (f'<td><a href="{src}" target="_blank">'
            f'<img src="{src}" width="160" loading="lazy" alt="실루엣 이미지"></a></td>')


def _seconds_cell(e):
    seconds = e.get("response_seconds")
    return "<td>-</td>" if seconds is None else f"<td>{seconds:.1f}</td>"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    denied = _page_or_401(request)
    if denied:
        return denied
    with _lock:
        _refresh_timeouts()
        rows_data = [_public(ev) for ev in reversed(list(events.values()))]
    rows = "".join(
        f"<tr><td>{e['time']}</td>"
        f"<td>{html.escape(e['device_id'])}</td>"
        f"<td>{html.escape(e['fall_type'])}</td>"
        f"<td>{'테스트' if e['is_test'] else '실제'}</td>"
        f"<td class='st-{e['status']}{' late' if e.get('late_response') else ''}'>{e['status_label']}</td>"
        f"<td>{e['responded_at'] or '-'}</td>"
        f"{_seconds_cell(e)}"
        f"{_image_cell(e)}</tr>"
        for e in rows_data
    )
    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="5">
        <title>낙상 감지 서버</title>
        <style>
            .st-awaiting_response, .st-detected {{ background: #fff4cc; }}
            .st-safe {{ background: #d9f2df; }}
            .st-help_needed {{ background: #ffd6d6; font-weight: bold; }}
            .st-timeout {{ background: #ffe0b3; font-weight: bold; }}
            .late {{ font-weight: bold; outline: 2px solid #bc4c00; outline-offset: -2px; }}
            .table-wrap {{ overflow-x: auto; }}
        </style>
    </head>
    <body style="font-family: sans-serif; padding: 16px">
        <h1>낙상 기록</h1>
        <p>총 {len(rows_data)}건 (5초마다 자동 새로고침) · <a href="/confirm">사용자 확인 화면</a>
           · 응답 제한 시간 {RESPONSE_TIMEOUT_SECONDS}초</p>
        <div class="table-wrap">
        <table border="1" cellpadding="8" style="border-collapse: collapse">
            <tr><th>시간</th><th>기기</th><th>유형</th><th>구분</th><th>상태</th><th>응답 시각</th><th>응답 소요(초)</th><th>이미지</th></tr>
            {rows}
        </table>
        </div>
    </body>
    </html>
    """
