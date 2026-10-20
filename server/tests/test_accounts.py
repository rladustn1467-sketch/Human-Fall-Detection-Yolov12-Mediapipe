"""accounts.py on a temporary database: passwords, sessions, rate limits, groups, invites, isolation.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import tempfile
import unittest
from pathlib import Path

import accounts
import db

IP = "10.0.0.1"
PW = "abcd1234"


class AccountsTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        db.init(self.path)
        self.conn = db.connect(self.path)
        self.now = 1_800_000_000.0

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def signup(self, name="김가족", phone="010-1111-2222", password=PW, ip=IP):
        return accounts.signup(self.conn, name, phone, password, ip, now=self.now)

    def assertAccountError(self, status, fn, *args, **kwargs):
        with self.assertRaises(accounts.AccountError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.status, status, ctx.exception.message)
        return ctx.exception


class InputTest(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(accounts.normalize_phone("010-1234-5678"), "01012345678")
        self.assertEqual(accounts.normalize_phone("011 123 4567"), "0111234567")
        self.assertIsNone(accounts.normalize_phone("02-123-4567"))
        self.assertIsNone(accounts.normalize_phone("010-12"))
        self.assertEqual(accounts.format_phone("01012345678"), "010-1234-5678")

    def test_password_rule_matches_signup_screen(self):
        self.assertEqual(accounts.password_problem("abcd1234"), "")
        self.assertIn("8~64자", accounts.password_problem("abc123"))
        self.assertIn("8~64자", accounts.password_problem("a1" * 33))
        self.assertIn("영문과 숫자", accounts.password_problem("abcdefgh"))
        self.assertIn("영문과 숫자", accounts.password_problem("12345678"))
        self.assertEqual(accounts.password_problem(" abcd1234 "), "")  # 공백 포함 그대로 허용


class PasswordHashTest(unittest.TestCase):
    def test_hash_is_salted_and_never_contains_the_password(self):
        h1, h2 = accounts.hash_password(PW), accounts.hash_password(PW)
        self.assertNotEqual(h1, h2)
        self.assertTrue(h1.startswith("scrypt$16384$8$1$"))
        self.assertNotIn(PW, h1)

    def test_verify(self):
        stored = accounts.hash_password(PW)
        self.assertTrue(accounts.verify_password(PW, stored))
        self.assertFalse(accounts.verify_password("abcd1235", stored))
        self.assertFalse(accounts.verify_password(PW, "garbage"))
        self.assertFalse(accounts.verify_password(PW, "md5$x$y$z$a$b"))


class SignupLoginTest(AccountsTestBase):
    def test_signup_stores_hash_only(self):
        user_id = self.signup()
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        self.assertEqual(row["phone"], "01011112222")
        self.assertNotIn(PW, row["password_hash"])
        self.assertTrue(accounts.verify_password(PW, row["password_hash"]))
        dump = "\n".join(self.conn.iterdump())
        self.assertNotIn(PW, dump)

    def test_signup_validation(self):
        self.assertEqual(self.assertAccountError(400, self.signup, name="김").field, "name")
        self.assertEqual(self.assertAccountError(400, self.signup, phone="12345").field, "phone")
        self.assertEqual(self.assertAccountError(400, self.signup, password="short1").field, "password")

    def test_duplicate_phone(self):
        self.signup()
        err = self.assertAccountError(409, self.signup, name="다른사람", phone="01011112222")
        self.assertEqual(err.field, "phone")

    def test_login(self):
        user_id = self.signup()
        self.assertEqual(accounts.authenticate(self.conn, "010-1111-2222", PW, IP, now=self.now), user_id)
        self.assertAccountError(401, accounts.authenticate, self.conn, "010-1111-2222", "wrong123", IP, now=self.now)
        self.assertAccountError(401, accounts.authenticate, self.conn, "010-9999-9999", PW, IP, now=self.now)

    def test_login_limit_per_phone(self):
        self.signup()
        limit, window = accounts.LOGIN_LIMIT_PER_PHONE
        for _ in range(limit):
            self.assertAccountError(401, accounts.authenticate, self.conn, "010-1111-2222", "wrong123", IP, now=self.now)
        # 맞는 비밀번호라도 제한 중에는 거절
        err = self.assertAccountError(429, accounts.authenticate, self.conn, "010-1111-2222", PW, IP, now=self.now + 1)
        self.assertGreater(err.retry_after, 0)
        # 기간이 지나면 다시 로그인 가능, 성공하면 실패 기록 삭제
        self.assertTrue(accounts.authenticate(self.conn, "010-1111-2222", PW, IP, now=self.now + window + 1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM auth_failures WHERE key LIKE 'login-phone:%'").fetchone()[0], 0)

    def test_login_limit_per_ip(self):
        limit, _ = accounts.LOGIN_LIMIT_PER_IP
        for i in range(limit):
            self.assertAccountError(401, accounts.authenticate, self.conn, f"010-5555-{i:04d}", "wrong123", IP, now=self.now)
        self.assertAccountError(429, accounts.authenticate, self.conn, "010-5555-9999", "wrong123", IP, now=self.now)
        self.assertAccountError(401, accounts.authenticate, self.conn, "010-5555-9999", "wrong123", "10.0.0.2", now=self.now)

    def test_signup_limit_per_ip(self):
        limit, _ = accounts.SIGNUP_LIMIT_PER_IP
        for i in range(limit):
            self.signup(phone=f"010-7777-{i:04d}")
        self.assertAccountError(429, self.signup, phone="010-7777-9999")


class SessionTest(AccountsTestBase):
    def test_session_lifecycle(self):
        user_id = self.signup()
        token = accounts.create_session(self.conn, user_id, now=self.now)
        self.assertEqual(accounts.session_user(self.conn, token, now=self.now + 1), user_id)
        # 쿠키 값 자체는 저장하지 않음 (해시만)
        stored = [r[0] for r in self.conn.execute("SELECT token_hash FROM sessions")]
        self.assertNotIn(token, stored)
        self.assertEqual(len(stored[0]), 64)
        accounts.end_session(self.conn, token)
        self.assertIsNone(accounts.session_user(self.conn, token, now=self.now + 2))

    def test_session_expires(self):
        user_id = self.signup()
        token = accounts.create_session(self.conn, user_id, now=self.now)
        self.assertIsNone(accounts.session_user(self.conn, token, now=self.now + accounts.SESSION_DAYS * 86400 + 1))

    def test_bad_tokens(self):
        self.assertIsNone(accounts.session_user(self.conn, None))
        self.assertIsNone(accounts.session_user(self.conn, "x" * 500))
        self.assertIsNone(accounts.session_user(self.conn, "not-a-token"))


class GroupTest(AccountsTestBase):
    def setUp(self):
        super().setUp()
        self.a = self.signup(name="가족에이", phone="010-1000-0001")
        self.b = self.signup(name="가족비", phone="010-1000-0002")
        self.c = self.signup(name="다른집", phone="010-1000-0003")

    def invite_code(self, user_id):
        return accounts.state_for(self.conn, user_id, now=self.now)["groups"][0]["invite"]["code"]

    def test_create_group_and_invite(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        state = accounts.state_for(self.conn, self.a, now=self.now)
        self.assertEqual(state["groups"][0]["name"], "가족에이님의 가족")
        invite = state["groups"][0]["invite"]
        self.assertEqual(len(invite["code"]), accounts.INVITE_LENGTH)
        self.assertTrue(set(invite["code"]) <= set(accounts.INVITE_ALPHABET))
        self.assertEqual(invite["expiresAt"] - invite["createdAt"], accounts.INVITE_HOURS * 3600 * 1000)
        self.assertAccountError(409, accounts.create_group, self.conn, self.a, now=self.now)

    def test_join_with_code(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        accounts.join_group(self.conn, self.b, self.invite_code(self.a).lower(), now=self.now + 10)
        members = [p["name"] for p in accounts.state_for(self.conn, self.b, now=self.now)["people"]]
        self.assertEqual(members, ["가족에이", "가족비"])

    def test_new_code_replaces_old(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        old = self.invite_code(self.a)
        accounts.regenerate_invite(self.conn, self.a, now=self.now + 5)
        self.assertNotEqual(self.invite_code(self.a), old)
        err = self.assertAccountError(400, accounts.join_group, self.conn, self.b, old, now=self.now + 6)
        self.assertEqual(err.field, "code")

    def test_invite_expires_after_24_hours(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        code = self.invite_code(self.a)
        expiry = self.now + accounts.INVITE_HOURS * 3600
        err = self.assertAccountError(400, accounts.join_group, self.conn, self.b, code, now=expiry + 1)
        self.assertIn("만료", err.message)
        accounts.join_group(self.conn, self.b, code, now=expiry - 1)

    def test_join_limit(self):
        limit, _ = accounts.JOIN_LIMIT_PER_USER
        for _ in range(limit):
            self.assertAccountError(400, accounts.join_group, self.conn, self.b, "ZZZZZZ", now=self.now)
        self.assertAccountError(429, accounts.join_group, self.conn, self.b, "ZZZZZZ", now=self.now)

    def test_groups_are_isolated(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        accounts.create_group(self.conn, self.c, now=self.now)
        state_a = accounts.state_for(self.conn, self.a, now=self.now)
        state_c = accounts.state_for(self.conn, self.c, now=self.now)
        self.assertNotEqual(state_a["groups"][0]["id"], state_c["groups"][0]["id"])
        self.assertEqual([p["id"] for p in state_a["people"]], [self.a])
        self.assertEqual([p["id"] for p in state_c["people"]], [self.c])
        # 그룹이 없는 사람은 자기 정보만
        self.assertEqual([p["id"] for p in accounts.state_for(self.conn, self.b, now=self.now)["people"]], [self.b])
        self.assertEqual(accounts.state_for(self.conn, self.b, now=self.now)["groups"], [])

    def test_already_in_group_cannot_join_another(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        accounts.create_group(self.conn, self.c, now=self.now)
        self.assertAccountError(409, accounts.join_group, self.conn, self.c, self.invite_code(self.a), now=self.now)

    def test_leave_group(self):
        accounts.create_group(self.conn, self.a, now=self.now)
        accounts.join_group(self.conn, self.b, self.invite_code(self.a), now=self.now)
        accounts.leave_group(self.conn, self.b)
        self.assertIsNone(accounts.state_for(self.conn, self.b, now=self.now)["people"][0]["groupId"])
        group_id = accounts.state_for(self.conn, self.a, now=self.now)["groups"][0]["id"]
        accounts.leave_group(self.conn, self.a)
        # 아무도 없는 그룹은 초대 코드와 함께 삭제
        self.assertIsNone(self.conn.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone())
        self.assertIsNone(self.conn.execute("SELECT 1 FROM invites WHERE group_id = ?", (group_id,)).fetchone())

    def test_onboarded(self):
        accounts.set_onboarded(self.conn, self.a, True)
        self.assertTrue(accounts.state_for(self.conn, self.a, now=self.now)["people"][0]["onboarded"])


if __name__ == "__main__":
    unittest.main()
