"""Road-name address search (address_search.py) with a FAKE 도로명주소 API: no internet and no real key needed.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import threading
import unittest
import urllib.error
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import accounts
import address_search
from tests.test_accounts import IP, PW, AccountsTestBase
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import Browser

FAKE_KEY = "fake-key-for-tests"


def juso_reply(items, code="0", message="정상"):
    return {"results": {"common": {"errorCode": code, "errorMessage": message, "totalCount": str(len(items))},
                        "juso": items}}


ITEMS = [{"roadAddr": "서울특별시 마포구 월드컵로 100 (망원동)", "zipNo": "03900", "bdNm": "한빛아파트", "jibunAddr": "서울 망원동 1"},
         {"roadAddr": "서울특별시 마포구 월드컵로 102", "zipNo": "03901", "bdNm": ""}]


class SearchTest(AccountsTestBase):
    def setUp(self):
        super().setUp()
        self.user = self.signup()
        self.urls = []

    def fake(self, reply):
        def fetch(url, timeout):
            self.urls.append(url)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return fetch

    def search(self, q="월드컵로 100", reply=None, key=FAKE_KEY, now=None):
        return address_search.search(self.conn, self.user, q, key, "http://fake/api", now=now or self.now,
                                     fetch=self.fake(juso_reply(ITEMS) if reply is None else reply))

    def test_results_only_carry_address_zip_and_building(self):
        results = self.search()
        self.assertEqual(results, [{"address": "서울특별시 마포구 월드컵로 100 (망원동)", "zip": "03900", "building": "한빛아파트"},
                                   {"address": "서울특별시 마포구 월드컵로 102", "zip": "03901", "building": ""}])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.urls[0]).query)
        self.assertEqual(query["confmKey"], [FAKE_KEY])          # 키는 서버에서 API 로만 보냄
        self.assertEqual(query["keyword"], ["월드컵로 100"])
        self.assertEqual(query["resultType"], ["json"])
        self.assertNotIn(FAKE_KEY, json.dumps(results))

    def test_keyword_rules(self):
        self.assertEqual(address_search.clean_keyword("  월드컵로   100 "), "월드컵로 100")
        self.assertEqual(address_search.clean_keyword("세종대로<209>"), "세종대로 209")
        self.assertAccountError(400, address_search.clean_keyword, "가")
        self.assertAccountError(400, address_search.clean_keyword, "가" * 81)
        self.assertAccountError(400, address_search.clean_keyword, "%%%")
        err = self.assertAccountError(400, address_search.clean_keyword, "월드컵로 union select")
        self.assertEqual(err.field, "q")
        self.assertEqual(self.urls, [])

    def test_unavailable_cases_answer_503(self):
        self.assertAccountError(503, self.search, key="")                                       # 키 없음
        self.assertAccountError(503, self.search, reply=juso_reply([], code="E0001", message="승인되지 않은 KEY"))
        self.assertAccountError(503, self.search, reply=urllib.error.URLError("timeout"))       # 연결 실패
        self.assertAccountError(503, self.search, reply={"unexpected": True})                    # 형식 오류
        self.assertEqual(self.search(reply=juso_reply([])), [])                                  # 결과 없음은 정상

    def test_rate_limit_per_user_and_old_rows_removed(self):
        count, window = address_search.SEARCH_LIMIT_PER_USER
        for i in range(count):
            self.search(now=self.now + i * 0.1)
        err = self.assertAccountError(429, self.search, now=self.now + count * 0.1)
        self.assertGreater(err.retry_after, 0)
        other = self.signup(name="다른사람", phone="010-3333-4444")
        address_search.search(self.conn, other, "월드컵로", FAKE_KEY, "http://fake", now=self.now, fetch=self.fake(juso_reply(ITEMS)))
        later = self.now + window + 5
        self.search(now=later)                                      # 시간이 지나면 다시 가능
        rows = self.conn.execute("SELECT COUNT(*) FROM auth_failures WHERE key = ?", (f"address-user:{self.user}",)).fetchone()[0]
        self.assertEqual(rows, 1)                                   # 지난 기록은 지워짐

    def test_withdraw_removes_search_records(self):
        self.search()
        accounts.withdraw(self.conn, self.user, PW, IP, self.now)
        rows = self.conn.execute("SELECT COUNT(*) FROM auth_failures WHERE key LIKE 'address-user:%'").fetchone()[0]
        self.assertEqual(rows, 0)


class FakeJuso(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        FakeJuso.seen.append(query)
        reply = juso_reply(ITEMS) if query.get("confmKey") == [FAKE_KEY] else juso_reply([], "E0001", "승인되지 않은 KEY")
        body = json.dumps(reply, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class SearchApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = HTTPServer(("127.0.0.1", 0), FakeJuso)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{cls.fake.server_port}/addrlink/addrLinkApi.do"
        cls.server = ServerCopy({"JUSO_API_KEY": FAKE_KEY, "JUSO_API_URL": url})
        cls.no_key = ServerCopy({"JUSO_API_KEY": "", "JUSO_API_URL": url})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.no_key.close()
        cls.fake.shutdown()
        cls.fake.server_close()

    def login(self, server):
        b = Browser(server)
        phone = "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]
        self.assertEqual(b.call("POST", "/api/v2/auth/signup", {"name": "주소검색", "phone": phone, "password": PW})[0], 200)
        return b

    def test_search_through_server(self):
        b = self.login(self.server)
        status, headers, data = b.call("GET", "/api/v2/address/search?q=" + urllib.parse.quote("월드컵로 100"))
        self.assertEqual(status, 200, data)
        self.assertEqual(data["results"][0]["address"], "서울특별시 마포구 월드컵로 100 (망원동)")
        self.assertEqual(headers.get("cache-control"), "no-store")
        self.assertEqual(FakeJuso.seen[-1]["confmKey"], [FAKE_KEY])
        status, _, text = self.server.request("GET", "/api/v2/address/search?q=abc", headers={"Cookie": f"fd_session={b.cookie}"})
        self.assertNotIn(FAKE_KEY, text)                           # 응답에 키 없음

    def test_needs_login_and_old_token_is_not_enough(self):
        self.assertEqual(Browser(self.server).call("GET", "/api/v2/address/search?q=abc")[0], 401)
        self.assertEqual(self.server.request("GET", "/api/v2/address/search?q=abc", token=self.server.token)[0], 401)

    def test_bad_keyword_and_missing_key(self):
        b = self.login(self.server)
        status, _, data = b.call("GET", "/api/v2/address/search?q=a")
        self.assertEqual((status, data["field"]), (400, "q"))
        c = self.login(self.no_key)
        status, _, data = c.call("GET", "/api/v2/address/search?q=" + urllib.parse.quote("월드컵로"))
        self.assertEqual(status, 503)
        self.assertIn("직접 입력", data["message"])


if __name__ == "__main__":
    unittest.main()
