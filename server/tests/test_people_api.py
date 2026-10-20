"""Stage C over HTTP on a COPY of the server: profile, homes, first setup, withdrawal, and requests that send
another group's user id or home id directly.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import unittest
import uuid

from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser


class PeopleApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def phone(self):
        return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]

    def member(self, name, code=None):
        """A logged-in browser in a new group (or in the group of `code`)."""
        b = Browser(self.server)
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": self.phone(), "password": PW})
        self.assertEqual(status, 200, data)
        b.id = data["me_id"]
        if code:
            self.assertEqual(b.call("POST", "/api/v2/groups/join", {"code": code})[0], 200)
        else:
            self.assertEqual(b.call("POST", "/api/v2/groups")[0], 200)
        return b

    def code(self, b):
        return b.state()["state"]["groups"][0]["invite"]["code"]

    def me(self, b):
        state = b.state()["state"]
        return next(p for p in state["people"] if p["id"] == b.id)

    def setup(self, b, info=None, home=None):
        return b.call("POST", "/api/v2/me/setup", {"info": info or {}, "home": home or {"mode": "new", "address": ""}})

    def test_setup_profile_and_family_view(self):
        a = self.member("가족에이")
        b = self.member("가족비", self.code(a))
        status, _, data = self.setup(a, {"birth": "1951-07-08", "conditions": ["고혈압"], "medications": []},
                                     {"mode": "new", "address": "서울 마포구 월드컵로 100 101동 1203호"})
        self.assertEqual(status, 200, data)
        home_id = data["state"]["homes"][0]["id"]
        # 같은 그룹 가족에게는 건강 정보와 집이 보임 (젠스파크 설계: "그룹 가족에게 공유돼요")
        seen = next(p for p in b.state()["state"]["people"] if p["id"] == a.id)
        self.assertEqual((seen["isTarget"], seen["birth"], seen["conditions"], seen["homeIds"]),
                         (True, "1951-07-08", ["고혈압"], [home_id]))
        # 이름·건강 정보 수정. 휴대전화 번호를 보내도 바뀌지 않음 (문자 인증 단계에서)
        old_phone = self.me(a)["phone"]
        status, _, data = a.call("POST", "/api/v2/me/profile",
                                 {"name": "에이수정", "phone": "010-9999-9999", "birth": None, "conditions": ["당뇨"]})
        self.assertEqual(status, 200, data)
        me = self.me(a)
        self.assertEqual((me["name"], me["phone"], me["birth"], me["conditions"], me["medications"]),
                         ("에이수정", old_phone, None, ["당뇨"], []))
        # 알림 설정
        status, _, _ = a.call("POST", "/api/v2/me/prefs", {"key": "device", "value": False})
        self.assertEqual(status, 200)
        self.assertFalse(self.me(a)["prefs"]["device"])
        # 비는 같은 집에 연결 → 주소 수정 가능
        self.assertEqual(self.setup(b, home={"mode": "existing", "id": home_id})[0], 200)
        status, _, data = b.call("POST", f"/api/v2/homes/{home_id}/address", {"address": "서울 마포구 2"})
        self.assertEqual(status, 200, data)
        self.assertEqual(a.state()["state"]["homes"][0]["address"], "서울 마포구 2")
        self.assertEqual(b.call("POST", f"/api/v2/homes/{home_id}/unlink")[0], 200)
        self.assertEqual(b.call("POST", f"/api/v2/homes/{home_id}/address", {"address": "서울 3"})[0], 403)
        self.assertEqual(b.call("POST", f"/api/v2/homes/{home_id}/link")[0], 200)

    def test_other_group_ids_sent_directly_are_rejected(self):
        a = self.member("가족에이")
        c = self.member("다른집씨")
        home_a = self.setup(a, {"birth": "1951-07-08"}, {"mode": "new", "address": "에이네 집"})[2]["state"]["homes"][0]["id"]
        # 다른 그룹의 집 id 로 연결·해제·주소 수정·처음 설정 → 모두 '찾을 수 없음'
        for path, body in ((f"/api/v2/homes/{home_a}/link", None), (f"/api/v2/homes/{home_a}/unlink", None),
                           (f"/api/v2/homes/{home_a}/address", {"address": "남의 집 바꿈"})):
            status, _, data = c.call("POST", path, body)
            self.assertEqual(status, 404, path)
            self.assertEqual(data["message"], "집을 찾을 수 없어요.")
        status, _, _ = self.setup(c, {"birth": "1960-01-01"}, {"mode": "existing", "id": home_a})
        self.assertEqual(status, 404)
        self.assertFalse(self.me(c)["isTarget"])          # 실패한 처음 설정은 아무것도 저장 안 됨
        # 다른 사람의 사용자 id 를 본문에 넣어도 무시되고 자기 정보만 바뀜
        status, _, _ = c.call("POST", "/api/v2/me/profile", {"name": "바꿔치기", "id": a.id, "personId": a.id, "userId": a.id})
        self.assertEqual(status, 200)
        self.assertEqual(self.me(a)["name"], "가족에이")
        self.assertEqual(self.me(c)["name"], "바꿔치기")
        c.call("POST", "/api/v2/me/prefs", {"key": "home", "value": False, "personId": a.id})
        self.assertTrue(self.me(a)["prefs"]["home"])
        # 상태에도 다른 그룹 정보 없음
        c_state = c.state()["state"]
        self.assertEqual([p["id"] for p in c_state["people"]], [c.id])
        self.assertEqual(c_state["homes"], [])
        self.assertEqual(a.state()["state"]["homes"][0]["address"], "에이네 집")

    def test_health_info_needs_detection_target(self):
        a = self.member("가족에이")
        status, _, _ = a.call("POST", "/api/v2/me/profile", {"name": "가족에이", "birth": "1951-07-08"})
        self.assertEqual(status, 409)
        status, _, data = self.setup(a, {"birth": "2999-01-01"})
        self.assertEqual((status, data["field"]), (400, "birth"))

    def test_new_endpoints_need_login_and_same_origin(self):
        anonymous = Browser(self.server)
        for path, body in (("/api/v2/me/profile", {"name": "누구"}), ("/api/v2/me/prefs", {"key": "home", "value": False}),
                           ("/api/v2/me/setup", {"info": {}, "home": {"mode": "new"}}), ("/api/v2/homes/h_x/link", None),
                           ("/api/v2/homes/h_x/unlink", None), ("/api/v2/homes/h_x/address", {"address": "서울"}),
                           ("/api/v2/me/withdraw", {"password": PW})):
            self.assertEqual(anonymous.call("POST", path, body)[0], 401, path)
        a = self.member("가족에이")
        a.origin = False   # Browser 가 자기 주소의 Origin 을 덮어쓰지 않도록
        status, _, _ = a.call("POST", "/api/v2/me/profile", {"name": "외부"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.me(a)["name"], "가족에이")
        # 기존 공용 토큰으로는 새 기능을 쓸 수 없음
        self.assertEqual(self.server.request("POST", "/api/v2/me/withdraw", {"password": PW}, token=self.server.token)[0], 401)

    def test_withdraw(self):
        a = self.member("가족에이")
        b = self.member("가족비", self.code(a))
        home_id = self.setup(a)[2]["state"]["homes"][0]["id"]
        self.setup(b, home={"mode": "existing", "id": home_id})
        status, _, data = a.call("POST", "/api/v2/me/withdraw", {"password": "wrong999"})
        self.assertEqual((status, data["field"]), (401, "password"))
        cookie = a.cookie
        status, headers, data = a.call("POST", "/api/v2/me/withdraw", {"password": PW})
        self.assertEqual(status, 200, data)
        self.assertFalse(data["authenticated"])
        self.assertIsNone(a.cookie)                        # 쿠키 삭제
        stale = Browser(self.server)
        stale.cookie = cookie
        self.assertFalse(stale.state()["authenticated"])   # 예전 쿠키로도 로그인 안 됨
        state_b = b.state()["state"]
        self.assertEqual([p["name"] for p in state_b["people"]], ["가족비"])
        self.assertEqual([h["id"] for h in state_b["homes"]], [home_id])

    def test_old_event_api_still_works(self):
        event_id = uuid.uuid4().hex
        status, _, _ = self.server.request("POST", "/api/events", {
            "event_id": event_id, "device_id": "unittest", "fall_type": "slip_and_fall", "is_test": True},
            token=self.server.token)
        self.assertEqual(status, 200)
        self.assertEqual(self.server.request("GET", f"/api/events/{event_id}", token=self.server.token)[0], 200)


if __name__ == "__main__":
    unittest.main()
