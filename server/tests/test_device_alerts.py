"""The family hears when a detection device stops (감사 2026-11-04 N-6, F15), and the settings toggles work.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import tempfile
import unittest
from pathlib import Path

import accounts
import alerts
import db
import devices
import door_codes
import people
import push
from tests.test_incidents import IncidentTestBase

T = 1_800_000_000_000
MIN = 60_000
STARTED = T - 3_600_000      # 서버는 한 시간 전부터 켜져 있음


class FakeSender:
    name = "fake"
    simulated = True

    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


class DeviceTestBase(IncidentTestBase):
    def setUp(self):
        super().setUp()
        code = devices.start_pairing(self.conn, self.a, self.home, "phone", "거실", now=T)["code"]
        self.device_id = devices.pair(self.conn, code, "10.0.0.1", now=T)["deviceId"]
        self.conn.execute("DELETE FROM notifications")   # 기기를 연결할 때의 집 변경 알림은 여기서 보지 않음

    def row(self):
        return self.conn.execute("SELECT * FROM devices WHERE id = ?", (self.device_id,)).fetchone()

    def beat(self, at, camera_ok=True):
        devices.heartbeat(self.conn, self.row(), camera_ok, now=at)

    def watch(self, at, started=STARTED):
        devices.watch(self.conn, started, now=at)

    def kinds(self, user):
        return [r["kind"] for r in self.conn.execute("SELECT kind FROM notifications WHERE user_id = ? ORDER BY created_at", (user,))]

    def pushes(self, kind):
        return sorted(r["user_id"] for r in self.conn.execute("SELECT user_id FROM push_deliveries WHERE kind = ?", (kind,)))

    def set_pref(self, user, key, value):
        people.set_pref(self.conn, user, key, value)


class DeviceProblemTest(DeviceTestBase):
    def test_family_hears_once_when_the_device_goes_silent(self):
        self.beat(T)
        self.watch(T + 5 * MIN - 1)
        self.assertEqual(self.kinds(self.b), [])                       # 잠깐 끊긴 것은 알리지 않음
        self.watch(T + 5 * MIN)
        self.watch(T + 6 * MIN)
        for user in (self.a, self.b, self.d):
            self.assertEqual(self.kinds(user), ["device_problem"])     # 한 번만
        self.assertEqual(self.pushes("device_problem"), sorted([self.a, self.b, self.d]))
        self.assertEqual(self.kinds(self.c), [])                       # 다른 그룹은 받지 않음

    def test_family_hears_when_it_comes_back(self):
        self.beat(T)
        self.watch(T + 5 * MIN)
        self.beat(T + 7 * MIN)
        self.watch(T + 7 * MIN)
        self.watch(T + 8 * MIN)
        self.assertEqual(self.kinds(self.b), ["device_problem", "device_back"])
        self.assertEqual(self.row()["alerted_at"], None)
        self.watch(T + 13 * MIN)                                       # 또 끊기면 다시 알림
        self.assertEqual(self.kinds(self.b).count("device_problem"), 2)

    def test_a_camera_that_stays_broken_is_a_problem_too(self):
        self.beat(T)
        self.beat(T + 1 * MIN, camera_ok=False)
        self.beat(T + 5 * MIN, camera_ok=False)
        self.watch(T + 5 * MIN)
        self.assertEqual(self.kinds(self.b), [])
        self.beat(T + 6 * MIN, camera_ok=False)
        self.watch(T + 6 * MIN)
        self.assertEqual(self.kinds(self.b), ["device_problem"])

    def test_no_false_alarm_when_the_server_itself_was_off(self):
        self.beat(T)
        started = T + 60 * MIN                                         # 서버가 한 시간 꺼져 있다가 켜짐
        self.watch(started + 1000, started=started)
        self.assertEqual(self.kinds(self.b), [])
        self.beat(started + 30_000)                                    # 기기는 멀쩡해서 신호를 계속 보냄
        self.beat(started + 5 * MIN)
        self.watch(started + 6 * MIN, started=started)
        self.assertEqual(self.kinds(self.b), [])

    def test_a_device_that_stays_silent_after_the_server_came_back_is_reported(self):
        self.beat(T)
        started = T + 60 * MIN
        self.watch(started + 4 * MIN, started=started)
        self.assertEqual(self.kinds(self.b), [])
        self.watch(started + 5 * MIN, started=started)
        self.assertEqual(self.kinds(self.b), ["device_problem"])

    def test_a_device_turned_off_on_purpose_is_not_a_problem(self):
        self.beat(T)
        devices.set_enabled_by_device(self.conn, self.row(), False, now=T + 1000)
        self.watch(T + 60 * MIN)
        self.assertEqual(self.kinds(self.b), [])

    def test_turning_it_off_after_the_alert_says_nothing_more(self):
        self.beat(T)
        self.watch(T + 5 * MIN)
        devices.set_enabled_by_device(self.conn, self.row(), False, now=T + 6 * MIN)
        self.watch(T + 7 * MIN)
        self.assertEqual(self.kinds(self.b), ["device_problem"])
        self.assertEqual(self.row()["alerted_at"], None)

    def test_a_device_that_never_connected_is_not_reported(self):
        self.watch(T + 60 * MIN)
        self.assertEqual(self.kinds(self.b), [])

    def test_the_setting_turns_it_off_for_that_person_only(self):
        self.set_pref(self.b, "device", False)
        self.beat(T)
        self.watch(T + 5 * MIN)
        self.assertEqual(self.kinds(self.b), [])
        self.assertEqual(self.kinds(self.d), ["device_problem"])
        self.assertNotIn(self.b, self.pushes("device_problem"))

    def test_the_text_names_the_place(self):
        self.beat(T)
        self.watch(T + 5 * MIN)
        texts = [n["text"] for n in self.state(self.b)["notifs"]]
        self.assertTrue(any("거실" in t and "감지 기기" in t for t in texts), texts)

    def test_push_goes_out_without_an_incident(self):
        token = "tok-" + "x" * 30
        cookie = accounts.create_session(self.conn, self.b, now=T / 1000 - 10)
        push.register_token(self.conn, self.b, accounts._token_hash(cookie), token, now=T)
        self.beat(T)
        self.watch(T + 5 * MIN)
        sender = FakeSender()
        push.process_due(self.conn, sender, now=T + 5 * MIN + 1)
        self.assertEqual(len(sender.sent), 1)
        self.assertNotIn("incidentId", sender.sent[0]["message"]["data"])
        self.assertIn("감지 기기", sender.sent[0]["message"]["notification"]["body"])

    def test_every_device_is_checked(self):
        code = devices.start_pairing(self.conn, self.a, self.home, "phone", "안방", now=T)["code"]
        other = devices.pair(self.conn, code, "10.0.0.1", now=T)["deviceId"]
        self.conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (T, other))
        self.conn.execute("DELETE FROM notifications")
        self.beat(T)
        self.watch(T + 5 * MIN)
        self.assertEqual(self.kinds(self.b), ["device_problem", "device_problem"])


class SettingsTest(DeviceTestBase):
    def test_join_notice_respects_the_setting(self):
        self.set_pref(self.b, "member", False)
        code = self.conn.execute("SELECT code FROM invites WHERE group_id = ?", (self.g1,)).fetchone()[0]
        e = self.signup(name="새가족", phone="010-1000-0009")
        accounts.join_group(self.conn, e, code, now=self.now)
        self.assertEqual(self.kinds(self.b), [])
        self.assertEqual(self.kinds(self.d), ["member_joined"])

    def linked(self):
        people.finish_setup(self.conn, self.b, {}, {"mode": "existing", "id": self.home}, now=self.now)
        self.conn.execute("DELETE FROM notifications")

    def test_address_change_tells_the_others_in_that_home(self):
        self.linked()
        people.update_home_address(self.conn, self.b, self.home, "서울 마포구 월드컵로 1", now=self.now)
        self.assertEqual(self.kinds(self.a), ["home_changed"])
        self.assertEqual(self.kinds(self.b), [])                       # 바꾼 사람 본인은 받지 않음
        self.assertEqual(self.kinds(self.d), [])                       # 이 집에 연결되지 않은 가족도 받지 않음
        text = next(n["text"] for n in self.state(self.a)["notifs"])
        self.assertIn("주소", text)
        self.assertIn("가족비", text)

    def test_the_setting_turns_home_notices_off(self):
        self.linked()
        self.set_pref(self.a, "home", False)
        people.update_home_address(self.conn, self.b, self.home, "서울 마포구 월드컵로 1", now=self.now)
        self.assertEqual(self.kinds(self.a), [])

    def test_entrance_and_code_changes_tell_the_home_without_the_code(self):
        self.linked()
        people.set_admin(self.conn, self.a, self.home, self.b, True)
        key = door_codes.parse_key(door_codes.generate_key())[0]
        door_codes.put(self.conn, self.b, self.home, "door", "1234", key=key, now=self.now)
        door_codes.set_entrance(self.conn, self.b, self.home, "central", "absent", now=self.now)
        door_codes.delete(self.conn, self.b, self.home, "door", now=self.now)
        self.assertEqual(self.kinds(self.a), ["home_changed"] * 3)
        self.assertNotIn("1234", json.dumps(self.state(self.a)["notifs"], ensure_ascii=False))

    def test_adding_and_removing_a_device_tells_the_home(self):
        self.linked()
        people.set_admin(self.conn, self.a, self.home, self.b, True)
        code = devices.start_pairing(self.conn, self.b, self.home, "phone", "안방", now=T)["code"]
        other = devices.pair(self.conn, code, "10.0.0.1", now=T)["deviceId"]
        devices.remove(self.conn, self.b, other)
        self.assertEqual(self.kinds(self.a), ["home_changed"] * 2)


class MigrationTest(unittest.TestCase):
    def test_push_rows_survive_and_device_pushes_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.db"
            db.init(path, [m for m in db.MIGRATIONS if m[0] <= 12])
            with db.session(path) as c:
                c.execute("INSERT INTO groups (id, name, created_at) VALUES ('g', 'g', 0)")
                c.execute("INSERT INTO users (id, name, phone, password_hash, created_at, group_id) VALUES ('u', 'u', '010', 'h', 0, 'g')")
                c.execute("INSERT INTO homes (id, group_id, created_by, created_at, updated_at) VALUES ('h', 'g', 'u', 0, 0)")
                c.execute("""INSERT INTO incidents (id, group_id, home_id, source, location, detected_at, status, updated_at)
                             VALUES ('i', 'g', 'h', 'dev', '거실', 0, 'detected', 0)""")
                c.execute("""INSERT INTO push_deliveries (incident_id, group_id, user_id, kind, n, status, created_at, updated_at)
                             VALUES ('i', 'g', 'u', 'help', 2, 'sent', 5, 6)""")
                c.execute("INSERT INTO notifications (id, group_id, user_id, incident_id, kind, created_at) VALUES ('n', 'g', 'u', 'i', 'help', 7)")
                c.commit()
            self.assertEqual(db.init(path), db.MIGRATIONS[-1][0])
            with db.session(path) as c:
                row = c.execute("SELECT * FROM push_deliveries").fetchone()
                self.assertEqual((row["incident_id"], row["kind"], row["n"], row["status"]), ("i", "help", 2, "sent"))
                self.assertEqual(c.execute("SELECT kind FROM notifications").fetchone()["kind"], "help")
                c.execute("""INSERT INTO push_deliveries (incident_id, group_id, user_id, kind, status, created_at, updated_at)
                             VALUES (NULL, 'g', 'u', 'device_problem', 'pending', 8, 8)""")


if __name__ == "__main__":
    unittest.main()
