"""Door codes over HTTP on COPIES of the server: one with a test key (made here, never the real one) and one
without a key. Checks permissions, that no response, state, log, database file or events.json contains the
plain code, and that a missing key fails safely.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import time
import unittest
import uuid

import door_codes
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser

SECRET = "84620*#"


class DoorCodeApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key_text = door_codes.generate_key()
        cls.server = ServerCopy({"DOOR_CODE_KEY": cls.key_text})
        cls.no_key = ServerCopy({"DOOR_CODE_KEY": ""})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.no_key.close()

    def member(self, server, name, code=None):
        b = Browser(server)
        phone = "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone, "password": PW})
        self.assertEqual(status, 200, data)
        b.id = data["me_id"]
        if code:
            self.assertEqual(b.call("POST", "/api/v2/groups/join", {"code": code})[0], 200)
        else:
            self.assertEqual(b.call("POST", "/api/v2/groups")[0], 200)
        return b

    def family(self, server):
        """a: 집에 연결된 가족, b: 같은 그룹이지만 집에 연결 안 됨, c: 다른 그룹"""
        a = self.member(server, "현관에이")
        code = a.state()["state"]["groups"][0]["invite"]["code"]
        b = self.member(server, "현관비", code)
        c = self.member(server, "다른집씨")
        status, _, data = a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": "서울"}})
        self.assertEqual(status, 200, data)
        return a, b, c, data["state"]["homes"][0]["id"]

    def call_text(self, server, browser, method, path, body=None, headers=None):
        h = dict(headers or {})
        if browser.cookie:
            h["Cookie"] = f"fd_session={browser.cookie}"
        h.setdefault("Origin", f"http://127.0.0.1:{server.port}")
        return server.request(method, path, body, headers=h)

    def test_register_change_delete_and_nothing_leaks(self):
        a, b, c, home = self.family(self.server)
        texts = []
        status, _, text = self.call_text(self.server, a, "PUT", f"/api/v2/homes/{home}/door-codes/door", {"code": SECRET})
        texts.append(text)
        self.assertEqual(status, 200, text)
        self.assertTrue(json.loads(text)["state"]["homes"][0]["doorPw"])
        seen_by_b = b.state()
        texts.append(json.dumps(seen_by_b, ensure_ascii=False))
        self.assertEqual((seen_by_b["state"]["homes"][0]["doorPw"], seen_by_b["state"]["homes"][0]["centralPw"]), (True, False))
        status, _, text = self.call_text(self.server, a, "PUT", f"/api/v2/homes/{home}/door-codes/door", {"code": "13579"})
        texts.append(text)
        self.assertEqual(status, 200)
        status, _, text = self.call_text(self.server, a, "DELETE", f"/api/v2/homes/{home}/door-codes/door")
        texts.append(text)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(text)["state"]["homes"][0]["doorPw"])
        self.assertEqual(self.call_text(self.server, a, "DELETE", f"/api/v2/homes/{home}/door-codes/door")[0], 404)
        # 응답·상태·로그·DB 파일·events.json 어디에도 원문 없음
        self.call_text(self.server, a, "PUT", f"/api/v2/homes/{home}/door-codes/central", {"code": SECRET})
        time.sleep(0.5)
        for t in texts:
            self.assertNotIn(SECRET, t)
            self.assertNotIn("13579", t)
        log = (self.server.dir / "server.log").read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(SECRET, log)
        self.assertNotIn(self.key_text, log)
        self.assertIn("[door] 현관 비밀번호 저장: 켜짐", log)
        raw = b"".join(p.read_bytes() for p in self.server.dir.glob("copy.db*"))
        self.assertNotIn(SECRET.encode(), raw)
        self.assertNotIn(self.key_text.encode(), raw)
        events = self.server.dir / "events.json"
        if events.exists():
            self.assertNotIn(SECRET, events.read_text(encoding="utf-8"))
        # 값을 꺼내는 주소는 없음
        self.assertIn(self.call_text(self.server, a, "GET", f"/api/v2/homes/{home}/door-codes/central")[0], (404, 405))

    def test_permissions(self):
        a, b, c, home = self.family(self.server)
        path = f"/api/v2/homes/{home}/door-codes/door"
        self.assertEqual(self.call_text(self.server, b, "PUT", path, {"code": "1234"})[0], 403)   # 집에 연결 안 됨
        status, _, text = self.call_text(self.server, c, "PUT", path, {"code": "1234"})            # 다른 그룹
        self.assertEqual(status, 404)
        self.assertIn("집을 찾을 수 없어요", text)
        self.assertEqual(self.call_text(self.server, a, "PUT", path, {"code": "1234"})[0], 200)
        self.assertEqual(self.call_text(self.server, b, "DELETE", path)[0], 403)
        self.assertEqual(self.call_text(self.server, c, "DELETE", path)[0], 404)
        self.assertEqual(self.call_text(self.server, a, "PUT", f"/api/v2/homes/{home}/door-codes/garage", {"code": "1234"})[0], 404)
        self.assertEqual(Browser(self.server).call("PUT", path, {"code": "1234"})[0], 401)          # 로그인 필요
        self.assertEqual(self.server.request("PUT", path, {"code": "1234"}, token=self.server.token)[0], 401)  # 공용 토큰 불가
        status, _, _ = self.call_text(self.server, a, "PUT", path, {"code": "1234"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertTrue(c.state()["state"]["homes"] == [])

    def test_rule_errors_do_not_echo_the_value(self):
        a, b, c, home = self.family(self.server)
        path = f"/api/v2/homes/{home}/door-codes/door"
        for bad in ("12ab99*", "12", "1" * 30, ["99887766"], {"x": "99887766"}, 99887766):
            status, _, text = self.call_text(self.server, a, "PUT", path, {"code": bad})
            self.assertEqual(status, 400, (bad, text))
            self.assertEqual(json.loads(text)["field"], "code")
            self.assertNotIn("99887766", text)
            self.assertNotIn("12ab99", text)
        # 형식이 깨진 요청(필수 항목 없음)도 입력값을 되돌려 주지 않음
        status, _, text = self.call_text(self.server, a, "POST", "/api/v2/me/setup", {"doors": {"door": "99887766"}})
        self.assertEqual(status, 422)
        self.assertNotIn("99887766", text)
        status, _, text = self.call_text(self.server, a, "POST", "/api/v2/auth/login", {"phone": "x", "password": "p" * 300 + "SECRETPW1"})
        self.assertEqual(status, 422)
        self.assertNotIn("SECRETPW1", text)

    def test_setup_with_door_codes(self):
        a = self.member(self.server, "설정에이")
        status, _, text = self.call_text(self.server, a, "POST", "/api/v2/me/setup",
                                         {"info": {}, "home": {"mode": "new", "address": "서울"}, "doors": {"central": "1234", "door": SECRET}})
        self.assertEqual(status, 200, text)
        home = json.loads(text)["state"]["homes"][0]
        self.assertEqual((home["centralPw"], home["doorPw"]), (True, True))
        self.assertNotIn(SECRET, text)
        b = self.member(self.server, "설정비")
        status, _, text = self.call_text(self.server, b, "POST", "/api/v2/me/setup",
                                         {"info": {}, "home": {"mode": "new", "address": "서울"}, "doors": {"door": "12a"}})
        self.assertEqual(status, 400)
        self.assertFalse([p for p in b.state()["state"]["people"] if p["id"] == b.id][0]["isTarget"])   # 아무것도 저장 안 됨

    def test_entrances_over_http(self):
        a, b, c, home = self.family(self.server)
        put = lambda who, kind, body, headers=None: self.call_text(self.server, who, "PUT", f"/api/v2/homes/{home}/entrances/{kind}", body, headers)
        status, _, text = put(a, "central", {"method": "absent"})
        self.assertEqual(status, 200, text)
        status, _, text = put(a, "door", {"method": "code", "code": SECRET})
        self.assertEqual(status, 200, text)
        self.assertNotIn(SECRET, text)
        seen = b.state()["state"]["homes"][0]                           # 같은 집의 다른 가족: 방식·등록 여부만
        self.assertEqual((seen["centralAccess"], seen["centralPw"], seen["doorAccess"], seen["doorPw"]), ("absent", False, "code", True))
        self.assertNotIn(SECRET, json.dumps(b.state(), ensure_ascii=False))
        self.assertEqual(put(a, "door", {"method": "code"})[0], 200)    # 입력 없이 저장 → 그대로 등록됨
        self.assertTrue(a.state()["state"]["homes"][0]["doorPw"])
        # 권한·CSRF·잘못된 값
        self.assertEqual(put(b, "door", {"method": "key"})[0], 403)
        self.assertEqual(put(c, "door", {"method": "key"})[0], 404)
        self.assertEqual(Browser(self.server).call("PUT", f"/api/v2/homes/{home}/entrances/door", {"method": "key"})[0], 401)
        a.origin = False
        self.assertEqual(put(a, "door", {"method": "key"}, {"Origin": "http://evil.example"})[0], 403)
        a.origin = True
        status, _, text = put(a, "door", {"method": "absent"})
        self.assertEqual((status, json.loads(text)["field"]), (400, "method"))
        self.assertTrue(a.state()["state"]["homes"][0]["doorPw"])       # 거부된 요청은 아무것도 안 바꿈
        # 열쇠로 바꾸면 집 현관 비밀번호만 삭제, 비밀번호 등록 요청은 409
        self.assertEqual(put(a, "door", {"method": "key"})[0], 200)
        h = a.state()["state"]["homes"][0]
        self.assertEqual((h["centralAccess"], h["doorAccess"], h["doorPw"]), ("absent", "key", False))
        status, _, text = self.call_text(self.server, a, "PUT", f"/api/v2/homes/{home}/door-codes/door", {"code": "4321"})
        self.assertEqual(status, 409, text)
        # 처음 설정에서 함께 저장
        d = self.member(self.server, "설정디")
        status, _, text = self.call_text(self.server, d, "POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": "부산"},
                                         "entrances": {"central": {"method": "code", "code": "1234"}, "door": {"method": "unlocked"}}})
        self.assertEqual(status, 200, text)
        h = json.loads(text)["state"]["homes"][0]
        self.assertEqual((h["centralAccess"], h["centralPw"], h["doorAccess"], h["doorPw"]), ("code", True, "unlocked", False))
        log = (self.server.dir / "server.log").read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(SECRET, log)

    def test_no_key_fails_safely(self):
        a, b, c, home = self.family(self.no_key)
        status, _, text = self.call_text(self.no_key, a, "PUT", f"/api/v2/homes/{home}/door-codes/door", {"code": SECRET})
        self.assertEqual(status, 503)
        self.assertIn("암호화 키", json.loads(text)["message"])
        self.assertFalse(a.state()["state"]["homes"][0]["doorPw"])
        d = self.member(self.no_key, "키없음설정")
        status, _, _ = self.call_text(self.no_key, d, "POST", "/api/v2/me/setup",
                                      {"info": {}, "home": {"mode": "new", "address": "서울"}, "doors": {"door": SECRET}})
        self.assertEqual(status, 503)
        self.assertEqual(self.call_text(self.no_key, d, "POST", "/api/v2/me/setup",
                                        {"info": {}, "home": {"mode": "new", "address": "서울"}})[0], 200)   # 비밀번호 없이는 완료
        log = (self.no_key.dir / "server.log").read_text(encoding="utf-8", errors="replace")
        self.assertIn("[door] 현관 비밀번호 저장: 꺼짐", log)
        raw = b"".join(p.read_bytes() for p in self.no_key.dir.glob("copy.db*"))
        self.assertNotIn(SECRET.encode(), raw)                                     # 평문으로도 저장 안 됨


if __name__ == "__main__":
    unittest.main()
