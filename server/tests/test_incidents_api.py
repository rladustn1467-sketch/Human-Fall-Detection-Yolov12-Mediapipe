"""Fall incidents over HTTP on a COPY of the server (D stage): developer fall switch, actions, permissions,
concurrent presses, notifications and the old /api/events bridge. Telegram is off in the copy (no messages).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import threading
import unittest
import uuid

import db
import legacy_devices
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


def member(server, name, code=None, target=False):
    b = Browser(server)
    status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone(), "password": PW})
    assert status == 200, data
    b.id = data["me_id"]
    if code:
        assert b.call("POST", "/api/v2/groups/join", {"code": code})[0] == 200
    else:
        assert b.call("POST", "/api/v2/groups")[0] == 200
    if target:
        status, _, data = b.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        assert status == 200, data
    return b


class DevSwitchOffTest(unittest.TestCase):
    def test_developer_fall_is_refused_without_the_switch(self):
        server = ServerCopy()
        try:
            a = member(server, "운영에이", target=True)
            home = a.state()["state"]["homes"][0]["id"]
            status, _, data = a.call("POST", "/api/v2/dev/falls", {"homeId": home, "location": "거실"})
            self.assertEqual(status, 404)
            self.assertEqual(a.state()["state"]["incidents"], [])
        finally:
            server.close()


class IncidentApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy(extra_env={"FD_DEV_TOOLS": "1"})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def setUp(self):
        self.a = member(self.server, "대상에이", target=True)
        code = self.a.state()["state"]["groups"][0]["invite"]["code"]
        self.b = member(self.server, "가족비", code)
        self.d = member(self.server, "가족디", code)
        self.c = member(self.server, "남씨", target=True)                  # 다른 그룹
        self.home = self.a.state()["state"]["homes"][0]["id"]

    def fall(self, ago=0, who=None):
        status, _, data = (who or self.a).call("POST", "/api/v2/dev/falls",
                                               {"homeId": self.home, "location": "거실", "agoSeconds": ago})
        self.assertEqual(status, 200, data)
        return next(i for i in data["state"]["incidents"] if i["status"] not in ("closed", "reported"))

    def act(self, who, iid, action, body=None):
        return who.call("POST", f"/api/v2/incidents/{iid}/{action}", body)

    def test_flow_take_over_close_and_state(self):
        inc = self.fall(ago=61)                                                  # 이미 60초 지남 → 가족 알림
        self.assertEqual(inc["status"], "no_response")
        self.assertIn("serverNow", self.b.state()["state"])
        seen_b = self.b.state()["state"]
        self.assertEqual([n["kind"] for n in seen_b["notifs"] if n["incidentId"]], ["family_alert"])   # 사고 알림만
        self.assertFalse(seen_b["notifs"][0]["read"])
        self.assertEqual(self.act(self.a, inc["id"], "take-over")[0], 403)      # 낙상 대상자
        status, _, data = self.act(self.b, inc["id"], "take-over")
        self.assertEqual(status, 200, data)
        mine = next(i for i in data["state"]["incidents"] if i["id"] == inc["id"])
        self.assertEqual((mine["status"], mine["checkedBy"]), ("checking", self.b.id))
        status, _, data = self.act(self.d, inc["id"], "take-over")
        self.assertEqual((status, data["message"]), (409, "이미 다른 가족이 확인하고 있어요."))
        self.assertEqual(self.act(self.b, inc["id"], "close")[0], 200)
        # 읽음 표시
        status, _, data = self.b.call("POST", "/api/v2/notifications/read")
        self.assertEqual(status, 200)
        self.assertTrue(all(n["read"] for n in data["state"]["notifs"]))

    def test_self_ok_help_report_and_permissions(self):
        inc = self.fall()
        self.assertEqual(self.act(self.b, inc["id"], "self-ok")[0], 403)
        self.assertEqual(self.act(self.c, inc["id"], "self-ok")[0], 404)        # 다른 그룹 = 없는 사고
        self.assertEqual(self.act(self.c, inc["id"], "report", {"targetIds": []})[0], 404)
        self.assertEqual(self.act(self.c, inc["id"], "dismiss")[0], 404)
        self.assertNotIn(inc["id"], [i["id"] for i in self.c.state()["state"]["incidents"]])
        status, _, data = self.act(self.a, inc["id"], "help")
        self.assertEqual(status, 200, data)
        mine = next(i for i in data["state"]["incidents"] if i["id"] == inc["id"])
        self.assertEqual((mine["status"], len(mine["helpTimes"])), ("help", 1))
        self.assertEqual(self.act(self.b, inc["id"], "report", {"targetIds": [self.b.id]})[0], 400)   # 대상자 아님
        status, _, data = self.act(self.b, inc["id"], "report", {"targetIds": [self.a.id]})
        self.assertEqual(status, 200, data)
        mine = next(i for i in data["state"]["incidents"] if i["id"] == inc["id"])
        self.assertEqual((mine["status"], mine["reportKind"], mine["reportedTargetIds"]), ("reported", "simulation", [self.a.id]))
        status, _, data = self.act(self.d, inc["id"], "report", {"targetIds": []})
        self.assertEqual((status, data["message"]), (409, "이미 신고되었거나 종료된 사고예요."))
        self.assertEqual(self.act(self.a, inc["id"], "self-ok")[0], 409)
        self.assertEqual(self.act(self.b, inc["id"], "dismiss")[0], 200)
        self.assertEqual(self.act(self.b, "inc_nothing", "dismiss")[0], 404)

    def test_requests_from_other_sites_and_logged_out(self):
        inc = self.fall()
        evil = Browser(self.server, origin=False)          # 같은 로그인 쿠키, 다른 사이트에서 보낸 요청
        evil.cookie = self.a.cookie
        status, _, _ = evil.call("POST", f"/api/v2/incidents/{inc['id']}/self-ok", headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.a.state()["state"]["incidents"][0]["status"], "detected")
        anon = Browser(self.server)
        self.assertEqual(anon.call("POST", f"/api/v2/incidents/{inc['id']}/self-ok")[0], 401)
        self.assertEqual(anon.call("POST", "/api/v2/dev/falls", {"homeId": self.home})[0], 401)
        self.assertEqual(self.c.call("POST", "/api/v2/dev/falls", {"homeId": self.home})[0], 404)   # 다른 그룹 집
        self.assertEqual(self.a.call("POST", "/api/v2/dev/falls", {"homeId": self.home, "agoSeconds": 9999})[0], 400)
        self.assertEqual(self.act(self.a, inc["id"], "self-ok")[0], 200)

    def test_concurrent_take_over_over_http(self):
        inc = self.fall(ago=61)
        barrier = threading.Barrier(2)
        results = {}

        def press(who):
            barrier.wait()
            results[who.id] = self.act(who, inc["id"], "take-over")[0]

        threads = [threading.Thread(target=press, args=(w,)) for w in (self.b, self.d)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results.values()), [200, 409], results)
        winner = next(k for k, v in results.items() if v == 200)
        state = self.a.state()["state"]
        self.assertEqual(next(i for i in state["incidents"] if i["id"] == inc["id"])["checkedBy"], winner)
        self.assertEqual(self.act(self.server_user(winner), inc["id"], "close")[0], 200)

    def server_user(self, uid):
        return self.b if self.b.id == uid else self.d

    def test_old_api_bridge_only_for_registered_device(self):
        token_headers = {"X-Access-Token": self.server.token}
        dev = f"pc-{uuid.uuid4().hex[:6]}"
        event = {"device_id": dev, "fall_type": "slip_and_fall", "is_test": False, "event_id": uuid.uuid4().hex}
        status, _, text = self.server.request("POST", "/api/events", event, headers=token_headers)
        self.assertEqual(status, 200, text)
        self.assertIn('"incident_id":null', text.replace(" ", ""))                       # 등록 안 된 기기
        self.assertEqual(self.b.state()["state"]["incidents"], [])
        with db.session(self.server.db_path) as conn:                                   # 관리자 등록
            legacy_devices.add(conn, dev, self.home, "안방")
        test_event = dict(event, event_id=uuid.uuid4().hex, is_test=True)
        self.server.request("POST", "/api/events", test_event, headers=token_headers)
        self.assertEqual(self.b.state()["state"]["incidents"], [])                      # 시험 이벤트는 사고 아님
        real = dict(event, event_id=uuid.uuid4().hex)
        self.server.request("POST", "/api/events", real, headers=token_headers)
        self.server.request("POST", "/api/events", real, headers=token_headers)          # 재시도
        incs = self.b.state()["state"]["incidents"]
        self.assertEqual(len(incs), 1)
        self.assertEqual((incs[0]["source"], incs[0]["location"], incs[0]["status"]), ("legacy", "안방", "detected"))
        self.assertEqual(self.c.state()["state"]["incidents"], [])                      # 다른 그룹에는 없음
        status, _, _ = self.server.request("POST", "/api/events", dict(event, event_id=uuid.uuid4().hex))
        self.assertEqual(status, 401)                                                    # 토큰 없이는 안 됨


if __name__ == "__main__":
    unittest.main()
