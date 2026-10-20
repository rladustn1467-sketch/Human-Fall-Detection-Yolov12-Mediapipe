"""Road-name address search for the family web app (/app/next), through the official 도로명주소 검색 API
(business.juso.go.kr). The server calls the API so the approval key never reaches the browser.

Settings (server/.env, not in git):
  JUSO_API_KEY   approval key (confmKey). Without it, search answers 503 and the screen offers manual input.
  JUSO_API_URL   optional, for tests only (a fake API on this computer)

Limits: logged-in users only, SEARCH_LIMIT_PER_USER searches per window (stored in auth_failures, old rows are
removed as new ones are added). Only the road address, zip code and building name are returned.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import accounts
import db
from accounts import AccountError

DEFAULT_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
TIMEOUT_SECONDS = 5
MAX_RESULTS = 10
KEYWORD_MIN, KEYWORD_MAX = 2, 80
SEARCH_LIMIT_PER_USER = (30, 60)   # 1분에 30회
# 도로명주소 API 가 검색어로 받지 않는 특수문자·예약어 (API 안내 기준). 미리 걸러 오류 대신 안내
_SPECIAL = re.compile(r"[%=><\[\]{}()'\";\\]")
_RESERVED = re.compile(r"\b(OR|SELECT|INSERT|DELETE|UPDATE|CREATE|DROP|EXEC|UNION|FETCH|DECLARE|TRUNCATE)\b", re.I)
UNAVAILABLE = "지금은 주소 검색을 할 수 없어요. '직접 입력하기'로 주소를 입력해 주세요."


def clean_keyword(value):
    keyword = re.sub(r"\s+", " ", _SPECIAL.sub(" ", value if isinstance(value, str) else "")).strip()
    if _RESERVED.search(keyword):
        raise AccountError(400, "검색어에 쓸 수 없는 단어가 있어요. 도로명이나 건물명으로 검색해 주세요.", "q")
    if not KEYWORD_MIN <= len(keyword) <= KEYWORD_MAX:
        raise AccountError(400, f"검색어를 {KEYWORD_MIN}~{KEYWORD_MAX}자로 입력해 주세요.", "q")
    return keyword


def _count_search(conn, user_id, now):
    key = f"address-user:{user_id}"
    count, window = SEARCH_LIMIT_PER_USER
    accounts._check_limit(conn, key, SEARCH_LIMIT_PER_USER, now, "주소 검색을 너무 자주 했어요. {minutes}분 뒤 다시 시도해 주세요.")
    with db.transaction(conn):
        conn.execute("DELETE FROM auth_failures WHERE key = ? AND at <= ?", (key, now - window))
        conn.execute("INSERT INTO auth_failures (key, at) VALUES (?, ?)", (key, now))


def _fetch(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def search(conn, user_id, query, api_key, api_url=None, now=None, fetch=_fetch):
    """Returns [{"address", "zip", "building"}]. Raises AccountError (400 keyword, 429 too often, 503 unavailable)."""
    now = time.time() if now is None else now
    keyword = clean_keyword(query)
    if not api_key:
        raise AccountError(503, UNAVAILABLE)
    _count_search(conn, user_id, now)
    params = urllib.parse.urlencode({"confmKey": api_key, "currentPage": 1, "countPerPage": MAX_RESULTS,
                                     "keyword": keyword, "resultType": "json"})
    try:
        data = fetch(f"{api_url or DEFAULT_URL}?{params}", TIMEOUT_SECONDS)
        common = data["results"]["common"]
        items = data["results"]["juso"] or []
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
        # 연결 실패·시간 초과·형식 오류. 키가 들어 있는 주소는 기록하지 않음
        print("[address] 도로명주소 API 응답 없음 또는 형식 오류")
        raise AccountError(503, UNAVAILABLE)
    if str(common.get("errorCode")) != "0":
        # 키 미승인·만료 등은 서버 관리자가 고칠 일이라 화면에는 같은 안내, 로그에는 코드만
        print(f"[address] 도로명주소 API 오류 코드 {common.get('errorCode')}")
        raise AccountError(503, UNAVAILABLE)
    results = []
    for item in items[:MAX_RESULTS]:
        if not isinstance(item, dict) or not item.get("roadAddr"):
            continue
        results.append({"address": str(item["roadAddr"]).strip(), "zip": str(item.get("zipNo") or ""),
                        "building": str(item.get("bdNm") or "")})
    return results
