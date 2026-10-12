"""Notification rules: decide which alert (if any) a fall event needs right now.

This module only decides *when* and *what* to send. It never sends anything;
delivery is done by notifiers.py.

Decisions are based on the alerts already sent for the event (ev["alerts"],
saved in events.json, so they survive a server restart):
  - no response before the deadline   -> TIMEOUT (once per fall)
  - response "help_needed"            -> HELP every time, numbered (1번째, 2번째, ...),
                                         except within help_cooldown seconds of the previous
                                         HELP alert (double press or retry)
  - response "safe" after any alert   -> SAFE_CORRECTION, unless the last alert sent was
                                         already SAFE_CORRECTION
  - response "safe" before any alert  -> nothing
"""
from datetime import datetime

from notifiers import Notification

TIMEOUT = "timeout"
HELP = "help"
SAFE_CORRECTION = "safe_correction"


def _alert_ts(alert):
    # 이전 버전 기록에는 ts가 없어 초 단위 시각 문자열로 계산
    if alert.get("ts") is not None:
        return alert["ts"]
    return datetime.strptime(alert["time"], "%Y-%m-%d %H:%M:%S").timestamp()


def decide(ev, trigger, timeout_seconds, previous_response=None, help_cooldown=10, now=None, image_path=None):
    """Return the Notification to send for this trigger, or None.

    trigger: "timeout" (deadline passed without a response), "safe" or "help_needed" (button pressed).
    previous_response: the event's response before this button press.
    help_cooldown: HELP requests within this many seconds of the previous HELP alert are not sent again.
    now: current timestamp (time.time()).
    image_path: the fall's privacy-processed photo; attached to TIMEOUT and HELP alerts only.
    """
    # 알림 기능이 생기기 전에 저장된 기록에는 알림을 보내지 않음
    if "last_alert" not in ev:
        return None
    alerts = ev.get("alerts", [])
    help_alerts = [a for a in alerts if a["kind"] == HELP]
    help_number = None

    if trigger == "timeout":
        kind = TIMEOUT if not alerts else None
    elif trigger == "help_needed":
        recent = help_alerts and now is not None and now - _alert_ts(help_alerts[-1]) < help_cooldown
        kind = None if recent else HELP
        help_number = len(help_alerts) + 1
    elif trigger == "safe":
        kind = SAFE_CORRECTION if alerts and alerts[-1]["kind"] != SAFE_CORRECTION else None
    else:
        kind = None
    if kind is None:
        return None
    # 사진은 '응답 없음'과 '도움 요청'에만 붙임 ('정정'에는 붙이지 않음)
    photo = image_path if kind in (TIMEOUT, HELP) else None
    return Notification(kind=kind, event_id=ev["event_id"], is_test=ev.get("is_test", False),
                        text=_message(kind, ev, timeout_seconds, previous_response, help_number),
                        image_path=photo)


def _message(kind, ev, timeout_seconds, previous_response, help_number=None):
    test = "[테스트] " if ev.get("is_test") else ""
    seconds = ev.get("response_seconds")
    after = f" (낙상 감지 후 {seconds:.0f}초)" if seconds is not None else ""

    if kind == TIMEOUT:
        title = "🚨 낙상 알림 - 응답 없음"
        body = f"{timeout_seconds}초 동안 응답이 없었어요. 확인이 필요해요."
    elif kind == HELP:
        title = f"🚨 낙상 알림 - 도움 요청 ({help_number}번째)"
        if previous_response == "safe":
            body = f"응답이 '괜찮아요'에서 '도움이 필요해요'로 바뀌었어요{after}."
        elif help_number > 1:
            body = f"본인이 '도움이 필요해요'를 다시 눌렀어요{after}."
        else:
            body = f"본인이 '도움이 필요해요'라고 응답했어요{after}."
    else:
        title = "✅ 정정 - 괜찮다고 응답함"
        body = f"본인이 괜찮다고 응답했어요{after}."

    return (f"{test}{title}\n"
            f"낙상 감지 시각: {ev['time']}\n"
            f"{body}\n"
            f"기기: {ev['device_id']} / 유형: {ev['fall_type']}")
