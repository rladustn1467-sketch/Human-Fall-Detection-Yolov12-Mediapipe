"""What a 119 report (SIMULATION ONLY) contains.

summarize() decides the contents and returns only item *names*, resident ids/aliases and
flags; that summary is what is saved in events.json and shown to guardians. The actual
values (address, door codes, contact, medical info) are filled in by details() only when
the report page is rendered, so they are never stored in events.json or sent in messages.
"""
from dataclasses import dataclass

import residents as residents_mod

HOME_ITEMS = ("주소", "현관 비번", "보호자 연락처")
MEDICAL_ITEMS = ("나이", "지병", "복용약", "정보 갱신일")
UNREGISTERED = "미등록"


@dataclass
class HomeInfo:
    address: str = ""
    door_code: str = ""           # 현관 비번
    building_door_code: str = ""  # 공동현관 비번
    contact: str = ""             # 보호자 연락처


def summarize(fallen, residents, unconfirmed_policy="exclude", stale_days=180):
    """Decide the report contents. fallen: the escalation's fallen record (or None)."""
    target_ids, confirmed, how = [], False, None
    if fallen and not fallen.get("after_report") and residents_mod.find(residents, fallen["resident_id"]):
        target_ids, confirmed, how = [fallen["resident_id"]], True, fallen.get("how")
    elif len(residents) == 1:
        # 거주자가 1명이면 그 사람으로 확정
        target_ids, confirmed, how = [residents[0]["id"]], True, "auto"
    elif unconfirmed_policy == "all":
        target_ids = [r["id"] for r in residents]

    targets = [residents_mod.find(residents, rid) for rid in target_ids]
    return {
        "resident_count": len(residents),
        "confirmed": confirmed,
        "confirm_how": how,
        "fallen_id": target_ids[0] if confirmed else None,
        "fallen_alias": targets[0]["alias"] if confirmed else None,
        "medical_resident_ids": target_ids,
        "medical_aliases": [r["alias"] for r in targets],
        "items": list(HOME_ITEMS) + (list(MEDICAL_ITEMS) if targets else []),
        "stale_aliases": [r["alias"] for r in targets if residents_mod.is_stale(r, stale_days)],
        # 신고 뒤 정보가 바뀌었는지 비교하려고 갱신일만 저장 (의료 정보 아님)
        "profile_updated": {r["id"]: r["updated"] for r in targets},
        "unconfirmed_policy": unconfirmed_policy,
    }


def fallen_line(summary):
    if summary["confirmed"]:
        how = " (거주자 1명 자동 확정)" if summary["confirm_how"] == "auto" else ""
        return f"낙상자: {summary['fallen_alias']}{how}"
    if summary["resident_count"] == 0:
        return "낙상자: 거주자 미등록"
    extra = " - 거주자 전원 정보 포함" if summary["medical_resident_ids"] else " - 의료 정보 제외"
    return f"거주자 {summary['resident_count']}명, 낙상자 미확인{extra}"


def details(summary, residents, home, stale_days=180):
    """Fill in the actual values for the report page (never stored, never sent)."""
    people = []
    for rid in summary["medical_resident_ids"]:
        r = residents_mod.find(residents, rid)
        if r is None:
            people.append({"id": rid, "missing": True})
            continue
        people.append({
            "id": rid, "missing": False, "alias": r["alias"],
            "age": r["age"] or UNREGISTERED, "conditions": r["conditions"] or UNREGISTERED,
            "medications": r["medications"] or UNREGISTERED, "updated": r["updated"] or UNREGISTERED,
            "stale": residents_mod.is_stale(r, stale_days),
            "changed_since_report": summary["profile_updated"].get(rid) != r["updated"],
        })
    return {
        "address": home.address or UNREGISTERED,
        "door_code": home.door_code or UNREGISTERED,
        "building_door_code": home.building_door_code or UNREGISTERED,
        "contact": home.contact or UNREGISTERED,
        "people": people,
    }


def format_text(header, summary, detail, after_report_note=""):
    """Plain-text report details for a chat reply (same contents as the report page). Never log or store."""
    lines = [header, fallen_line(summary)]
    if after_report_note:
        lines.append(after_report_note)
    lines += ["", "[집 정보]",
              f"주소: {detail['address']}",
              f"현관 비번: {detail['door_code']} / 공동현관 비번: {detail['building_door_code']}",
              f"보호자 연락처: {detail['contact']}",
              "", "[거주자 정보]"]
    if not detail["people"]:
        lines.append("의료 정보 제외 (낙상자 미확인)")
    for p in detail["people"]:
        if p["missing"]:
            lines.append(f"- 거주자 ID {p['id']}: 현재 거주자 파일에 없음")
            continue
        notes = (" ⚠️ 정보가 오래됐을 수 있음" if p["stale"] else "") + \
                (" (신고 뒤 정보가 수정됨, 현재 정보)" if p["changed_since_report"] else "")
        lines.append(f"- {p['alias']}{notes}")
        lines.append(f"  나이: {p['age']} / 지병: {p['conditions']} / 복용약: {p['medications']} / 정보 갱신일: {p['updated']}")
    return "\n".join(lines)
