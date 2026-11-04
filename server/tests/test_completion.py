"""Finishing existing features (docs/PROTOTYPE_STATUS.md): report result pushes, late falls, consent, password change.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import uuid

import accounts
import devices
import incidents
from tests.test_accounts import IP, PW
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import Browser
from tests.test_incidents import IncidentTestBase, S, T
import unittest

NEW_PW = "NewPass2026x"


class ReportPushTest(IncidentTestBase):
    def pushes(self, kind):
        return sorted(r["user_id"] for r in self.conn.execute("SELECT user_id FROM push_deliveries WHERE kind = ?", (kind,)))

    def test_the_others_hear_about_a_report(self):
        iid = self.fall()
        incidents.tick(self.conn, now=T + 60 * S)
        incidents.report(self.conn, self.b, iid, now=T + 61 * S)
        self.assertEqual(self.pushes("reported"), sorted([self.a, self.d]))        # 신고한 사람은 제외

    def test_everyone_hears_about_the_automatic_report(self):
        self.fall()
        incidents.tick(self.conn, now=T + 60 * S)
        incidents.tick(self.conn, now=T + 60 * S + incidents.AUTO_REPORT_MS)
        self.assertEqual(self.pushes("auto_reported"), sorted([self.a, self.b, self.d]))


class LateFallTest(IncidentTestBase):
    def setUp(self):
        super().setUp()
        code = devices.start_pairing(self.conn, self.a, self.home, "phone", "거실", now=T)["code"]
        self.device_id = devices.pair(self.conn, code, "10.0.0.1", now=T)["deviceId"]

    def fall_late(self, age_ms, key):
        row = self.conn.execute("SELECT * FROM devices WHERE id = ?", (self.device_id,)).fetchone()
        iid = devices.incident_for_fall(self.conn, row, key, now=T, age_ms=age_ms)
        return self.inc(iid)

    def test_a_fall_sent_right_away_starts_now(self):
        self.assertEqual(self.fall_late(None, "a")["detected_at"], T)

    def test_a_delayed_fall_keeps_its_real_age(self):
        self.assertEqual(self.fall_late(20 * S, "a")["detected_at"], T - 20 * S)

    def test_a_long_delay_alerts_the_family_at_once_but_leaves_them_time(self):
        row = self.fall_late(9 * 60 * S, "a")
        self.assertEqual(row["detected_at"], T - 60 * S)                           # 최대 60초만 앞당김
        incidents.tick(self.conn, now=T)
        row = self.inc(row["id"])
        self.assertEqual(row["status"], "no_response")                             # 도착하자마자 가족 알림
        self.assertEqual(row["auto_report_at"], T + incidents.AUTO_REPORT_MS)      # 자동 신고까지는 180초가 남음

    def test_wrong_ages_are_ignored(self):
        for i, bad in enumerate((-5000, "soon", True)):
            self.conn.execute("DELETE FROM incidents")
            self.assertEqual(self.fall_late(bad, f"b{i}")["detected_at"], T, bad)


class PasswordTest(IncidentTestBase):
    def test_change(self):
        keep = accounts.create_session(self.conn, self.b, now=self.now)
        other = accounts.create_session(self.conn, self.b, now=self.now)
        accounts.change_password(self.conn, self.b, PW, NEW_PW, keep, now=self.now)
        phone = self.conn.execute("SELECT phone FROM users WHERE id = ?", (self.b,)).fetchone()[0]
        self.assertEqual(accounts.authenticate(self.conn, phone, NEW_PW, IP, now=self.now), self.b)
        self.assertAccountError(401, accounts.authenticate, self.conn, phone, PW, IP, now=self.now)
        self.assertEqual(accounts.session_user(self.conn, keep, now=self.now), self.b)      # 지금 기기는 유지
        self.assertIsNone(accounts.session_user(self.conn, other, now=self.now))            # 다른 기기는 끊김

    def test_wrong_current_password(self):
        err = self.assertAccountError(401, accounts.change_password, self.conn, self.b, "Wrong2026x", NEW_PW, None, now=self.now)
        self.assertEqual(err.field, "password")

    def test_the_new_password_follows_the_rule(self):
        err = self.assertAccountError(400, accounts.change_password, self.conn, self.b, PW, "short1", None, now=self.now)
        self.assertEqual(err.field, "new_password")

    def test_guessing_is_limited(self):
        for _ in range(accounts.LOGIN_LIMIT_PER_PHONE[0]):
            self.assertAccountError(401, accounts.change_password, self.conn, self.b, "Wrong2026x", NEW_PW, None, now=self.now)
        self.assertAccountError(429, accounts.change_password, self.conn, self.b, PW, NEW_PW, None, now=self.now)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def signup(self, **extra):
        b = Browser(self.server)
        b.phone = "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": "동의시험", "phone": b.phone, "password": PW, **extra})
        self.assertEqual(status, 200, data)
        b.id = data["me_id"]
        return b

    def agreed_at(self, user):
        import sqlite3
        c = sqlite3.connect(self.server.db_path, timeout=10)
        try:
            return c.execute("SELECT agreed_at FROM users WHERE id = ?", (user,)).fetchone()[0]
        finally:
            c.close()

    def test_consent_time_is_kept(self):
        self.assertIsNotNone(self.agreed_at(self.signup(agreed=True).id))
        self.assertIsNone(self.agreed_at(self.signup().id))

    def test_password_change_keeps_this_login(self):
        b = self.signup(agreed=True)
        status, _, data = b.call("POST", "/api/v2/me/password", {"current": PW, "new": NEW_PW})
        self.assertEqual(status, 200, data)
        self.assertEqual(b.call("GET", "/api/v2/state")[2]["me_id"], b.id)
        fresh = Browser(self.server)
        self.assertEqual(fresh.call("POST", "/api/v2/auth/login", {"phone": b.phone, "password": NEW_PW})[0], 200)

    def test_password_change_needs_login(self):
        self.assertEqual(Browser(self.server).call("POST", "/api/v2/me/password", {"current": PW, "new": NEW_PW})[0], 401)


if __name__ == "__main__":
    unittest.main()
