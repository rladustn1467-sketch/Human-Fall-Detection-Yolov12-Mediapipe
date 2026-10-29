"""Photos of ended incidents are deleted 14 days after the incident ended (closed or reported); photos of open
incidents, including those a family member is checking ('checking'), stay. Runs on a COPY of the server with the
retention shortened to 2 seconds and the cleanup run every second (PHOTO_RETENTION_DAYS, PHOTO_CLEANUP_SECONDS).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import json
import time
import unittest
import uuid

import db
import legacy_devices
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser

JPEG = b"\xff\xd8\xff\xe0" + b"R" * 64 + b"\xff\xd9"
SHORT = {"PHOTO_RETENTION_DAYS": str(2 / 86400), "PHOTO_CLEANUP_SECONDS": "1"}


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


class PhotoRetentionApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy(extra_env=SHORT)
        cls.a = Browser(cls.server)
        assert cls.a.call("POST", "/api/v2/auth/signup", {"name": "대상에이", "phone": phone(), "password": PW})[0] == 200
        cls.a.call("POST", "/api/v2/groups")
        cls.a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        cls.home = cls.a.state()["state"]["homes"][0]["id"]
        with db.session(cls.server.db_path) as conn:
            legacy_devices.add(conn, "pc-incident", cls.home, "거실", "incident")
        status, _, data = cls.a.call("POST", f"/api/v2/homes/{cls.home}/devices/pairing", {"type": "phone", "location": "안방"})
        assert status == 200, data
        status, _, text = cls.server.request("POST", "/api/v2/device/pair",
                                             {"code": data["pairing"]["code"], "appVersion": "test-1"})
        assert status == 200, text
        cls.device_token = json.loads(text)["deviceToken"]

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def incident(self, iid):
        return next(i for i in self.a.state()["state"]["incidents"] if i["id"] == iid)

    def wait_until(self, check, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            if check():
                return True
            time.sleep(0.3)
        return check()

    def self_ok(self, iid):
        status, _, data = self.a.call("POST", f"/api/v2/incidents/{iid}/self-ok")
        self.assertEqual(status, 200, data)

    def test_old_event_photo_of_a_closed_incident(self):
        # 운영 노트북과 같은 경로: /api/events (incident 방식 기기) → 사고 + 사진 (사진 이름 = event_id)
        event_id = uuid.uuid4().hex
        body = {"event_id": event_id, "device_id": "pc-incident", "fall_type": "slip_and_fall", "is_test": False,
                "image_jpeg_base64": base64.b64encode(JPEG).decode()}
        token = {"X-Access-Token": self.server.token}
        status, _, text = self.server.request("POST", "/api/events", body, headers=token)
        self.assertEqual(status, 200, text)
        iid = json.loads(text)["incident_id"]
        path = self.server.dir / "images" / f"{event_id}.jpg"
        self.assertTrue(path.is_file())
        self.self_ok(iid)
        self.assertTrue(self.wait_until(lambda: not path.exists()), "끝난 사고의 사진 파일이 지워져야 함")
        self.assertEqual(self.incident(iid)["photos"], [])
        self.assertEqual(self.incident(iid)["status"], "closed")                      # 사고 기록은 남음
        self.assertEqual(self.server.request("GET", f"/images/{event_id}.jpg", headers=token)[0], 404)
        status, _, text = self.server.request("GET", f"/api/events/{event_id}", headers=token)
        self.assertEqual((status, json.loads(text).get("image")), (200, None))         # 옛 기록에서도 사진 없음

    def test_device_photo_stays_while_open_and_goes_after_close(self):
        status, _, text = self.server.request(
            "POST", "/api/v2/device/events",
            {"event_id": uuid.uuid4().hex, "fall_type": "slip_and_fall", "is_test": False,
             "image_jpeg_base64": base64.b64encode(JPEG).decode()},
            headers={"Authorization": f"Bearer {self.device_token}"})
        self.assertEqual(status, 200, text)
        iid = json.loads(text)["incident_id"]
        photo = self.incident(iid)["photos"][0]["id"]
        path = self.server.dir / "images" / f"{photo}.jpg"
        time.sleep(4)                                                                   # 보존 시간(2초)보다 오래
        self.assertTrue(path.is_file(), "진행 중인 사고의 사진은 남아야 함")
        self.assertEqual(self.a.call("GET", f"/api/v2/incidents/{iid}/photos/{photo}.jpg")[0], 200)
        self.self_ok(iid)
        self.assertTrue(self.wait_until(lambda: not path.exists()), "끝난 뒤 보존 시간이 지나면 지워져야 함")
        self.assertEqual(self.a.call("GET", f"/api/v2/incidents/{iid}/photos/{photo}.jpg")[0], 404)


if __name__ == "__main__":
    unittest.main()
