"""Guardian escalation rules: guardian wait -> 119 report (SIMULATION ONLY).

This module only decides state changes and which alerts to send. It never sends
anything (delivery: notifiers.py) and never contacts 119 or any real service.

State is kept in ev["escalation"] (saved in events.json, so it survives a restart):
  idle               nothing started (the person has not timed out or asked for help)
  waiting            guardians were alerted; auto report at report_at unless someone acts
  guardian_confirmed a guardian pressed '확인했어요' -> auto report stopped
  reported           119 report (simulation) done (at most once per fall)
  closed_by_self     the person pressed '괜찮아요' -> flow ended, guardian buttons ignored

Transitions:
  person timeout / help_needed      -> waiting (help uses the shorter wait; never extends a wait;
                                       help restarts the wait after guardian_confirmed or closed_by_self)
  person safe (not reported)        -> closed_by_self (scheduled report cancelled)
  person safe (reported)            -> '신고 취소 요청' alert once, '신고 후 취소' recorded
  guardian ack (waiting)            -> guardian_confirmed, other guardians told
  guardian call (waiting/confirmed) -> reported now
  report_at passed (waiting)        -> reported automatically
Every other combination (double press, late press) changes nothing and only returns a reply.

Who fell (ev["escalation"]["fallen"], resident id/alias only - never medical info):
  one resident                      -> confirmed automatically
  guardian picks a resident         -> confirmed (can be changed until the report; does not stop the wait)
  picked after the report           -> recorded as '신고 후 확정(참고용)'; the report itself is not changed
The report contents are decided by report119.py; only item names are stored and sent.
"""
from dataclasses import dataclass, field
from datetime import datetime

import report119
import residents as residents_mod
from notifiers import Notification

GUARDIAN_ACK = "guardian_ack"
FALLEN_SELECTED = "fallen_selected"
REPORT = "report_119"
REPORT_CANCEL = "report_cancel_request"

ACK, CALL, WHO, DETAIL = "ack", "call", "who", "detail"
# 보호자 알림에 붙이는 버튼 (글자, 동작)
GUARDIAN_BUTTONS = (("확인했어요", ACK), ("119 신고해주세요", CALL))
# 신고 완료 알림의 버튼: 누른 보호자의 대화창에 신고 상세를 답장 (main.py에서 처리)
DETAIL_BUTTON = ("📄 상세 보기", DETAIL)
WHO_BUTTONS_PER_ROW = 3

REASON_LABELS = {"timeout": "무응답", "help_needed": "도움 요청"}
LATE_NOTE_SECONDS = 5  # 예정 시각보다 이만큼 넘게 늦으면 (서버 재시작 등) 늦게 처리됐다고 표시


@dataclass
class Settings:
    wait_after_timeout: float = 180
    wait_after_help: float = 90
    unconfirmed_policy: str = "exclude"  # 낙상자 미확인 시 의료 정보: exclude(제외) / all(거주자 전원 포함)
    stale_days: int = 180                # 정보 갱신일이 이보다 오래되면 '정보가 오래됐을 수 있음'
    public_base_url: str = ""            # 휴대폰에서 열리는 서버 주소 (있을 때만 신고 기록 링크를 붙임)
    show_detail: bool = True             # 신고 완료 알림에 '상세 보기' 버튼 (텔레그램으로 상세 답장)


@dataclass
class Steps:
    """Result of a rule: history entries to add, alerts to send, and a reply for the button presser."""
    history: list = field(default_factory=list)        # (status, note)
    notifications: list = field(default_factory=list)  # Notification
    reply: str = ""


def new_state():
    return {"state": "idle", "reason": None, "report_at": None, "acks": [],
            "report": None, "cancel_requested": None, "cancelled_wait": False, "fallen": None}


def enabled(ev):
    # 이 기능이 생기기 전에 저장된 기록은 대상이 아님
    return "escalation" in ev


def _time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _actor_name(actor):
    return actor.get("name") or str(actor.get("id"))


def guardian_buttons(residents):
    """Button rows for guardian alerts: ack/119, plus '누가 쓰러졌나요?' when there are 2+ residents."""
    rows = [list(GUARDIAN_BUTTONS)]
    if len(residents) >= 2:
        names = [(f"🙋 {r['alias']}", f"{WHO}={r['id']}") for r in residents]
        rows += [names[i:i + WHO_BUTTONS_PER_ROW] for i in range(0, len(names), WHO_BUTTONS_PER_ROW)]
    return rows


def start_wait(ev, reason, now, settings):
    """The person timed out or asked for help: alert guardians and schedule an auto report."""
    steps = Steps()
    if not enabled(ev):
        return steps
    esc = ev["escalation"]
    wait = settings.wait_after_help if reason == "help_needed" else settings.wait_after_timeout
    if esc["state"] == "reported":
        return steps
    if esc["state"] == "waiting":
        # 도움 요청은 대기를 줄이기만 하고 늘리지 않음
        if now + wait < esc["report_at"]:
            esc["report_at"] = now + wait
            esc["reason"] = reason
            steps.history.append(("guardian_wait", f"도움 요청으로 대기 단축 - {wait:g}초 뒤 자동 신고"))
        return steps
    if esc["state"] == "guardian_confirmed" and reason != "help_needed":
        return steps
    esc.update(state="waiting", reason=reason, report_at=now + wait)
    steps.history.append(("guardian_wait", f"보호자 응답 대기 - {wait:g}초 뒤 자동 119 신고(시뮬레이션)"))
    return steps


def remaining(ev, now):
    """Seconds until the auto report, or None when no report is scheduled."""
    if not enabled(ev) or ev["escalation"]["state"] != "waiting":
        return None
    return max(0.0, ev["escalation"]["report_at"] - now)


def report_due(ev, now):
    return enabled(ev) and ev["escalation"]["state"] == "waiting" and now >= ev["escalation"]["report_at"]


def on_person_safe(ev, now, settings):
    steps = Steps()
    if not enabled(ev):
        return steps
    esc = ev["escalation"]
    if esc["state"] == "reported":
        if not esc["cancel_requested"]:
            esc["cancel_requested"] = {"time": _time(now), "ts": now}
            steps.history.append(("report_cancel_requested", "신고 후 본인 '괜찮아요' - 보호자에게 신고 취소 요청"))
            steps.notifications.append(_notification(REPORT_CANCEL, ev))
        return steps
    if esc["state"] == "waiting":
        esc["cancelled_wait"] = True
        steps.history.append(("escalation_cancelled", "본인 '괜찮아요' - 예약된 119 신고(시뮬레이션) 취소"))
    esc.update(state="closed_by_self", report_at=None)
    return steps


def select_fallen(ev, resident, actor, now, how="guardian"):
    """Confirm who fell. how: auto (one resident) / guardian (Telegram) / web (record page). Never stops the wait."""
    steps = Steps()
    if not enabled(ev):
        steps.reply = "처리할 수 없는 낙상 기록이에요."
        return steps
    esc = ev["escalation"]
    current = esc.get("fallen")
    after_report = esc["state"] == "reported"
    if current and current["resident_id"] == resident["id"]:
        steps.reply = f"이미 {resident['alias']}(으)로 확정된 낙상이에요."
        return steps
    by = _actor_name(actor) if actor else None
    esc["fallen"] = {"resident_id": resident["id"], "alias": resident["alias"], "how": how, "by": by,
                     "time": _time(now), "ts": now, "after_report": after_report}
    who = f"{by} 선택" if by else "거주자 1명 자동 확정"
    if after_report:
        steps.history.append(("fallen_confirmed_after_report", f"{resident['alias']} ({who}) - 참고용, 신고 내용은 바뀌지 않음"))
        steps.reply = f"{resident['alias']}(으)로 기록했어요. 이미 신고(시뮬레이션)된 뒤라 참고용이에요."
    else:
        changed = f", 이전: {current['alias']}" if current and not current["after_report"] else ""
        steps.history.append(("fallen_confirmed", f"{resident['alias']} ({who}{changed})"))
        steps.reply = f"낙상자를 {resident['alias']}(으)로 확정했어요. 자동 신고 대기는 계속돼요."
    if how != "auto":
        steps.notifications.append(_notification(FALLEN_SELECTED, ev))
    return steps


def on_guardian(ev, action, actor, now, settings, residents, image_path=None):
    """A guardian pressed a button. Safe to call any number of times."""
    steps = Steps()
    if not enabled(ev):
        steps.reply = "처리할 수 없는 낙상 기록이에요."
        return steps
    if action.startswith(WHO + "="):
        resident = residents_mod.find(residents, action.split("=", 1)[1])
        if resident is None:
            steps.reply = "거주자 목록에 없는 사람이에요."
            return steps
        return select_fallen(ev, resident, actor, now)

    esc = ev["escalation"]
    state = esc["state"]
    if state == "reported":
        steps.reply = "이미 119 신고(시뮬레이션)가 끝난 낙상이에요."
    elif state == "closed_by_self":
        steps.reply = "본인이 괜찮다고 응답해 종료된 낙상이에요. 실제 응급이면 직접 119에 전화하세요."
    elif action == ACK:
        if state == "waiting":
            ack = {"by": _actor_name(actor), "id": actor.get("id"), "time": _time(now), "ts": now}
            esc["acks"].append(ack)
            esc.update(state="guardian_confirmed", report_at=None)
            steps.history.append(("guardian_confirmed", f"{ack['by']} - 자동 119 신고 중지"))
            steps.notifications.append(_notification(GUARDIAN_ACK, ev))
            steps.reply = "확인했어요. 자동 119 신고(시뮬레이션)를 멈췄어요."
        elif state == "guardian_confirmed":
            steps.reply = f"이미 {esc['acks'][-1]['by']}님이 확인한 낙상이에요."
        else:
            steps.reply = "보호자 응답을 기다리는 낙상이 아니에요."
    elif action == CALL:
        if state in ("waiting", "guardian_confirmed"):
            steps = _report(ev, now, settings, residents, image_path, by=actor)
            steps.reply = "119 신고(시뮬레이션)를 했어요. 실제 119에는 연락하지 않았어요."
        else:
            steps.reply = "보호자 응답을 기다리는 낙상이 아니에요."
    else:
        steps.reply = "알 수 없는 버튼이에요."
    return steps


def on_tick(ev, now, settings, residents, image_path=None):
    """Auto report once the guardian wait has run out (call when report_due() is True)."""
    if report_due(ev, now):
        return _report(ev, now, settings, residents, image_path, by=None)
    return Steps()


def _report(ev, now, settings, residents, image_path, by):
    esc = ev["escalation"]
    late = None
    if by is None and esc["report_at"] is not None and now - esc["report_at"] > LATE_NOTE_SECONDS:
        late = round(now - esc["report_at"])
    # 신고 내용은 항목 이름·거주자 ID·별칭만 저장 (주소·비번·의료 정보 값은 저장하지 않음)
    contents = report119.summarize(esc.get("fallen"), residents, settings.unconfirmed_policy, settings.stale_days)
    report = {
        "time": _time(now), "ts": now,
        "reason": esc["reason"],
        "trigger": "guardian_request" if by else "auto",
        "by": _actor_name(by) if by else None,
        "contents": contents,
        "late_seconds": late,
    }
    esc.update(state="reported", report=report, report_at=None)
    how = f"보호자 요청 ({report['by']})" if by else "보호자 무응답으로 자동 신고"
    if late:
        how += f", 서버 재시작 등으로 {late}초 늦게 처리됨"
    steps = Steps()
    steps.history.append(("reported_119", f"{how} - {report119.fallen_line(contents)}"))
    steps.notifications.append(_notification(REPORT, ev, image_path, settings,
                                              buttons=[[DETAIL_BUTTON]] if settings.show_detail else []))
    return steps


def describe(ev, now):
    """Short text for the '보호자·119' column of the record page."""
    if not enabled(ev):
        return "-"
    esc = ev["escalation"]
    state = esc["state"]
    if state == "waiting":
        return f"보호자 대기 중 ({remaining(ev, now):.0f}초 뒤 자동 신고)"
    if state == "guardian_confirmed":
        ack = esc["acks"][-1]
        return f"보호자 확인 ({ack['by']}, {ack['time'][11:]})"
    if state == "reported":
        r = esc["report"]
        how = f"보호자 요청: {r['by']}" if r["by"] else "자동"
        text = f"119 신고(시뮬레이션) {r['time'][11:]} ({how})"
        if esc["cancel_requested"]:
            text += f" → 신고 후 취소 ({esc['cancel_requested']['time'][11:]})"
        return text
    if state == "closed_by_self" and esc["cancelled_wait"]:
        return "예약 신고 취소 (본인 괜찮아요)"
    return "-"


def describe_fallen(ev):
    """Who fell, for the record page (alias only)."""
    fallen = ev["escalation"].get("fallen") if enabled(ev) else None
    if not fallen:
        return "낙상자 미확인"
    if fallen["after_report"]:
        return f"신고 후 확정(참고용): {fallen['alias']} ({fallen['by']}, {fallen['time'][11:]})"
    if fallen["how"] == "auto":
        return f"낙상자: {fallen['alias']} (거주자 1명 자동 확정)"
    return f"낙상자: {fallen['alias']} ({fallen['by']}, {fallen['time'][11:]})"


def _notification(kind, ev, image_path=None, settings=None, buttons=None):
    return Notification(kind=kind, event_id=ev["event_id"], is_test=ev.get("is_test", False),
                        text=_message(kind, ev, settings), image_path=image_path, buttons=buttons or [])


def _message(kind, ev, settings=None):
    test = "[테스트] " if ev.get("is_test") else ""
    esc = ev["escalation"]
    head = f"낙상 감지 시각: {ev['time']}"
    if kind == GUARDIAN_ACK:
        ack = esc["acks"][-1]
        return (f"{test}✅ 보호자 확인 - {ack['by']}님이 확인했어요\n{head}\n"
                f"자동 119 신고(시뮬레이션)를 멈췄어요.")
    if kind == FALLEN_SELECTED:
        fallen = esc["fallen"]
        tail = ("이미 신고(시뮬레이션)된 뒤라 참고용으로만 기록했어요." if fallen["after_report"]
                else "자동 신고 대기는 계속돼요.")
        return f"{test}🙋 낙상자 선택 - {fallen['by']}님이 {fallen['alias']}(으)로 선택했어요\n{head}\n{tail}"
    if kind == REPORT:
        # 내용 대신 전달 항목 이름만 (주소·비번·의료 정보 값은 넣지 않음)
        r = esc["report"]
        c = r["contents"]
        how = f"보호자 요청 ({r['by']})" if r["by"] else "보호자 무응답으로 자동 신고"
        lines = [f"{test}🚑 119 신고(시뮬레이션) 완료",
                 "⚠️ 시뮬레이션입니다. 실제 119에는 연락하지 않았습니다. 실제 응급 상황이면 직접 119에 전화하세요.",
                 head,
                 f"상태: {REASON_LABELS.get(r['reason'], r['reason'])}",
                 f"신고 경위: {how}",
                 report119.fallen_line(c),
                 f"전달 항목: {', '.join(c['items'])}"]
        if c["stale_aliases"]:
            lines.append(f"⚠️ 정보가 오래됐을 수 있음: {', '.join(c['stale_aliases'])}")
        if settings and settings.public_base_url:
            lines.append(f"자세한 신고 내용: 서버 웹페이지 신고 기록 ({settings.public_base_url}/reports/{ev['event_id']})")
        elif settings and settings.show_detail:
            lines.append("자세한 내용: 아래 '상세 보기' 버튼")
        else:
            lines.append("자세한 내용: 서버 PC의 기록 페이지 → 신고 기록 보기")
        return "\n".join(lines)
    return (f"{test}↩️ 신고 취소 요청 - 본인이 괜찮다고 응답했어요\n{head}\n"
            f"119 신고(시뮬레이션) 뒤에 본인이 '괜찮아요'를 눌렀어요. "
            f"이미 한 신고는 되돌릴 수 없으니, 실제 신고였다면 119에 취소를 요청해 주세요.")
