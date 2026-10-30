import base64
import binascii
import html
import json
import logging
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
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

import accounts
import background
import address_search
import alerts
import db
import devices
import push
import door_codes
import escalation
import incidents
import legacy_devices
import notify_rules
import people as people_mod
import report119
import report_message
import residents as residents_mod
from notifiers import ButtonResult, NotificationDispatcher, build_notifiers, build_receivers

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
# 보호자 대기 -> 119 신고(시뮬레이션). 실제 119에는 절대 연락하지 않음 (규칙: escalation.py)
ESCALATION = escalation.Settings(
    # 무응답 알림 후 보호자가 아무 버튼도 누르지 않으면 자동 신고하기까지의 시간(초)
    wait_after_timeout=float(os.environ.get("GUARDIAN_WAIT_AFTER_TIMEOUT", "180")),
    # 본인 '도움이 필요해요' 알림 후 보호자 대기 시간(초)
    wait_after_help=float(os.environ.get("GUARDIAN_WAIT_AFTER_HELP", "90")),
    # 낙상자 미확인일 때 의료 정보: exclude(제외, 기본) / all(거주자 전원 포함)
    unconfirmed_policy="all" if os.environ.get("REPORT_UNCONFIRMED_MEDICAL", "").strip().lower() == "all" else "exclude",
    # 거주자 정보 갱신일이 이 일수보다 오래되면 '정보가 오래됐을 수 있음'
    stale_days=int(os.environ.get("PROFILE_STALE_DAYS", "180")),
)
# 신고(시뮬레이션)의 집 공통 정보 (비어 있으면 '미등록'). 웹페이지 신고 기록에만 표시, 저장·전송하지 않음
HOME_INFO = report119.HomeInfo(
    address=os.environ.get("REPORT_ADDRESS", "").strip(),
    door_code=os.environ.get("DOOR_CODE", "").strip(),
    building_door_code=os.environ.get("BUILDING_DOOR_CODE", "").strip(),
    contact=os.environ.get("REPORT_CONTACT", "").strip(),
)
# 신고 기록 상세(주소·현관 비번·의료 정보) 페이지 접근 범위: anywhere(토큰만 있으면 어디서나, 기본) / local(이 PC에서만)
REPORT_PAGE_LOCAL_ONLY = os.environ.get("REPORT_PAGE_ACCESS", "").strip().lower() == "local"
# 신고 완료 알림의 '상세 보기' 버튼: 누른 보호자의 텔레그램 대화창에 신고 상세(주소·현관 비번·의료 정보)를 답장.
# 진짜 정보를 넣을 때는 false 로 끄세요 (텔레그램에 보낸 내용은 텔레그램 서버와 휴대폰에 남습니다)
ESCALATION.show_detail = os.environ.get("SHOW_DETAIL_IN_TELEGRAM", "true").strip().lower() not in ("false", "0", "off", "no")
# 휴대폰에서 열리는 서버 주소 (예: https://example.com). 있을 때만 신고 완료 알림에 웹 링크를 붙임
ESCALATION.public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
MAX_IMAGE_BYTES = 1_000_000  # 디코딩 후 최대 1MB
COOKIE_MAX_AGE = 30 * 24 * 3600  # 로그인 쿠키 유지 기간(초)
SERVER_PORT = 8000  # 접속 주소 안내용 (실행 포트와 맞출 것)
TIMEOUT_CHECK_INTERVAL = 1  # 응답 시간 초과를 검사하는 주기(초)
# 끝난 사고의 사진 보관 기간(일)과 지우는 작업 주기(초). 시험에서만 짧게 바꿈
PHOTO_RETENTION_DAYS = float(os.environ.get("PHOTO_RETENTION_DAYS", "14"))
PHOTO_CLEANUP_SECONDS = float(os.environ.get("PHOTO_CLEANUP_SECONDS", "3600"))

BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "images"
EVENTS_FILE = BASE_DIR / "events.json"
TOKEN_FILE = BASE_DIR / "access_token.txt"
TELEGRAM_STATE_FILE = BASE_DIR / "telegram_state.json"  # 마지막으로 처리한 텔레그램 버튼 번호
RESIDENTS_FILE = BASE_DIR / "residents.json"  # 거주자 프로필 (의료 정보 포함, GitHub에 올리지 않음)
CONFIRM_PAGE = BASE_DIR / "static" / "confirm.html"
# 새 웹앱(/app/next) 데이터베이스. 기존 events.json·residents.json 은 아직 여기로 옮기지 않음 (db.py 참고)
DB_PATH = Path(os.environ.get("FALL_DB_PATH") or BASE_DIR / "fall.db")
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
    # 보호자·119 흐름 (history에만 기록)
    "guardian_wait": "보호자 응답 대기",
    "guardian_confirmed": "보호자 확인",
    "reported_119": "119 신고(시뮬레이션)",
    "report_cancel_requested": "신고 후 취소",
    "escalation_cancelled": "예약 신고 취소",
    "fallen_confirmed": "낙상자 확정",
    "fallen_confirmed_after_report": "신고 후 확정(참고용)",
    "report_detail_sent": "상세 보기 전송",
    # incident 방식으로 등록된 기기 (legacy_devices.py): 새 웹앱 사고가 처리하고 옛 흐름은 시작하지 않음
    "handed_over": "새 웹앱에서 처리",
}
LATE_PREFIX = "시간 초과 후 "  # 제한 시간이 지난 뒤 누른 응답의 표시 앞말

# ---- 알림 (규칙: notify_rules.py, 전송: notifiers.py) ----
dispatcher = NotificationDispatcher(build_notifiers(os.environ))


def _expire_photos():
    """Delete the photos of incidents that ended PHOTO_RETENTION_DAYS ago (incidents.expire_photos). For a photo of
    an old /api/events event, its event record also forgets the photo, so the old screens show none.
    Old events that never became an incident keep their photo PHOTO_RETENTION_DAYS from the event time."""
    keep_s = PHOTO_RETENTION_DAYS * 24 * 3600
    with db.session(DB_PATH) as conn:
        ids = incidents.expire_photos(conn, keep_ms=int(keep_s * 1000))
        linked = {r["photo_id"] for r in conn.execute("SELECT photo_id FROM incident_photos")}
    now = time.time()
    with _lock:
        ids += [eid for eid, ev in events.items()
                if ev.get("image") and eid not in linked and _detected_ts(ev) + keep_s <= now]
    changed = False
    for photo_id in ids:
        if not EVENT_ID_RE.match(photo_id):
            continue
        with _lock:
            ev = events.get(photo_id)
            if ev and ev.get("image"):
                ev["image"] = None
                changed = True
        try:
            (IMAGE_DIR / f"{photo_id}.jpg").unlink(missing_ok=True)
        except OSError as e:
            print(f"[photo] 사진 파일을 지우지 못함: {type(e).__name__}: {e}")
    if changed:
        with _lock:
            _save_events()
    if ids:
        print(f"[photo] 끝난 지 {PHOTO_RETENTION_DAYS:g}일이 지난 사고의 사진 {len(ids)}장을 지움")


def _timeout_watcher(stop):
    """Every second: mark overdue events as timed out and run due auto reports, even when nobody is viewing a page.
    Every PHOTO_CLEANUP_SECONDS (and once at start): delete the photos of incidents that ended long enough ago."""
    next_cleanup = 0.0
    while not stop.wait(TIMEOUT_CHECK_INTERVAL):
        if time.time() >= next_cleanup:
            next_cleanup = time.time() + PHOTO_CLEANUP_SECONDS
            try:
                _expire_photos()
            except Exception as e:  # 사진 정리 오류가 다른 처리를 막지 않도록 따로 잡음
                print(f"[photo] 사진 보관 기간 처리 오류: {type(e).__name__}: {e}")
        try:
            with _lock:
                _refresh_timeouts()
        except Exception as e:  # 감시 작업이 멈추지 않도록 오류는 기록만 함
            print(f"[server] 시간 초과 검사 오류: {type(e).__name__}: {e}")
        # 새 웹앱 낙상 사고: 60초 무응답·자동 신고(모의) 시간 처리, 대기 중인 문자(모의)·텔레그램·푸시 보내기.
        # 단계마다 따로: 한 단계의 오류가 다른 단계(예: 푸시)를 막지 않음 (background.py)
        try:
            with db.session(DB_PATH) as conn:
                background.run_each([
                    ("사고 시간", lambda: incidents.tick(conn)),
                    ("문자", lambda: alerts.process_due(conn, SMS_SENDER, incidents.now_ms())),
                    ("텔레그램", lambda: alerts.process_telegram_due(conn, TELEGRAM_CHANNEL, incidents.now_ms())),
                    ("푸시", lambda: push.process_due(conn, PUSH_SENDER, incidents.now_ms())),
                ])
        except Exception as e:
            print(f"[incident] 사고 처리 준비 오류: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app):
    dispatcher.start()
    # 보호자 버튼 수신 (텔레그램 getUpdates 폴링)
    for receiver in build_receivers(os.environ, str(TELEGRAM_STATE_FILE), _on_guardian_action):
        receiver.start()
    stop = threading.Event()
    threading.Thread(target=_timeout_watcher, args=(stop,), name="timeout-watcher", daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Fall Detection Server", lifespan=lifespan)

# 모든 응답에 기본 보안 헤더 (감사 2026-10-29, H-4): 다른 사이트가 화면을 몰래 끼워 보여 주지 못하게, 파일 종류를
# 짐작하지 않게, 다른 사이트로 주소를 넘기지 않게. 응답이 이미 정한 값(예: 로그인의 no-referrer)은 그대로 둠
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"}


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        if key not in response.headers:
            response.headers[key] = value
    return response


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


# 관리자 로그인 안내. 토큰 값은 화면·로그에 남지 않게 출력하지 않음 (파일에서 직접 확인)
print("=" * 60)
print("낙상 감지 서버 관리자 로그인 (처음 한 번 이 주소로 접속하면 로그인됩니다)")
print(f"  이 컴퓨터 : http://127.0.0.1:{SERVER_PORT}/login?token=<토큰>")
print(f"  이 컴퓨터의 네트워크 주소: {_lan_ip()} (HTTPS 로 공개할 때는 deploy/https/README.md)")
print(f"  <토큰> = {TOKEN_FILE} 파일의 내용. 외부에 공유하지 마세요")
print("=" * 60)
print(f"[report] 신고 기록 상세 페이지: {'이 PC에서만' if REPORT_PAGE_LOCAL_ONLY else '토큰이 있으면 어디서나'} (REPORT_PAGE_ACCESS)")
print(f"[report] 텔레그램 '상세 보기' 버튼: {'켜짐' if ESCALATION.show_detail else '꺼짐'} (SHOW_DETAIL_IN_TELEGRAM)"
      f" / 웹 링크: {ESCALATION.public_base_url or '없음'} (PUBLIC_BASE_URL)")


class _HideTokenInAccessLog(logging.Filter):
    """uvicorn's access log prints each request path with its query; the old admin login sends the shared token as
    ?token=..., and the address search sends the home address as ?q=..., so both are masked here (behind the HTTPS
    proxy, the proxy's own log is filtered the same way)."""
    _token = re.compile(r"(?i)\b(token|q)=[^&\s\"]+")

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            record.args = record.args[:2] + (self._token.sub(r"\1=***", record.args[2]),) + record.args[3:]
        return True


logging.getLogger("uvicorn.access").addFilter(_HideTokenInAccessLog())


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


def _residents():
    # 필요할 때마다 다시 읽음 (파일을 고친 뒤 서버를 재시작하지 않아도 됨)
    return residents_mod.load(RESIDENTS_FILE)


def _image_path(ev):
    path = IMAGE_DIR / f"{ev['event_id']}.jpg"
    return str(path) if ev.get("image") and path.is_file() else None


def _notify(ev, trigger, previous_response=None):
    """Ask the rules whether this change needs an alert; if so, record it and hand it to the dispatcher."""
    now = time.time()
    notification = notify_rules.decide(ev, trigger, RESPONSE_TIMEOUT_SECONDS, previous_response,
                                       help_cooldown=HELP_ALERT_COOLDOWN, now=now, image_path=_image_path(ev),
                                       guardian_wait=escalation.remaining(ev, now), residents=_residents())
    if notification is None:
        if trigger == "help_needed":
            print(f"[notify] help 알림 생략 - 직전 도움 요청 알림 후 {HELP_ALERT_COOLDOWN:g}초 이내 (event {ev['event_id'][:8]})")
        return
    _send(ev, notification, now)


def _send(ev, notification, now):
    # 보내기 전에 먼저 기록해 같은 알림이 두 번 나가지 않게 함 (규칙은 이 기록으로 횟수·간격을 판단)
    ev["last_alert"] = notification.kind
    ev["alerts"].append({"kind": notification.kind, "time": _now_str(now), "ts": now,
                         "channels": dispatcher.channel_names})
    channels = ", ".join(dispatcher.channel_names) or "채널 없음 - 전송 안 함"
    photo = ", 사진 포함" if notification.image_path else ""
    print(f"[notify] {notification.kind} 알림 (event {ev['event_id'][:8]}, {channels}{photo})")
    dispatcher.notify(notification)


def _apply_steps(ev, steps, now):
    """Apply the result of an escalation rule: add history entries and send its alerts. Returns True if changed."""
    for status, note in steps.history:
        _add_history(ev, status, now, note)
    for notification in steps.notifications:
        _send(ev, notification, now)
    return bool(steps.history or steps.notifications)


def _report_view(ev):
    """(report, contents, details, after-report note) for the report page and the Telegram detail reply.

    The values are filled in now from residents.json and .env; the result is never stored or logged.
    Returns None when the fall has no report in the current format.
    """
    report = (ev.get("escalation") or {}).get("report")
    if not report or "contents" not in report:
        return None
    fallen = ev["escalation"].get("fallen")
    after = escalation.describe_fallen(ev) if fallen and fallen["after_report"] else ""
    detail = report119.details(report["contents"], _residents(), HOME_INFO, ESCALATION.stale_days)
    return report, report["contents"], detail, after


def _detail_reply(ev, actor, now):
    """'상세 보기' button: reply with the report details to the presser's chat only."""
    if not ESCALATION.show_detail:
        return ButtonResult(reply="상세 보기 기능이 꺼져 있어요.")
    view = _report_view(ev)
    if view is None:
        return ButtonResult(reply="이 낙상에는 상세 신고 기록이 없어요.")
    report, contents, detail, after = view
    how = f"보호자 요청 ({report['by']})" if report["by"] else "보호자 무응답으로 자동 신고"
    header = ("[테스트] " if ev.get("is_test") else "") + "📄 119 신고(시뮬레이션) 상세\n" \
        "⚠️ 시뮬레이션입니다. 실제 119에는 연락하지 않았습니다.\n" \
        f"낙상 감지: {ev['time']} / 신고: {report['time']}\n" \
        f"상태: {escalation.REASON_LABELS.get(report['reason'], report['reason'])} / 신고 경위: {how}"
    # 누가 언제 상세를 받았는지만 기록 (내용은 저장하지 않음)
    _add_history(ev, "report_detail_sent", now, actor.get("name") or str(actor.get("id")))
    _save_events()
    return ButtonResult(reply="상세 내용을 이 대화창에 보냈어요.",
                        message=report119.format_text(header, contents, detail, after))


def _on_guardian_action(event_id, action, actor):
    """A registered guardian pressed a button (called by a receiver thread). Returns the reply to show."""
    if not EVENT_ID_RE.match(event_id or ""):
        return "알 수 없는 버튼이에요."
    with _lock:
        ev = events.get(event_id)
        if not ev:
            return "낙상 기록을 찾을 수 없어요."
        now = time.time()
        if action == escalation.DETAIL:
            return _detail_reply(ev, actor, now)
        steps = escalation.on_guardian(ev, action, actor, now, ESCALATION, _residents(), _image_path(ev))
        if _apply_steps(ev, steps, now):
            _save_events()
        return steps.reply


def _apply_timeout(ev, now=None):
    """Switch an unanswered event to timeout once its deadline has passed. Returns True if changed."""
    now = now if now is not None else time.time()
    if ev["status"] == "awaiting_response" and now > ev["deadline"]:
        ev["status"] = "timeout"
        _add_history(ev, "timeout", ev["deadline"])
        # 보호자 대기를 먼저 시작해야 알림에 버튼과 남은 시간이 붙음
        _apply_steps(ev, escalation.start_wait(ev, "timeout", now, ESCALATION), now)
        _notify(ev, "timeout")
        return True
    return False


def _refresh_timeouts():
    changed = False
    now = time.time()
    for ev in events.values():
        changed |= _apply_timeout(ev, now)
        # 보호자 대기 시간이 끝났으면 자동 119 신고(시뮬레이션)
        if escalation.report_due(ev, now):
            changed |= _apply_steps(ev, escalation.on_tick(ev, now, ESCALATION, _residents(), _image_path(ev)), now)
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
    now = time.time()
    out["remaining_seconds"] = (max(0, int(ev["deadline"] - now))
                                if ev["status"] == "awaiting_response" else 0)
    # 자동 119 신고(시뮬레이션) 예정 시각 (대기 중이 아니면 None). 대시보드 카운트다운용
    wait = escalation.remaining(ev, now)
    out["report_at"] = ev["escalation"]["report_at"] if wait is not None else None
    out["report_in_seconds"] = None if wait is None else int(wait)
    out["escalation_label"] = escalation.describe(ev, now)
    return out


_load_events()

# 새 웹앱 데이터베이스 준비 (없으면 만들고, 필요한 스키마 변경을 적용)
DB_SCHEMA_VERSION = db.init(DB_PATH)
print(f"[db] 웹앱 데이터베이스: {DB_PATH.name} (스키마 버전 {DB_SCHEMA_VERSION})")
# 현관 비밀번호 암호화 키 (server/.env 의 DOOR_CODE_KEY). 키 값은 출력하지 않음
print(f"[door] 현관 비밀번호 저장: {door_codes.configure(os.environ.get('DOOR_CODE_KEY', ''))}")
# 새 웹앱 낙상 사고 (incidents.py). 문자는 모의 발송만 (alerts.py, 실제 문자 업체 연결은 G단계).
# 개발용 낙상 발생(/api/v2/dev/falls)은 FD_DEV_TOOLS=1 로 켠 복사본 서버에서만 (운영 .env 에는 넣지 않음)
SMS_SENDER = alerts.build_sender(os.environ)
# 텔레그램: 새 사고의 알림도 같은 보호자 봇으로 (글자만, 버튼 없음). 받을 대화방은 legacy_devices.py 'telegram add'
TELEGRAM_CHANNEL = alerts.build_telegram(os.environ)
# 가족 휴대폰 푸시 (push.py): FCM 서비스 계정 키 파일 경로는 FCM_SERVICE_ACCOUNT_FILE (저장소 밖). 없으면 보내지 않음
PUSH_SENDER = push.build_sender(os.environ)
DEV_TOOLS = os.environ.get("FD_DEV_TOOLS", "").strip() == "1"
print(f"[incident] 문자 알림: {SMS_SENDER.name} (모의 발송 - 실제 문자를 보내지 않음) / "
      f"개발용 낙상 발생: {'켜짐 (FD_DEV_TOOLS=1 - 운영 서버에서는 켜지 마세요)' if DEV_TOOLS else '꺼짐'} / "
      f"사고 알림 텔레그램: {'사용 (등록한 그룹의 대화방에만)' if TELEGRAM_CHANNEL else '없음'}")
# 개발용 기기(PC 감지 프로그램 연결 코드, 홈캠·CCTV 시연 화면)는 FD_DEV_DEVICES=1 로 켠 시험 서버에서만 (devices.py)
print(f"[push] 가족 휴대폰 푸시: {push.describe(PUSH_SENDER)}")
print(f"[devices] 개발용 기기: {'켜짐 (FD_DEV_DEVICES=1 - 운영 서버에서는 켜지 마세요)' if devices.dev_devices() else '꺼짐'}")


def config_warnings(env):
    """Settings a real service needs, checked once at start. Only names and what is missing are printed, never
    values (audit 2026-10-29, H-5). Returns the warning lines."""
    get = lambda k: str(env.get(k, "") or "").strip()
    out = []
    if not get("DOOR_CODE_KEY"):
        out.append("DOOR_CODE_KEY 가 없어 현관 비밀번호를 저장할 수 없어요")
    if not get("JUSO_API_KEY"):
        out.append("JUSO_API_KEY 가 없어 주소 검색이 안 돼요 (직접 입력만)")
    fcm = get("FCM_SERVICE_ACCOUNT_FILE")
    if not fcm:
        out.append("FCM_SERVICE_ACCOUNT_FILE 이 없어 휴대폰 푸시 알림이 안 가요")
    elif not Path(fcm).is_file():
        out.append("FCM_SERVICE_ACCOUNT_FILE 의 파일을 찾을 수 없어 휴대폰 푸시 알림이 안 가요")
    if get("TELEGRAM_BOT_TOKEN") and get("SHOW_DETAIL_IN_TELEGRAM").lower() not in ("false", "0", "off", "no"):
        out.append("SHOW_DETAIL_IN_TELEGRAM 이 켜져 있어 신고 상세(주소·현관 비밀번호·의료 정보)가 텔레그램으로 갈 수 있어요")
    if get("REPORT_PAGE_ACCESS").lower() != "local":
        out.append("REPORT_PAGE_ACCESS 가 local 이 아니라 신고 기록 페이지가 이 PC 밖에서도 열려요")
    for key in ("FD_DEV_TOOLS", "FD_DEV_DEVICES"):
        if get(key) == "1":
            out.append(f"{key} 가 켜져 있어요 (개발·시험 서버에서만 켜세요)")
    return [f"[설정 확인] {line}" for line in out]


for _line in config_warnings(os.environ):
    print(_line)


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
            return _duplicate_event(event, event_id)
        # incident 방식 기기: 새 사고를 먼저 만들고, 성공했을 때만 옛 흐름을 넘김 (실패하면 옛 흐름으로 처리해 알림이 사라지지 않게).
        # 잠금 안에서 해서 같은 event_id 가 동시에 와도 '새 사고' 와 '옛 흐름' 이 나뉘어 둘 다 시작되지 않게 함
        handed_to = _handover_incident(event, event_id)

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
            "escalation": escalation.new_state(),  # 보호자 대기 -> 119 신고(시뮬레이션) 상태
            "history": [],
        }
        _add_history(ev, "detected", now)

        # 이미지가 잘못되어도 낙상 기록 자체는 저장함
        if event.image_jpeg_base64:
            image = _decode_jpeg(event.image_jpeg_base64)
            if image:
                (IMAGE_DIR / f"{event_id}.jpg").write_bytes(image)
                ev["image"] = f"/images/{event_id}.jpg"

        if handed_to:
            # 새 사고가 처리: 응답 대기·시간 초과·텔레그램 버튼 알림·옛 모의 신고를 시작하지 않음 (기록과 사진만 남김)
            ev["status"] = "handed_over"
            ev["incident_id"] = handed_to
            ev["deadline"] = now
            _add_history(ev, "handed_over", now)
        else:
            ev["status"] = "awaiting_response"
            _add_history(ev, "awaiting_response", now)
            # 거주자가 1명이면 그 사람으로 낙상자 자동 확정 (얼굴 인식 등 식별 기능은 쓰지 않음)
            people = _residents()
            if len(people) == 1:
                _apply_steps(ev, escalation.select_fallen(ev, people[0], None, now, how="auto"), now)
        events[event_id] = ev
        _save_events()
    # both 방식은 옛 흐름과 함께 새 사고도 만듦 (미등록 기기는 None)
    incident_id = handed_to or _legacy_incident(event, event_id)
    _link_photo(incident_id, ev)
    return {"ok": True, "event_id": event_id, "image_saved": ev["image"] is not None, "count": len(events),
            "incident_id": incident_id}


def _duplicate_event(event, event_id):
    """Retry of an event already saved: same answer, no new record. (Called with _lock held.)
    넘긴 이벤트는 그 사고 id. both 기기는 첫 요청 때 사고 연결이 실패했어도 재시도에서 연결됨 (같은 event_id 로는 사고 하나).
    incident 기기인데 첫 요청이 옛 흐름으로 처리됐으면 재시도에서도 사고를 만들지 않음 (두 흐름이 함께 돌지 않게)"""
    ev = events[event_id]
    incident_id = ev.get("incident_id") or _legacy_incident(event, event_id)
    _link_photo(incident_id, ev)
    return {"ok": True, "event_id": event_id, "image_saved": ev["image"] is not None, "duplicate": True,
            "incident_id": incident_id}


def _link_photo(incident_id, ev):
    """Link the event's saved silhouette photo to its incident (same photo only once). A failure is only logged:
    the incident and its alerts go on without the photo."""
    if not incident_id or not ev["image"]:
        return
    try:
        with db.session(DB_PATH) as conn:
            incidents.add_photo(conn, incident_id, ev["event_id"])
    except Exception as e:
        print(f"[incident] 사진을 사고에 연결하지 못함 (사고·알림은 그대로): {type(e).__name__}: {e}")


def _handover_incident(event, event_id):
    """For a device registered in 'incident' mode (not test events): create the incident and return its id,
    so the old flow is not started. None for other devices, or when it fails (then the old flow runs)."""
    if event.is_test:
        return None
    try:
        with db.session(DB_PATH) as conn:
            if legacy_devices.mode_for(conn, event.device_id) != "incident":
                return None
            return legacy_devices.incident_for_event(conn, event.device_id, event_id, event.is_test)
    except Exception as e:
        print(f"[incident] 새 사고로 넘기지 못해 옛 흐름으로 처리 (알림 유지): {type(e).__name__}: {e}")
        return None


def _legacy_incident(event, event_id):
    """New web app incident NEXT TO the old flow: only for a device registered in 'both' mode.
    An 'incident' device whose hand-over failed keeps the old flow alone (never both flows for one fall).
    Failures are logged and never break the old flow."""
    try:
        with db.session(DB_PATH) as conn:
            if legacy_devices.mode_for(conn, event.device_id) != "both":
                return None
            return legacy_devices.incident_for_event(conn, event.device_id, event_id, event.is_test)
    except Exception as e:
        print(f"[incident] 옛 이벤트를 사고로 연결하지 못함 (옛 흐름은 그대로): {type(e).__name__}: {e}")
        return None


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
        if ev.get("status") == "handed_over":
            # 새 웹앱 사고가 처리하는 낙상: 옛 응답으로 옛 흐름(텔레그램 버튼·옛 모의 신고)을 다시 시작하지 않음
            raise HTTPException(status_code=409, detail="이 낙상은 새 웹앱에서 응답해 주세요.")
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
        if body.response == "help_needed":
            # 보호자 대기를 먼저 시작(또는 단축)해야 알림에 버튼과 남은 시간이 붙음
            _apply_steps(ev, escalation.start_wait(ev, "help_needed", now, ESCALATION), now)
        else:
            # 예약된 신고 취소, 이미 신고했으면 보호자에게 신고 취소 요청
            _apply_steps(ev, escalation.on_person_safe(ev, now, ESCALATION), now)
        _notify(ev, body.response, previous_response)
        _save_events()
        return _public(ev)


@app.get("/images/{event_id}.jpg", dependencies=[Depends(require_auth)])
def get_image(event_id: str):
    """Photo of an old /api/events event (old screens, shared token). Photos sent through the device API are kept
    in the same folder but only served by /api/v2/incidents/{id}/photos (group check), so they are refused here."""
    if not EVENT_ID_RE.match(event_id):
        raise HTTPException(status_code=404, detail="Image not found")
    with _lock:
        ev = events.get(event_id)
        legacy = bool(ev and ev.get("image"))
    if not legacy:
        raise HTTPException(status_code=404, detail="Image not found")
    path = IMAGE_DIR / f"{event_id}.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---- 새 웹앱(/app/next) API: /api/v2 ----
# 사용자 로그인(fd_session 쿠키)으로만 접근. 기존 /api/... 와 공용 토큰(감지 프로그램·대시보드·Android)은 그대로.
# 그룹 관련 동작은 모두 '로그인한 사람의 그룹'에만 적용되므로 다른 가족의 그룹은 읽거나 바꿀 수 없음 (accounts.py)
NO_STORE = {"Cache-Control": "no-store"}
SESSION_COOKIE = "fd_session"
# 로그인 쿠키의 Secure 설정: HTTPS 로 접속할 때만 켤 수 있음 (HTTP 에서 켜면 브라우저가 쿠키를 보내지 않아 로그인이 안 됨).
# 비워 두면 접속 방식(https)에 따라 자동, true/false 로 고정 가능 (HTTPS 운영 시 true 권장)
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower()


class SignupBody(BaseModel):
    name: str = Field(max_length=100)
    phone: str = Field(max_length=30)
    password: str = Field(max_length=200)


class LoginBody(BaseModel):
    phone: str = Field(max_length=30)
    password: str = Field(max_length=200)


class JoinBody(BaseModel):
    code: str = Field(max_length=20)


class OnboardedBody(BaseModel):
    onboarded: bool


class ProfileBody(BaseModel):
    # 휴대전화 번호(로그인 아이디) 변경은 문자 인증 단계에서. 보내도 쓰지 않음
    name: str = Field(max_length=100)
    birth: Optional[str] = Field(default=None, max_length=20)
    conditions: Optional[List[str]] = Field(default=None, max_length=100)
    medications: Optional[List[str]] = Field(default=None, max_length=100)


class PrefBody(BaseModel):
    key: str = Field(max_length=20)
    value: bool


class SetupInfo(BaseModel):
    birth: Optional[str] = Field(default=None, max_length=20)
    conditions: Optional[List[str]] = Field(default=None, max_length=100)
    medications: Optional[List[str]] = Field(default=None, max_length=100)


class SetupHome(BaseModel):
    mode: str = Field(max_length=20)
    id: Optional[str] = Field(default=None, max_length=60)
    address: Optional[str] = Field(default=None, max_length=1000)


class SetupBody(BaseModel):
    info: SetupInfo
    home: SetupHome
    # 현관 비밀번호 {"central": "...", "door": "..."}: 형식 검사는 door_codes.py 에서 (오류 응답에 값이 나오지 않게 Any)
    doors: Optional[Dict[str, Any]] = None
    # 현관 출입 방식 {"central": {"method", "code"}, "door": {...}} (검사는 door_codes.py)
    entrances: Optional[Dict[str, Any]] = None


class DoorCodeBody(BaseModel):
    code: Any = None   # door_codes.clean_code 가 검사 (FastAPI 형식 오류는 입력값을 되돌려 주므로 여기서는 검사하지 않음)


class EntranceBody(BaseModel):
    method: Any = None   # door_codes.clean_method 가 검사
    code: Any = None     # 비밀번호 방식일 때만. 비워 두면 등록된 비밀번호를 그대로 둠


class AddressBody(BaseModel):
    address: str = Field(max_length=1000)


class PasswordBody(BaseModel):
    password: str = Field(max_length=200)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    # /api/v2 는 입력값(비밀번호·현관 비밀번호 등)을 오류 응답에 되돌려 주지 않음. 다른 주소는 FastAPI 기본 그대로
    if not request.url.path.startswith("/api/v2/"):
        return await request_validation_exception_handler(request, exc)
    detail = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
    return JSONResponse({"message": "요청 형식이 올바르지 않아요.", "field": None, "detail": detail},
                        status_code=422, headers=NO_STORE)


@app.exception_handler(accounts.AccountError)
def _account_error(request: Request, exc: accounts.AccountError):
    headers = dict(NO_STORE)
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse({"message": exc.message, "field": exc.field}, status_code=exc.status, headers=headers)


def _cookie_secure(request: Request):
    if SESSION_COOKIE_SECURE in ("true", "1", "yes", "on"):
        return True
    if SESSION_COOKIE_SECURE in ("false", "0", "no", "off"):
        return False
    return request.url.scheme == "https"


def _client_ip(request: Request):
    return request.client.host if request.client else "unknown"


def _check_origin(request: Request):
    # 다른 사이트에서 몰래 보낸 요청(CSRF) 차단: 브라우저가 붙이는 Origin 이 이 서버 주소와 다르면 거절
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host", ""):
        raise accounts.AccountError(403, "허용되지 않은 요청이에요.")


def _current_user(conn, request: Request):
    return accounts.session_user(conn, request.cookies.get(SESSION_COOKIE))


def _require_user(conn, request: Request):
    user_id = _current_user(conn, request)
    if not user_id:
        raise accounts.AccountError(401, "로그인이 필요해요. 다시 로그인해 주세요.")
    return user_id


def _state_response(conn, user_id):
    return JSONResponse({"authenticated": True, "me_id": user_id, "state": accounts.state_for(conn, user_id)},
                        headers=NO_STORE)


def _logged_in_response(conn, request: Request, user_id):
    response = _state_response(conn, user_id)
    response.set_cookie(SESSION_COOKIE, accounts.create_session(conn, user_id),
                        max_age=accounts.SESSION_DAYS * 86400, path="/",
                        httponly=True, samesite="lax", secure=_cookie_secure(request))
    return response


@app.get("/api/v2/health")
def api_v2_health():
    ok, version = db.health(DB_PATH)
    return JSONResponse({"ok": ok, "db": "ok" if ok else "error", "schema_version": version}, headers=NO_STORE)


@app.get("/api/v2/state")
def api_v2_state(request: Request):
    # 로그인한 사람: 본인과 본인 그룹 정보만. 로그인 전: 빈 상태 (예시 데이터는 쓰지 않음)
    with db.session(DB_PATH) as conn:
        user_id = _current_user(conn, request)
        if user_id:
            return _state_response(conn, user_id)
    return JSONResponse({"authenticated": False, "me_id": None, "state": accounts.empty_state()}, headers=NO_STORE)


@app.post("/api/v2/auth/signup")
def api_v2_signup(body: SignupBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = accounts.signup(conn, body.name, body.phone, body.password, _client_ip(request))
        return _logged_in_response(conn, request, user_id)


@app.post("/api/v2/auth/login")
def api_v2_login(body: LoginBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = accounts.authenticate(conn, body.phone, body.password, _client_ip(request))
        return _logged_in_response(conn, request, user_id)


@app.post("/api/v2/auth/logout")
def api_v2_logout(request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        accounts.end_session(conn, request.cookies.get(SESSION_COOKIE))
    response = JSONResponse({"authenticated": False, "me_id": None, "state": accounts.empty_state()}, headers=NO_STORE)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=_cookie_secure(request))
    return response


@app.post("/api/v2/groups")
def api_v2_create_group(request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        accounts.create_group(conn, user_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/groups/invite")
def api_v2_new_invite(request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        accounts.regenerate_invite(conn, user_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/groups/join")
def api_v2_join_group(body: JoinBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        accounts.join_group(conn, user_id, body.code)
        return _state_response(conn, user_id)


def _group_photo_ids(conn, user_id):
    """Photo ids of the incidents of the user's group (to clean up their files if the group gets deleted)."""
    return [r["photo_id"] for r in conn.execute(
        """SELECT p.photo_id FROM incident_photos p JOIN incidents i ON i.id = p.incident_id
           JOIN users u ON u.group_id = i.group_id WHERE u.id = ?""", (user_id,))]


def _remove_unlinked_photos(conn, photo_ids):
    """Delete the files of photos whose incident records are gone (the group was deleted with its last member).
    Photos of old /api/events events stay: their event record (events.json) still uses the file."""
    for photo_id in photo_ids:
        if not EVENT_ID_RE.match(photo_id) or conn.execute(
                "SELECT 1 FROM incident_photos WHERE photo_id = ?", (photo_id,)).fetchone():
            continue
        with _lock:
            legacy = photo_id in events
        if legacy:
            continue
        try:
            (IMAGE_DIR / f"{photo_id}.jpg").unlink(missing_ok=True)
        except OSError as e:
            print(f"[photo] 사진 파일을 지우지 못함: {type(e).__name__}: {e}")


@app.post("/api/v2/groups/members/{member_id}/remove")
def api_v2_remove_member(member_id: str, request: Request):
    # 다른 구성원을 그룹에서 내보내기 (구성원 누구나, 초대 코드도 새로 바뀜)
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        accounts.remove_member(conn, user_id, member_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/groups/leave")
def api_v2_leave_group(request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        photos = _group_photo_ids(conn, user_id)
        accounts.leave_group(conn, user_id)
        _remove_unlinked_photos(conn, photos)
        return _state_response(conn, user_id)


@app.post("/api/v2/me/onboarded")
def api_v2_onboarded(body: OnboardedBody, request: Request):
    # B단계: 처음 설정 완료 표시만 (감지 대상·건강 정보 등 프로필은 C단계)
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        accounts.set_onboarded(conn, user_id, body.onboarded)
        return _state_response(conn, user_id)


# 가족 휴대폰 푸시 (push.py): 로그인한 휴대폰의 알림 토큰 등록·해제. 토큰은 이 로그인 세션에 묶임 (로그아웃·탈퇴하면 함께 삭제)
class PushTokenBody(BaseModel):
    token: Any = None
    platform: Any = "android"


@app.post("/api/v2/me/push-token")
def api_v2_push_token(body: PushTokenBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        session_hash = accounts._token_hash(request.cookies.get(SESSION_COOKIE))
        push.register_token(conn, user_id, session_hash, body.token, body.platform)
        return JSONResponse({"ok": True}, headers=NO_STORE)


@app.delete("/api/v2/me/push-token")
def api_v2_push_token_delete(body: PushTokenBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        push.unregister_token(conn, user_id, body.token)
        return JSONResponse({"ok": True}, headers=NO_STORE)


# C단계: 내 정보·집·탈퇴. 모두 로그인한 사람 본인 기준이고, 집 id 는 그 사람 그룹 안에서만 찾음 (people.py)
@app.post("/api/v2/me/profile")
def api_v2_profile(body: ProfileBody, request: Request):
    _check_origin(request)
    health = {k: getattr(body, k) for k in ("birth", "conditions", "medications") if k in body.model_fields_set}
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.update_profile(conn, user_id, body.name, health)
        return _state_response(conn, user_id)


@app.post("/api/v2/me/prefs")
def api_v2_prefs(body: PrefBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.set_pref(conn, user_id, body.key, body.value)
        return _state_response(conn, user_id)


@app.post("/api/v2/me/setup")
def api_v2_setup(body: SetupBody, request: Request):
    # 처음 설정(감지 대상 켜기) 완료: 건강 정보 + 집을 한 번에 저장 (전부 저장되거나 전부 취소)
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.finish_setup(conn, user_id, body.info.model_dump(), body.home.model_dump(), doors=body.doors,
                                entrances=body.entrances)
        return _state_response(conn, user_id)


@app.post("/api/v2/homes/{home_id}/link")
def api_v2_link_home(home_id: str, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.link_home(conn, user_id, home_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/homes/{home_id}/unlink")
def api_v2_unlink_home(home_id: str, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.unlink_home(conn, user_id, home_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/homes/{home_id}/address")
def api_v2_home_address(home_id: str, body: AddressBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        people_mod.update_home_address(conn, user_id, home_id, body.address)
        return _state_response(conn, user_id)


# 현관 비밀번호: 등록·변경·삭제만 (값을 돌려주는 주소는 없음). 그 집에 연결된 가족만, 내 그룹의 집만 (door_codes.py)
@app.put("/api/v2/homes/{home_id}/door-codes/{kind}")
def api_v2_put_door_code(home_id: str, kind: str, body: DoorCodeBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        door_codes.put(conn, user_id, home_id, kind, body.code)
        return _state_response(conn, user_id)


@app.put("/api/v2/homes/{home_id}/entrances/{kind}")
def api_v2_put_entrance(home_id: str, kind: str, body: EntranceBody, request: Request):
    # 현관 출입 방식 (+ 비밀번호 방식이면 비밀번호). 다른 방식으로 바꾸면 이 현관의 비밀번호만 삭제
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        door_codes.set_entrance(conn, user_id, home_id, kind, body.method, body.code)
        return _state_response(conn, user_id)


@app.delete("/api/v2/homes/{home_id}/door-codes/{kind}")
def api_v2_delete_door_code(home_id: str, kind: str, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        door_codes.delete(conn, user_id, home_id, kind)
        return _state_response(conn, user_id)


# ---- 낙상 사고 (D단계, incidents.py): 같은 그룹만, 다른 그룹 사고는 404. 동시에 누르면 먼저 처리된 것이 기준 (나머지 409) ----
class ReportBody(BaseModel):
    targetIds: Any = None   # 낙상 대상자 id 목록 (incidents.report 가 그 집의 감지 대상자인지 검사, 비우면 전원)


class DevFallBody(BaseModel):
    homeId: Any = None
    location: Any = None
    agoSeconds: Any = 0     # 개발 시험용: 몇 초 전에 감지된 것으로 (0~600)


def _incident_action(request: Request, action, *args):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        action(conn, user_id, *args)
        return _state_response(conn, user_id)


@app.post("/api/v2/incidents/{incident_id}/self-ok")
def api_v2_incident_self_ok(incident_id: str, request: Request):
    return _incident_action(request, incidents.self_ok, incident_id)


@app.post("/api/v2/incidents/{incident_id}/help")
def api_v2_incident_help(incident_id: str, request: Request):
    return _incident_action(request, incidents.self_help, incident_id)


@app.post("/api/v2/incidents/{incident_id}/take-over")
def api_v2_incident_take_over(incident_id: str, request: Request):
    return _incident_action(request, incidents.take_over, incident_id)


@app.post("/api/v2/incidents/{incident_id}/close")
def api_v2_incident_close(incident_id: str, request: Request):
    return _incident_action(request, incidents.close_checked, incident_id)


@app.post("/api/v2/incidents/{incident_id}/report")
def api_v2_incident_report(incident_id: str, body: ReportBody, request: Request):
    # 119 신고는 모의 기록만 (report_kind='simulation'). 실제 119 전화·문자·외부 요청은 없음
    return _incident_action(request, incidents.report, incident_id, body.targetIds)


@app.post("/api/v2/incidents/{incident_id}/dismiss")
def api_v2_incident_dismiss(incident_id: str, request: Request):
    return _incident_action(request, incidents.dismiss, incident_id)


@app.get("/api/v2/incidents/{incident_id}/photos/{photo_id}.jpg")
def api_v2_incident_photo(incident_id: str, photo_id: str, request: Request):
    # 감지 기기가 가공해 보낸 실루엣 사진만 (원본은 서버에 없음). 같은 그룹의 그 사고에 연결된 사진만, 다른 그룹은 404
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        incidents.check_photo(conn, user_id, incident_id, photo_id)
    path = IMAGE_DIR / f"{photo_id}.jpg"
    if not EVENT_ID_RE.match(photo_id) or not path.is_file():
        raise accounts.AccountError(404, "사진을 찾을 수 없어요.")
    # no-cache: 브라우저가 보관본을 쓰기 전에 매번 서버에 물어봄 (로그아웃·탈퇴 뒤에는 보관본도 보이지 않게). 사진은 작음 (긴 변 640px)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})


# ---- 감지 기기 (devices.py): 앱 = 연결 코드·설정·삭제 (그 집에 연결된 가족만), 기기 = 기기 토큰으로 상태 신호·낙상 ----
# 기존 공용 토큰 API(/api/events)와 관리자 등록(legacy_devices.py)은 그대로 (지금 PC 프로그램·Android 시험 앱용)
class PairingBody(BaseModel):
    type: Any = None
    location: Any = None


class DeviceUpdateBody(BaseModel):
    location: Any = None
    enabled: Any = None


class DevicePairBody(BaseModel):
    code: Any = None
    appVersion: Any = None


class DeviceHeartbeatBody(BaseModel):
    cameraOk: Any = None
    appVersion: Any = None


class DeviceFallBody(BaseModel):
    # PC 프로그램의 /api/events 와 같은 칸 (device_id 는 토큰이 정함). 사진은 기기에서 가공한 실루엣만
    event_id: str = Field(..., pattern=r"^[0-9a-f]{32}$")
    fall_type: str = "unknown"
    is_test: bool = False
    image_jpeg_base64: Optional[str] = Field(None, max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)


@app.post("/api/v2/homes/{home_id}/devices/pairing")
def api_v2_device_pairing(home_id: str, body: PairingBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        pairing = devices.start_pairing(conn, user_id, home_id, body.type, body.location)
        return JSONResponse({"authenticated": True, "me_id": user_id, "pairing": pairing,
                             "state": accounts.state_for(conn, user_id)}, headers=NO_STORE)


@app.patch("/api/v2/devices/{device_id}")
def api_v2_device_update(device_id: str, body: DeviceUpdateBody, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        devices.update(conn, user_id, device_id, body.location, body.enabled)
        return _state_response(conn, user_id)


@app.delete("/api/v2/devices/{device_id}")
def api_v2_device_delete(device_id: str, request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        devices.remove(conn, user_id, device_id)
        return _state_response(conn, user_id)


@app.post("/api/v2/device/pair")
def api_v2_device_pair(body: DevicePairBody, request: Request):
    # 기기가 연결 코드를 한 번 보냄 → 기기 토큰 (이 응답에서만 한 번 보임, 서버에는 해시만)
    with db.session(DB_PATH) as conn:
        return JSONResponse(devices.pair(conn, body.code, _client_ip(request), body.appVersion), headers=NO_STORE)


@app.post("/api/v2/device/heartbeat")
def api_v2_device_heartbeat(body: DeviceHeartbeatBody, request: Request):
    with db.session(DB_PATH) as conn:
        device = devices.authenticate(conn, request.headers.get("authorization"))
        return JSONResponse(devices.heartbeat(conn, device, body.cameraOk, body.appVersion), headers=NO_STORE)


class DeviceEnabledBody(BaseModel):
    enabled: Any = None


@app.post("/api/v2/device/enabled")
def api_v2_device_enabled(body: DeviceEnabledBody, request: Request):
    # 감지 켜기/끄기는 기기에서만 (앱은 상태만 봄, PATCH /api/v2/devices/{id} 의 enabled 는 거절)
    with db.session(DB_PATH) as conn:
        device = devices.authenticate(conn, request.headers.get("authorization"))
        return JSONResponse(devices.set_enabled_by_device(conn, device, body.enabled), headers=NO_STORE)


@app.post("/api/v2/device/unpair")
def api_v2_device_unpair(request: Request):
    # 기기가 자기 기록만 삭제 ('이 휴대폰'으로 감지하던 사람이 그 휴대폰에서 탈퇴). 기기 토큰으로만, 다른 기기는 못 지움
    with db.session(DB_PATH) as conn:
        device = devices.authenticate(conn, request.headers.get("authorization"))
        devices.unpair_by_device(conn, device)
        return JSONResponse({"ok": True}, headers=NO_STORE)


@app.post("/api/v2/device/events")
def api_v2_device_fall(body: DeviceFallBody, request: Request):
    """A fall from a connected device: the home's incident is created directly, with the silhouette photo linked.
    Test falls only record the time (no incident, no alert). With detection turned off in the app, nothing is made."""
    with db.session(DB_PATH) as conn:
        device = devices.authenticate(conn, request.headers.get("authorization"))
        if body.is_test:
            devices.record_test(conn, device)
            return JSONResponse({"ok": True, "test": True}, headers=NO_STORE)
        devices.seen(conn, device)
        if not device["enabled"]:
            return JSONResponse({"ok": True, "ignored": "off"}, headers=NO_STORE)
        incident_id = devices.incident_for_fall(conn, device, body.event_id)
        image_saved = False
        image = _decode_jpeg(body.image_jpeg_base64) if body.image_jpeg_base64 else None
        if image:
            # 사진 저장·연결이 실패해도 사고와 알림은 그대로 (기록만 남김)
            try:
                photo = devices.photo_id(device, body.event_id)
                (IMAGE_DIR / f"{photo}.jpg").write_bytes(image)
                incidents.add_photo(conn, incident_id, photo)
                image_saved = True
            except Exception as e:
                print(f"[device] 사진을 저장·연결하지 못함 (사고·알림은 그대로): {type(e).__name__}: {e}")
        return JSONResponse({"ok": True, "incident_id": incident_id, "image_saved": image_saved}, headers=NO_STORE)


@app.post("/api/v2/notifications/read")
def api_v2_notifications_read(request: Request):
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        alerts.mark_read(conn, user_id, incidents.now_ms())
        return _state_response(conn, user_id)


@app.post("/api/v2/dev/falls")
def api_v2_dev_fall(body: DevFallBody, request: Request):
    """Developer fall for copy servers (FD_DEV_TOOLS=1). Same incident logic as real devices; source 'dev'."""
    if not DEV_TOOLS:
        raise accounts.AccountError(404, "찾을 수 없어요.")
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        me = people_mod._my_group(conn, user_id)
        home = people_mod._group_home(conn, me, body.homeId)
        try:
            ago = int(body.agoSeconds or 0)
        except (TypeError, ValueError):
            ago = -1
        if not 0 <= ago <= 600:
            raise accounts.AccountError(400, "agoSeconds 는 0~600 이에요.", "agoSeconds")
        now = incidents.now_ms()
        incidents.create(conn, home["id"], body.location if body.location is not None else "거실", "dev",
                         source_ref=user_id, now=now, detected_at=now - ago * 1000)
        incidents.tick(conn, now)   # 지난 시각으로 만든 경우 바로 시간 처리
        return _state_response(conn, user_id)


@app.get("/api/v2/address/search")
def api_v2_address_search(request: Request, q: str = ""):
    # 도로명주소 검색: 서버가 대신 호출 (승인키 JUSO_API_KEY 는 브라우저로 보내지 않음). address_search.py
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        results = address_search.search(conn, user_id, q[:200], os.environ.get("JUSO_API_KEY", "").strip(),
                                        os.environ.get("JUSO_API_URL", "").strip() or None)
    return JSONResponse({"results": results}, headers=NO_STORE)


@app.post("/api/v2/me/withdraw")
def api_v2_withdraw(body: PasswordBody, request: Request):
    # 회원 탈퇴: 비밀번호를 다시 확인한 뒤 한 번에 삭제 (accounts.withdraw), 로그인 쿠키도 지움
    _check_origin(request)
    with db.session(DB_PATH) as conn:
        user_id = _require_user(conn, request)
        photos = _group_photo_ids(conn, user_id)
        accounts.withdraw(conn, user_id, body.password, _client_ip(request))
        _remove_unlinked_photos(conn, photos)
    response = JSONResponse({"authenticated": False, "me_id": None, "state": accounts.empty_state()}, headers=NO_STORE)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=_cookie_secure(request))
    return response


# ---- 페이지 ----
# 로그인 뒤 이동할 수 있는 주소 (그 밖의 값은 무시하고 /confirm 으로)
LOGIN_NEXT_PAGES = {"/confirm": "/confirm", "/app": "/app/", "/app/": "/app/"}


@app.get("/login")
def login(request: Request, token: str = "", next: str = "/confirm"):
    if not secrets.compare_digest(token.encode(), ACCESS_TOKEN.encode()):
        return HTMLResponse(UNAUTHORIZED_PAGE, status_code=401)
    response = RedirectResponse(LOGIN_NEXT_PAGES.get(next, "/confirm"), status_code=303)
    # HTTPS 로 접속했으면 쿠키도 HTTPS 에서만 (앱 로그인 쿠키와 같은 규칙). 토큰이 든 이 주소는 저장·전달되지 않게
    response.set_cookie(COOKIE_NAME, ACCESS_TOKEN, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
                        secure=_cookie_secure(request))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ---- 사용자용 앱 (/app, 파일은 server/app/) ----
APP_DIR = (BASE_DIR / "app").resolve()
# 확장자별 파일 형식 (Windows 설정에 따라 .js 를 잘못 알려 주는 경우가 있어 직접 지정)
APP_MEDIA_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                   ".css": "text/css; charset=utf-8", ".webmanifest": "application/manifest+json",
                   ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json"}
APP_LOGIN_PAGE = """
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>로그인이 필요해요</title></head>
<body style="font-family: sans-serif; font-size: 22px; line-height: 1.5; padding: 24px; max-width: 640px">
<h1 style="font-size: 30px">로그인이 필요해요</h1>
<p>서버 창에 표시된 로그인 주소 끝에 <b>&amp;next=/app</b> 을 붙여 한 번 접속해 주세요.</p>
<p style="background:#f2f2f2; padding:12px; word-break: break-all">http://서버주소:8000/login?token=…&amp;next=/app</p>
</body></html>
"""


# 새 웹앱 (젠스파크 화면, /app/next/). 가입·로그인 전에도 화면이 열려야 하므로 파일은 로그인 없이 제공.
# 화면 파일에는 실제 데이터가 없고, 실제 데이터 API(/api/...)는 계속 토큰·로그인으로 보호됨
NEXT_DIR = APP_DIR / "next"


def _app_public(target):
    # 공개 여부는 실제 파일 위치로 판단 (주소에 ../ 를 넣어 로그인이 필요한 파일을 공개 파일처럼 여는 것을 막음)
    rel = target.relative_to(APP_DIR).as_posix()
    # PWA 정보와 아이콘은 데이터가 없고, 브라우저가 쿠키 없이 가져가기도 해서 로그인 없이 허용
    if rel == "manifest.webmanifest" or rel.startswith("icons/"):
        return True
    return NEXT_DIR in target.parents


@app.get("/app")
def app_root():
    # 상대 주소(css/, js/)가 맞게 풀리도록 끝에 / 를 붙임
    return RedirectResponse("/app/", status_code=307)


@app.get("/app/{path:path}")
def app_files(path: str, request: Request):
    path = path or "index.html"
    target = (APP_DIR / path).resolve()
    # server/app 폴더 밖의 파일은 열지 않음
    if APP_DIR not in target.parents:
        raise HTTPException(status_code=404, detail="Not found")
    # 폴더 주소(/app/next/)는 그 안의 index.html. 끝에 / 가 없으면 붙여서 다시 요청 (상대 주소가 맞게 풀리도록)
    if target.is_dir():
        if not path.endswith("/"):
            return RedirectResponse(f"/app/{target.relative_to(APP_DIR).as_posix()}/", status_code=307)
        target = target / "index.html"
    if not target.is_file() or target.suffix not in APP_MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="Not found")
    if not _app_public(target) and not _is_authorized(request):
        return HTMLResponse(APP_LOGIN_PAGE, status_code=401)
    return FileResponse(target, media_type=APP_MEDIA_TYPES[target.suffix], headers={"Cache-Control": "no-cache"})


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


def _guardian_cell(e, people):
    """'보호자·119' cell: escalation state, who fell, resident buttons and the report link."""
    parts = [html.escape(e["escalation_label"])]
    if escalation.enabled(e):
        parts.append(html.escape(escalation.describe_fallen(e)))
        if len(people) >= 2:
            eid = html.escape(e["event_id"])
            buttons = "".join(
                f'<form method="post" action="/events/{eid}/fallen/{html.escape(r["id"])}" style="display:inline">'
                f'<button type="submit">🙋 {html.escape(r["alias"])}</button></form> ' for r in people)
            parts.append(f"<small>누가 쓰러졌나요?</small> {buttons}")
        if e["escalation"].get("report"):
            parts.append(f'<a href="/reports/{html.escape(e["event_id"])}">신고 기록 보기</a>')
    return "<td>" + "<br>".join(parts) + "</td>"


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
    people = _residents()
    rows = "".join(
        f"<tr><td>{e['time']}</td>"
        f"<td>{html.escape(e['device_id'])}</td>"
        f"<td>{html.escape(e['fall_type'])}</td>"
        f"<td>{'테스트' if e['is_test'] else '실제'}</td>"
        f"<td class='st-{e['status']}{' late' if e.get('late_response') else ''}'>{e['status_label']}</td>"
        f"<td>{e['responded_at'] or '-'}</td>"
        f"{_seconds_cell(e)}"
        f"{_guardian_cell(e, people)}"
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
           · 응답 제한 시간 {RESPONSE_TIMEOUT_SECONDS}초
           · 보호자 대기 {ESCALATION.wait_after_timeout:g}초(무응답) / {ESCALATION.wait_after_help:g}초(도움 요청)
           · 119 신고는 <b>시뮬레이션</b>입니다 (실제 신고 안 함) · 거주자 {len(people)}명</p>
        <div class="table-wrap">
        <table border="1" cellpadding="8" style="border-collapse: collapse">
            <tr><th>시간</th><th>기기</th><th>유형</th><th>구분</th><th>상태</th><th>응답 시각</th><th>응답 소요(초)</th><th>보호자·119</th><th>이미지</th></tr>
            {rows}
        </table>
        </div>
    </body>
    </html>
    """


@app.post("/events/{event_id}/fallen/{resident_id}")
def select_fallen_web(event_id: str, resident_id: str, request: Request):
    """Record page: pick who fell (same rule as the Telegram '누가 쓰러졌나요?' buttons)."""
    denied = _page_or_401(request)
    if denied:
        return denied
    with _lock:
        ev = events.get(event_id)
        resident = residents_mod.find(_residents(), resident_id)
        if ev and resident:
            now = time.time()
            if _apply_steps(ev, escalation.select_fallen(ev, resident, {"name": "웹페이지"}, now, how="web"), now):
                _save_events()
    return RedirectResponse("/", status_code=303)


def _report_page_denied(request: Request):
    denied = _page_or_401(request)
    if denied:
        return denied
    host = request.client.host if request.client else ""
    if REPORT_PAGE_LOCAL_ONLY and host not in ("127.0.0.1", "::1", "localhost"):
        return HTMLResponse("<h2>신고 기록 상세는 이 PC에서만 볼 수 있도록 설정되어 있습니다</h2>"
                            "<p>설정: server/.env 의 REPORT_PAGE_ACCESS=local</p>", status_code=403)
    return None


@app.get("/reports/{event_id}", response_class=HTMLResponse)
def report_page(event_id: str, request: Request):
    """119 report (simulation) details. Values are filled in now from residents.json and .env; never stored."""
    denied = _report_page_denied(request)
    if denied:
        return denied
    with _lock:
        ev = events.get(event_id)
        view = _report_view(ev) if ev else None
    if view is None:
        return HTMLResponse("<h2>이 낙상에는 신고(시뮬레이션) 기록이 없습니다</h2><p><a href='/'>기록으로</a></p>",
                            status_code=404, headers={"Cache-Control": "no-store"})
    report, c, d, fallen_now = view
    esc = lambda v: html.escape(str(v))  # noqa: E731
    how = f"보호자 요청 ({report['by']})" if report["by"] else "보호자 무응답으로 자동 신고"
    people_html = ""
    for p in d["people"]:
        if p["missing"]:
            people_html += f"<li>거주자 ID {esc(p['id'])}: 현재 거주자 파일에 없음</li>"
            continue
        notes = []
        if p["stale"]:
            notes.append("⚠️ 정보가 오래됐을 수 있음")
        if p["changed_since_report"]:
            notes.append("ℹ️ 신고 뒤 정보가 수정됨 (아래는 현재 정보)")
        people_html += (f"<li><b>{esc(p['alias'])}</b> {' · '.join(notes)}<br>"
                        f"나이: {esc(p['age'])} · 지병: {esc(p['conditions'])} · 복용약: {esc(p['medications'])}"
                        f" · 정보 갱신일: {esc(p['updated'])}</li>")
    if not people_html:
        people_html = "<li>의료 정보 제외 (낙상자 미확인)</li>"
    after = f"<p>{esc(fallen_now)}</p>" if fallen_now else ""
    # 모의 신고 메시지: 지금 등록된 정보로 화면에서만 만듦 (저장·로그·전송 없음). report_message.py
    message = report_message.build(ev, report, c, d)
    missing = esc(", ".join(message["missing"])) if message["missing"] else "없음"
    message_html = f"""
    <h3>모의 신고 메시지</h3>
    <p style="background:#ffe1e1; padding:8px; border:2px solid #c62828"><b>🚫 실제 119에 전송되지 않았습니다.</b>
       이 문구는 화면에만 표시되며 저장되거나 어디로도 보내지지 않습니다. 실제 신고가 필요하면 직접 119에 전화하세요.</p>
    <textarea id="mock-report" readonly rows="18" style="width:100%; box-sizing:border-box; font-size:14px">{esc(message['text'])}</textarea>
    <p><button type="button" id="copy-mock-report">메시지 복사</button> <span id="copy-result" aria-live="polite"></span></p>
    <p><small>미등록 항목: {missing}</small></p>
    <script>
    // 이 기기의 클립보드에만 복사 (전화·문자·전송 없음)
    document.getElementById("copy-mock-report").addEventListener("click", async function () {{
      var box = document.getElementById("mock-report"), out = document.getElementById("copy-result");
      try {{ await navigator.clipboard.writeText(box.value); out.textContent = "복사했어요"; }}
      catch (e) {{ box.focus(); box.select(); out.textContent = document.execCommand("copy") ? "복사했어요" : "복사하지 못했어요. 직접 선택해 복사하세요"; }}
    }});
    </script>"""
    body = f"""
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex"><title>119 신고(시뮬레이션) 기록</title></head>
    <body style="font-family: sans-serif; padding: 16px; max-width: 720px">
    <p style="background:#fff4cc; padding:8px"><b>⚠️ 시뮬레이션입니다. 실제 119에는 연락하지 않았습니다.</b></p>
    <h2>119 신고(시뮬레이션) 기록</h2>
    <p>낙상 감지: {esc(ev['time'])} · 신고: {esc(report['time'])} · 상태: {esc(escalation.REASON_LABELS.get(report['reason'], report['reason']))}
       · 신고 경위: {esc(how)}</p>
    <p><b>{esc(report119.fallen_line(c))}</b></p>{after}
    <h3>집 정보</h3>
    <ul><li>주소: {esc(d['address'])}</li>
        <li>현관 비번: {esc(d['door_code'])} · 공동현관 비번: {esc(d['building_door_code'])}</li>
        <li>보호자 연락처: {esc(d['contact'])}</li></ul>
    <h3>거주자 정보</h3><ul>{people_html}</ul>
    <p><small>전달 항목: {esc(', '.join(c['items']))}. 이 페이지의 값은 저장된 것이 아니라 현재 등록된 정보로 표시합니다.</small></p>
    {message_html}
    <p><a href="/">기록으로</a></p>
    </body></html>"""
    # 브라우저·중간 서버에 저장되지 않게 함
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})
