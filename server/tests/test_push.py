"""Family push notifications (push.py): who gets it, once per incident, phone tokens tied to login sessions,
failures that never touch the incident, and the real FCM sender against a fake OAuth/FCM server on this computer.
Nothing is sent to Google or to a phone.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import accounts
import incidents
import push
from accounts import AccountError
from tests.test_accounts import IP, PW
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import Browser
from tests.test_incidents import IncidentTestBase, S, T

TOK = "fcm-token-"   # 시험용 토큰 앞부분 (실제 토큰 아님)


class PushTestBase(IncidentTestBase):
    """Group 1: 에이 (target, home H) + 비 + 디 (family). Group 2: 씨 (target, own home)."""

    def session(self, user):
        cookie = accounts.create_session(self.conn, user, now=T / 1000 - 10)
        return accounts._token_hash(cookie)

    def phone(self, user, name, session=None):
        token = TOK + name + "-" + "x" * 30
        push.register_token(self.conn, user, session or self.session(user), token, now=T)
        return token

    def deliveries(self, kind="detected"):
        """{user_id: delivery} of one step (kind)."""
        return {r["user_id"]: dict(r) for r in self.conn.execute(
            "SELECT * FROM push_deliveries WHERE kind = ? ORDER BY id", (kind,))}

    def steps(self):
        return sorted((r["user_id"], r["kind"], r["n"]) for r in self.conn.execute("SELECT * FROM push_deliveries"))

    def send(self, sender, at=T + S):
        return push.process_due(self.conn, sender, now=at)


class ReceiversTest(PushTestBase):
    """Who gets a push at which step (user decision 2026-10-29): first detection → the detection targets of that
    home; 60 s without answer or the first help request → the family; a new fall while checking → the family;
    every 30 minutes of checking → the member who is checking. Once per step."""

    def test_first_detection_goes_to_the_detection_target_only(self):
        iid = self.fall()
        d = self.deliveries()
        self.assertEqual(set(d), {self.a})                                        # 감지 대상(에이)만, 가족은 아직
        self.assertNotIn(self.c, d)                                               # 다른 그룹 없음
        self.assertTrue(all(x["incident_id"] == iid and x["status"] == "pending" for x in d.values()))
        self.fall(at=T + 5 * S)                                                   # 진행 중에 다시 감지
        self.fall(at=T + 6 * S, key="dup")
        self.assertEqual(self.count("push_deliveries"), 1)                        # 다시 보내지 않음
        incidents.self_ok(self.conn, self.a, iid, now=T + 20 * S)
        second = self.fall(at=T + 30 * S)                                         # 끝난 뒤 새 사고 → 새로 한 번
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM push_deliveries WHERE incident_id = ?", (second,)).fetchone()[0], 1)

    def test_no_answer_in_60_seconds_goes_to_the_family(self):
        self.fall()
        incidents.tick(self.conn, T + 59 * S)
        self.assertEqual(self.deliveries("family_alert"), {})
        incidents.tick(self.conn, T + 60 * S)
        incidents.tick(self.conn, T + 61 * S)
        self.assertEqual(set(self.deliveries("family_alert")), {self.b, self.d})  # 가족 모두, 대상자 제외, 한 번
        self.assertEqual(self.count("push_deliveries"), 3)

    def test_first_help_request_goes_to_the_family_once(self):
        iid = self.fall()
        incidents.self_help(self.conn, self.a, iid, now=T + 10 * S)
        self.assertEqual(set(self.deliveries("help")), {self.b, self.d})
        incidents.self_help(self.conn, self.a, iid, now=T + 20 * S)               # 다시 눌러도 앱 알림만
        self.assertEqual(self.count("push_deliveries"), 3)
        self.assertEqual(self.kinds(self.b).count("help"), 2)

    def test_help_after_no_answer_is_pushed_too(self):
        iid = self.fall()
        incidents.tick(self.conn, T + 60 * S)
        incidents.self_help(self.conn, self.a, iid, now=T + 70 * S)
        self.assertEqual(set(self.deliveries("help")), {self.b, self.d})

    def test_new_fall_while_checking_and_checking_reminder(self):
        iid = self.fall(key="first")
        incidents.tick(self.conn, T + 60 * S)
        incidents.take_over(self.conn, self.b, iid, now=T + 70 * S)
        self.fall(at=T + 100 * S, key="second")
        self.fall(at=T + 101 * S, key="second")                                   # 기기 재전송
        self.assertEqual(set(self.deliveries("redetected")), {self.b, self.d})
        incidents.tick(self.conn, T + 70 * S + incidents.CHECKING_REMIND_MS)
        self.assertEqual(set(self.deliveries("checking_reminder")), {self.b})    # 확인 중인 가족만
        self.assertEqual(self.steps(), sorted([
            (self.a, "detected", 0), (self.b, "family_alert", 0), (self.d, "family_alert", 0),
            (self.b, "redetected", 1), (self.d, "redetected", 1), (self.b, "checking_reminder", 1)]))

    def test_other_group_incident_reaches_only_that_group(self):
        self.fall(home=self.home_c)
        self.assertEqual(set(self.deliveries()), {self.c})

    def test_sent_to_every_phone_of_every_member_and_nothing_else(self):
        a1, a2 = self.phone(self.a, "a1"), self.phone(self.a, "a2")              # 한 사람이 휴대폰 두 대
        b1 = self.phone(self.b, "b1")
        c1 = self.phone(self.c, "c1")                                             # 다른 그룹
        iid = self.fall()
        sender = push.FakeSender()
        self.assertEqual(self.send(sender), 1)                                    # 처음: 감지 대상자(에이)만
        self.assertEqual(sorted(m["message"]["token"] for m in sender.sent), sorted([a1, a2]))
        d = self.deliveries()
        self.assertEqual((d[self.a]["status"], d[self.a]["sent_count"]), ("simulated", 2))
        m = sender.sent[0]["message"]
        self.assertEqual((m["notification"]["body"], m["data"]["incidentId"], m["android"]["notification"]["channel_id"]),
                         ("낙상 사고가 감지됐어요. 확인해 주세요.", iid, "fall_alert"))
        incidents.tick(self.conn, T + 60 * S)                                    # 60초 무응답 → 가족
        sender.sent.clear()
        self.assertEqual(self.send(sender, at=T + 61 * S), 2)
        to = [m["message"]["token"] for m in sender.sent]
        self.assertEqual(to, [b1])
        self.assertNotIn(c1, to)
        d = self.deliveries("family_alert")
        self.assertEqual(d[self.b]["status"], "simulated")
        self.assertEqual(d[self.d]["status"], "no_token")                        # 앱을 설치하지 않은 가족
        m = sender.sent[0]["message"]
        self.assertEqual((m["notification"]["body"], m["data"]["step"]), (push.PUSH_TEXT["family_alert"], "family_alert"))
        for text in push.PUSH_TEXT.values():
            self.assertNotIn("가족", text)                                        # 이름 등 개인정보 없음
        self.assertEqual(self.send(sender, at=T + 99 * S), 0)                     # 다시 처리해도 다시 보내지 않음

    def test_member_who_left_the_group_meanwhile_gets_nothing(self):
        self.phone(self.b, "b1")
        self.fall()
        incidents.tick(self.conn, T + 60 * S)                                    # 가족 푸시 대기
        accounts.leave_group(self.conn, self.b)
        sender = push.FakeSender()
        self.send(sender, at=T + 61 * S)
        self.assertEqual(sender.sent, [])
        self.assertEqual(self.deliveries("family_alert")[self.b]["status"], "no_token")


class TokenTest(PushTestBase):
    def test_register_rules(self):
        s = self.session(self.a)
        for bad in ("", "short", "x" * 5000, "has space " + "x" * 30, None):
            with self.assertRaises(AccountError):
                push.register_token(self.conn, self.a, s, bad)
        with self.assertRaises(AccountError):
            push.register_token(self.conn, self.a, s, TOK + "x" * 30, platform="ios")

    def test_token_moves_to_the_phone_s_current_login(self):
        token = self.phone(self.a, "shared")
        push.register_token(self.conn, self.b, self.session(self.b), token, now=T)   # 같은 휴대폰에 다른 계정으로 로그인
        row = self.conn.execute("SELECT user_id FROM push_tokens WHERE token = ?", (token,)).fetchone()
        self.assertEqual(row["user_id"], self.b)
        self.assertEqual(self.count("push_tokens"), 1)

    def test_only_own_token_can_be_removed(self):
        token = self.phone(self.a, "a1")
        push.unregister_token(self.conn, self.b, token)                           # 다른 사람 토큰은 못 지움
        self.assertEqual(self.count("push_tokens"), 1)
        push.unregister_token(self.conn, self.a, token)
        self.assertEqual(self.count("push_tokens"), 0)

    def test_logout_expired_session_and_withdrawal_stop_pushes(self):
        cookie = accounts.create_session(self.conn, self.b, now=T / 1000 - 10)
        token_b = self.phone(self.b, "b1", session=accounts._token_hash(cookie))
        accounts.end_session(self.conn, cookie)                                   # 로그아웃 → 토큰도 삭제
        self.assertIsNone(self.conn.execute("SELECT 1 FROM push_tokens WHERE token = ?", (token_b,)).fetchone())
        old = accounts.create_session(self.conn, self.d, now=T / 1000 - (accounts.SESSION_DAYS + 10) * 86400)  # 만료된 세션의 토큰
        push.register_token(self.conn, self.d, accounts._token_hash(old), TOK + "d-old-" + "x" * 30, now=T)
        self.phone(self.a, "a1")
        self.fall()
        incidents.tick(self.conn, T + 60 * S)
        sender = push.FakeSender()
        self.send(sender, at=T + 61 * S)
        self.assertEqual(len(sender.sent), 1)                                     # 에이만
        self.assertEqual(self.deliveries("family_alert")[self.d]["status"], "no_token")
        accounts.withdraw(self.conn, self.a, PW, IP, now=T / 1000)  # 탈퇴 → 토큰 삭제
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM push_tokens WHERE user_id = ?", (self.a,)).fetchone()[0], 0)

    def test_too_many_phones_keeps_the_newest(self):
        s = self.session(self.a)
        for i in range(push.MAX_TOKENS_PER_USER + 3):
            push.register_token(self.conn, self.a, s, f"{TOK}{i:02d}-" + "x" * 30, now=T + i)
        self.assertEqual(self.count("push_tokens"), push.MAX_TOKENS_PER_USER)


class FailureTest(PushTestBase):
    def test_failures_never_touch_the_incident(self):
        bad, down, ok = self.phone(self.a, "bad"), self.phone(self.b, "down"), self.phone(self.d, "ok")
        self.conn.execute("UPDATE push_tokens SET token = 'bad-' || token WHERE token = ?", (bad,))
        self.conn.execute("UPDATE push_tokens SET token = 'down-' || token WHERE token = ?", (down,))
        iid = self.fall()
        sender = push.FakeSender()
        self.send(sender)
        self.assertEqual(self.deliveries()[self.a]["status"], "failed")          # 무효 토큰: 실패, 토큰 삭제
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM push_tokens WHERE user_id = ?", (self.a,)).fetchone()[0], 0)
        self.assertEqual(self.inc(iid)["status"], "detected")                    # 사고는 그대로
        incidents.tick(self.conn, now=T + 60 * S)
        self.assertEqual(self.inc(iid)["status"], "no_response")                 # 기존 알림 흐름도 그대로
        self.assertIn("family_alert", self.kinds(self.b))
        self.send(sender, at=T + 61 * S)
        d = self.deliveries("family_alert")
        self.assertEqual(d[self.b]["status"], "retry")                           # 일시 오류: 다시 시도
        self.assertEqual(d[self.d]["status"], "simulated")
        self.send(sender, at=T + 100 * S)
        self.send(sender, at=T + 300 * S)
        self.assertEqual(self.deliveries("family_alert")[self.b]["status"], "failed")   # 3번 뒤 포기
        self.assertEqual(self.deliveries("family_alert")[self.b]["attempts"], 3)

    def test_not_configured_marks_skipped(self):
        self.phone(self.a, "a1")
        self.fall()
        self.send(None)
        self.assertEqual({x["status"] for x in self.deliveries().values()}, {"skipped"})

    def test_queue_problem_does_not_stop_the_incident(self):
        self.conn.execute("DROP TABLE push_deliveries")
        iid = self.fall()
        self.assertEqual(self.inc(iid)["status"], "detected")


# ---- 실제 FCM 전송기: 이 컴퓨터의 가짜 OAuth·FCM 서버로 ----
def make_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return private.public_key(), pem


class FakeGoogle(BaseHTTPRequestHandler):
    log = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        FakeGoogle.log.append((self.path, dict(self.headers), body))
        if self.path == "/token":
            out, code = {"access_token": "test-access", "expires_in": 3600}, 200
        elif "unregistered" in body.decode():
            out, code = {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}}, 404
        else:
            out, code = {"name": "projects/test-project/messages/1"}, 200
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FcmSenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeGoogle)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_oauth_jwt_and_message(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        FakeGoogle.log.clear()
        public, pem = make_key()
        key = {"client_email": "sender@test-project.iam.gserviceaccount.com", "private_key": pem,
               "project_id": "test-project", "token_uri": self.base + "/token"}
        sender = push.FcmSender(key, api=self.base)
        msg = push.message(TOK + "y" * 30, "inc_1")
        sender.send(msg)
        sender.send(msg)                                                          # 액세스 토큰은 한 번만 받음
        paths = [p for p, _, _ in FakeGoogle.log]
        self.assertEqual(paths, ["/token", "/v1/projects/test-project/messages:send", "/v1/projects/test-project/messages:send"])
        assertion = FakeGoogle.log[0][2].decode().split("assertion=")[1]
        head, claims, sig = assertion.split(".")
        pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        public.verify(pad(sig), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())   # 서명 확인
        c = json.loads(pad(claims))
        self.assertEqual((c["iss"], c["scope"], c["aud"]), (key["client_email"], push.FCM_SCOPE, key["token_uri"]))
        self.assertEqual(FakeGoogle.log[1][1].get("Authorization"), "Bearer test-access")
        self.assertEqual(json.loads(FakeGoogle.log[1][2])["message"]["data"]["incidentId"], "inc_1")
        with self.assertRaises(push.PushError) as e:
            sender.send(push.message("unregistered-" + "y" * 30, "inc_1"))
        self.assertTrue(e.exception.invalid_token)

    def test_build_sender_from_settings(self):
        self.assertIsNone(push.build_sender({}))                                 # 설정 없음 → 보내지 않음
        self.assertIsInstance(push.build_sender({"PUSH_FAKE_URL": self.base + "/fake"}), push.FakeSender)
        self.assertIsNone(push.build_sender({"FCM_SERVICE_ACCOUNT_FILE": "C:/no/such/key.json"}))


# ---- API: 로그인한 휴대폰의 토큰 등록·해제, 서버 전체 흐름 (가짜 FCM 서버) ----
class FakeFcm(BaseHTTPRequestHandler):
    got = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        FakeFcm.got.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


class PushApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fcm = HTTPServer(("127.0.0.1", 0), FakeFcm)
        threading.Thread(target=cls.fcm.serve_forever, daemon=True).start()
        cls.server = ServerCopy(extra_env={"PUSH_FAKE_URL": f"http://127.0.0.1:{cls.fcm.server_port}/send", "FD_DEV_TOOLS": "1"})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.fcm.shutdown()

    def member(self, name, phone):
        b = Browser(self.server)
        self.assertEqual(b.call("POST", "/api/v2/auth/signup", {"name": name, "phone": phone, "password": "Famly2024pw"})[0], 200)
        return b

    def test_register_and_family_push_end_to_end(self):
        import time
        a, f, other = self.member("대상", "010-7100-0001"), self.member("가족", "010-7100-0002"), self.member("다른이", "010-7100-0003")
        code = a.call("POST", "/api/v2/groups")[2]["state"]["groups"][0]["invite"]["code"]
        home = a.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})[2]["state"]["homes"][0]["id"]
        f.call("POST", "/api/v2/groups/join", {"code": code})
        other.call("POST", "/api/v2/groups")
        self.assertEqual(Browser(self.server).call("POST", "/api/v2/me/push-token", {"token": TOK + "z" * 30})[0], 401)
        self.assertEqual(a.call("POST", "/api/v2/me/push-token", {"token": "bad"})[0], 400)
        for b, name in ((a, "a"), (f, "f"), (other, "o")):
            self.assertEqual(b.call("POST", "/api/v2/me/push-token", {"token": f"{TOK}{name}-" + "z" * 30})[0], 200)
        def wait_for(count):
            end = time.time() + 10
            while time.time() < end and len(FakeFcm.got) < count:
                time.sleep(0.2)
            time.sleep(1.5)
            return [m["message"]["token"] for m in FakeFcm.got]

        FakeFcm.got.clear()
        status, _, data = a.call("POST", "/api/v2/dev/falls", {"homeId": home, "location": "거실"})
        self.assertEqual(status, 200, data)
        self.assertEqual(wait_for(1), [f"{TOK}a-" + "z" * 30])                    # 처음: 감지 대상자만
        self.assertTrue(FakeFcm.got[0]["message"]["notification"]["title"].startswith("[개발 시험]"))
        iid = next(i["id"] for i in a.state()["state"]["incidents"] if i["status"] == "detected")
        FakeFcm.got.clear()
        self.assertEqual(a.call("POST", f"/api/v2/incidents/{iid}/help")[0], 200)
        self.assertEqual(wait_for(1), [f"{TOK}f-" + "z" * 30])                    # 도움 요청: 가족, 다른 그룹 없음
        # 로그아웃 → 그 휴대폰에는 더 이상 안 감
        self.assertEqual(f.call("POST", "/api/v2/auth/logout")[0], 200)
        a.call("DELETE", "/api/v2/me/push-token", {"token": f"{TOK}a-" + "z" * 30})   # 앱이 로그아웃 전에 지움
        with __import__("db").session(self.server.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM push_tokens").fetchone()[0], 1)   # 남은 건 다른 그룹 사람 것


if __name__ == "__main__":
    unittest.main()
