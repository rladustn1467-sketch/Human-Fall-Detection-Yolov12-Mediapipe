"""Notification delivery: sends alerts decided by notify_rules.py / escalation.py to external channels.

This module only knows *how* to send (and how to receive guardian button presses).
It never decides *when* to send. To add a channel (web push, app push, ...): subclass
Notifier, implement send() (render notification.buttons in the channel's own way if it
can), and add it in build_notifiers().
"""
import json
import os
import queue
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# 시험 때만 TELEGRAM_API_URL 로 가짜 텔레그램 서버를 가리킴 (운영 .env 에는 넣지 않음, 없으면 실제 주소)
TELEGRAM_API_URL = os.environ.get("TELEGRAM_API_URL") or "https://api.telegram.org/bot{token}/{method}"


@dataclass
class Notification:
    """One alert, independent of the channel that delivers it."""
    kind: str                         # notify_rules.TIMEOUT / HELP / SAFE_CORRECTION, escalation.REPORT, ...
    event_id: str
    text: str
    is_test: bool = False
    image_path: Optional[str] = None  # 사생활 보호 처리된 사진 파일 (없으면 글자만)
    # 받는 사람이 누를 수 있는 버튼 줄 목록 [[(글자, 동작), ...], ...].
    # 눌리면 채널이 (event_id, 동작, 누른 사람)을 서버에 알려 줌
    buttons: list = field(default_factory=list)


@dataclass
class ButtonResult:
    """What a button handler returns: a short notice for the presser and an optional reply
    sent only to the presser's chat (may contain private details: never log or store it)."""
    reply: str = ""
    message: str = ""


class NotifyError(Exception):
    def __init__(self, message, retryable=True, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class Notifier:
    """Base class for a delivery channel. send() raises NotifyError on failure."""
    name = "base"

    def send(self, notification):
        raise NotImplementedError


def _multipart(fields, files):
    """Encode form fields and files ({name: (filename, bytes, content_type)}) as multipart/form-data."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                     + str(value).encode("utf-8") + b"\r\n")
    for name, (filename, content, content_type) in files.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                     f"Content-Type: {content_type}\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _telegram_call(token, method, params, files=None, timeout=10):
    """Call a Telegram Bot API method and return its result. Raises NotifyError."""
    url = TELEGRAM_API_URL.format(token=token, method=method)
    if files:
        data, content_type = _multipart(params, files)
    else:
        data, content_type = urllib.parse.urlencode(params).encode("utf-8"), "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": content_type})
    # 오류 메시지에는 URL(토큰 포함)을 절대 넣지 않음
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except ValueError:
            body = {}
        description = body.get("description", "")
        retry_after = (body.get("parameters") or {}).get("retry_after")
        hint = {401: " (봇 토큰 확인)", 403: " (봇이 차단되었거나 채팅방에 없음)", 404: " (봇 토큰 확인)",
                409: " (같은 봇 토큰으로 서버가 두 개 실행 중인지 확인)"}.get(e.code, "")
        if e.code == 400 and "chat not found" in description:
            hint = " (채팅 ID 확인, 봇에게 먼저 메시지를 보냈는지 확인)"
        raise NotifyError(f"HTTP {e.code} {description}{hint}",
                          retryable=e.code == 429 or e.code >= 500, retry_after=retry_after)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise NotifyError(f"연결 실패: {getattr(e, 'reason', e)}")
    if not body.get("ok"):
        raise NotifyError(f"텔레그램 오류: {body.get('description', body)}", retryable=False)
    return body.get("result")


class TelegramNotifier(Notifier):
    """Sends to one Telegram chat (one notifier per guardian, so a failure for one never re-sends to others)."""
    CAPTION_LIMIT = 1024  # 텔레그램 사진 설명 최대 글자 수

    def __init__(self, bot_token, chat_id, timeout=10, photo_timeout=30):
        self._token = bot_token
        self.chat_id = chat_id
        self.name = f"telegram:{chat_id}"
        self.timeout = timeout
        self.photo_timeout = photo_timeout

    def _markup(self, notification):
        # 버튼 데이터: "동작:낙상ID" (텔레그램 제한 64바이트 이내)
        return json.dumps({"inline_keyboard": [[
            {"text": label, "callback_data": f"{action}:{notification.event_id}"}
            for label, action in row] for row in notification.buttons]}, ensure_ascii=False)

    def send(self, notification):
        # 사진이 있으면 사진+글자를 한 메시지로, 사진 전송이 실패하면 글자만 보냄
        if notification.image_path:
            try:
                self._send_photo(notification)
                return
            except NotifyError as e:
                print(f"[notify:telegram] 사진 전송 실패 - 글자만 보냅니다 (event {notification.event_id[:8]}): {e}")
        params = {"chat_id": self.chat_id, "text": notification.text, "disable_web_page_preview": "true"}
        if notification.buttons:
            params["reply_markup"] = self._markup(notification)
        self._call("sendMessage", params)

    def _send_photo(self, notification):
        try:
            with open(notification.image_path, "rb") as f:
                photo = f.read()
        except OSError as e:
            raise NotifyError(f"사진 파일을 읽을 수 없음: {e}", retryable=False)
        caption = notification.text
        if len(caption) > self.CAPTION_LIMIT:
            caption = caption[:self.CAPTION_LIMIT - 1] + "…"
        params = {"chat_id": self.chat_id, "caption": caption}
        if notification.buttons:
            params["reply_markup"] = self._markup(notification)
        self._call("sendPhoto", params,
                   files={"photo": (os.path.basename(notification.image_path), photo, "image/jpeg")},
                   timeout=self.photo_timeout)

    def _call(self, method, params, files=None, timeout=None):
        return _telegram_call(self._token, method, params, files, timeout or self.timeout)


class TelegramPoller:
    """Receives guardian button presses with getUpdates long polling (no public server address needed).

    Only presses from registered guardian chat IDs are passed to handler(event_id, action, actor),
    which returns a short reply shown to the presser (str) or a ButtonResult whose message is sent
    to the presser's chat only. The last processed update number is saved, so a restart never
    processes the same press twice.
    """

    def __init__(self, bot_token, allowed_chat_ids, state_file, handler, poll_timeout=25):
        self._token = bot_token
        self.allowed = {str(c) for c in allowed_chat_ids}
        self.state_file = state_file
        self.handler = handler
        self.poll_timeout = poll_timeout
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="telegram-poller", daemon=True)
            self._thread.start()

    def _load_offset(self):
        try:
            with open(self.state_file, encoding="utf-8") as f:
                return json.load(f).get("offset")
        except (OSError, ValueError):
            return None

    def _save_offset(self, offset):
        tmp = f"{self.state_file}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"offset": offset}, f)
        os.replace(tmp, self.state_file)

    def _loop(self):
        offset = self._load_offset()
        last_error = None
        while True:
            params = {"timeout": self.poll_timeout, "allowed_updates": json.dumps(["callback_query"])}
            if offset is not None:
                params["offset"] = offset
            try:
                updates = _telegram_call(self._token, "getUpdates", params, timeout=self.poll_timeout + 10)
                last_error = None
            except NotifyError as e:
                if str(e) != last_error:  # 같은 오류는 한 번만 기록
                    print(f"[telegram] 버튼 수신 오류, 잠시 후 재시도: {e}")
                    last_error = str(e)
                time.sleep(5)
                continue
            for update in updates or []:
                offset = update["update_id"] + 1
                self._save_offset(offset)  # 처리 전에 저장: 재시작해도 같은 누름을 다시 처리하지 않음
                try:
                    self._handle(update.get("callback_query"))
                except Exception as e:  # 버튼 하나의 오류가 수신 작업을 멈추지 않게 함
                    print(f"[telegram] 버튼 처리 오류: {type(e).__name__}: {e}")

    def _handle(self, query):
        if not query:
            return
        presser = query.get("from") or {}
        chat = (query.get("message") or {}).get("chat") or {}
        presser_id, chat_id = str(presser.get("id")), str(chat.get("id"))
        result = ButtonResult()
        if presser_id not in self.allowed and chat_id not in self.allowed:
            print(f"[telegram] 등록되지 않은 사용자의 버튼 무시 (사용자 {presser_id}, 채팅 {chat_id})")
        else:
            action, _, event_id = (query.get("data") or "").partition(":")
            name = " ".join(filter(None, [presser.get("first_name"), presser.get("last_name")])) \
                or presser.get("username") or presser_id
            actor = {"channel": "telegram", "id": presser_id, "name": name}
            print(f"[telegram] 버튼 '{action}' - {name} ({presser_id}), event {event_id[:8]}")
            handled = self.handler(event_id, action, actor)
            result = handled if isinstance(handled, ButtonResult) else ButtonResult(reply=handled or "")
        if result.message:
            # 누른 사람의 대화창에만 답장 (내용은 로그에 남기지 않음)
            target = chat_id if chat_id != "None" else presser_id
            try:
                _telegram_call(self._token, "sendMessage",
                               {"chat_id": target, "text": result.message, "disable_web_page_preview": "true"})
                print(f"[telegram] 답장 전송 (채팅 {target})")
            except NotifyError as e:
                print(f"[telegram] 답장 전송 실패 (채팅 {target}): {e}")
                result.reply = "보내지 못했어요. 잠시 후 다시 눌러 주세요."
        reply = result.reply
        try:
            # 버튼의 로딩 표시를 끝내고 짧은 안내를 보여 줌
            _telegram_call(self._token, "answerCallbackQuery", {"callback_query_id": query["id"], "text": reply[:200]})
        except NotifyError as e:
            print(f"[telegram] 버튼 응답 실패: {e}")


class NotificationDispatcher:
    """Delivers notifications to every channel on a background thread, in order, with retries."""

    def __init__(self, notifiers, retry_delays=(2, 5, 15)):
        self.notifiers = list(notifiers)
        self.retry_delays = retry_delays
        self._queue = queue.Queue()
        self._thread = None

    @property
    def channel_names(self):
        return [n.name for n in self.notifiers]

    def start(self):
        if self.notifiers and self._thread is None:
            self._thread = threading.Thread(target=self._worker, name="notify-dispatcher", daemon=True)
            self._thread.start()

    def notify(self, notification):
        """Queue a notification; returns immediately (never blocks the caller on the network)."""
        if self.notifiers:
            self._queue.put(notification)

    def _worker(self):
        while True:
            notification = self._queue.get()
            for notifier in self.notifiers:
                self._deliver(notifier, notification)

    def _deliver(self, notifier, notification):
        tag = f"[notify:{notifier.name}] {notification.kind} (event {notification.event_id[:8]})"
        for attempt in range(len(self.retry_delays) + 1):
            try:
                notifier.send(notification)
                print(f"{tag} 전송 완료")
                return
            except NotifyError as e:
                if not e.retryable or attempt == len(self.retry_delays):
                    print(f"{tag} 전송 실패: {e}")
                    return
                delay = e.retry_after or self.retry_delays[attempt]
                print(f"{tag} 전송 실패, {delay}초 후 재시도: {e}")
                time.sleep(delay)
            except Exception as e:  # 채널 코드의 예기치 못한 오류도 서버를 멈추지 않게 함
                print(f"{tag} 전송 오류: {type(e).__name__}: {e}")
                return


def _telegram_settings(env):
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    # 보호자 여러 명: 쉼표로 구분 (예: 111,222)
    chat_ids = [c.strip() for c in env.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    return token, chat_ids


def build_notifiers(env):
    """Create the channels configured in env (os.environ). Missing settings only log a message."""
    notifiers = []
    token, chat_ids = _telegram_settings(env)
    if token and chat_ids:
        notifiers.extend(TelegramNotifier(token, chat_id) for chat_id in chat_ids)
        print(f"[notify] 텔레그램 알림 사용 (보호자 {len(chat_ids)}명: {', '.join(chat_ids)})")
    else:
        print("[notify] 텔레그램 설정 없음 - server/.env 의 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 채우면 알림을 보냅니다")
    return notifiers


def build_receivers(env, state_file, handler):
    """Create the channels that receive guardian button presses (currently Telegram only)."""
    token, chat_ids = _telegram_settings(env)
    if token and chat_ids:
        return [TelegramPoller(token, chat_ids, state_file, handler)]
    return []
