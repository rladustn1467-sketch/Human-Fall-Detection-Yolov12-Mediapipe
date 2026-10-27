"""The PC detector's app connection (dashboard/device_link.py) against a COPY of the server.

Pairing code, wrong codes, token saved outside the project and reused after a restart, status signals, the app's
detection on/off, falls with photos and retries, and the token refused after the device is deleted in the app.
No Telegram settings on the copy (nothing is sent anywhere).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from tests.test_api_v2 import ServerCopy, free_port
from tests.test_auth_api import PW, Browser

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard"))
import device_link  # noqa: E402

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"L" * 64 + b"\xff\xd9").decode()


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


class DeviceLinkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy(extra_env={"FD_DEV_DEVICES": "1"})   # PC 감지 프로그램 = 개발 도구 (시험 서버에서만 연결 코드)
        cls.events_url = f"http://127.0.0.1:{cls.server.port}/api/events"   # 대시보드가 가진 주소 그대로
        cls.a = Browser(cls.server)
        cls.a.call("POST", "/api/v2/auth/signup", {"name": "대상에이", "phone": phone(), "password": PW})
        cls.a.call("POST", "/api/v2/groups")
        cls.home = cls.a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})[2]["state"]["homes"][0]["id"]
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.state = str(Path(self.tmp.name) / f"{uuid.uuid4().hex}.json")   # 시험마다 새 저장 파일 (프로젝트 밖)
        for inc in self.a.state()["state"]["incidents"]:
            if inc["status"] not in ("closed", "reported"):
                self.a.call("POST", f"/api/v2/incidents/{inc['id']}/report", {"targetIds": []})

    def code(self, location="거실"):
        return self.a.call("POST", f"/api/v2/homes/{self.home}/devices/pairing", {"type": "pc", "location": location})[2]["pairing"]["code"]

    def link(self):
        return device_link.DeviceLink(self.events_url, state_path=self.state)

    def paired_link(self, location="거실"):
        link = self.link()
        ok, message = link.pair(self.code(location))
        self.assertTrue(ok, message)
        return link

    def device_view(self, device_id):
        return next((d for d in self.a.state()["state"]["devices"] if d["id"] == device_id), None)

    def test_unpaired_keeps_the_old_way(self):
        link = self.link()
        self.assertEqual((link.paired, link.revoked), (False, False))
        self.assertEqual(link.heartbeat(True), 60)                                   # 연결 전에는 아무것도 보내지 않음
        with self.assertRaises(device_link.DeviceRevoked):
            link.send_fall(uuid.uuid4().hex, "slip_and_fall", False)

    def test_wrong_and_used_codes(self):
        link = self.link()
        self.assertEqual(link.pair(""), (False, "연결 코드를 입력해 주세요."))
        ok, message = link.pair("ZZZZZZ")
        self.assertEqual((ok, message), (False, "연결 코드를 확인해 주세요."))
        code = self.code()
        self.assertTrue(link.pair(code.lower())[0])                                   # 소문자·공백도 받음
        self.assertEqual(self.link().pair(code)[1], "만료된 연결 코드예요. 앱에서 새 코드를 받아 주세요.")   # 한 번만
        self.assertFalse(Path(self.state).read_text(encoding="utf-8").count("ZZZZZZ"))

    def test_token_saved_outside_and_reused_after_restart(self):
        link = self.paired_link()
        saved = json.loads(Path(self.state).read_text(encoding="utf-8"))
        base = f"http://127.0.0.1:{self.server.port}"
        self.assertEqual(list(saved), [base])                                        # 서버 주소마다 따로
        self.assertTrue(saved[base]["deviceToken"])
        self.assertNotIn("deviceToken", json.dumps(link.info))                       # 화면에 보여 줄 정보에는 토큰 없음
        again = self.link()                                                          # 프로그램을 다시 켬
        self.assertTrue(again.paired)
        self.assertEqual(again.heartbeat(True), 60)
        other = device_link.DeviceLink(f"http://127.0.0.1:{free_port()}/api/events", state_path=self.state)
        self.assertFalse(other.paired)                                               # 다른 서버에는 이 토큰을 쓰지 않음
        self.assertIn("FallDetection", device_link.default_state_path())             # 기본 위치: 사용자 폴더 (프로젝트 밖)
        self.assertNotIn(str(Path(__file__).resolve().parents[2]), device_link.default_state_path())

    def test_status_signal_and_on_off_only_on_this_pc(self):
        link = self.paired_link()
        device_id = link.info["deviceId"]
        self.assertEqual(self.device_view(device_id)["problem"], "never")
        link.heartbeat(True)
        self.assertEqual(self.device_view(device_id)["status"], "ok")
        link.heartbeat(False)
        self.assertEqual(self.device_view(device_id)["problem"], "camera")
        status, _, _ = self.a.call("PATCH", f"/api/v2/devices/{device_id}", {"enabled": False})
        self.assertEqual(status, 403)                                                # 앱에서 끌 수 없음
        link.set_local(False)                                                        # 이 PC 에서 Stop
        link.heartbeat(False)
        self.assertEqual((link.server_on, self.device_view(device_id)["status"]), (False, "off"))
        link.set_local(True)                                                         # 이 PC 에서 Start
        self.a.call("PATCH", f"/api/v2/devices/{device_id}", {"location": "안방"})  # 위치 이름은 앱에서 바꿀 수 있음
        link.heartbeat(True)
        self.assertEqual((link.server_on, link.info["location"]), (True, "안방"))
        self.assertEqual(self.device_view(device_id)["status"], "ok")
        self.assertEqual(self.link().info["location"], "안방")                        # 바뀐 위치도 저장

    def test_fall_photo_retry_and_test_signal(self):
        link = self.paired_link(location="작은방")
        event_id = uuid.uuid4().hex
        first = link.send_fall(event_id, "slip_and_fall", False, JPEG)
        again = link.send_fall(event_id, "slip_and_fall", False, JPEG)              # 같은 event_id 재전송
        self.assertEqual((first["image_saved"], again["incident_id"]), (True, first["incident_id"]))
        inc = next(i for i in self.a.state()["state"]["incidents"] if i["id"] == first["incident_id"])
        self.assertEqual((inc["source"], inc["location"], len(inc["photos"])), ("device", "작은방", 1))
        self.assertEqual(link.send_fall(uuid.uuid4().hex, "slip_and_fall", True), {"ok": True, "test": True})

    def test_server_down_is_retried_then_reported(self):
        link = self.paired_link()
        saved = device_link.SEND_RETRY_DELAYS
        device_link.SEND_RETRY_DELAYS = (0, 0, 0)
        try:
            down = device_link.DeviceLink(f"http://127.0.0.1:{free_port()}/api/events", state_path=self.state)
            down._entry = dict(link._entry)                                          # 같은 기기, 꺼진 서버
            logs = []
            with self.assertRaises(RuntimeError):
                down.send_fall(uuid.uuid4().hex, "slip_and_fall", False, log=logs.append)
            self.assertEqual(len(logs), 3)                                           # 재시도 3번
            self.assertTrue(down.heartbeat(True) <= 10 and down.last_error)          # 끊김은 표시하고 곧 다시 시도
        finally:
            device_link.SEND_RETRY_DELAYS = saved

    def test_deleted_in_app_is_refused_and_remembered(self):
        link = self.paired_link()
        self.assertEqual(self.a.call("DELETE", f"/api/v2/devices/{link.info['deviceId']}")[0], 200)
        link.heartbeat(True)
        self.assertEqual((link.paired, link.revoked), (False, True))
        saved = Path(self.state).read_text(encoding="utf-8")
        self.assertNotIn("deviceToken", saved)                                       # 토큰은 지움
        restarted = self.link()
        self.assertEqual((restarted.paired, restarted.revoked), (False, True))       # 다시 켜도 '해제됨' 유지
        link2 = self.paired_link()                                                   # 새 코드로 다시 연결
        self.assertEqual((link2.paired, link2.revoked), (True, False))
        self.a.call("DELETE", f"/api/v2/devices/{link2.info['deviceId']}")
        with self.assertRaises(device_link.DeviceRevoked):
            link2.send_fall(uuid.uuid4().hex, "slip_and_fall", False, JPEG)          # 낙상 전송도 401 → 거절
        link2.forget()                                                               # 'PC에서 연결 해제'
        self.assertEqual((self.link().paired, self.link().revoked), (False, False))


if __name__ == "__main__":
    unittest.main()
