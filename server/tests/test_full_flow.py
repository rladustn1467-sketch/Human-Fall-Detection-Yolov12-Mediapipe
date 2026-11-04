"""The whole service in one run, on a copy of the server with a virtual device (tools/virtual_device.py):
register, pair, start, fall, incident, photo, family alert, response, device off, device deleted.

This proves the server's part of the flow. It does not prove that a real phone works: camera, background limits,
battery and real networks are checked on a real phone only (docs/DEVICE_HTTPS_READINESS.md).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import sqlite3
import sys
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from virtual_device import VirtualDevice  # noqa: E402

from tests.test_api_v2 import ServerCopy  # noqa: E402
from tests.test_auth_api import PW, Browser  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + bytes(300) + b"\xff\xd9"


class FakeFcm(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        FakeFcm.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"name": "fake"}')

    def log_message(self, *args):
        pass


class FullFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeFcm.received = []
        cls.fcm = HTTPServer(("127.0.0.1", 0), FakeFcm)
        threading.Thread(target=cls.fcm.serve_forever, daemon=True).start()
        cls.server = ServerCopy(extra_env={"PUSH_FAKE_URL": f"http://127.0.0.1:{cls.fcm.server_port}/send"})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.fcm.shutdown()

    def person(self, name, code=None):
        b = Browser(self.server)
        b.phone = "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": b.phone, "password": PW})
        self.assertEqual(status, 200, data)
        b.id = data["me_id"]
        if code:
            self.assertEqual(b.call("POST", "/api/v2/groups/join", {"code": code})[0], 200)
        else:
            b.call("POST", "/api/v2/groups")
        return b

    def sql(self, statement, *args):
        c = sqlite3.connect(self.server.db_path, timeout=10)
        try:
            rows = c.execute(statement, args).fetchall()
            c.commit()
            return rows
        finally:
            c.close()

    def wait(self, condition, seconds=8):
        import time
        end = time.time() + seconds
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.2)
        return condition()

    def texts(self, who):
        return [n["text"] for n in who.state()["state"]["notifs"]]

    def test_from_pairing_to_the_device_being_deleted(self):
        base = f"http://127.0.0.1:{self.server.port}"
        target = self.person("대상자에이")
        code = target.state()["state"]["groups"][0]["invite"]["code"]
        home = target.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})[2]["state"]["homes"][0]["id"]
        family = self.person("가족비", code)
        family.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        stranger = self.person("다른집씨")

        # 1. 감지 기기 등록: 앱에서 연결 코드를 받음
        status, _, data = target.call("POST", f"/api/v2/homes/{home}/devices/pairing", {"type": "phone", "location": "거실"})
        self.assertEqual(status, 200, data)

        # 2. 기기 인증: 코드는 한 번만, 토큰이 없으면 거절
        device = VirtualDevice(base)
        self.assertEqual(device.pair("WRONG1")[0], 400)
        self.assertEqual(device.pair(data["pairing"]["code"])[0], 200)
        self.assertEqual(VirtualDevice(base).pair(data["pairing"]["code"])[0], 400)
        self.assertEqual(VirtualDevice(base, "no-such-token").heartbeat()[0], 401)

        # 3. 감지 시작: 상태 신호가 오면 가족 화면에 정상으로 보임
        self.assertEqual(device.heartbeat()[0], 200)
        self.assertEqual(family.state()["state"]["devices"][0]["status"], "ok")

        # 4~5. 가상 낙상 → 서버 수신 (같은 이벤트를 다시 보내도 사고는 하나)
        event = uuid.uuid4().hex
        status, fall = device.fall(JPEG, event_id=event)
        self.assertEqual((status, fall["image_saved"]), (200, True), fall)
        self.assertEqual(device.fall(JPEG, event_id=event)[1]["incident_id"], fall["incident_id"])

        # 6. 사고 기록: 처음에는 감지 대상자만 응답 대기
        iid = fall["incident_id"]
        incident = next(i for i in target.state()["state"]["incidents"] if i["id"] == iid)
        self.assertEqual((incident["status"], incident["location"]), ("detected", "거실"))

        # 7. 사진: 같은 그룹만 볼 수 있음
        photo = incident["photos"][0]["id"]
        path = f"/api/v2/incidents/{iid}/photos/{photo}.jpg"
        self.assertEqual(family.call("GET", path)[0], 200)
        self.assertEqual(stranger.call("GET", path)[0], 404)

        # 8. 가족 알림: 60초 동안 응답이 없으면 앱 알림과 푸시 (시험 DB 의 시각을 앞당김)
        self.sql("UPDATE incidents SET detected_at = detected_at - 61000 WHERE id = ?", iid)
        self.assertTrue(self.wait(lambda: any("응답이 없어요" in t for t in self.texts(family))))
        self.assertTrue(self.wait(lambda: self.sql(
            "SELECT status FROM push_deliveries WHERE incident_id = ? AND kind = 'family_alert' AND user_id = ?", iid, family.id)
            in ([("no_token",)], [("simulated",)])))

        # 9. 알림 확인과 대응: 가족이 맡아서 종료
        self.assertEqual(family.call("POST", f"/api/v2/incidents/{iid}/take-over")[0], 200)
        self.assertEqual(family.call("POST", f"/api/v2/incidents/{iid}/close")[0], 200)
        done = next(i for i in target.state()["state"]["incidents"] if i["id"] == iid)
        self.assertEqual((done["status"], done["result"]), ("closed", "family"))
        self.assertTrue(any("종료" in t for t in self.texts(target)))

        # 10. 감지 중단: 로그아웃한 폰이 보내는 꺼짐 요청 뒤에는 낙상이 사고가 되지 않고, 기기를 지우면 토큰이 막힘
        self.assertEqual(device.enabled(False)[0], 200)
        self.assertEqual(family.state()["state"]["devices"][0]["status"], "off")
        self.assertEqual(device.fall(JPEG)[1].get("ignored"), "off")
        self.assertEqual(len(target.state()["state"]["incidents"]), 1)
        self.assertEqual(target.call("DELETE", f"/api/v2/devices/{device.device_id}")[0], 200)
        self.assertEqual(device.heartbeat()[0], 401)


if __name__ == "__main__":
    unittest.main()
