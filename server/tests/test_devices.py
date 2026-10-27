"""Detection devices connected from the app (devices.py): pairing code → device token → status signal → falls.

Runs on a COPY of the server without Telegram settings (nothing is sent anywhere). The 'device' here is this test
calling the device API exactly as a detector would (Authorization: Bearer <device token>).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import json
import sqlite3
import unittest
import uuid

import db
import legacy_devices
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser

DEV_DEVICES = {"FD_DEV_DEVICES": "1"}   # PC 감지 프로그램(개발 도구) 연결 코드도 발급되는 시험 서버

JPEG = b"\xff\xd8\xff\xe0" + b"S" * 64 + b"\xff\xd9"


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


def member(server, name):
    b = Browser(server)
    status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone(), "password": PW})
    assert status == 200, data
    b.id = data["me_id"]
    return b


class DeviceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy(extra_env=DEV_DEVICES)
        # 그룹 1: 에이(감지 대상, 집에 연결) + 비(가족, 집에 연결 안 됨) / 그룹 2: 씨
        cls.a = member(cls.server, "대상에이")
        cls.a.call("POST", "/api/v2/groups")
        cls.a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        st = cls.a.state()["state"]
        cls.home = st["homes"][0]["id"]
        cls.b = member(cls.server, "가족비")
        cls.b.call("POST", "/api/v2/groups/join", {"code": st["groups"][0]["invite"]["code"]})
        cls.b.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        cls.c = member(cls.server, "다른씨")
        cls.c.call("POST", "/api/v2/groups")
        cls.c.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        cls.c_home = cls.c.state()["state"]["homes"][0]["id"]

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def setUp(self):
        for inc in self.b.state()["state"]["incidents"]:
            if inc["status"] not in ("closed", "reported"):
                self.b.call("POST", f"/api/v2/incidents/{inc['id']}/report", {"targetIds": []})

    # ---- 도우미 ----
    def code(self, who=None, home=None, type_="pc", location="거실"):
        status, _, data = (who or self.a).call("POST", f"/api/v2/homes/{home or self.home}/devices/pairing",
                                               {"type": type_, "location": location})
        self.assertEqual(status, 200, data)
        return data["pairing"]

    def device(self, path, body, token=None):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        status, _, text = self.server.request("POST", f"/api/v2/device/{path}", body, headers=h)
        return status, (json.loads(text) if text.startswith("{") else text)

    def paired(self, **kw):
        status, data = self.device("pair", {"code": self.code(**kw)["code"], "appVersion": "test-1"})
        self.assertEqual(status, 200, data)
        return data

    def view(self, device_id, who=None):
        return next((d for d in (who or self.b).state()["state"]["devices"] if d["id"] == device_id), None)

    def sql(self, query, *args):
        c = sqlite3.connect(self.server.db_path)
        try:
            rows = c.execute(query, args).fetchall()
            c.commit()
            return rows
        finally:
            c.close()

    def fall(self, token, event_id=None, image=JPEG, is_test=False):
        body = {"event_id": event_id or uuid.uuid4().hex, "fall_type": "slip_and_fall", "is_test": is_test}
        if image is not None:
            body["image_jpeg_base64"] = base64.b64encode(image).decode()
        return self.device("events", body, token)

    # ---- 연결 코드 (앱) ----
    def test_pairing_code_rules(self):
        p = self.code()
        self.assertRegex(p["code"], r"^[A-HJ-NP-Z2-9]{6}$")
        self.assertEqual((p["type"], p["location"]), ("pc", "거실"))
        anon = Browser(self.server)
        self.assertEqual(anon.call("POST", f"/api/v2/homes/{self.home}/devices/pairing", {"type": "pc", "location": "거실"})[0], 401)
        status, _, data = self.b.call("POST", f"/api/v2/homes/{self.home}/devices/pairing", {"type": "pc", "location": "거실"})
        self.assertEqual((status, data["field"]), (403, "home"))                 # 집에 연결 안 된 가족
        self.assertEqual(self.c.call("POST", f"/api/v2/homes/{self.home}/devices/pairing",
                                     {"type": "pc", "location": "거실"})[0], 404)   # 다른 그룹의 집
        for body, field in (({"type": "homecam", "location": "거실"}, "type"), ({"type": "pc", "location": ""}, "location")):
            status, _, data = self.a.call("POST", f"/api/v2/homes/{self.home}/devices/pairing", body)
            self.assertEqual((status, data["field"]), (400, field), body)
        self.assertTrue(self.a.state()["state"]["features"]["devDevices"])        # 화면도 개발용 항목을 보여 줌

    # ---- 연결 (기기) ----
    def test_pair_once_and_token_is_only_hashed(self):
        p = self.code(type_="phone", location="안방")
        status, data = self.device("pair", {"code": p["code"].lower()})              # 대소문자 상관없음
        self.assertEqual(status, 200, data)
        self.assertEqual((data["type"], data["location"], data["heartbeatSeconds"]), ("phone", "안방", 60))
        token = data["deviceToken"]
        self.assertGreater(len(token), 30)
        self.assertEqual(self.device("pair", {"code": p["code"]})[0], 400)          # 한 번만
        stored = self.sql("SELECT token_hash FROM devices WHERE id = ?", data["deviceId"])[0][0]
        self.assertNotEqual(stored, token)
        for path in (self.server.db_path, self.server.db_path.with_name(self.server.db_path.name + "-wal")):
            if path.exists():
                self.assertNotIn(token.encode(), path.read_bytes())                 # DB(·WAL) 에 토큰 그대로 없음
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, token)[0], 200)

    def test_expired_and_wrong_codes(self):
        p = self.code()
        self.sql("UPDATE device_pairings SET expires_at = 0 WHERE code = ?", p["code"])
        status, data = self.device("pair", {"code": p["code"]})
        self.assertEqual((status, data["field"]), (400, "code"))
        self.assertIn("만료", data["message"])
        self.assertEqual(self.device("pair", {"code": "ZZZZZZ"})[0], 400)
        self.assertEqual(self.device("pair", {})[0], 400)

    # ---- 상태 신호와 화면 상태 ----
    def test_status_from_signals(self):
        d = self.paired()
        v = self.view(d["deviceId"])
        self.assertEqual((v["status"], v["problem"], v["lastSeenAt"], v["type"], v["homeId"]),
                         ("disconnected", "never", None, "pc", self.home))         # 아직 신호 없음
        status, hb = self.device("heartbeat", {"cameraOk": True, "appVersion": "pc-1.0"}, d["deviceToken"])
        self.assertEqual((status, hb["enabled"], hb["location"]), (200, True, "거실"))
        v = self.view(d["deviceId"])
        self.assertEqual((v["status"], v["problem"]), ("ok", None))
        self.device("heartbeat", {"cameraOk": False}, d["deviceToken"])
        self.assertEqual((self.view(d["deviceId"])["status"], self.view(d["deviceId"])["problem"]), ("disconnected", "camera"))
        self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])
        self.sql("UPDATE devices SET last_seen_at = last_seen_at - 181000 WHERE id = ?", d["deviceId"])   # 3분 넘게 신호 없음
        v = self.view(d["deviceId"])
        self.assertEqual((v["status"], v["problem"]), ("disconnected", "offline"))
        self.assertIsNone(self.view(d["deviceId"], self.c))                         # 다른 그룹에는 안 보임

    def test_device_auth(self):
        d = self.paired()
        self.assertEqual(self.device("heartbeat", {"cameraOk": True})[0], 401)                      # 토큰 없음
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, "x" + d["deviceToken"])[0], 401)
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, self.server.token)[0], 401)   # 공용 토큰은 안 됨
        self.assertEqual(self.device("heartbeat", {"cameraOk": "yes"}, d["deviceToken"])[0], 400)
        self.assertEqual(self.fall(None)[0], 401)

    # ---- 낙상 ----
    def test_fall_creates_incident_with_photo(self):
        d = self.paired(location="안방")
        event_id = uuid.uuid4().hex
        status, res = self.fall(d["deviceToken"], event_id)
        self.assertEqual((status, res["image_saved"]), (200, True), res)
        again = self.fall(d["deviceToken"], event_id)[1]                             # 기기 재시도
        self.assertEqual(again["incident_id"], res["incident_id"])
        inc = next(i for i in self.b.state()["state"]["incidents"] if i["id"] == res["incident_id"])
        self.assertEqual((inc["source"], inc["location"], inc["homeId"], inc["status"]), ("device", "안방", self.home, "detected"))
        self.assertEqual(len(inc["photos"]), 1)
        photo = inc["photos"][0]["id"]
        self.assertNotEqual(photo, event_id)                                         # 사진 이름은 서버가 기기별로 정함
        status, headers, text = self.b.call("GET", f"/api/v2/incidents/{inc['id']}/photos/{photo}.jpg")
        self.assertEqual((status, headers["content-type"]), (200, "image/jpeg"))
        self.assertEqual(self.c.call("GET", f"/api/v2/incidents/{inc['id']}/photos/{photo}.jpg")[0], 404)
        self.assertIsNotNone(self.view(d["deviceId"])["lastSeenAt"])                 # 낙상도 살아 있다는 신호

    def test_same_event_id_from_two_devices_never_shares_a_photo(self):
        d1, d2 = self.paired(), self.paired(location="안방")
        event_id = uuid.uuid4().hex
        r1, r2 = self.fall(d1["deviceToken"], event_id)[1], self.fall(d2["deviceToken"], event_id, image=JPEG[:-2] + b"Q\xff\xd9")[1]
        self.assertEqual(r1["incident_id"], r2["incident_id"])                       # 같은 집의 진행 중 사고에 기록
        photos = [p["id"] for p in next(i for i in self.b.state()["state"]["incidents"] if i["id"] == r1["incident_id"])["photos"]]
        self.assertEqual(len(set(photos)), 2)

    def test_fall_without_or_with_bad_photo(self):
        d = self.paired()
        res = self.fall(d["deviceToken"], image=None)[1]
        self.assertEqual((bool(res["incident_id"]), res["image_saved"]), (True, False))
        self.setUp()
        res = self.fall(d["deviceToken"], image=b"not a jpeg")[1]
        self.assertEqual((bool(res["incident_id"]), res["image_saved"]), (True, False))

    def test_test_fall_only_records_time(self):
        d = self.paired()
        before = (len(self.b.state()["state"]["incidents"]), self.sql("SELECT COUNT(*) FROM notifications")[0][0],
                  self.sql("SELECT COUNT(*) FROM incident_photos")[0][0])
        status, res = self.fall(d["deviceToken"], is_test=True)
        self.assertEqual((status, res), (200, {"ok": True, "test": True}))
        after = (len(self.b.state()["state"]["incidents"]), self.sql("SELECT COUNT(*) FROM notifications")[0][0],
                 self.sql("SELECT COUNT(*) FROM incident_photos")[0][0])
        self.assertEqual(after, before)                                               # 사고·알림·사진 없음
        self.assertIsNotNone(self.view(d["deviceId"])["lastTestAt"])

    def test_device_turns_itself_off_and_on(self):
        # 기기 화면의 켜기/끄기: 앱과 같은 값 (앱에서 보면 꺼짐/정상, 다음 상태 신호도 같은 값)
        d = self.paired()
        self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])
        status, res = self.device("enabled", {"enabled": False}, d["deviceToken"])
        self.assertEqual((status, res["enabled"]), (200, False))
        self.assertEqual(self.view(d["deviceId"])["status"], "off")
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])[1]["enabled"], False)
        self.assertEqual(self.device("enabled", {"enabled": "no"}, d["deviceToken"])[0], 400)
        self.assertEqual(self.device("enabled", {"enabled": True})[0], 401)                     # 토큰 없음
        self.assertEqual(self.device("enabled", {"enabled": True}, d["deviceToken"])[1]["enabled"], True)
        self.assertEqual(self.view(d["deviceId"])["status"], "ok")

    # ---- 켜기/끄기 · 위치 · 삭제 (앱) ----
    def test_turn_off_and_on(self):
        d = self.paired()
        self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])
        self.assertEqual(self.b.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"enabled": False})[0], 403)
        self.assertEqual(self.a.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"enabled": "no"})[0], 400)
        self.assertEqual(self.a.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"enabled": False})[0], 200)
        self.assertEqual(self.view(d["deviceId"])["status"], "off")
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])[1]["enabled"], False)   # 기기에 알림
        before = len(self.b.state()["state"]["incidents"])
        self.assertEqual(self.fall(d["deviceToken"])[1], {"ok": True, "ignored": "off"})
        self.assertEqual(len(self.b.state()["state"]["incidents"]), before)
        self.a.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"enabled": True})
        self.assertEqual(self.view(d["deviceId"])["status"], "ok")

    def test_rename(self):
        d = self.paired()
        status, _, data = self.a.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"location": "작은방"})
        self.assertEqual(status, 200, data)
        self.assertEqual(self.view(d["deviceId"])["location"], "작은방")
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])[1]["location"], "작은방")
        self.assertEqual(self.a.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"location": ""})[0], 400)
        self.assertEqual(self.c.call("PATCH", f"/api/v2/devices/{d['deviceId']}", {"location": "x"})[0], 404)

    def test_delete_revokes_the_token(self):
        d = self.paired()
        self.assertEqual(self.b.call("DELETE", f"/api/v2/devices/{d['deviceId']}")[0], 403)
        self.assertEqual(self.c.call("DELETE", f"/api/v2/devices/{d['deviceId']}")[0], 404)
        self.assertEqual(self.a.call("DELETE", f"/api/v2/devices/{d['deviceId']}")[0], 200)
        self.assertIsNone(self.view(d["deviceId"]))
        self.assertEqual(self.device("heartbeat", {"cameraOk": True}, d["deviceToken"])[0], 401)
        self.assertEqual(self.fall(d["deviceToken"])[0], 401)

    # ---- 기존 방식 호환 ----
    def test_shared_token_api_and_admin_registration_still_work(self):
        body = {"event_id": uuid.uuid4().hex, "device_id": "pc-old", "fall_type": "slip_and_fall", "is_test": False}
        status, _, text = self.server.request("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        self.assertEqual((status, json.loads(text)["incident_id"]), (200, None))      # 미등록 기기: 옛 흐름만
        with db.session(self.server.db_path) as conn:
            legacy_devices.add(conn, "pc-registered", self.home, "거실", "incident")
        body = dict(body, event_id=uuid.uuid4().hex, device_id="pc-registered")
        status, _, text = self.server.request("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(text)["incident_id"])                             # 관리자 등록: 새 사고


class PairingLimitTest(unittest.TestCase):
    """Wrong pairing codes are limited per address (own server copy, so other tests are not blocked)."""

    def test_product_server_has_no_dev_devices(self):
        """Without FD_DEV_DEVICES (production): no pairing code for the PC program, phones as usual."""
        server = ServerCopy(extra_env={"FD_DEV_DEVICES": ""})
        try:
            a = member(server, "대상에이")
            a.call("POST", "/api/v2/groups")
            a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
            st = a.state()["state"]
            home = st["homes"][0]["id"]
            self.assertFalse(st["features"]["devDevices"])
            self.assertFalse(Browser(server).state()["state"]["features"]["devDevices"])   # 로그인 전에도
            path = f"/api/v2/homes/{home}/devices/pairing"
            for type_ in ("pc", "homecam", "cctv"):
                status, _, data = a.call("POST", path, {"type": type_, "location": "거실"})
                self.assertEqual((status, data["field"]), (400, "type"), type_)
            status, _, data = a.call("POST", path, {"type": "phone", "location": "거실"})
            self.assertEqual((status, data["pairing"]["type"]), (200, "phone"))
        finally:
            server.close()

    def test_too_many_wrong_codes(self):
        server = ServerCopy()
        try:
            a = member(server, "대상에이")
            a.call("POST", "/api/v2/groups")
            a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
            home = a.state()["state"]["homes"][0]["id"]
            for _ in range(10):
                self.assertEqual(server.request("POST", "/api/v2/device/pair", {"code": "WRONG2"})[0], 400)
            good = a.call("POST", f"/api/v2/homes/{home}/devices/pairing", {"type": "phone", "location": "거실"})[2]["pairing"]["code"]
            status, headers, _ = server.request("POST", "/api/v2/device/pair", {"code": good})
            self.assertEqual(status, 429)                                            # 맞는 코드도 잠시 막힘
            self.assertIn("retry-after", headers)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
