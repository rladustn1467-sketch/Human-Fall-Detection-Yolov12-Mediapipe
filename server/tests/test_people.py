"""people.py and the stage-C parts of accounts.py on a temporary database: profile, health information,
notification settings, homes, first-setup transaction, leaving a group, withdrawal.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import sqlite3
from datetime import date

import accounts
import people
from tests.test_accounts import IP, PW, AccountsTestBase

TODAY = date(2027, 1, 1)


class PeopleTestBase(AccountsTestBase):
    def setUp(self):
        super().setUp()
        # 그룹 1: 에이(만든 사람)·비 / 그룹 2: 씨
        self.a = self.signup(name="가족에이", phone="010-1000-0001")
        self.b = self.signup(name="가족비", phone="010-1000-0002")
        self.c = self.signup(name="다른집씨", phone="010-1000-0003")
        self.g1 = accounts.create_group(self.conn, self.a, now=self.now)
        code = self.conn.execute("SELECT code FROM invites WHERE group_id = ?", (self.g1,)).fetchone()[0]
        accounts.join_group(self.conn, self.b, code, now=self.now)
        self.g2 = accounts.create_group(self.conn, self.c, now=self.now)

    def setup(self, user, info=None, home=None):
        return people.finish_setup(self.conn, user, info or {}, home or {"mode": "new", "address": ""},
                                   now=self.now, today=TODAY)

    def state(self, user):
        return accounts.state_for(self.conn, user, now=self.now)

    def me(self, user):
        return next(p for p in self.state(user)["people"] if p["id"] == user)

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def fail_on(self, table, action):
        # 일부러 중간에 오류를 내는 트리거 (트랜잭션이 전부 취소되는지 확인용)
        self.conn.execute(f"""CREATE TRIGGER fail_{table}_{action} BEFORE {action} ON {table}
                              BEGIN SELECT RAISE(ABORT, 'test failure'); END""")


class InputTest(PeopleTestBase):
    def test_birth(self):
        self.assertEqual(people.clean_birth("1951-07-08", TODAY), "1951-07-08")
        self.assertIsNone(people.clean_birth(None))
        self.assertIsNone(people.clean_birth(""))
        for bad in ("1951-13-01", "1899-12-31", "2027-01-02", "어제", 19510708):
            self.assertAccountError(400, people.clean_birth, bad, TODAY)

    def test_lists(self):
        self.assertIsNone(people.clean_list(None, "conditions"))
        self.assertEqual(people.clean_list([], "conditions"), [])
        self.assertEqual(people.clean_list([" 고혈압 ", "고혈압", "당뇨"], "conditions"), ["고혈압", "당뇨"])
        self.assertAccountError(400, people.clean_list, ["가" * 31], "conditions")
        self.assertAccountError(400, people.clean_list, [""], "conditions")
        self.assertAccountError(400, people.clean_list, [str(i) for i in range(21)], "conditions")
        self.assertAccountError(400, people.clean_list, "고혈압", "conditions")

    def test_address(self):
        self.assertEqual(people.clean_address("  서울   마포구 1 ", True), "서울 마포구 1")
        self.assertEqual(people.clean_address("", False), "")
        self.assertAccountError(400, people.clean_address, "", True)
        self.assertAccountError(400, people.clean_address, "가" * 201, False)


class ProfileTest(PeopleTestBase):
    def test_name_and_health_only_for_target(self):
        people.update_profile(self.conn, self.a, "새이름", today=TODAY)
        self.assertEqual(self.me(self.a)["name"], "새이름")
        # 감지 대상이 아니면 건강 정보 입력 불가
        self.assertAccountError(409, people.update_profile, self.conn, self.a, "새이름", {"birth": "1950-01-01"}, TODAY)
        self.setup(self.a)
        people.update_profile(self.conn, self.a, "새이름", {"birth": "1950-01-01", "conditions": ["당뇨"], "medications": []}, TODAY)
        me = self.me(self.a)
        self.assertEqual((me["birth"], me["conditions"], me["medications"]), ("1950-01-01", ["당뇨"], []))
        # 보내지 않은 항목은 그대로
        people.update_profile(self.conn, self.a, "새이름", {"medications": None}, TODAY)
        me = self.me(self.a)
        self.assertEqual((me["conditions"], me["medications"]), (["당뇨"], None))

    def test_invalid_name_changes_nothing(self):
        self.assertAccountError(400, people.update_profile, self.conn, self.a, "가", None, TODAY)
        self.assertEqual(self.me(self.a)["name"], "가족에이")

    def test_prefs(self):
        self.assertEqual(self.me(self.a)["prefs"], {"device": True, "member": True, "home": True})
        people.set_pref(self.conn, self.a, "home", False)
        self.assertEqual(self.me(self.a)["prefs"], {"device": True, "member": True, "home": False})
        self.assertAccountError(400, people.set_pref, self.conn, self.a, "is_target", True)


class SetupTest(PeopleTestBase):
    def test_new_home_saves_everything(self):
        home_id = self.setup(self.a, {"birth": "1951-07-08", "conditions": ["고혈압"], "medications": None},
                             {"mode": "new", "address": "서울 마포구 월드컵로 100 101동 1203호"})
        me = self.me(self.a)
        self.assertTrue(me["isTarget"] and me["onboarded"])
        self.assertEqual((me["birth"], me["conditions"], me["medications"]), ("1951-07-08", ["고혈압"], None))
        self.assertEqual(me["homeIds"], [home_id])
        home = self.state(self.b)["homes"][0]
        self.assertEqual(home, {"id": home_id, "groupId": self.g1, "address": "서울 마포구 월드컵로 100 101동 1203호",
                                "centralPw": False, "doorPw": False})

    def test_existing_home_of_own_group(self):
        home_id = self.setup(self.a)
        self.assertEqual(self.setup(self.b, home={"mode": "existing", "id": home_id}), home_id)
        self.assertEqual(self.me(self.b)["homeIds"], [home_id])
        self.assertEqual(self.count("homes"), 1)

    def test_other_group_home_is_rejected_and_nothing_is_saved(self):
        home_c = self.setup(self.c)
        err = self.assertAccountError(404, self.setup, self.a, {"birth": "1951-07-08"}, {"mode": "existing", "id": home_c})
        self.assertEqual(err.field, "home")
        me = self.me(self.a)
        self.assertFalse(me["isTarget"] or me["onboarded"])   # 건강 정보도 같이 취소됨
        self.assertIsNone(me["birth"])
        self.assertEqual(self.me(self.c)["homeIds"], [home_c])

    def test_failure_in_the_middle_rolls_back_everything(self):
        self.fail_on("home_members", "INSERT")
        with self.assertRaises(sqlite3.DatabaseError):
            self.setup(self.a, {"birth": "1951-07-08"}, {"mode": "new", "address": "서울"})
        self.assertEqual(self.count("homes"), 0)               # 집도 만들어지지 않음
        self.assertFalse(self.me(self.a)["isTarget"])
        self.assertIsNone(self.me(self.a)["birth"])

    def test_invalid_input_saves_nothing(self):
        self.assertAccountError(400, self.setup, self.a, {"birth": "2999-01-01"})
        self.assertAccountError(400, self.setup, self.a, {}, {"mode": "?"})
        self.assertFalse(self.me(self.a)["isTarget"])
        self.assertEqual(self.count("homes"), 0)

    def test_needs_a_group(self):
        accounts.leave_group(self.conn, self.c)
        self.assertAccountError(409, self.setup, self.c)


class HomeTest(PeopleTestBase):
    def test_link_unlink_and_address_permissions(self):
        home_id = self.setup(self.a)
        # 연결 안 된 가족은 주소 수정 불가, 연결하면 가능 (젠스파크 설계)
        self.assertAccountError(403, people.update_home_address, self.conn, self.b, home_id, "서울 1", self.now)
        people.link_home(self.conn, self.b, home_id, self.now)
        people.update_home_address(self.conn, self.b, home_id, "서울 마포구 1", self.now)
        self.assertEqual(self.state(self.a)["homes"][0]["address"], "서울 마포구 1")
        people.unlink_home(self.conn, self.b, home_id)
        self.assertEqual(self.me(self.b)["homeIds"], [])
        self.assertAccountError(409, people.unlink_home, self.conn, self.b, home_id)
        self.assertEqual(self.count("homes"), 1)                # 집은 그룹에 남음

    def test_other_group_home_ids_are_not_found(self):
        home_a = self.setup(self.a, home={"mode": "new", "address": "에이네 집"})
        for fn, args in ((people.link_home, (home_a, self.now)), (people.unlink_home, (home_a,)),
                         (people.update_home_address, (home_a, "바꿈", self.now))):
            err = self.assertAccountError(404, fn, self.conn, self.c, *args)
            self.assertEqual(err.message, "집을 찾을 수 없어요.")
        self.assertEqual(self.state(self.a)["homes"][0]["address"], "에이네 집")
        self.assertEqual(self.state(self.c)["homes"], [])       # 다른 그룹의 집은 상태에도 없음


class LeaveAndWithdrawTest(PeopleTestBase):
    def test_leave_clears_shared_profile_but_keeps_group_for_others(self):
        home_id = self.setup(self.a, {"birth": "1951-07-08", "conditions": ["당뇨"]})
        self.setup(self.b, home={"mode": "existing", "id": home_id})
        accounts.leave_group(self.conn, self.a)
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (self.a,)).fetchone()
        self.assertEqual((row["is_target"], row["birth"], row["conditions"], row["group_id"]), (0, None, None, None))
        self.assertEqual(self.me(self.a)["homeIds"], [])
        self.assertEqual(self.me(self.b)["homeIds"], [home_id])   # 남은 가족과 집은 그대로
        self.assertEqual(len(self.state(self.b)["homes"]), 1)

    def test_last_member_leaving_deletes_group_and_homes(self):
        self.setup(self.c)
        accounts.leave_group(self.conn, self.c)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM groups WHERE id = ?", (self.g2,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM homes WHERE group_id = ?", (self.g2,)).fetchone()[0], 0)

    def test_withdraw_needs_the_password(self):
        err = self.assertAccountError(401, accounts.withdraw, self.conn, self.a, "wrong999", IP, self.now)
        self.assertEqual(err.field, "password")
        self.assertIsNotNone(self.conn.execute("SELECT 1 FROM users WHERE id = ?", (self.a,)).fetchone())
        limit, _ = accounts.LOGIN_LIMIT_PER_PHONE
        for _ in range(limit - 1):
            self.assertAccountError(401, accounts.withdraw, self.conn, self.a, "wrong999", IP, self.now)
        self.assertAccountError(429, accounts.withdraw, self.conn, self.a, PW, IP, self.now)

    def test_withdraw_with_others_left(self):
        home_id = self.setup(self.a, {"birth": "1951-07-08"})
        self.setup(self.b, home={"mode": "existing", "id": home_id})
        accounts.create_session(self.conn, self.a, now=self.now)
        accounts.withdraw(self.conn, self.a, PW, IP, self.now)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM users WHERE id = ?", (self.a,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (self.a,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM home_members WHERE user_id = ?", (self.a,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM auth_failures WHERE key LIKE '%01010000001%'").fetchone()[0], 0)
        # 그룹·집·다른 가족은 그대로
        state_b = self.state(self.b)
        self.assertEqual([p["name"] for p in state_b["people"]], ["가족비"])
        self.assertEqual([h["id"] for h in state_b["homes"]], [home_id])
        self.assertEqual(self.me(self.b)["homeIds"], [home_id])
        # 같은 번호로 다시 가입할 수 있음 (계정이 남아 있지 않음)
        self.signup(name="다시가입", phone="010-1000-0001")

    def test_withdraw_last_member_deletes_group_and_homes(self):
        self.setup(self.c)
        accounts.withdraw(self.conn, self.c, PW, IP, self.now)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM groups WHERE id = ?", (self.g2,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM homes WHERE group_id = ?", (self.g2,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM invites WHERE group_id = ?", (self.g2,)).fetchone()[0], 0)
        # 다른 그룹은 영향 없음
        self.assertEqual(len(self.state(self.a)["people"]), 2)

    def test_withdraw_failure_in_the_middle_deletes_nothing(self):
        self.setup(self.c)
        accounts.create_session(self.conn, self.c, now=self.now)
        self.fail_on("groups", "DELETE")   # 마지막 구성원 → 그룹 삭제 단계에서 오류
        with self.assertRaises(sqlite3.DatabaseError):
            accounts.withdraw(self.conn, self.c, PW, IP, self.now)
        self.assertIsNotNone(self.conn.execute("SELECT 1 FROM users WHERE id = ?", (self.c,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (self.c,)).fetchone()[0], 1)
        self.assertEqual(self.me(self.c)["homeIds"], [self.state(self.c)["homes"][0]["id"]])
