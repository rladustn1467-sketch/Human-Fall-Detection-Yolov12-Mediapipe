"""PC detector falls (old /api/events) per device mode, over HTTP on a COPY of the server connected to a FAKE
Telegram server on this computer (TELEGRAM_API_URL). No real Telegram message is sent.

  unregistered device  old flow only: old Telegram alert with guardian buttons, no incident
  'incident' device    one new incident only: old event handed over (no old timer / old Telegram / old report),
                       the incident's alerts go to Telegram as text without buttons
  'both' device        both flows (comparison)
  test events          old flow only ([테스트])

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import http.server
import json
import re
import sqlite3
import threading
import time
import unittest
import urllib.parse
import uuid

import db
import legacy_devices
from tests.test_api_v2 import ServerCopy, free_port
from tests.test_auth_api import PW, Browser

CHAT = "777"
TINY_JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9").decode()


class FakeTelegram:
    """Records sendMessage / sendPhoto calls. getUpdates waits a little and returns nothing (no button presses)."""

    def __init__(self):
        self.messages = []
        self.lock = threading.Lock()
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                method = self.path.rsplit("/", 1)[-1]
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if method == "getUpdates":
                    time.sleep(1)
                    return self.reply({"ok": True, "result": []})
                if "multipart" in (self.headers.get("Content-Type") or ""):   # sendPhoto: 글자 칸만 꺼냄
                    body = raw.decode("utf-8", "replace")
                    params = dict(re.findall(r'name="(chat_id|caption|reply_markup)"\r\n\r\n(.*?)\r\n--', body, re.S))
                else:
                    params = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8")).items()}
                markup = params.get("reply_markup") or ""
                with fake.lock:
                    fake.messages.append({"method": method, "text": params.get("text") or params.get("caption") or "",
                                          "buttons": bool(markup), "chat": params.get("chat_id"),
                                          # 옛 흐름의 보호자 버튼 ('확인했어요'·'119 신고해주세요')
                                          "guardian": '"ack:' in markup and '"call:' in markup})
                self.reply({"ok": True, "result": {"message_id": len(fake.messages)}})

            def reply(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        class Server(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass   # 시험이 끝날 때 끊긴 연결은 무시

        self.port = free_port()
        self.server = Server(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def count(self):
        with self.lock:
            return len(self.messages)

    def wait_quiet(self, quiet=3.0, limit=20.0):
        """Wait until no message arrived for `quiet` seconds (earlier tests' old-flow alerts are all sent)."""
        start, last, n = time.time(), time.time(), self.count()
        while time.time() - start < limit:
            time.sleep(0.5)
            if self.count() != n:
                n, last = self.count(), time.time()
            elif time.time() - last >= quiet:
                return

    def since(self, n):
        with self.lock:
            return list(self.messages[n:])

    def close(self):
        self.server.shutdown()


def phone():
    return "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]


class LegacyIncidentModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tg = FakeTelegram()
        # 옛 흐름 시간을 짧게: 응답 2초, 보호자 대기 3초 (새 사고 시간은 60/180초 그대로)
        cls.server = ServerCopy(extra_env={
            "TELEGRAM_BOT_TOKEN": "fake-token", "TELEGRAM_CHAT_ID": CHAT,
            "TELEGRAM_API_URL": f"http://127.0.0.1:{cls.tg.port}/bot{{token}}/{{method}}",
            "FALL_RESPONSE_TIMEOUT": "2", "GUARDIAN_WAIT_AFTER_TIMEOUT": "3", "GUARDIAN_WAIT_AFTER_HELP": "3"})
        # 가족: 에이(감지 대상, 집) + 비(가족)
        cls.a = cls.member("대상에이")
        cls.a.call("POST", "/api/v2/groups")
        cls.a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})
        st = cls.a.state()["state"]
        cls.group, cls.home = st["groups"][0]["id"], st["homes"][0]["id"]
        cls.b = cls.member("가족비")
        cls.b.call("POST", "/api/v2/groups/join", {"code": st["groups"][0]["invite"]["code"]})
        cls.b.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        with db.session(cls.server.db_path) as conn:
            legacy_devices.add_telegram(conn, cls.group, CHAT)       # 새 사고 알림도 같은 보호자 대화방으로

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.tg.close()

    @classmethod
    def member(cls, name):
        b = Browser(cls.server)
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone(), "password": PW})
        assert status == 200, data
        b.id = data["me_id"]
        return b

    def post_fall(self, device, event_id, is_test=False):
        """Exactly what dashboard_app.py sends (same address, token header, JSON keys)."""
        body = {"event_id": event_id, "device_id": device, "fall_type": "slip_and_fall", "is_test": is_test,
                "image_jpeg_base64": TINY_JPEG}
        status, _, text = self.server.request("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        self.assertEqual(status, 200, text)
        return json.loads(text)

    def legacy_event(self, event_id):
        status, _, text = self.server.request("GET", f"/api/events/{event_id}", headers={"X-Access-Token": self.server.token})
        return json.loads(text)

    def incidents(self):
        return self.b.state()["state"]["incidents"]

    def register(self, device, mode):
        with db.session(self.server.db_path) as conn:
            legacy_devices.add(conn, device, self.home, "거실", mode)

    def close_open_incidents(self):
        for inc in self.incidents():
            if inc["status"] not in ("closed", "reported"):
                self.b.call("POST", f"/api/v2/incidents/{inc['id']}/report", {"targetIds": []})

    def setUp(self):
        self.close_open_incidents()
        self.tg.wait_quiet()                  # 직전 시험의 알림(옛 흐름의 자동 신고 알림 등)이 다 나간 뒤 세기 시작

    def test_1_unregistered_device_keeps_old_flow(self):
        start, before = self.tg.count(), len(self.incidents())
        res = self.post_fall("laptop", uuid.uuid4().hex)
        self.assertEqual((res["ok"], res["image_saved"], res["incident_id"]), (True, True, None))
        time.sleep(4)                                                     # 옛 응답 2초 지남
        old = [m for m in self.tg.since(start) if m["guardian"]]
        self.assertEqual(len(old), 1, self.tg.since(start))               # 옛 무응답 알림 (사진 + 보호자 버튼)
        self.assertEqual(old[0]["method"], "sendPhoto")
        self.assertEqual(len(self.incidents()), before)                   # 새 사고 없음

    def test_2_incident_device_one_incident_no_old_telegram(self):
        self.register("pc-incident", "incident")
        start, before = self.tg.count(), len(self.incidents())
        event_id = uuid.uuid4().hex
        first = self.post_fall("pc-incident", event_id)
        retry1 = self.post_fall("pc-incident", event_id)                  # PC 프로그램 재시도
        retry2 = self.post_fall("pc-incident", event_id)
        self.assertTrue(first["incident_id"])
        self.assertEqual((retry1["duplicate"], retry1["incident_id"], retry2["incident_id"]),
                         (True, first["incident_id"], first["incident_id"]))
        self.assertEqual(first["image_saved"], True)
        self.assertEqual(len(self.incidents()), before + 1)              # 사고 하나
        ev = self.legacy_event(event_id)
        self.assertEqual((ev["status"], ev["status_label"], ev["remaining_seconds"], ev["alerts"]),
                         ("handed_over", "새 웹앱에서 처리", 0, []))
        time.sleep(6)                                                     # 옛 응답(2초)·보호자 대기(3초)가 지나도
        self.assertEqual(self.tg.since(start), [])                        # 옛 텔레그램 0건 (새 사고는 아직 60초 전)
        self.assertEqual(self.legacy_event(event_id)["alerts"], [])
        status, _, text = self.server.request("POST", f"/api/events/{event_id}/response", {"response": "help_needed"},
                                              headers={"X-Access-Token": self.server.token})
        self.assertEqual(status, 409, text)                               # 옛 응답으로 옛 흐름을 다시 시작하지 않음
        # 새 사고를 61초 전 감지로 당겨서 60초 무응답 → 텔레그램은 새 사고 알림 1건 (버튼 없음)
        c = sqlite3.connect(self.server.db_path)
        try:
            with c:
                c.execute("UPDATE incidents SET detected_at = detected_at - 61000 WHERE id = ?", (first["incident_id"],))
        finally:
            c.close()                                                     # 파일을 잡고 있지 않게
        time.sleep(3)
        got = self.tg.since(start)
        self.assertEqual(len(got), 1, got)
        self.assertEqual((got[0]["buttons"], got[0]["chat"]), (False, CHAT))
        self.assertIn("60초 동안 응답이 없어요", got[0]["text"])
        # 앱에서 확인 → 종료: 텔레그램 알림 각 1건, 옛 흐름 알림은 계속 0건
        iid = first["incident_id"]
        self.assertEqual(self.b.call("POST", f"/api/v2/incidents/{iid}/take-over")[0], 200)
        self.assertEqual(self.b.call("POST", f"/api/v2/incidents/{iid}/close")[0], 200)
        time.sleep(3)
        got = self.tg.since(start)
        self.assertEqual([("확인하고 있어요" in m["text"], "종료했어요" in m["text"]) for m in got[1:]],
                         [(True, False), (False, True)], got)
        self.assertTrue(all(not m["buttons"] for m in got))
        self.assertEqual(self.legacy_event(event_id)["status"], "handed_over")

    def test_3_test_event_keeps_old_test_flow(self):
        self.register("pc-incident", "incident")
        start, before = self.tg.count(), len(self.incidents())
        res = self.post_fall("pc-incident", uuid.uuid4().hex, is_test=True)
        self.assertIsNone(res["incident_id"])
        time.sleep(4)
        got = [m for m in self.tg.since(start) if m["guardian"]]
        self.assertEqual(len(got), 1, self.tg.since(start))
        self.assertTrue(got[0]["text"].startswith("[테스트]"), got[0]["text"][:40])
        self.assertEqual(len(self.incidents()), before)

    def test_4_both_mode_runs_both_flows(self):
        self.register("pc-both", "both")
        start, before = self.tg.count(), len(self.incidents())
        res = self.post_fall("pc-both", uuid.uuid4().hex)
        self.assertTrue(res["incident_id"])
        self.assertEqual(len(self.incidents()), before + 1)
        time.sleep(4)
        self.assertEqual(len([m for m in self.tg.since(start) if m["guardian"]]), 1)  # 옛 흐름도 그대로

    def test_5_unregister_goes_back_to_old_flow(self):
        self.register("pc-back", "incident")
        with db.session(self.server.db_path) as conn:
            legacy_devices.remove(conn, "pc-back")
        start, before = self.tg.count(), len(self.incidents())
        res = self.post_fall("pc-back", uuid.uuid4().hex)
        self.assertIsNone(res["incident_id"])
        time.sleep(4)
        self.assertEqual(len([m for m in self.tg.since(start) if m["guardian"]]), 1)
        self.assertEqual(len(self.incidents()), before)

    # ---- 새 사고 만들기 실패·후속 작업 실패·동시 재시도 (두 흐름이 함께 돌거나 알림이 사라지지 않는지) ----
    def sql(self, statement, args=()):
        c = sqlite3.connect(self.server.db_path)
        try:
            with c:
                c.execute(statement, args)
        finally:
            c.close()

    def new_flow_messages(self, start):
        return [m for m in self.tg.since(start) if m["text"].startswith("[지킴이]")]

    def test_6_handover_failure_runs_old_flow_only_even_on_retry(self):
        self.register("pc-fail", "incident")
        # 새 사고 저장이 DB 에서 실패하는 상황 (이 기기만)
        self.sql("""CREATE TRIGGER fail_pc_fail BEFORE INSERT ON incidents WHEN NEW.source_ref = 'pc-fail'
                    BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        start, before = self.tg.count(), len(self.incidents())
        event_id = uuid.uuid4().hex
        try:
            first = self.post_fall("pc-fail", event_id)
        finally:
            self.sql("DROP TRIGGER fail_pc_fail")                         # DB 가 곧 회복됨
        self.assertIsNone(first["incident_id"])
        self.assertEqual(self.legacy_event(event_id)["status"], "awaiting_response")   # 옛 흐름으로 처리 (알림 유지)
        retry1 = self.post_fall("pc-fail", event_id)                      # 회복 뒤 재시도
        retry2 = self.post_fall("pc-fail", event_id)
        self.assertEqual((retry1["duplicate"], retry1["incident_id"], retry2["incident_id"]), (True, None, None))
        time.sleep(4)
        self.assertEqual(len(self.incidents()), before)                   # 새 사고는 만들지 않음 (두 흐름 금지)
        self.assertEqual(len([m for m in self.tg.since(start) if m["guardian"]]), 1)   # 옛 무응답 알림 한 번만
        self.assertEqual(self.new_flow_messages(start), [])
        self.assertNotEqual(self.legacy_event(event_id)["status"], "handed_over")
        # 다음 낙상부터는 다시 새 사고로 넘어감
        nxt = self.post_fall("pc-fail", uuid.uuid4().hex)
        self.assertTrue(nxt["incident_id"])
        self.assertEqual(len(self.incidents()), before + 1)

    def test_7_failure_after_incident_saved_retry_reuses_it(self):
        self.register("pc-img", "incident")
        images = self.server.dir / "images"
        off = self.server.dir / "images_off"
        images.rename(off)
        images.write_bytes(b"")                                           # 사진 저장이 실패하게 (폴더 자리에 파일)
        start, before = self.tg.count(), len(self.incidents())
        event_id = uuid.uuid4().hex
        body = {"event_id": event_id, "device_id": "pc-img", "fall_type": "slip_and_fall", "is_test": False,
                "image_jpeg_base64": TINY_JPEG}
        try:
            status, _, _ = self.server.request("POST", "/api/events", body, headers={"X-Access-Token": self.server.token})
        finally:
            images.unlink()
            off.rename(images)
        self.assertEqual(status, 500)                                     # 새 사고는 저장된 뒤 후속 작업 실패
        self.assertEqual(len(self.incidents()), before + 1)
        first_id = next(i["id"] for i in self.incidents() if i["source"] == "legacy" and i["status"] == "detected")
        res = self.post_fall("pc-img", event_id)                          # PC 프로그램 재시도
        self.assertEqual(res["incident_id"], first_id)                    # 같은 사고 (중복 생성 없음)
        self.assertEqual(len(self.incidents()), before + 1)
        self.assertEqual(self.legacy_event(event_id)["status"], "handed_over")
        time.sleep(4)
        self.assertEqual([m for m in self.tg.since(start) if m["guardian"]], [])        # 옛 텔레그램 없음

    def test_8_same_event_at_once_one_incident_one_flow(self):
        self.register("pc-race", "incident")
        start, before = self.tg.count(), len(self.incidents())
        event_id = uuid.uuid4().hex
        barrier = threading.Barrier(6)
        got = []

        def send():
            barrier.wait()
            got.append(self.post_fall("pc-race", event_id)["incident_id"])

        threads = [threading.Thread(target=send) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(got), 6)
        self.assertEqual(len(set(got)), 1)
        self.assertTrue(got[0])
        self.assertEqual(len(self.incidents()), before + 1)
        self.assertEqual(self.legacy_event(event_id)["status"], "handed_over")
        time.sleep(4)
        self.assertEqual([m for m in self.tg.since(start) if m["guardian"]], [])


if __name__ == "__main__":
    unittest.main()
