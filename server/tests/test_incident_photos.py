"""Silhouette photos sent by a detector (/api/events) linked to the new incident, and shown only to the same group.

The photo is the privacy-processed JPEG the detector sends (the original never reaches the server). The server keeps
the file where it always did (images/{event_id}.jpg) and only stores which incident it belongs to.
Runs on a COPY of the server without Telegram settings (nothing is sent anywhere).

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

JPEG_A = b"\xff\xd8\xff\xe0" + b"A" * 64 + b"\xff\xd9"
JPEG_B = b"\xff\xd8\xff\xe0" + b"B" * 64 + b"\xff\xd9"


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


class IncidentPhotoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()
        # 그룹 1: 에이(감지 대상, 집) + 비(가족) / 그룹 2: 씨 (다른 가족)
        cls.a = cls.member("대상에이")
        cls.a.call("POST", "/api/v2/groups")
        cls.a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        st = cls.a.state()["state"]
        cls.home = st["homes"][0]["id"]
        cls.b = cls.member("가족비")
        cls.b.call("POST", "/api/v2/groups/join", {"code": st["groups"][0]["invite"]["code"]})
        cls.b.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        cls.c = cls.member("다른씨")
        cls.c.call("POST", "/api/v2/groups")
        with db.session(cls.server.db_path) as conn:
            legacy_devices.add(conn, "pc-incident", cls.home, "거실", "incident")

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    @classmethod
    def member(cls, name):
        b = Browser(cls.server)
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone(), "password": PW})
        assert status == 200, data
        return b

    def setUp(self):
        # 집마다 진행 중인 사고는 하나: 시험마다 새 사고가 생기게 앞 사고를 끝냄
        for inc in self.b.state()["state"]["incidents"]:
            if inc["status"] not in ("closed", "reported"):
                self.b.call("POST", f"/api/v2/incidents/{inc['id']}/report", {"targetIds": []})

    def post_fall(self, event_id, image=JPEG_A, device="pc-incident", is_test=False):
        """What dashboard_app.py sends (same keys, token header)."""
        body = {"event_id": event_id, "device_id": device, "fall_type": "slip_and_fall", "is_test": is_test}
        if image is not None:
            body["image_jpeg_base64"] = base64.b64encode(image).decode()
        status, _, text = self.server.request("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        self.assertEqual(status, 200, text)
        return json.loads(text)

    def incident(self, incident_id, who=None):
        return next(i for i in (who or self.b).state()["state"]["incidents"] if i["id"] == incident_id)

    def photo(self, incident_id, photo_id, who=None):
        return (who or self.b).call("GET", f"/api/v2/incidents/{incident_id}/photos/{photo_id}.jpg")

    def raw_photo(self, incident_id, photo_id, who):
        h = {"Cookie": f"fd_session={who.cookie}"} if who and who.cookie else {}
        return self.server.request("GET", f"/api/v2/incidents/{incident_id}/photos/{photo_id}.jpg", headers=h)

    def photo_rows(self):
        c = sqlite3.connect(self.server.db_path)
        try:
            return c.execute("SELECT photo_id, incident_id FROM incident_photos ORDER BY at").fetchall()
        finally:
            c.close()

    def test_photo_linked_and_served_to_the_group(self):
        event_id = uuid.uuid4().hex
        res = self.post_fall(event_id)
        self.assertEqual((res["image_saved"], bool(res["incident_id"])), (True, True))
        inc = self.incident(res["incident_id"])
        self.assertEqual([p["id"] for p in inc["photos"]], [event_id])
        self.assertIsInstance(inc["photos"][0]["at"], int)
        for who in (self.a, self.b):                                      # 감지 대상자와 가족 모두
            status, headers, text = self.raw_photo(res["incident_id"], event_id, who)
            self.assertEqual((status, headers["content-type"]), (200, "image/jpeg"))
            self.assertEqual(text, JPEG_A.decode("utf-8", "replace"))    # 기기가 보낸 실루엣 그대로
            self.assertEqual(headers["cache-control"], "private, no-cache")   # 로그아웃 뒤 브라우저 보관본도 안 보이게
        # 옛 화면의 사진 경로는 옛 이벤트 사진에는 그대로 열림
        status, _, text = self.server.request("GET", f"/images/{event_id}.jpg", headers={"X-Access-Token": self.server.token})
        self.assertEqual((status, text), (200, JPEG_A.decode("utf-8", "replace")))

    def test_retry_links_once(self):
        event_id = uuid.uuid4().hex
        first = self.post_fall(event_id)
        again = self.post_fall(event_id)                                  # PC 프로그램 재시도
        self.assertEqual((again["duplicate"], again["incident_id"]), (True, first["incident_id"]))
        self.assertEqual([p["id"] for p in self.incident(first["incident_id"])["photos"]], [event_id])

    def test_redetection_adds_a_second_photo_in_order(self):
        e1, e2 = uuid.uuid4().hex, uuid.uuid4().hex
        first = self.post_fall(e1, JPEG_A)
        second = self.post_fall(e2, JPEG_B)                              # 진행 중에 같은 집에서 다시 감지
        self.assertEqual(second["incident_id"], first["incident_id"])
        self.assertEqual([p["id"] for p in self.incident(first["incident_id"])["photos"]], [e1, e2])
        self.assertEqual(self.raw_photo(first["incident_id"], e2, self.b)[2], JPEG_B.decode("utf-8", "replace"))

    def test_fall_without_photo(self):
        res = self.post_fall(uuid.uuid4().hex, image=None)
        self.assertEqual(res["image_saved"], False)
        self.assertEqual(self.incident(res["incident_id"])["photos"], [])

    def test_both_mode_device_links_too(self):
        # 같은 그룹의 두 번째 집 (복사본 DB에 직접): 'both' 기기 사고가 첫 집의 사고와 섞이지 않게
        home2 = "h_" + uuid.uuid4().hex[:16]
        with db.session(self.server.db_path) as conn:
            with db.transaction(conn):
                conn.execute("""INSERT INTO homes (id, group_id, created_at, updated_at)
                                SELECT ?, group_id, 0, 0 FROM homes WHERE id = ?""", (home2, self.home))
            legacy_devices.add(conn, "pc-both", home2, "안방", "both")
        event_id = uuid.uuid4().hex
        res = self.post_fall(event_id, device="pc-both")
        self.assertTrue(res["incident_id"])
        self.assertEqual([p["id"] for p in self.incident(res["incident_id"])["photos"]], [event_id])

    def test_other_group_and_logged_out_cannot_see(self):
        event_id = uuid.uuid4().hex
        res = self.post_fall(event_id)
        self.assertEqual(self.photo(res["incident_id"], event_id, self.c)[0], 404)       # 다른 그룹 = 없는 것과 같음
        self.assertEqual(self.raw_photo(res["incident_id"], event_id, None)[0], 401)     # 로그인 안 함

    def test_only_photos_of_that_incident(self):
        e_old = uuid.uuid4().hex
        old = self.post_fall(e_old)
        self.setUp()                                                       # 앞 사고 종료 → 다음 낙상은 새 사고
        e_new = uuid.uuid4().hex
        new = self.post_fall(e_new)
        self.assertNotEqual(old["incident_id"], new["incident_id"])
        self.assertEqual(self.photo(new["incident_id"], e_old)[0], 404)  # 다른 사고의 사진 id
        unlinked = uuid.uuid4().hex                                       # 옛 흐름(미등록 기기) 사진: 사고에 없음
        self.assertIsNone(self.post_fall(unlinked, device="pc-unregistered")["incident_id"])
        self.assertEqual(self.photo(new["incident_id"], unlinked)[0], 404)
        for bad in ("..%2F..%2Fcopy", "ABC", "x" * 32):
            self.assertEqual(self.raw_photo(new["incident_id"], bad, self.b)[0], 404, bad)

    def test_missing_file_is_404(self):
        event_id = uuid.uuid4().hex
        res = self.post_fall(event_id)
        (self.server.dir / "images" / f"{event_id}.jpg").unlink()
        self.assertEqual(self.photo(res["incident_id"], event_id)[0], 404)

    def test_link_failure_keeps_the_incident(self):
        c = sqlite3.connect(self.server.db_path)
        c.execute("CREATE TRIGGER block_photo BEFORE INSERT ON incident_photos BEGIN SELECT RAISE(ABORT, 'test'); END")
        c.commit()
        try:
            res = self.post_fall(uuid.uuid4().hex)
            self.assertTrue(res["incident_id"])                           # 사고와 알림은 그대로
            inc = self.incident(res["incident_id"])
            self.assertEqual((inc["status"], inc["photos"]), ("detected", []))
        finally:
            c.execute("DROP TRIGGER block_photo")
            c.commit()
            c.close()

    def test_test_events_and_unregistered_devices_are_not_linked(self):
        before = self.photo_rows()
        self.assertIsNone(self.post_fall(uuid.uuid4().hex, is_test=True)["incident_id"])
        self.assertIsNone(self.post_fall(uuid.uuid4().hex, device="pc-unregistered")["incident_id"])
        self.assertEqual(self.photo_rows(), before)


if __name__ == "__main__":
    unittest.main()
