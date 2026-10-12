"""Resident profiles (server/residents.json, not in git).

Medical information lives ONLY in that file. Never print its values, save them in
events.json or put them in any message: elsewhere a resident is referred to by id/alias only.
The file is read again whenever it is needed, so edits apply without restarting the server.
"""
import json
import re
from datetime import date, datetime

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
DATE_FORMAT = "%Y-%m-%d"

_last_message = None


def _log_once(message):
    # 페이지가 5초마다 새로고침되며 파일을 다시 읽으므로 같은 안내는 한 번만 출력
    global _last_message
    if message != _last_message:
        print(message)
        _last_message = message


def _text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def load(path):
    """Return the residents as [{id, alias, age, conditions, medications, updated}], or [] if unusable."""
    if not path.exists():
        _log_once(f"[residents] {path.name} 없음 - 거주자 0명으로 처리 (예시: residents.example.json)")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        # 오류 위치만 알림 (내용은 출력하지 않음)
        _log_once(f"[residents] {path.name} 형식 오류: {e.lineno}번째 줄 {e.colno}번째 칸 근처 - 거주자 0명으로 처리")
        return []
    except OSError as e:
        _log_once(f"[residents] {path.name} 읽기 실패 ({type(e).__name__}) - 거주자 0명으로 처리")
        return []
    items = data.get("residents") if isinstance(data, dict) else None
    if not isinstance(items, list):
        _log_once(f'[residents] {path.name} 에 "residents" 목록이 없음 - 거주자 0명으로 처리')
        return []

    residents, seen, problems = [], set(), []
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append(f"{number}번째 거주자 형식 오류")
            continue
        rid = _text(item.get("id")) or f"r{number}"
        if not ID_RE.match(rid) or rid in seen:
            problems.append(f"{number}번째 거주자 id 오류(영문·숫자 20자 이내, 중복 불가)")
            continue
        seen.add(rid)
        residents.append({
            "id": rid,
            "alias": _text(item.get("alias")) or f"거주자{number}",
            "age": _text(item.get("age")),
            "conditions": _text(item.get("conditions")),
            "medications": _text(item.get("medications")),
            "updated": _text(item.get("updated")),
        })
    aliases = ", ".join(r["alias"] for r in residents)
    note = f" / 건너뜀: {'; '.join(problems)}" if problems else ""
    _log_once(f"[residents] 거주자 {len(residents)}명 ({aliases or '없음'}){note}")
    return residents


def find(residents, rid):
    return next((r for r in residents if r["id"] == rid), None)


def is_stale(resident, stale_days, today=None):
    """True when the profile's update date is missing, invalid or older than stale_days."""
    try:
        updated = datetime.strptime(resident.get("updated", ""), DATE_FORMAT).date()
    except ValueError:
        return True
    return ((today or date.today()) - updated).days > stale_days
