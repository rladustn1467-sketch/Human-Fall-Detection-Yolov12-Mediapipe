"""Entrance methods (db.py migration 5, door_codes.py) on a temporary database: the method combinations,
changing a method deletes only that entrance's code, an empty save keeps a registered code, permissions,
first-setup rollback, the DB rules, and that existing codes survive the migration.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import accounts
import db
import door_codes
import people
from tests.test_accounts import IP, PW
from tests.test_door_codes import KEY
from tests.test_people import TODAY, PeopleTestBase

CENTRAL, DOOR = "2580#", "*1379"


class EntranceTest(PeopleTestBase):
    def setUp(self):
        super().setUp()
        self.home = self.setup(self.a, home={"mode": "new", "address": "서울"})   # 에이만 연결, 비는 같은 그룹, 씨는 다른 그룹

    def ent(self, kind, method, code=None, user=None, key=KEY):
        return door_codes.set_entrance(self.conn, user or self.a, self.home, kind, method, code, key=key, now=self.now)

    def view(self, user=None):
        h = self.state(user or self.b)["homes"][0]        # 같은 집의 다른 가족(비)이 보는 정보
        return h["centralAccess"], h["centralPw"], h["doorAccess"], h["doorPw"]

    def reveal(self, kind):
        return door_codes.reveal(self.conn, self.home, kind, key=KEY)

    def test_unset_at_first(self):
        self.assertEqual(self.view(), (None, False, None, False))

    def test_1_both_code(self):
        self.ent("central", "code", CENTRAL)
        self.ent("door", "code", DOOR)
        self.assertEqual(self.view(), ("code", True, "code", True))
        self.assertEqual((self.reveal("central"), self.reveal("door")), (CENTRAL, DOOR))

    def test_2_no_central_door_code(self):
        self.ent("central", "absent")
        self.ent("door", "code", DOOR)
        self.assertEqual(self.view(), ("absent", False, "code", True))

    def test_3_central_code_door_key(self):
        self.ent("central", "code", CENTRAL)
        self.ent("door", "key")
        self.assertEqual(self.view(), ("code", True, "key", False))

    def test_4_both_key(self):
        self.ent("central", "key")
        self.ent("door", "key")
        self.assertEqual(self.view(), ("key", False, "key", False))

    def test_5_door_unlocked(self):
        self.ent("door", "unlocked")
        self.assertEqual(self.view()[2:], ("unlocked", False))

    def test_absent_and_unlocked_do_not_mix(self):
        self.assertAccountError(400, self.ent, "door", "absent")       # 집 현관에 '중앙현관 없음' 불가
        self.assertAccountError(400, self.ent, "central", "unlocked")  # 중앙현관에 '잠금장치 없음' 불가
        self.assertAccountError(400, self.ent, "door", "none")
        self.assertAccountError(400, self.ent, "door", None)
        with self.assertRaises(sqlite3.IntegrityError):                # DB 규칙도 막음
            self.conn.execute("INSERT INTO home_entrances (home_id, kind, method, updated_at) VALUES (?, 'door', 'absent', 0)", (self.home,))
        self.assertEqual(self.view(), (None, False, None, False))

    def test_6_changing_method_deletes_only_that_code(self):
        self.ent("central", "code", CENTRAL)
        self.ent("door", "code", DOOR)
        self.ent("door", "key")                                      # 집 현관만 열쇠로
        self.assertEqual(self.view(), ("code", True, "key", False))
        self.assertEqual(self.reveal("central"), CENTRAL)             # 중앙현관 비밀번호는 그대로
        self.assertIsNone(self.reveal("door"))
        self.ent("central", "absent")
        self.assertEqual(self.view(), ("absent", False, "key", False))
        actions = [r["action"] for r in self.conn.execute("SELECT action FROM home_events ORDER BY id")]
        self.assertEqual(actions.count("door_code_deleted"), 2)

    def test_empty_save_keeps_the_registered_code(self):
        self.ent("door", "code", DOOR)
        self.ent("door", "code")                                      # 입력 없이 저장
        self.ent("door", "code", "")
        self.assertEqual(self.reveal("door"), DOOR)
        door_codes.set_entrance(self.conn, self.a, self.home, "door", "code", None, key=None, now=self.now)   # 키 없이도 그대로 둠
        self.assertEqual(self.reveal("door"), DOOR)
        self.assertAccountError(400, self.ent, "door", "code", "12ab")   # 규칙 위반 → 아무것도 안 바뀜
        self.assertEqual(self.reveal("door"), DOOR)
        self.assertAccountError(503, self.ent, "door", "code", "5555", key=None)
        self.assertEqual(self.reveal("door"), DOOR)

    def test_code_only_when_method_is_code(self):
        self.ent("door", "key")
        err = self.assertAccountError(409, door_codes.put, self.conn, self.a, self.home, "door", DOOR, KEY, self.now)
        self.assertEqual(err.field, "method")
        self.assertEqual(self.view()[2:], ("key", False))
        # 프로그램을 거치지 않고 DB 에 직접 넣어도 막힘 (안전장치)
        n, c = door_codes.encrypt(KEY, self.home, "door", DOOR)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO home_door_codes VALUES (?, 'door', ?, ?, ?, ?, 0)", (self.home, c, n, KEY.key_id, self.a))
        door_codes.put(self.conn, self.a, self.home, "central", CENTRAL, KEY, self.now)   # 미설정 현관에 등록 → 비밀번호 방식
        self.assertEqual(self.view()[:2], ("code", True))

    def test_7_permissions(self):
        self.assertAccountError(403, self.ent, "door", "key", user=self.b)    # 집에 연결 안 된 같은 그룹 가족
        err = self.assertAccountError(404, self.ent, "door", "key", user=self.c)   # 다른 그룹
        self.assertEqual(err.message, "집을 찾을 수 없어요.")
        self.assertAccountError(404, self.ent, "garage", "key")
        self.assertEqual(self.view(), (None, False, None, False))

    def test_8_values_never_leave_the_server(self):
        self.ent("central", "code", CENTRAL)
        self.ent("door", "code", DOOR)
        for user in (self.a, self.b):
            text = json.dumps(self.state(user), ensure_ascii=False)
            self.assertNotIn(CENTRAL, text)
            self.assertNotIn(DOOR, text)
        events = json.dumps([dict(r) for r in self.conn.execute("SELECT * FROM home_events")])
        self.assertNotIn(DOOR, events)
        raw = b"".join(p.read_bytes() for p in self.path.parent.glob(self.path.name + "*"))
        self.assertNotIn(DOOR.encode(), raw)
        self.assertNotIn(CENTRAL.encode(), raw)

    def test_last_member_leaving_removes_entrances(self):
        self.ent("door", "code", DOOR)
        accounts.withdraw(self.conn, self.a, PW, IP, self.now)       # 그룹 1 에는 비가 남아 집이 유지됨
        self.assertEqual(self.count("home_entrances"), 1)
        accounts.leave_group(self.conn, self.b)                       # 마지막 구성원 → 집과 함께 삭제
        self.assertEqual((self.count("home_entrances"), self.count("home_door_codes")), (0, 0))


class SetupEntranceTest(PeopleTestBase):
    def finish(self, user, entrances, home=None, key=KEY):
        return people.finish_setup(self.conn, user, {"birth": "1951-07-08"}, home or {"mode": "new", "address": "서울"},
                                   now=self.now, today=TODAY, entrances=entrances, key=key)

    def view(self, home):
        h = [x for x in self.state(self.a)["homes"] if x["id"] == home][0]
        return h["centralAccess"], h["centralPw"], h["doorAccess"], h["doorPw"]

    def test_combinations_in_first_setup(self):
        home = self.finish(self.a, {"central": {"method": "absent"}, "door": {"method": "code", "code": DOOR}})
        self.assertEqual(self.view(home), ("absent", False, "code", True))
        # 같은 집 관리자가 다시 설정: 보내지 않은 현관은 그대로, '비밀번호' + 빈 값이면 등록된 비밀번호 유지
        self.finish(self.a, {"door": {"method": "code", "code": ""}}, home={"mode": "existing", "id": home})
        self.assertEqual(self.view(home), ("absent", False, "code", True))
        self.assertEqual(door_codes.reveal(self.conn, home, "door", key=KEY), DOOR)
        # 같은 집을 고른 가족(구성원)은 현관을 바꿀 수 없음: 처음 설정 전체가 취소됨 (관리자만, 사용자 결정 2026-10-30)
        self.assertAccountError(403, self.finish, self.b, {"door": {"method": "key"}}, home={"mode": "existing", "id": home})
        self.assertEqual(self.view(home), ("absent", False, "code", True))
        self.assertEqual(self.me(self.b)["homeIds"], [])
        self.finish(self.b, {}, home={"mode": "existing", "id": home})            # 현관을 보내지 않으면 연결됨
        self.assertEqual(self.me(self.b)["homeIds"], [home])

    def test_9_failure_rolls_back_everything(self):
        self.fail_on("home_door_codes", "INSERT")
        with self.assertRaises(sqlite3.DatabaseError):
            self.finish(self.a, {"central": {"method": "key"}, "door": {"method": "code", "code": DOOR}})
        self.assertFalse(self.me(self.a)["isTarget"])
        self.assertEqual((self.count("homes"), self.count("home_entrances"), self.count("home_events")), (0, 0, 0))

    def test_bad_input_saves_nothing(self):
        for entrances in ({"door": {"method": "absent"}}, {"door": {"method": "code", "code": "1a2"}}, {"door": "key"}):
            self.assertAccountError(400, self.finish, self.a, entrances)
        self.assertAccountError(503, self.finish, self.a, {"door": {"method": "code", "code": DOOR}}, key=None)
        self.finish(self.a, {"door": {"method": "key"}}, key=None)    # 비밀번호가 없으면 키가 없어도 완료
        self.assertTrue(self.me(self.a)["isTarget"])

    def test_old_doors_form_still_works(self):
        home = people.finish_setup(self.conn, self.a, {}, {"mode": "new", "address": "서울"}, now=self.now, today=TODAY,
                                   doors={"door": DOOR}, key=KEY)
        self.assertEqual(self.view(home), (None, False, "code", True))


class MigrationKeepsDataTest(unittest.TestCase):
    def test_codes_saved_before_migration_5_become_method_code(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "old.db"
        try:
            self.assertEqual(db.init(path, db.MIGRATIONS[:4]), 4)     # 5번 전 구조
            conn = db.connect(path)
            try:
                now = time.time()
                with db.transaction(conn):
                    conn.execute("INSERT INTO groups (id, name, created_at) VALUES ('g1', '가족', ?)", (now,))
                    conn.execute("INSERT INTO homes (id, group_id, address, created_at, updated_at) VALUES ('h1', 'g1', '서울', ?, ?)", (now, now))
                    n, c = door_codes.encrypt(KEY, "h1", "door", DOOR)
                    conn.execute("INSERT INTO home_door_codes VALUES ('h1', 'door', ?, ?, ?, 'u1', ?)", (c, n, KEY.key_id, now))
            finally:
                conn.close()
            self.assertEqual(db.init(path), db.MIGRATIONS[-1][0])      # 5번 적용
            conn = db.connect(path)
            try:
                rows = [tuple(r) for r in conn.execute("SELECT home_id, kind, method FROM home_entrances")]
                self.assertEqual(rows, [("h1", "door", "code")])        # 기존 비밀번호 → 비밀번호 방식
                self.assertEqual(door_codes.reveal(conn, "h1", "door", key=KEY), DOOR)   # 비밀번호 그대로
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM home_entrances WHERE kind = 'central'").fetchone()[0], 0)
            finally:
                conn.close()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
