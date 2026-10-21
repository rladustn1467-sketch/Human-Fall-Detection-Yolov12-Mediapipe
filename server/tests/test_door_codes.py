"""door_codes.py on a temporary database: key handling, code rules, encryption, permissions, work record,
first-setup transaction, and that the plain code never ends up in the state, the database file or errors.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import json
import sqlite3

import accounts
import door_codes
import people
from tests.test_accounts import IP, PW
from tests.test_people import TODAY, PeopleTestBase

KEY = door_codes.parse_key(door_codes.generate_key())[0]
OTHER_KEY = door_codes.parse_key(door_codes.generate_key())[0]
SECRET = "73591*#"           # 시험용 비밀번호 (DB·응답·기록 어디에도 원문이 없어야 함)


class KeyAndRuleTest(PeopleTestBase):
    def test_key_parsing(self):
        self.assertEqual(door_codes.parse_key("")[1], "missing")
        self.assertEqual(door_codes.parse_key(None)[1], "missing")
        self.assertEqual(door_codes.parse_key("not-a-key")[1], "invalid")
        self.assertEqual(door_codes.parse_key("QUFBQQ==")[1], "invalid")          # 길이가 32바이트가 아님
        key_text = door_codes.generate_key()
        key, problem = door_codes.parse_key(key_text)
        self.assertEqual(problem, "")
        self.assertNotEqual(key.key_id, door_codes.parse_key(door_codes.generate_key())[0].key_id)
        status = door_codes.configure(key_text)                               # 서버 시작 로그 문구
        self.assertIn("켜짐", status)
        self.assertNotIn(key_text, status)
        self.assertIn("꺼짐", door_codes.configure(""))
        self.assertIn("형식 오류", door_codes.configure("bad"))
        self.assertIsNone(door_codes.current_key())

    def test_code_rule(self):
        for ok in ("123", "1234", "*1234#", "#*0", "1" * 20):
            self.assertEqual(door_codes.clean_code(ok), ok)
        for bad in ("12", "1" * 21, "12a4", "12 34", "", None, 1234, "１２３４", "12-34"):
            err = self.assertAccountError(400, door_codes.clean_code, bad)
            self.assertEqual(err.field, "code")
            if bad not in ("", None):
                self.assertNotIn(str(bad), err.message)                            # 값은 안내에 넣지 않음
        self.assertAccountError(404, door_codes.clean_kind, "garage")

    def test_encryption(self):
        n1, c1 = door_codes.encrypt(KEY, "h_1", "door", SECRET)
        n2, c2 = door_codes.encrypt(KEY, "h_1", "door", SECRET)
        self.assertNotEqual((n1, c1), (n2, c2))                                 # 같은 값도 매번 다르게
        self.assertNotIn(SECRET.encode(), c1)
        self.assertEqual(door_codes.decrypt(KEY, "h_1", "door", n1, c1), SECRET)
        for args in ((KEY, "h_2", "door"), (KEY, "h_1", "central"), (OTHER_KEY, "h_1", "door")):
            with self.assertRaises(door_codes.DoorCodeKeyError):               # 다른 집·종류·키로는 풀리지 않음
                door_codes.decrypt(*args, n1, c1)


class DoorCodeTest(PeopleTestBase):
    def setUp(self):
        super().setUp()
        # 에이·비: 그룹 1, 에이만 집에 연결 / 씨: 그룹 2
        self.home = self.setup(self.a, home={"mode": "new", "address": "서울"})

    def put(self, user, code=SECRET, kind="door", key=KEY, home=None):
        return door_codes.put(self.conn, user, home or self.home, kind, code, key=key, now=self.now)

    def events(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM home_events ORDER BY id")]

    def test_register_change_delete_and_record(self):
        self.put(self.a, kind="central", code="1234")
        self.put(self.a)
        self.assertEqual(door_codes.registered(self.conn, [self.home])[self.home], {"central": True, "door": True})
        home_b = self.state(self.b)["homes"][0]
        self.assertEqual((home_b["centralPw"], home_b["doorPw"]), (True, True))      # 가족에게는 등록 여부만
        self.assertNotIn(SECRET, json.dumps(self.state(self.b), ensure_ascii=False))
        self.put(self.a, code="99999")                                             # 변경
        self.assertEqual(door_codes.reveal(self.conn, self.home, "door", key=KEY), "99999")
        door_codes.delete(self.conn, self.a, self.home, "central", now=self.now)
        self.assertFalse(self.state(self.a)["homes"][0]["centralPw"])
        # 미설정 현관에 처음 등록하면 출입 방식이 '비밀번호'로 정해지고 그것도 기록됨 (값은 없음)
        self.assertEqual([(e["action"], e["kind"], e["actor_id"]) for e in self.events()],
                         [("entrance_code", "central", self.a), ("door_code_set", "central", self.a),
                          ("entrance_code", "door", self.a), ("door_code_set", "door", self.a),
                          ("door_code_changed", "door", self.a), ("door_code_deleted", "central", self.a)])
        self.assertNotIn(SECRET, json.dumps(self.events()))
        self.assertAccountError(404, door_codes.delete, self.conn, self.a, self.home, "central")   # 이미 없음

    def test_permissions(self):
        # 같은 그룹이지만 집에 연결되지 않은 가족: 403 / 다른 그룹: 404 (집이 없는 것처럼)
        self.assertAccountError(403, self.put, self.b)
        err = self.assertAccountError(404, self.put, self.c)
        self.assertEqual(err.message, "집을 찾을 수 없어요.")
        self.put(self.a)
        self.assertAccountError(403, door_codes.delete, self.conn, self.b, self.home, "door")
        self.assertAccountError(404, door_codes.delete, self.conn, self.c, self.home, "door")
        self.assertTrue(door_codes.registered(self.conn, [self.home])[self.home]["door"])
        self.setup(self.b)                                                          # 비도 감지를 켜고 (다른 집)
        people.link_home(self.conn, self.b, self.home, self.now)                   # 이 집에 연결하면 가능
        self.put(self.b, code="2468")
        self.assertEqual(self.state(self.c)["homes"], [])                         # 다른 그룹 상태에는 집도 없음

    def test_no_key_fails_safely(self):
        err = self.assertAccountError(503, self.put, self.a, key=None)
        self.assertIn("암호화 키", err.message)
        self.assertEqual(self.count("home_door_codes"), 0)                         # 평문으로도 저장하지 않음
        self.assertEqual(self.events(), [])
        self.assertAccountError(400, self.put, self.a, code="12ab", key=None)      # 규칙 검사가 먼저

    def test_reveal_needs_the_same_key(self):
        self.assertIsNone(door_codes.reveal(self.conn, self.home, "door", key=KEY))
        self.put(self.a)
        with self.assertRaises(door_codes.DoorCodeKeyError):
            door_codes.reveal(self.conn, self.home, "door", key=OTHER_KEY)
        door_codes.configure("")
        with self.assertRaises(door_codes.DoorCodeKeyError):
            door_codes.reveal(self.conn, self.home, "door")
        # DB 에서 암호문을 다른 집으로 옮겨도 풀리지 않음
        other = self.setup(self.c, home={"mode": "new", "address": "부산"})
        self.conn.execute("""INSERT INTO home_door_codes SELECT ?, kind, ciphertext, nonce, key_id, updated_by, updated_at
                             FROM home_door_codes WHERE home_id = ?""", (other, self.home))
        with self.assertRaises(door_codes.DoorCodeKeyError):
            door_codes.reveal(self.conn, other, "door", key=KEY)

    def test_plain_code_is_not_in_the_database_file(self):
        self.put(self.a, kind="central")
        self.put(self.a)
        raw = b""
        for suffix in ("", "-wal", "-shm"):
            path = self.path.with_name(self.path.name + suffix)
            if path.exists():
                raw += path.read_bytes()
        self.assertTrue(raw)
        self.assertNotIn(SECRET.encode(), raw)

    def test_deleted_with_home_but_kept_for_others(self):
        self.put(self.a)
        self.setup(self.b)
        people.link_home(self.conn, self.b, self.home, self.now)
        accounts.withdraw(self.conn, self.a, PW, IP, self.now)                     # 다른 가족(비)이 남음 → 그대로
        self.assertTrue(door_codes.registered(self.conn, [self.home])[self.home]["door"])
        accounts.leave_group(self.conn, self.b)                                    # 마지막 구성원 → 집과 함께 삭제
        self.assertEqual(self.count("home_door_codes"), 0)
        self.assertEqual(self.count("home_events"), 0)


class SetupWithDoorCodesTest(PeopleTestBase):
    def finish(self, user, doors, key=KEY, home=None):
        return people.finish_setup(self.conn, user, {"birth": "1951-07-08"}, home or {"mode": "new", "address": "서울"},
                                   now=self.now, today=TODAY, doors=doors, key=key)

    def test_saved_in_the_same_transaction(self):
        home = self.finish(self.a, {"central": "1234", "door": SECRET})
        self.assertEqual(door_codes.registered(self.conn, [home])[home], {"central": True, "door": True})
        self.assertEqual(door_codes.reveal(self.conn, home, "door", key=KEY), SECRET)
        # 같은 그룹의 다른 가족이 같은 집을 고르고 비밀번호를 비워 두면 기존 값은 그대로
        self.finish(self.b, {"central": "", "door": None}, home={"mode": "existing", "id": home})
        self.assertEqual(door_codes.reveal(self.conn, home, "door", key=KEY), SECRET)

    def test_invalid_code_or_no_key_saves_nothing(self):
        self.assertAccountError(400, self.finish, self.a, {"door": "12ab"})
        self.assertAccountError(503, self.finish, self.a, {"door": SECRET}, key=None)
        self.assertFalse(self.me(self.a)["isTarget"])
        self.assertEqual(self.count("homes"), 0)
        self.finish(self.a, {}, key=None)                                         # 비밀번호 없이는 키가 없어도 완료
        self.assertTrue(self.me(self.a)["isTarget"])

    def test_failure_while_saving_codes_rolls_back_everything(self):
        self.fail_on("home_events", "INSERT")
        with self.assertRaises(sqlite3.DatabaseError):
            self.finish(self.a, {"door": SECRET})
        self.assertFalse(self.me(self.a)["isTarget"])
        self.assertEqual(self.count("homes"), 0)
        self.assertEqual(self.count("home_door_codes"), 0)
