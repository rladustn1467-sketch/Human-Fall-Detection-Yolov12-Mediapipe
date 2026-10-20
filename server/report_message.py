"""Mock 119 report message (SIMULATION ONLY): the text a person could read to 119, built from registered data.

build() is a pure function. It takes values that were already looked up (report119.details() and the fall
record) and returns text. It does not open files, write logs, touch the database or use the network, and it
never sends anything: there is no phone, SMS, Telegram or 119 connection here. The caller shows the text on a
page and must not store or log it (it contains the address, door codes and health information).

Only registered data is used. A missing value is written as report119.UNREGISTERED ('미등록') and listed in
`missing`; nothing is guessed or made up. Left out on purpose: the fall type (the detector does not really
classify it) and resident aliases (not real names). Health information is used only for a confirmed fallen
resident; otherwise the message says the person could not be identified.
"""
from report119 import UNREGISTERED

NOT_SENT_NOTICE = "※ 모의 신고 메시지입니다. 실제 119에는 전송되지 않았습니다."
REASON_TEXT = {"timeout": "본인 무응답 (응답 시간 초과)", "help_needed": "본인이 도움을 요청함"}
TRIGGER_TEXT = {"auto": "보호자 무응답으로 자동 신고", "guardian_request": "보호자 요청"}
# 낙상자를 정한 방법 (escalation.select_fallen 의 how)
CONFIRM_TEXT = {"auto": "등록된 거주자가 1명이라 자동으로 지정", "guardian": "보호자가 텔레그램에서 선택",
                "web": "기록 페이지에서 선택"}


def _value(v):
    text = str(v).strip() if v is not None else ""
    return text or UNREGISTERED


def build(event, report, summary, detail):
    """Return {"text": str, "missing": [item names]}.

    event:   the fall record (uses time and is_test only; the fall type is left out on purpose)
    report:  ev["escalation"]["report"] (uses time, reason, trigger)
    summary: report["contents"] from report119.summarize() (who fell, how many residents)
    detail:  report119.details() result (address, door codes, contact, people) - values looked up just now
    """
    missing = []

    def field(name, value):
        text = _value(value)
        if text == UNREGISTERED:
            missing.append(name)
        return text

    def label(table, key, name):
        return table[key] if key in table else field(name, None)   # 모르는 값은 지어내지 않고 '미등록'

    lines = [NOT_SENT_NOTICE]
    if event.get("is_test"):
        lines.append("[테스트 낙상 기록]")
    lines += [
        "",
        "낙상 사고 신고입니다. 구급 출동을 요청합니다.",
        "",
        "[사고]",
        f"- 발생 시각: {field('발생 시각', event.get('time'))} (낙상 자동 감지)",
        f"- 신고 시각: {field('신고 시각', report.get('time'))}",
        f"- 신고 사유: {label(REASON_TEXT, report.get('reason'), '신고 사유')}",
        f"- 신고 경위: {label(TRIGGER_TEXT, report.get('trigger'), '신고 경위')}",
        # 낙상 유형은 넣지 않음: 감지기가 유형을 실제로 구분하지 않아 기본값(slip_and_fall)만 오기 때문
        "",
        "[위치]",
        f"- 주소: {field('주소', detail.get('address'))}",
        f"- 현관 비밀번호: {field('현관 비밀번호', detail.get('door_code'))}",
        f"- 공동현관 비밀번호: {field('공동현관 비밀번호', detail.get('building_door_code'))}",
        "",
        "[환자]",
    ]
    # 낙상자가 확인된 경우에만 그 한 사람의 건강 정보를 씀. 별칭은 실제 이름이 아니므로 넣지 않음.
    # 확인되지 않았으면 (설정 REPORT_UNCONFIRMED_MEDICAL=all 이어도) 누구의 건강 정보도 넣지 않음
    if summary.get("confirmed"):
        how = CONFIRM_TEXT.get(summary.get("confirm_how"), "확인됨")
        lines.append(f"- 낙상자: 확인됨 ({how})")
        person = next((p for p in detail.get("people") or [] if p.get("id") == summary.get("fallen_id")), None)
        if person is None or person.get("missing"):
            lines.append("- 건강 정보: 미등록 (확인된 낙상자의 정보가 거주자 파일에 없음)")
            missing.append("낙상자 건강 정보")
        else:
            lines += [f"- 나이: {field('낙상자 나이', person.get('age'))}",
                      f"- 지병: {field('낙상자 지병', person.get('conditions'))}",
                      f"- 복용약: {field('낙상자 복용약', person.get('medications'))}"]
            if person.get("stale"):
                lines.append(f"  (정보 갱신일 {_value(person.get('updated'))}: 오래된 정보일 수 있음)")
    else:
        count = summary.get("resident_count") or 0
        lines.append(f"- 낙상자: 확인되지 않음 (등록된 거주자 {count}명 중 누구인지 알 수 없음)" if count
                     else "- 낙상자: 확인되지 않음 (등록된 거주자 없음)")
        lines.append("- 건강 정보: 낙상자를 확인할 수 없어 넣지 않음")
        missing.append("낙상자")
    lines += ["", "[연락처]", f"- 보호자 연락처: {field('보호자 연락처', detail.get('contact'))}"]
    return {"text": "\n".join(lines), "missing": missing}
