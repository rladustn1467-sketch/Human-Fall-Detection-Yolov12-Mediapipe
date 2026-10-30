"""Moving the old detectors to the device API (user request 2026-10-30), before the old paths are removed:
an administrator issues a pairing code for a registered old device (PC detection program) on the server itself,
and every call of an old path is logged (route only: never tokens, event ids or query strings).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import time
import unittest

import devices
import legacy_devices
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import Browser
from tests.test_people import PeopleTestBase
from tests.test_accounts import IP


class PcCodeTest(PeopleTestBase):
    def test_pc_code_for_a_registered_old_device(self):
        home = self.setup(self.a)
        legacy_devices.add(self.conn, "laptop", home, "거실", "incident")
        p = legacy_devices.pc_code(self.conn, "laptop", now=1_800_000_000_000)
        self.assertRegex(p["code"], r"^[A-HJ-NP-Z2-9]{6}$")
        self.assertEqual((p["type"], p["location"], p["homeId"]), ("pc", "거실", home))
        # 운영 서버(개발용 기기 꺼짐)에서도 이 코드로 PC 프로그램이 연결됨
        self.assertFalse(devices.dev_devices())
        paired = devices.pair(self.conn, p["code"], IP, "pc-test", now=1_800_000_000_000 + 1000)
        self.assertEqual((paired["type"], paired["location"]), ("pc", "거실"))
        row = self.conn.execute("SELECT home_id, type FROM devices WHERE id = ?", (paired["deviceId"],)).fetchone()
        self.assertEqual((row["home_id"], row["type"]), (home, "pc"))

    def test_unknown_old_device(self):
        self.assertAccountError(404, legacy_devices.pc_code, self.conn, "no-such-device")


class LegacyCallLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def lines(self):
        time.sleep(0.3)
        path = self.server.dir / "logs" / "legacy_calls.log"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_old_paths_are_logged_without_ids_or_tokens(self):
        token = {"X-Access-Token": self.server.token}
        event_id = "0123456789abcdef0123456789abcdef"
        self.server.request("GET", "/api/events", headers=token)
        self.server.request("GET", f"/api/events/{event_id}", headers=token)
        self.server.request("GET", f"/images/{event_id}.jpg", headers=token)
        self.server.request("GET", f"/login?token={self.server.token}&next=/app")
        self.server.request("GET", "/app/")
        # 새 경로는 기록하지 않음
        self.server.request("GET", "/api/v2/state")
        self.server.request("GET", "/app/next/index.html")
        Browser(self.server).call("GET", "/api/v2/health")
        lines = self.lines()
        routes = {(l["method"], l["route"]) for l in lines}
        self.assertEqual(routes, {("GET", "/api/events"), ("GET", "/api/events/{id}"), ("GET", "/images/{id}.jpg"),
                                  ("GET", "/login"), ("GET", "/app/*")})
        text = (self.server.dir / "logs" / "legacy_calls.log").read_text(encoding="utf-8")
        self.assertNotIn(self.server.token, text)                                       # 토큰 없음
        self.assertNotIn(event_id, text)                                                # 이벤트 id 없음
        self.assertTrue(all({"at", "method", "route", "client", "status"} <= set(l) for l in lines))
        server_log = (self.server.dir / "server.log").read_text(encoding="utf-8", errors="replace")
        self.assertIn("[옛 경로] GET /api/events", server_log)

    def test_repeated_calls_are_counted_not_repeated(self):
        token = {"X-Access-Token": self.server.token}
        before = len([l for l in self.lines() if l["route"] == "/api/events/{id}/response"])
        for _ in range(5):
            self.server.request("POST", "/api/events/0123456789abcdef0123456789abcdee/response", {"response": "safe"},
                                headers=token)
        after = [l for l in self.lines() if l["route"] == "/api/events/{id}/response"]
        self.assertEqual(len(after) - before, 1)                                         # 10분에 한 줄 (횟수는 다음 줄에)


if __name__ == "__main__":
    unittest.main()
