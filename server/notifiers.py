"""Notification delivery: sends alerts decided by notify_rules.py to external channels.

This module only knows *how* to send. It never decides *when* to send.
To add a channel (web push, app push, ...): subclass Notifier, implement send(),
and add it in build_notifiers().
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
from dataclasses import dataclass
from typing import Optional


@dataclass
class Notification:
    """One alert, independent of the channel that delivers it."""
    kind: str                         # notify_rules.TIMEOUT / HELP / SAFE_CORRECTION
    event_id: str
    text: str
    is_test: bool = False
    image_path: Optional[str] = None  # 사생활 보호 처리된 사진 파일 (없으면 글자만)


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


class TelegramNotifier(Notifier):
    name = "telegram"
    API_URL = "https://api.telegram.org/bot{token}/{method}"
    CAPTION_LIMIT = 1024  # 텔레그램 사진 설명 최대 글자 수

    def __init__(self, bot_token, chat_id, timeout=10, photo_timeout=30):
        self._token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.photo_timeout = photo_timeout

    def send(self, notification):
        # 사진이 있으면 사진+글자를 한 메시지로, 사진 전송이 실패하면 글자만 보냄
        if notification.image_path:
            try:
                self._send_photo(notification)
                return
            except NotifyError as e:
                print(f"[notify:telegram] 사진 전송 실패 - 글자만 보냅니다 (event {notification.event_id[:8]}): {e}")
        self._call("sendMessage", {
            "chat_id": self.chat_id,
            "text": notification.text,
            "disable_web_page_preview": "true",
        })

    def _send_photo(self, notification):
        try:
            with open(notification.image_path, "rb") as f:
                photo = f.read()
        except OSError as e:
            raise NotifyError(f"사진 파일을 읽을 수 없음: {e}", retryable=False)
        caption = notification.text
        if len(caption) > self.CAPTION_LIMIT:
            caption = caption[:self.CAPTION_LIMIT - 1] + "…"
        self._call("sendPhoto", {"chat_id": self.chat_id, "caption": caption},
                   files={"photo": (os.path.basename(notification.image_path), photo, "image/jpeg")},
                   timeout=self.photo_timeout)

    def _call(self, method, params, files=None, timeout=None):
        url = self.API_URL.format(token=self._token, method=method)
        if files:
            data, content_type = _multipart(params, files)
        else:
            data, content_type = urllib.parse.urlencode(params).encode("utf-8"), "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": content_type})
        # 오류 메시지에는 URL(토큰 포함)을 절대 넣지 않음
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read())
            except ValueError:
                body = {}
            description = body.get("description", "")
            retry_after = (body.get("parameters") or {}).get("retry_after")
            hint = {401: " (봇 토큰 확인)", 403: " (봇이 차단되었거나 채팅방에 없음)", 404: " (봇 토큰 확인)"}.get(e.code, "")
            if e.code == 400 and "chat not found" in description:
                hint = " (채팅 ID 확인, 봇에게 먼저 메시지를 보냈는지 확인)"
            raise NotifyError(f"HTTP {e.code} {description}{hint}",
                              retryable=e.code == 429 or e.code >= 500, retry_after=retry_after)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise NotifyError(f"연결 실패: {getattr(e, 'reason', e)}")
        if not body.get("ok"):
            raise NotifyError(f"텔레그램 오류: {body.get('description', body)}", retryable=False)


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


def build_notifiers(env):
    """Create the channels configured in env (os.environ). Missing settings only log a message."""
    notifiers = []
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        notifiers.append(TelegramNotifier(token, chat_id))
        print(f"[notify] 텔레그램 알림 사용 (채팅 ID {chat_id})")
    else:
        print("[notify] 텔레그램 설정 없음 - server/.env 의 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 채우면 알림을 보냅니다")
    return notifiers
