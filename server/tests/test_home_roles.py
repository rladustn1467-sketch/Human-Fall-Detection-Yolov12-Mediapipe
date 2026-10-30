"""Home administrators and members (user decisions 2026-10-30): the person who registers a home is its first
administrator; administrators can make other linked members administrators (several allowed) and take it back
(at least one stays); when the last administrator leaves, the longest-linked member becomes one.
Only administrators add, rename or delete devices (also 'this phone') and change entrances and door codes; the
address can still be changed by every linked member.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

import accounts
import db
import door_codes
import people
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser
from tests.test_people import PeopleTestBase


class RoleRulesTest(PeopleTestBase):
    """에이: 집을 등록 (관리자), 비: 같은 집에 연결 (구성원), 디: 같은 집에 나중에 연결."""

    def setUp(self):
        super().setUp()
        self.home = self.setup(self.a)
        self.setup(self.b, home={"mode": "existing", "id": self.home})
        self.d = self.signup(name="가족디", phone="010-1000-0004")
        code = self.conn.execute("SELECT code FROM invites WHERE group_id = ?", (self.g1,)).fetchone()[0]
        accounts.join_group(self.conn, self.d, code, now=self.now)
        people.finish_setup(self.conn, self.d, {}, {"mode": "existing", "id": self.home}, now=self.now + 10)   # 비보다 나중에 연결

    def admins(self):
        return next(h for h in self.state(self.a)["homes"] if h["id"] == self.home)["adminIds"]

    def test_first_admin_is_the_one_who_registered_the_home(self):
        self.assertEqual(self.admins(), [self.a])
        self.assertTrue(people.is_admin(self.conn, self.home, self.a))
        self.assertFalse(people.is_admin(self.conn, self.home, self.b))

    def test_admin_can_add_and_remove_admins_but_one_must_stay(self):
        self.assertAccountError(403, people.set_admin, self.conn, self.b, self.home, self.d, True)   # 구성원은 못 함
        people.set_admin(self.conn, self.a, self.home, self.b, True)
        self.assertEqual(sorted(self.admins()), sorted([self.a, self.b]))                         # 여러 명
        people.set_admin(self.conn, self.b, self.home, self.a, False)                             # 다른 관리자가 해제
        self.assertEqual(self.admins(), [self.b])
        self.assertAccountError(409, people.set_admin, self.conn, self.b, self.home, self.b, False)   # 마지막 관리자
        self.assertAccountError(404, people.set_admin, self.conn, self.b, self.home, self.c, True)    # 다른 그룹 사람
        e = self.signup(name="연결안된이", phone="010-1000-0005")
        code = self.conn.execute("SELECT code FROM invites WHERE group_id = ?", (self.g1,)).fetchone()[0]
        accounts.join_group(self.conn, e, code, now=self.now)
        self.assertAccountError(409, people.set_admin, self.conn, self.b, self.home, e, True)      # 집에 연결 안 됨

    def test_last_admin_leaving_passes_it_to_the_longest_linked_member(self):
        people.unlink_home(self.conn, self.a, self.home)
        self.assertEqual(self.admins_seen_by(self.b), [self.b])                                   # 비가 디보다 먼저 연결
        accounts.leave_group(self.conn, self.b)
        self.assertEqual(self.admins_seen_by(self.d), [self.d])

    def test_withdrawal_of_the_admin_passes_it_on(self):
        accounts.withdraw(self.conn, self.a, PW, "10.0.0.1", self.now)
        self.assertEqual(self.admins_seen_by(self.b), [self.b])

    def admins_seen_by(self, user):
        return next(h for h in self.state(user)["homes"] if h["id"] == self.home)["adminIds"]

    def test_address_stays_open_to_linked_members(self):
        people.update_home_address(self.conn, self.b, self.home, "서울 마포구 월드컵로 1", now=self.now)


class RoleApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy({"DOOR_CODE_KEY": door_codes.generate_key()})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def member(self, name, code=None):
        b = Browser(self.server)
        phone = "010-" + str(uuid.uuid4().int)[:4] + "-" + str(uuid.uuid4().int)[:4]
        status, _, data = b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone, "password": PW})
        self.assertEqual(status, 200, data)
        b.id = data["me_id"]
        b.call("POST", "/api/v2/groups/join", {"code": code}) if code else b.call("POST", "/api/v2/groups")
        return b

    def test_only_admins_change_devices_and_entrances(self):
        a = self.member("관리자에이")
        home = a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})[2]["state"]["homes"][0]["id"]
        b = self.member("구성원비", a.state()["state"]["groups"][0]["invite"]["code"])
        self.assertEqual(b.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "existing", "id": home}})[0], 200)
        door = f"/api/v2/homes/{home}/door-codes/door"
        pairing = f"/api/v2/homes/{home}/devices/pairing"
        # 구성원: 현관·기기 안 됨, 주소는 됨
        status, _, data = b.call("PUT", door, {"code": "1234"})
        self.assertEqual((status, data["field"]), (403, "home"))
        self.assertIn("관리자", data["message"])
        self.assertEqual(b.call("PUT", f"/api/v2/homes/{home}/entrances/door", {"method": "key"})[0], 403)
        self.assertEqual(b.call("POST", pairing, {"type": "phone", "location": "거실"})[0], 403)
        self.assertEqual(b.call("POST", f"/api/v2/homes/{home}/address", {"address": "서울 중구 세종대로 110"})[0], 200)
        # 관리자: 됨
        self.assertEqual(a.call("PUT", door, {"code": "1234"})[0], 200)
        status, _, data = a.call("POST", pairing, {"type": "phone", "location": "거실"})
        self.assertEqual(status, 200, data)
        pair = self.server.request("POST", "/api/v2/device/pair", {"code": data["pairing"]["code"], "appVersion": "t"})
        device_id = __import__("json").loads(pair[2])["deviceId"]
        self.assertEqual(b.call("PATCH", f"/api/v2/devices/{device_id}", {"location": "안방"})[0], 403)
        self.assertEqual(b.call("DELETE", f"/api/v2/devices/{device_id}")[0], 403)
        # 관리자 지정 → 구성원도 바꿀 수 있게 됨
        path = f"/api/v2/homes/{home}/members/{b.id}/admin"
        self.assertEqual(b.call("POST", path, {"admin": True})[0], 403)
        status, _, data = a.call("POST", path, {"admin": True})
        self.assertEqual(status, 200, data)
        self.assertEqual(sorted(data["state"]["homes"][0]["adminIds"]), sorted([a.id, b.id]))
        self.assertEqual(b.call("PATCH", f"/api/v2/devices/{device_id}", {"location": "안방"})[0], 200)
        self.assertEqual(b.call("PUT", door, {"code": "5678"})[0], 200)


class RoleMigrationTest(unittest.TestCase):
    def test_existing_homes_get_their_registrant_or_earliest_member_as_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.db"
            db.init(path, [m for m in db.MIGRATIONS if m[0] <= 11])
            c = sqlite3.connect(path)
            c.execute("INSERT INTO groups (id, name, created_at) VALUES ('g', 'g', 0)")
            for uid in ("u1", "u2", "u3"):
                c.execute("INSERT INTO users (id, name, phone, password_hash, created_at, group_id) VALUES (?, ?, ?, 'h', 0, 'g')",
                          (uid, uid, "010" + uid))
            c.execute("INSERT INTO homes (id, group_id, created_by, created_at, updated_at) VALUES ('h1', 'g', 'u2', 0, 0)")
            c.execute("INSERT INTO homes (id, group_id, created_by, created_at, updated_at) VALUES ('h2', 'g', 'gone', 0, 0)")
            for home, uid, at in (("h1", "u1", 1), ("h1", "u2", 2), ("h2", "u3", 5), ("h2", "u1", 3)):
                c.execute("INSERT INTO home_members (home_id, user_id, linked_at) VALUES (?, ?, ?)", (home, uid, at))
            c.commit()
            c.close()
            self.assertEqual(db.init(path), db.MIGRATIONS[-1][0])
            c = sqlite3.connect(path)
            roles = {(h, u): r for h, u, r in c.execute("SELECT home_id, user_id, role FROM home_members")}
            c.close()
            self.assertEqual(roles, {("h1", "u1"): "member", ("h1", "u2"): "admin",      # 등록한 사람
                                     ("h2", "u3"): "member", ("h2", "u1"): "admin"})     # 등록한 사람 없음 → 가장 먼저 연결


if __name__ == "__main__":
    unittest.main()
