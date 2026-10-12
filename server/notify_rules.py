"""Notification rules: decide which alert (if any) a fall event needs right now.

This module only decides *when* and *what* to send. It never sends anything;
delivery is done by notifiers.py.

Each event remembers the kind of the last alert sent (ev["last_alert"]), so the
same alert is never sent twice for one fall:
  - no response before the deadline   -> TIMEOUT (once per fall)
  - response "help_needed"            -> HELP, unless the last alert was already HELP
  - response "safe" after any alert   -> SAFE_CORRECTION, unless already sent last
  - response "safe" before any alert  -> nothing
"""
from notifiers import Notification

TIMEOUT = "timeout"
HELP = "help"
SAFE_CORRECTION = "safe_correction"


def decide(ev, trigger, timeout_seconds, previous_response=None):
    """Return the Notification to send for this trigger, or None.

    trigger: "timeout" (deadline passed without a response), "safe" or "help_needed" (button pressed).
    previous_response: the event's response before this button press.
    """
    # 알림 기능이 생기기 전에 저장된 기록에는 알림을 보내지 않음
    if "last_alert" not in ev:
        return None
    last = ev["last_alert"]

    if trigger == "timeout":
        kind = TIMEOUT if last is None else None
    elif trigger == "help_needed":
        kind = HELP if last != HELP else None
    elif trigger == "safe":
        kind = SAFE_CORRECTION if last in (TIMEOUT, HELP) else None
    else:
        kind = None
    if kind is None:
        return None
    return Notification(kind=kind, event_id=ev["event_id"], is_test=ev.get("is_test", False),
                        text=_message(kind, ev, timeout_seconds, previous_response))


def _message(kind, ev, timeout_seconds, previous_response):
    test = "[테스트] " if ev.get("is_test") else ""
    seconds = ev.get("response_seconds")
    after = f" (낙상 감지 후 {seconds:.0f}초)" if seconds is not None else ""

    if kind == TIMEOUT:
        title = "🚨 낙상 알림 - 응답 없음"
        body = f"{timeout_seconds}초 동안 응답이 없었어요. 확인이 필요해요."
    elif kind == HELP:
        title = "🚨 낙상 알림 - 도움 요청"
        if previous_response == "safe":
            body = f"응답이 '괜찮아요'에서 '도움이 필요해요'로 바뀌었어요{after}."
        else:
            body = f"본인이 '도움이 필요해요'라고 응답했어요{after}."
    else:
        title = "✅ 정정 - 괜찮다고 응답함"
        body = f"본인이 괜찮다고 응답했어요{after}."

    return (f"{test}{title}\n"
            f"낙상 감지 시각: {ev['time']}\n"
            f"{body}\n"
            f"기기: {ev['device_id']} / 유형: {ev['fall_type']}")
