"""incidents.py, alerts.py and legacy_devices.py on a temporary database (D stage).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import sqlite3
import threading

import accounts
import alerts
import db
import incidents
import legacy_devices
from tests.test_people import PeopleTestBase

T = 1_800_000_000_000          # 감지 시각 (ms)
S = 1000


class IncidentTestBase(PeopleTestBase):
    """Group 1: 에이 (detection target, home H) + 비 (family) + 디 (family). Group 2: 씨 (target, own home)."""

    def setUp(self):
        super().setUp()
        self.home = self.setup(self.a)                      # 에이: 감지 대상, 집 H
        code = self.conn.execute("SELECT code FROM invites WHERE group_id = ?", (self.g1,)).fetchone()[0]
        self.d = self.signup(name="가족디", phone="010-1000-0004")
        accounts.join_group(self.conn, self.d, code, now=self.now)
        self.home_c = self.setup(self.c)                    # 씨: 다른 그룹의 감지 대상

    def fall(self, at=T, home=None, key=None, location="거실"):
        return incidents.create(self.conn, home or self.home, location, "dev", dedupe_key=key, now=at, detected_at=at)[0]

    def inc(self, iid):
        return self.conn.execute("SELECT * FROM incidents WHERE id = ?", (iid,)).fetchone()

    def view(self, user, iid):
        state = self.state(user)
        return next((i for i in state["incidents"] if i["id"] == iid), None)

    def notifs(self, user):
        return [(n["kind"], n["to"]) for n in self.state(user)["notifs"]]

    def kinds(self, user):
        return [n["kind"] for n in self.state(user)["notifs"]]

    def deliveries(self):
        return [dict(r) for r in self.conn.execute(
            """SELECT d.*, n.user_id, n.kind FROM notification_deliveries d JOIN notifications n ON n.id = d.notification_id
               ORDER BY d.id""")]


class CreateTest(IncidentTestBase):
    def test_create_and_state_shape(self):
        iid = self.fall()
        inc = self.view(self.b, iid)
        self.assertEqual((inc["status"], inc["homeId"], inc["groupId"], inc["location"], inc["detectedAt"]),
                         ("detected", self.home, self.g1, "거실", T))
        for key in ("response", "familyNotifiedAt", "autoReportAt", "checkedBy", "closedAt", "result", "reportedBy",
                    "reportKind", "recognizedId"):
            self.assertIsNone(inc[key], key)
        self.assertEqual((inc["helpTimes"], inc["reportedTargetIds"], inc["dismissed"]), ([], [], {}))
        self.assertEqual(inc["log"], [{"at": T, "text": "낙상이 감지됐어요"}])
        self.assertEqual(self.state(self.c)["incidents"], [])          # 다른 그룹에는 보이지 않음

    def test_same_event_and_open_incident_are_not_duplicated(self):
        first = self.fall(key="legacy:abc")
        self.assertEqual(self.fall(at=T + 5 * S, key="legacy:abc"), first)       # 같은 이벤트 재시도
        self.assertEqual(self.fall(at=T + 9 * S, key="legacy:other"), first)     # 같은 집에 진행 중 사고가 있음
        self.assertEqual(self.count("incidents"), 1)
        self.assertIn("같은 집에서 다시 감지됐어요", [l["text"] for l in self.view(self.a, first)["log"]])
        incidents.self_ok(self.conn, self.a, first, now=T + 20 * S)
        second = self.fall(at=T + 30 * S)                                      # 끝난 뒤에는 새 사고
        self.assertNotEqual(second, first)
        self.assertEqual(self.count("incidents"), 2)
        # DB 도 한 집에 진행 중인 사고를 둘 이상 허용하지 않음
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("""INSERT INTO incidents (id, group_id, home_id, source, location, detected_at, status,
                                 updated_at) VALUES ('x', ?, ?, 'dev', '방', 1, 'detected', 1)""", (self.g1, self.home))

    def test_invalid_input(self):
        self.assertAccountError(404, incidents.create, self.conn, "h_none", "거실", "dev")
        self.assertAccountError(400, incidents.create, self.conn, self.home, "", "dev")
        self.assertAccountError(400, incidents.create, self.conn, self.home, "가" * 21, "dev")
        self.assertEqual(self.count("incidents"), 0)


class TimeTest(IncidentTestBase):
    def test_no_response_then_automatic_report_simulation(self):
        iid = self.fall()
        self.assertEqual(incidents.tick(self.conn, T + 59_999), 0)
        self.assertEqual(self.inc(iid)["status"], "detected")
        self.assertEqual(incidents.tick(self.conn, T + 60 * S), 1)
        inc = self.inc(iid)
        self.assertEqual((inc["status"], inc["family_notified_at"], inc["auto_report_at"]),
                         ("no_response", T + 60 * S, T + 240 * S))
        self.assertEqual(self.kinds(self.b), ["family_alert"])            # 가족에게
        self.assertEqual(self.kinds(self.d), ["family_alert"])
        self.assertEqual(self.kinds(self.a), [])                          # 낙상 대상자는 긴급 화면으로 (알림 기록 없음)
        self.assertEqual([(d["user_id"], d["kind"], d["status"]) for d in self.deliveries()],
                         [(self.b, "family_alert", "pending"), (self.d, "family_alert", "pending")])
        self.assertEqual(incidents.tick(self.conn, T + 240 * S - 1), 0)
        self.assertEqual(incidents.tick(self.conn, T + 240 * S), 1)
        v = self.view(self.b, iid)
        self.assertEqual((v["status"], v["result"], v["reportKind"], v["reportedBy"], v["reportedAt"], v["closedAt"],
                          v["response"], v["autoReportAt"], v["reportedTargetIds"]),
                         ("reported", "auto_reported", "simulation", "auto", T + 240 * S, T + 240 * S, "none", None, [self.a]))
        self.assertIn("모의 신고", v["log"][-1]["text"])
        self.assertIn("실제 119에는 연락하지 않았어요", v["log"][-1]["text"])
        self.assertEqual(self.kinds(self.a), ["auto_reported"])
        self.assertEqual(self.kinds(self.b), ["family_alert", "auto_reported"])
        self.assertEqual(incidents.tick(self.conn, T + 999 * S), 0)       # 끝난 사고는 그대로

    def test_restart_late_processing_uses_original_times(self):
        iid = self.fall()
        self.conn.close()                                                   # 서버 재시작 (새 연결)
        self.conn = db.connect(self.path)
        incidents.tick(self.conn, T + 600 * S)                             # 꺼져 있다가 늦게 처리
        v = self.view(self.b, iid)
        self.assertEqual((v["status"], v["familyNotifiedAt"], v["reportedAt"]), ("reported", T + 60 * S, T + 240 * S))
        self.assertTrue(v["log"][1]["text"].endswith("(서버가 늦게 처리했어요)"))
        self.assertTrue(v["log"][2]["text"].endswith("(서버가 늦게 처리했어요)"))

    def test_help_deadline_is_first_request_plus_180s(self):
        iid = self.fall()
        self.assertEqual(incidents.self_help(self.conn, self.a, iid, now=T + 10 * S), 1)
        self.assertEqual(incidents.self_help(self.conn, self.a, iid, now=T + 70 * S), 2)
        incidents.tick(self.conn, T + 80 * S)                               # 도움 요청 중에는 무응답 전환 없음
        inc = self.inc(iid)
        self.assertEqual((inc["status"], inc["family_notified_at"], inc["auto_report_at"], inc["response"]),
                         ("help", T + 10 * S, T + 190 * S, "within60"))
        self.assertEqual([(k, n["text"].endswith(f"({i + 1}번째)")) for i, (k, n) in enumerate(
            (n["kind"], n) for n in self.state(self.b)["notifs"])], [("help", True), ("help", True)])
        # 문자는 처음 가족에게 알릴 때만
        self.assertEqual([d["kind"] for d in self.deliveries()], ["help", "help"])
        self.assertEqual({d["user_id"] for d in self.deliveries()}, {self.b, self.d})
        incidents.tick(self.conn, T + 190 * S)
        self.assertEqual(self.inc(iid)["result"], "auto_reported")

    def test_help_after_no_response_keeps_deadline(self):
        iid = self.fall()
        incidents.tick(self.conn, T + 60 * S)
        incidents.self_help(self.conn, self.a, iid, now=T + 100 * S)
        inc = self.inc(iid)
        self.assertEqual((inc["status"], inc["auto_report_at"], inc["response"]), ("help", T + 240 * S, "after60"))
        self.assertEqual([d["kind"] for d in self.deliveries()], ["family_alert", "family_alert"])   # 도움 문자 추가 없음


class ActionTest(IncidentTestBase):
    def test_self_ok(self):
        iid = self.fall()
        self.assertAccountError(403, incidents.self_ok, self.conn, self.b, iid, now=T + S)    # 가족은 응답 불가
        self.assertAccountError(404, incidents.self_ok, self.conn, self.c, iid, now=T + S)    # 다른 그룹
        incidents.self_ok(self.conn, self.a, iid, now=T + 30 * S)
        v = self.view(self.a, iid)
        self.assertEqual((v["status"], v["result"], v["closedBy"], v["response"], v["reportKind"]),
                         ("closed", "self", self.a, "within60", None))
        self.assertEqual(v["log"][-1]["text"], "가족에이님이 괜찮다고 응답했어요")
        self.assertEqual(self.kinds(self.b), [])                             # 가족 알림 전이면 가족에게 알리지 않음
        err = self.assertAccountError(409, incidents.self_ok, self.conn, self.a, iid, now=T + 31 * S)
        self.assertEqual(err.message, "이미 신고되었거나 종료된 사고예요.")

    def test_take_over_and_close(self):
        iid = self.fall()
        self.assertAccountError(409, incidents.take_over, self.conn, self.b, iid, now=T + S)   # 가족 알림 전
        incidents.tick(self.conn, T + 60 * S)
        self.assertAccountError(403, incidents.take_over, self.conn, self.a, iid, now=T + 61 * S)   # 낙상 대상자
        incidents.take_over(self.conn, self.b, iid, now=T + 70 * S)
        inc = self.inc(iid)
        self.assertEqual((inc["status"], inc["checked_by"], inc["checked_at"], inc["auto_report_at"]),
                         ("checking", self.b, T + 70 * S, None))
        incidents.tick(self.conn, T + 999 * S)
        self.assertEqual(self.inc(iid)["status"], "checking")              # 자동 신고 멈춤
        self.assertAccountError(409, incidents.take_over, self.conn, self.d, iid, now=T + 71 * S)
        self.assertAccountError(409, incidents.self_help, self.conn, self.a, iid, now=T + 72 * S)
        self.assertAccountError(409, incidents.close_checked, self.conn, self.d, iid, now=T + 73 * S)
        incidents.close_checked(self.conn, self.b, iid, now=T + 80 * S)
        v = self.view(self.d, iid)
        self.assertEqual((v["status"], v["result"], v["closedBy"]), ("closed", "family", self.b))
        self.assertEqual(self.kinds(self.d), ["family_alert", "checked", "closed"])
        self.assertEqual(self.kinds(self.a), ["checked", "closed"])
        self.assertEqual(self.kinds(self.b), ["family_alert"])               # 내가 한 일은 내게 알리지 않음

    def test_report_simulation_and_targets(self):
        iid = self.fall()
        self.assertAccountError(400, incidents.report, self.conn, self.b, iid, [self.d], now=T + S)   # 대상자 아님
        self.assertAccountError(404, incidents.report, self.conn, self.c, iid, [], now=T + S)
        incidents.report(self.conn, self.b, iid, [self.a], now=T + 5 * S)
        v = self.view(self.a, iid)
        self.assertEqual((v["status"], v["result"], v["reportKind"], v["reportedBy"], v["reportedTargetIds"]),
                         ("reported", "reported", "simulation", self.b, [self.a]))
        self.assertIn("모의 신고", v["log"][-1]["text"])
        self.assertAccountError(409, incidents.report, self.conn, self.d, iid, [], now=T + 6 * S)   # 중복 신고 없음
        self.assertEqual(self.count("incidents"), 1)
        self.assertEqual([d["kind"] for d in self.deliveries()], ["reported", "reported"])   # 에이·디에게 (신고한 비 제외)

    def test_dismiss_is_per_person_and_idempotent(self):
        iid = self.fall()
        incidents.self_ok(self.conn, self.a, iid, now=T + S)
        incidents.dismiss(self.conn, self.b, iid, now=T + 2 * S)
        incidents.dismiss(self.conn, self.b, iid, now=T + 3 * S)
        self.assertEqual(self.view(self.b, iid)["dismissed"], {self.b: True})
        self.assertAccountError(404, incidents.dismiss, self.conn, self.c, iid)

    def test_names_are_not_stored(self):
        iid = self.fall()
        incidents.self_help(self.conn, self.a, iid, now=T + S)
        accounts_rows = self.conn.execute("SELECT * FROM incident_log").fetchall()
        self.assertNotIn("가족에이", repr([tuple(r) for r in accounts_rows]))
        self.conn.execute("UPDATE users SET name = '새이름' WHERE id = ?", (self.a,))
        self.assertIn("새이름님이 도움이 필요하다고", self.view(self.b, iid)["log"][-1]["text"])

    def test_leaving_the_group_removes_my_notifications(self):
        iid = self.fall()
        incidents.tick(self.conn, T + 60 * S)
        accounts.leave_group(self.conn, self.d)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ?", (self.d,)).fetchone()[0], 0)
        self.assertEqual(self.state(self.d)["incidents"], [])
        self.assertEqual(self.view(self.b, iid)["status"], "no_response")   # 사고 기록은 그룹에 남음


class ConcurrencyTest(IncidentTestBase):
    def race(self, *calls):
        """Run the calls at the same moment on separate connections (like separate requests)."""
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(i, fn, args):
            conn = db.connect(self.path)
            try:
                barrier.wait()
                fn(conn, *args)
                results[i] = "ok"
            except accounts.AccountError as e:
                results[i] = e.status
            finally:
                conn.close()

        threads = [threading.Thread(target=run, args=(i, fn, args)) for i, (fn, args) in enumerate(calls)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def test_two_family_members_take_over_at_once(self):
        for round_no in range(5):
            iid = self.fall(at=T + round_no * 1000 * S)
            incidents.tick(self.conn, T + round_no * 1000 * S + 60 * S)
            results = self.race((incidents.take_over, (self.b, iid)), (incidents.take_over, (self.d, iid)))
            self.assertEqual(sorted(results, key=str), [409, "ok"], results)
            winner = self.b if results[0] == "ok" else self.d
            self.assertEqual(self.inc(iid)["checked_by"], winner)
            self.assertEqual([l["text"] for l in self.view(self.a, iid)["log"]].count(
                f"{'가족비' if winner == self.b else '가족디'}님이 확인했어요"), 1)
            incidents.close_checked(self.conn, winner, iid)

    def test_report_and_self_ok_at_once(self):
        iid = self.fall()
        results = self.race((incidents.report, (self.b, iid, [])), (incidents.self_ok, (self.a, iid)))
        self.assertEqual(sorted(results, key=str), [409, "ok"], results)
        inc = self.inc(iid)
        self.assertEqual(inc["status"], "reported" if results[0] == "ok" else "closed")
        self.assertEqual(self.count("incident_targets"), 1 if results[0] == "ok" else 0)

    def test_same_event_from_two_requests(self):
        results = self.race(*[(lambda conn: legacy_devices.add(conn, "pc", self.home, "거실"), ())])
        self.assertEqual(results, ["ok"])
        got = []
        lock = threading.Lock()

        def send(conn):
            iid = legacy_devices.incident_for_event(conn, "pc", "e" * 32, False)
            with lock:
                got.append(iid)

        self.race((send, ()), (send, ()), (send, ()))
        self.assertEqual(len(set(got)), 1)
        self.assertEqual(self.count("incidents"), 1)


class SmsTest(IncidentTestBase):
    def queue_two(self):
        iid = self.fall()
        incidents.tick(self.conn, T + 60 * S)            # 비·디에게 무응답 문자 대기
        return iid

    def test_mock_sender_is_recorded_as_simulated_never_sent(self):
        self.queue_two()
        sender = alerts.MockSmsSender()
        self.assertEqual(alerts.process_due(self.conn, sender, T + 60 * S), 2)
        rows = self.deliveries()
        self.assertEqual([(r["status"], r["provider"], r["attempts"]) for r in rows], [("simulated", "mock", 1)] * 2)
        self.assertNotIn("sent", [r["status"] for r in rows])
        self.assertEqual({s["phone"] for s in sender.sent}, {"01010000002", "01010000004"})
        body = sender.sent[0]["body"]
        self.assertTrue(body.startswith("[지킴이] 가족에이님 댁 거실에서 낙상이 감지됐는데 응답이 없어요"), body)
        self.assertEqual(alerts.process_due(self.conn, sender, T + 999 * S), 0)    # 다시 보내지 않음

    def test_retry_then_success_and_final_failure(self):
        self.queue_two()
        sender = alerts.MockSmsSender(fail_plan=[alerts.SmsError("timeout"), alerts.SmsError("bad number", retryable=False)])
        alerts.process_due(self.conn, sender, T + 60 * S)
        rows = self.deliveries()
        self.assertEqual([(r["status"], r["attempts"], r["next_attempt_at"]) for r in rows],
                         [("retry", 1, T + 90 * S), ("failed", 1, None)])
        self.assertEqual(alerts.process_due(self.conn, sender, T + 89 * S), 0)    # 아직 다시 시도할 때가 아님
        alerts.process_due(self.conn, sender, T + 90 * S)
        self.assertEqual([r["status"] for r in self.deliveries()], ["simulated", "failed"])

    def test_gives_up_after_max_attempts(self):
        self.queue_two()
        sender = alerts.MockSmsSender(fail_plan=[alerts.SmsError("down")] * 6)
        for at in (60, 90, 210):
            alerts.process_due(self.conn, sender, T + at * S)
        self.assertEqual([(r["status"], r["attempts"]) for r in self.deliveries()], [("failed", 3)] * 2)

    def test_real_sender_success_would_be_sent(self):
        class FakeRealSender(alerts.SmsSender):   # 실제 업체 모양만 (네트워크 없음)
            name, simulated = "fake-real", False

            def send(self, phone, body):
                return "ref-1"
        self.queue_two()
        alerts.process_due(self.conn, FakeRealSender(), T + 60 * S)
        self.assertEqual({r["status"] for r in self.deliveries()}, {"sent"})

    def test_build_sender_is_always_mock(self):
        self.assertIsInstance(alerts.build_sender({}), alerts.MockSmsSender)
        self.assertIsInstance(alerts.build_sender({"SMS_PROVIDER": "someco"}), alerts.MockSmsSender)

    def test_no_phone_numbers_or_health_info_in_message(self):
        self.queue_two()
        bodies = [r["body"] for r in self.deliveries()]
        for body in bodies:
            self.assertNotRegex(body, r"010-?\d{4}")
            self.assertNotIn("1951", body)


class LegacyDeviceTest(IncidentTestBase):
    def test_only_registered_devices_create_incidents(self):
        self.assertIsNone(legacy_devices.incident_for_event(self.conn, "laptop", "a" * 32, False))
        self.assertAccountError(404, legacy_devices.add, self.conn, "laptop", "h_none", "거실")
        legacy_devices.add(self.conn, "laptop", self.home, "안방")
        self.assertIsNone(legacy_devices.incident_for_event(self.conn, "laptop", "b" * 32, True))   # 시험 이벤트
        iid = legacy_devices.incident_for_event(self.conn, "laptop", "c" * 32, False)
        self.assertEqual(legacy_devices.incident_for_event(self.conn, "laptop", "c" * 32, False), iid)
        inc = self.inc(iid)
        self.assertEqual((inc["source"], inc["source_ref"], inc["location"], inc["home_id"]), ("legacy", "laptop", "안방", self.home))
        self.assertEqual(legacy_devices.remove(self.conn, "laptop"), 1)
        self.assertIsNone(legacy_devices.incident_for_event(self.conn, "laptop", "d" * 32, False))
        self.assertEqual(self.count("incidents"), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
