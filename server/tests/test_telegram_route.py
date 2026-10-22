"""Registered device modes (incident / both) and Telegram as an alert channel of the new incidents, on a
temporary database with fake senders (no network, no real Telegram).

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import alerts
import incidents
import legacy_devices
import notifiers
from tests.test_incidents import S, T, IncidentTestBase


class DeviceModeTest(IncidentTestBase):
    def test_modes(self):
        self.assertIsNone(legacy_devices.mode_for(self.conn, "laptop"))                   # 미등록 = 옛 흐름만
        legacy_devices.add(self.conn, "laptop", self.home, "거실")
        self.assertEqual(legacy_devices.mode_for(self.conn, "laptop"), "incident")       # 새 등록 기본값
        legacy_devices.add(self.conn, "laptop", self.home, "거실", "both")
        self.assertEqual(legacy_devices.mode_for(self.conn, "laptop"), "both")
        self.assertAccountError(400, legacy_devices.add, self.conn, "laptop", self.home, "거실", "telegram")
        self.assertEqual(legacy_devices.entries(self.conn)[0]["mode"], "both")

    def test_rows_registered_before_migration_7_keep_both(self):
        # 7번 변경 전 등록(방식 칸 없이 넣은 줄)은 지금 동작(두 흐름)을 유지
        self.conn.execute("INSERT INTO legacy_device_homes (device_id, home_id, location, created_at) VALUES ('old', ?, '방', 1)",
                          (self.home,))
        self.assertEqual(legacy_devices.mode_for(self.conn, "old"), "both")


class TelegramRouteTest(IncidentTestBase):
    def setUp(self):
        super().setUp()
        legacy_devices.add_telegram(self.conn, self.g1, "777")

    def rows(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM telegram_deliveries ORDER BY id")]

    def test_routes(self):
        self.assertAccountError(404, legacy_devices.add_telegram, self.conn, "g_none", "1")
        self.assertAccountError(400, legacy_devices.add_telegram, self.conn, self.g1, "")
        legacy_devices.add_telegram(self.conn, self.g1, "777")                          # 두 번 등록해도 하나
        self.assertEqual(legacy_devices.telegram_entries(self.conn), [{"group_id": self.g1, "chat_id": "777"}])
        self.assertEqual(legacy_devices.remove_telegram(self.conn, self.g1, "777"), 1)
        iid = self.fall()
        incidents.tick(self.conn, T + 60 * S)
        self.assertEqual(self.rows(), [])                                                 # 대화방이 없으면 보내지 않음

    def test_one_message_per_step_without_buttons(self):
        legacy_devices.add_telegram(self.conn, self.g1, "888")
        iid = incidents.create(self.conn, self.home, "거실", "legacy", dedupe_key="legacy:x", now=T)[0]
        self.assertEqual(self.rows(), [])                                                 # 감지 순간에는 없음 (옛 흐름과 같음)
        incidents.tick(self.conn, T + 60 * S)
        incidents.tick(self.conn, T + 61 * S)                                             # 다시 돌아도 중복 없음
        incidents.self_help(self.conn, self.a, iid, now=T + 70 * S)
        incidents.take_over(self.conn, self.b, iid, now=T + 80 * S)
        incidents.close_checked(self.conn, self.b, iid, now=T + 90 * S)
        alerts.queue_telegram(self.conn, self.g1, iid, "closed", self.b, T + 91 * S)       # 같은 알림을 다시 예약해도 하나
        got = [(r["chat_id"], r["kind"], r["n"]) for r in self.rows()]
        self.assertEqual(sorted(got), sorted([(c, k, n) for c in ("777", "888")
                                              for k, n in (("family_alert", 0), ("help", 1), ("checked", 0), ("closed", 0))]))
        body = {r["kind"]: r["body"] for r in self.rows() if r["chat_id"] == "777"}
        self.assertEqual(body["family_alert"],
                         "[지킴이] 가족에이님 댁 거실에서 낙상이 감지됐는데 60초 동안 응답이 없어요. 앱에서 확인해 주세요.")
        self.assertIn("가족에이님이 도움을 요청했어요 (1번째)", body["help"])
        self.assertIn("가족비님이 확인하고 있어요", body["checked"])
        for text in body.values():
            self.assertNotRegex(text, r"010-?\d{4}")
            self.assertNotIn("확인했어요'", text)

    def test_report_messages_say_simulation_and_dev_falls_are_marked(self):
        iid = self.fall()                                                                 # source 'dev'
        incidents.report(self.conn, self.b, iid, [], now=T + 5 * S)
        (row,) = self.rows()
        self.assertTrue(row["body"].startswith("[개발 시험] [지킴이]"))
        self.assertIn("모의 신고, 실제 119에는 연락되지 않았어요", row["body"])

    def test_other_group_is_not_sent_here(self):
        incidents.create(self.conn, self.home_c, "안방", "legacy", now=T)
        incidents.tick(self.conn, T + 60 * S)
        self.assertEqual(self.rows(), [])

    def test_send_retry_failure_and_not_configured(self):
        self.fall()
        incidents.tick(self.conn, T + 60 * S)
        fake = alerts.FakeTelegramSender(fail_plan=[alerts.SmsError("timeout")])
        alerts.process_telegram_due(self.conn, fake, T + 60 * S)
        self.assertEqual([(r["status"], r["attempts"]) for r in self.rows()], [("retry", 1)])
        alerts.process_telegram_due(self.conn, fake, T + 90 * S)
        self.assertEqual([r["status"] for r in self.rows()], ["simulated"])              # 가짜 발송 = 보낸 것으로 기록 안 함
        self.assertEqual([m["chat_id"] for m in fake.sent], ["777"])
        incidents.self_help(self.conn, self.a, self.conn.execute("SELECT id FROM incidents").fetchone()[0], now=T + 95 * S)
        alerts.process_telegram_due(self.conn, None, T + 95 * S)                          # 텔레그램 설정 없음
        self.assertEqual(self.rows()[-1]["status"], "failed")
        self.assertIn("TELEGRAM_BOT_TOKEN", self.rows()[-1]["last_error"])

    def test_telegram_channel_uses_existing_notifier_without_buttons(self):
        calls = []
        original = notifiers._telegram_call

        def fake_call(token, method, params, files=None, timeout=10):
            calls.append((token, method, dict(params)))
            if len(calls) == 2:
                raise notifiers.NotifyError("429", retryable=True)
            return {"ok": True}
        notifiers._telegram_call = fake_call
        try:
            channel = alerts.TelegramChannel("tok")
            channel.send("777", "안녕")
            with self.assertRaises(alerts.SmsError) as ctx:
                channel.send("777", "다시")
            self.assertTrue(ctx.exception.retryable)
        finally:
            notifiers._telegram_call = original
        self.assertEqual(calls[0][:2], ("tok", "sendMessage"))
        self.assertEqual((calls[0][2]["chat_id"], calls[0][2]["text"]), ("777", "안녕"))
        self.assertNotIn("reply_markup", calls[0][2])                                     # 버튼 없음
        self.assertIsNone(alerts.build_telegram({}))
        self.assertIsInstance(alerts.build_telegram({"TELEGRAM_BOT_TOKEN": "x"}), alerts.TelegramChannel)


if __name__ == "__main__":
    import unittest
    unittest.main()
