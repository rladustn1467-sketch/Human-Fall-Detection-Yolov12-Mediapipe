"""Sign-up, log-in, groups and invites over HTTP, on a COPY of the server (see test_api_v2.ServerCopy).

Each "browser" below keeps its own cookie, like separate browsers. The real server data is never used.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import sqlite3
import time
import unittest
import uuid

import accounts
from tests.test_api_v2 import ServerCopy

PW = "abcd1234"


class Browser:
    """Keeps the fd_session cookie between requests, like one browser."""

    def __init__(self, server, origin=True):
        self.server = server
        self.cookie = None
        self.origin = origin

    def call(self, method, path, body=None, headers=None):
        h = dict(headers or {})
        if self.cookie:
            h["Cookie"] = f"fd_session={self.cookie}"
        if self.origin and method == "POST":
            h["Origin"] = f"http://127.0.0.1:{self.server.port}"
        status, res_headers, text = self.server.request(method, path, body, headers=h)
        set_cookie = res_headers.get("set-cookie")
        if set_cookie and set_cookie.startswith("fd_session="):
            value = set_cookie.split(";", 1)[0].split("=", 1)[1].strip('"')
            self.cookie = value or None
        data = json.loads(text) if text and text.lstrip().startswith("{") else None
        return status, res_headers, data

    def state(self):
        return self.call("GET", "/api/v2/state")[2]


class AuthApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def phone(self):
        # 시험마다 다른 번호 (같은 서버 복사본을 함께 씀)
        return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]

    def signup(self, browser, name="가족테스트", phone=None, password=PW):
        return browser.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone or self.phone(), "password": password})

    # ---- 가입 → 로그아웃 → 로그인 ----
    def test_signup_logout_login(self):
        b = Browser(self.server)
        phone = self.phone()
        status, headers, data = self.signup(b, name="가입시험", phone=phone)
        self.assertEqual(status, 200, data)
        self.assertTrue(data["authenticated"])
        me = data["me_id"]
        self.assertEqual(data["state"]["people"][0]["name"], "가입시험")
        self.assertTrue(b.state()["authenticated"])
        old_cookie = b.cookie

        status, _, data = b.call("POST", "/api/v2/auth/logout")
        self.assertEqual(status, 200)
        self.assertIsNone(b.cookie)
        self.assertFalse(b.state()["authenticated"])
        # 로그아웃한 쿠키를 다시 써도 로그인되지 않음
        stale = Browser(self.server)
        stale.cookie = old_cookie
        self.assertFalse(stale.state()["authenticated"])

        status, _, data = b.call("POST", "/api/v2/auth/login", {"phone": phone, "password": PW})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["me_id"], me)
        self.assertTrue(b.state()["authenticated"])

    def test_session_cookie_flags(self):
        b = Browser(self.server)
        status, headers, _ = self.signup(b)
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"]
        lower = cookie.lower()
        self.assertIn("httponly", lower)
        self.assertIn("samesite=lax", lower)
        self.assertIn("path=/", lower)
        self.assertIn(f"max-age={accounts.SESSION_DAYS * 86400}", lower)
        self.assertNotIn("secure", lower)  # HTTP 시험 서버이므로 자동으로 꺼짐 (HTTPS 에서만 켜짐)
        self.assertEqual(headers.get("cache-control"), "no-store")
        # 쓰는 동안 연장: 하루 넘게 지난 세션이면 만료일을 늦추고 쿠키도 다시 보냄 (DB 시각을 앞당겨 하루 지난 것처럼)
        import sqlite3, time
        c = sqlite3.connect(self.server.db_path)
        mine = accounts._token_hash(b.cookie)
        c.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?", (time.time() + 80 * 86400, mine))
        c.commit()
        c.close()
        status, headers, _ = b.call("GET", "/api/v2/state")
        self.assertEqual(status, 200)
        renewed = headers.get("set-cookie", "").lower()
        self.assertIn("fd_session=", renewed)
        self.assertIn(f"max-age={accounts.SESSION_DAYS * 86400}", renewed)
        self.assertIn("httponly", renewed)
        c = sqlite3.connect(self.server.db_path)
        left = c.execute("SELECT expires_at FROM sessions WHERE token_hash = ?", (mine,)).fetchone()[0] - time.time()
        c.close()
        self.assertGreater(left, 89 * 86400)
        status, headers, _ = b.call("GET", "/api/v2/state")
        self.assertNotIn("fd_session=", headers.get("set-cookie", ""))                # 같은 날 다시: 보내지 않음

    def test_wrong_password_and_rate_limit(self):
        b = Browser(self.server)
        phone = self.phone()
        self.signup(b, phone=phone)
        b.call("POST", "/api/v2/auth/logout")
        limit, _ = accounts.LOGIN_LIMIT_PER_PHONE
        for _ in range(limit):
            status, _, data = b.call("POST", "/api/v2/auth/login", {"phone": phone, "password": "wrong999"})
            self.assertEqual(status, 401)
            self.assertEqual(data["field"], "password")
        status, headers, data = b.call("POST", "/api/v2/auth/login", {"phone": phone, "password": PW})
        self.assertEqual(status, 429, data)
        self.assertGreater(int(headers["retry-after"]), 0)
        self.assertIn("분 뒤", data["message"])

    def test_duplicate_phone(self):
        phone = self.phone()
        self.assertEqual(self.signup(Browser(self.server), phone=phone)[0], 200)
        status, _, data = self.signup(Browser(self.server), phone=phone)
        self.assertEqual(status, 409)
        self.assertEqual(data["field"], "phone")

    def test_server_checks_password_rule(self):
        status, _, data = self.signup(Browser(self.server), password="onlyletters")
        self.assertEqual(status, 400)
        self.assertEqual(data["field"], "password")

    def test_other_site_requests_are_rejected(self):
        b = Browser(self.server, origin=False)
        status, _, data = b.call("POST", "/api/v2/auth/signup",
                                 {"name": "외부사이트", "phone": self.phone(), "password": PW},
                                 headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403, data)

    # ---- 그룹 · 초대 · 권한 ----
    def test_group_invite_join_and_isolation(self):
        a, b, c = Browser(self.server), Browser(self.server), Browser(self.server)
        for browser, name in ((a, "가족에이"), (b, "가족비"), (c, "다른집씨")):
            self.assertEqual(self.signup(browser, name=name)[0], 200, name)

        status, _, data = a.call("POST", "/api/v2/groups")
        self.assertEqual(status, 200, data)
        code = data["state"]["groups"][0]["invite"]["code"]

        status, _, data = b.call("POST", "/api/v2/groups/join", {"code": code})
        self.assertEqual(status, 200, data)
        self.assertEqual([p["name"] for p in data["state"]["people"]], ["가족에이", "가족비"])
        self.assertEqual([p["name"] for p in a.state()["state"]["people"]], ["가족에이", "가족비"])

        # 다른 그룹: 서로의 그룹·구성원이 보이지 않음
        c.call("POST", "/api/v2/groups")
        c_state = c.state()["state"]
        self.assertEqual([p["name"] for p in c_state["people"]], ["다른집씨"])
        self.assertNotEqual(c_state["groups"][0]["id"], a.state()["state"]["groups"][0]["id"])
        # 브라우저가 다른 그룹 id 를 보내도 서버는 자기 그룹에만 적용 (요청의 그룹 id 를 쓰지 않음)
        a_group = a.state()["state"]["groups"][0]
        c.call("POST", "/api/v2/groups/invite", {"groupId": a_group["id"]})
        self.assertEqual(a.state()["state"]["groups"][0]["invite"]["code"], a_group["invite"]["code"])
        # 이미 다른 그룹에 있는 사람은 참여 불가
        self.assertEqual(c.call("POST", "/api/v2/groups/join", {"code": a_group["invite"]["code"]})[0], 409)

    def test_new_code_invalidates_old_and_expiry(self):
        a, b = Browser(self.server), Browser(self.server)
        self.signup(a)
        self.signup(b)
        old = a.call("POST", "/api/v2/groups")[2]["state"]["groups"][0]["invite"]["code"]
        new = a.call("POST", "/api/v2/groups/invite")[2]["state"]["groups"][0]["invite"]["code"]
        self.assertNotEqual(old, new)
        status, _, data = b.call("POST", "/api/v2/groups/join", {"code": old})
        self.assertEqual(status, 400)
        self.assertEqual(data["field"], "code")
        # 24시간이 지난 코드: 복사본 DB 에서 만료 시각을 과거로 바꿔 확인
        conn = sqlite3.connect(self.server.db_path)
        try:
            with conn:  # 변경 확정 (with 는 연결을 닫지 않으므로 아래에서 직접 닫음)
                conn.execute("UPDATE invites SET expires_at = ? WHERE code = ?", (time.time() - 1, new))
        finally:
            conn.close()
        status, _, data = b.call("POST", "/api/v2/groups/join", {"code": new})
        self.assertEqual(status, 400)
        self.assertIn("만료", data["message"])

    def test_group_actions_need_login(self):
        anonymous = Browser(self.server)
        for path, body in (("/api/v2/groups", None), ("/api/v2/groups/invite", None),
                           ("/api/v2/groups/join", {"code": "ABCDEF"}), ("/api/v2/groups/leave", None),
                           ("/api/v2/me/onboarded", {"onboarded": True})):
            self.assertEqual(anonymous.call("POST", path, body)[0], 401, path)

    def test_old_shared_token_does_not_log_in_to_new_app(self):
        status, _, text = self.server.request("GET", "/api/v2/state", token=self.server.token)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(text)["authenticated"])
        status, _, _ = self.server.request("POST", "/api/v2/groups", token=self.server.token)
        self.assertEqual(status, 401)

    def test_leave_and_onboarded(self):
        a = Browser(self.server)
        self.signup(a)
        a.call("POST", "/api/v2/groups")
        status, _, data = a.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["state"]["people"][0]["onboarded"])
        status, _, data = a.call("POST", "/api/v2/groups/leave")
        self.assertEqual(status, 200)
        self.assertEqual(data["state"]["groups"], [])
        self.assertIsNone(data["state"]["people"][0]["groupId"])

    # ---- 저장 내용 · 기존 기능 ----
    def test_database_has_no_plain_password(self):
        secret = "Plain9text8pw"
        b = Browser(self.server)
        self.assertEqual(self.signup(b, password=secret)[0], 200)
        raw = b""
        for suffix in ("", "-wal", "-shm"):
            path = self.server.db_path.with_name(self.server.db_path.name + suffix)
            if path.exists():
                raw += path.read_bytes()
        self.assertNotIn(secret.encode(), raw)
        self.assertNotIn(b.cookie.encode(), raw)  # 로그인 쿠키 값도 해시로만 저장

    def test_old_event_api_and_token_still_work(self):
        self.assertEqual(self.server.request("GET", "/api/events")[0], 401)
        event_id = uuid.uuid4().hex
        status, _, _ = self.server.request("POST", "/api/events", {
            "event_id": event_id, "device_id": "unittest", "fall_type": "slip_and_fall", "is_test": True},
            token=self.server.token)
        self.assertEqual(status, 200)
        self.assertEqual(self.server.request("GET", f"/api/events/{event_id}", token=self.server.token)[0], 200)
        self.assertEqual(self.server.request("GET", "/app/", token=self.server.token)[0], 200)


if __name__ == "__main__":
    unittest.main()
