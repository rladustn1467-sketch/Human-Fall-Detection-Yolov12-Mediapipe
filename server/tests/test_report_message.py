"""Mock 119 report message (report_message.py) and its place on the /reports/{id} page.

Checks that the message uses only registered data ('미등록' otherwise), says clearly that nothing was sent,
makes no network call, writes no file or log, and that the page adds no tel:/sms: link.
The HTTP test runs on a COPY of the server without .env (no Telegram) and with fake residents.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import builtins
import html
import json
import re
import socket
import time
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

import report119
import report_message
from tests.test_api_v2 import ServerCopy

EVENT = {"time": "2026-10-20 14:03:11", "fall_type": "slip_and_fall", "is_test": False}
REPORT = {"time": "2026-10-20 14:06:15", "reason": "timeout", "trigger": "auto"}
RESIDENT = {"id": "r1", "alias": "할머니", "age": "82", "conditions": "고혈압, 당뇨", "medications": "혈압약",
            "updated": "2026-09-01"}
HOME = report119.HomeInfo(address="서울특별시 마포구 월드컵로 100 101동 1203호", door_code="1234*",
                          building_door_code="#5678", contact="010-1111-2222")


def parts(residents, fallen=None, home=HOME):
    summary = report119.summarize(fallen, residents)
    detail = report119.details(summary, residents, home)
    return summary, detail


class BuildTest(unittest.TestCase):
    def test_full_information(self):
        summary, detail = parts([RESIDENT])
        result = report_message.build(EVENT, REPORT, summary, detail)
        text = result["text"]
        self.assertTrue(text.startswith(report_message.NOT_SENT_NOTICE))
        for value in ("2026-10-20 14:03:11", "2026-10-20 14:06:15", "본인 무응답", "보호자 무응답으로 자동 신고",
                      "월드컵로 100 101동 1203호", "1234*", "#5678", "- 낙상자: 확인됨 (등록된 거주자가 1명이라 자동으로 지정)",
                      "- 나이: 82", "- 지병: 고혈압, 당뇨", "- 복용약: 혈압약", "010-1111-2222"):
            self.assertIn(value, text)
        self.assertEqual(result["missing"], [])

    def test_no_fall_type_and_no_alias(self):
        summary, detail = parts([RESIDENT])
        for fall_type in ("slip_and_fall", "trip_and_fall", "unknown", None):
            text = report_message.build(dict(EVENT, fall_type=fall_type), REPORT, summary, detail)["text"]
            self.assertNotIn("낙상 유형", text)
            self.assertNotIn("_and_fall", text)
            self.assertNotIn("미분류", text)
            self.assertNotIn("할머니", text)        # 별칭은 실제 이름이 아니므로 넣지 않음
            self.assertNotIn("r1", text)            # 거주자 ID 도 넣지 않음

    def test_missing_values_are_unregistered_not_invented(self):
        empty_resident = {"id": "r1", "alias": "할아버지", "age": "", "conditions": "", "medications": "", "updated": ""}
        summary, detail = parts([empty_resident], home=report119.HomeInfo())
        result = report_message.build({"time": "", "fall_type": "unknown"}, {"reason": "?", "trigger": None},
                                      summary, detail)
        text = result["text"]
        self.assertIn("- 주소: 미등록", text)
        self.assertIn("- 현관 비밀번호: 미등록", text)
        self.assertIn("- 공동현관 비밀번호: 미등록", text)
        self.assertIn("- 보호자 연락처: 미등록", text)
        self.assertIn("- 나이: 미등록\n- 지병: 미등록\n- 복용약: 미등록", text)
        self.assertIn("- 신고 사유: 미등록", text)
        self.assertNotIn("할아버지", text)
        for item in ("발생 시각", "신고 시각", "신고 사유", "신고 경위", "주소", "현관 비밀번호", "공동현관 비밀번호",
                     "보호자 연락처", "낙상자 나이", "낙상자 지병", "낙상자 복용약"):
            self.assertIn(item, result["missing"])
        self.assertFalse(any("할아버지" in m for m in result["missing"]))
        # 등록되지 않은 값을 숫자 등으로 지어내지 않음 (본문 안의 숫자는 '0명' 같은 고정 문구뿐)
        body = text.split("\n", 1)[1]
        self.assertNotRegex(body, r"\d{3,}")

    def test_unconfirmed_fallen_with_two_residents_has_no_health_info(self):
        other = dict(RESIDENT, id="r2", alias="할아버지", age="85", conditions="심장질환", medications="혈전약")
        # 설정이 '미확인이어도 전원 포함(all)'이어도 메시지에는 누구의 건강 정보도 넣지 않음
        for policy in ("exclude", "all"):
            summary = report119.summarize(None, [RESIDENT, other], unconfirmed_policy=policy)
            detail = report119.details(summary, [RESIDENT, other], HOME)
            result = report_message.build(EVENT, dict(REPORT, reason="help_needed", trigger="guardian_request"),
                                          summary, detail)
            text = result["text"]
            self.assertIn("- 낙상자: 확인되지 않음 (등록된 거주자 2명 중 누구인지 알 수 없음)", text, policy)
            self.assertIn("- 건강 정보: 낙상자를 확인할 수 없어 넣지 않음", text, policy)
            for private in ("고혈압", "심장질환", "혈압약", "혈전약", "82", "85", "할머니", "할아버지", "나이:", "지병:"):
                self.assertNotIn(private, text, (policy, private))
            self.assertIn("본인이 도움을 요청함", text)
            self.assertIn("낙상자", result["missing"])

    def test_guardian_picked_resident_only(self):
        other = dict(RESIDENT, id="r2", alias="할아버지", age="85", conditions="심장질환", medications="혈전약")
        fallen = {"resident_id": "r2", "alias": "할아버지", "how": "guardian", "after_report": False}
        summary, detail = parts([RESIDENT, other], fallen=fallen)
        text = report_message.build(EVENT, REPORT, summary, detail)["text"]
        self.assertIn("- 낙상자: 확인됨 (보호자가 텔레그램에서 선택)", text)
        self.assertIn("- 지병: 심장질환", text)
        self.assertNotIn("고혈압", text)          # 다른 거주자의 정보는 없음
        self.assertNotIn("할아버지", text)

    def test_confirmed_but_removed_from_file(self):
        summary = report119.summarize(None, [RESIDENT])          # 신고 때는 거주자 1명 → 자동 확정
        detail = report119.details(summary, [], HOME)            # 그 뒤 거주자 파일에서 지워짐
        result = report_message.build(EVENT, REPORT, summary, detail)
        self.assertIn("- 건강 정보: 미등록 (확인된 낙상자의 정보가 거주자 파일에 없음)", result["text"])
        self.assertIn("낙상자 건강 정보", result["missing"])
        self.assertNotIn("r1", result["text"])

    def test_no_residents_and_test_event(self):
        summary, detail = parts([])
        result = report_message.build(dict(EVENT, is_test=True), REPORT, summary, detail)
        self.assertIn("[테스트 낙상 기록]", result["text"])
        self.assertIn("- 낙상자: 확인되지 않음 (등록된 거주자 없음)", result["text"])

    def test_no_network_no_file_no_log(self):
        summary, detail = parts([RESIDENT])
        boom = mock.Mock(side_effect=AssertionError("외부 통신·파일·로그를 쓰면 안 됨"))
        with mock.patch.object(socket.socket, "connect", boom), \
                mock.patch.object(socket, "create_connection", boom), \
                mock.patch.object(urllib.request, "urlopen", boom), \
                mock.patch.object(builtins, "open", boom), \
                mock.patch.object(builtins, "print", boom):
            result = report_message.build(EVENT, REPORT, summary, detail)
        self.assertIn("고혈압", result["text"])
        boom.assert_not_called()

    def test_module_has_no_sending_code(self):
        source = Path(report_message.__file__).read_text(encoding="utf-8")
        for word in ("import socket", "import urllib", "requests", "http.client", "notifiers", "telegram",
                     "tel:", "sms:", "open(", "print("):
            self.assertNotIn(word, source.split('"""', 2)[2], word)   # 맨 위 설명 글은 제외하고 코드만 검사


class ReportPageTest(unittest.TestCase):
    ADDRESS = "테스트시 시험구 모의로 1 101호"

    @classmethod
    def setUpClass(cls):
        # .env 없음(텔레그램 꺼짐), 도움 요청 뒤 1초 만에 자동 신고(시뮬레이션)
        cls.server = ServerCopy({"GUARDIAN_WAIT_AFTER_HELP": "1", "REPORT_ADDRESS": cls.ADDRESS,
                                 "REPORT_CONTACT": "", "DOOR_CODE": "", "BUILDING_DOOR_CODE": ""})
        (cls.server.dir / "residents.json").write_text(json.dumps({"residents": [
            {"id": "r1", "alias": "시험할머니", "age": "80", "conditions": ["시험지병"], "medications": [],
             "updated": time.strftime("%Y-%m-%d")}]}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def reported_event(self):
        event_id = uuid.uuid4().hex
        token = self.server.token
        status, _, _ = self.server.request("POST", "/api/events", {"event_id": event_id, "device_id": "unittest",
                                                                   "fall_type": "trip_and_fall"}, token=token)
        self.assertEqual(status, 200)
        status, _, _ = self.server.request("POST", f"/api/events/{event_id}/response", {"response": "help_needed"},
                                           token=token)
        self.assertEqual(status, 200)
        deadline = time.time() + 15
        while time.time() < deadline:
            status, _, text = self.server.request("GET", f"/reports/{event_id}", token=token)
            if status == 200:
                return event_id, text
            time.sleep(0.5)
        self.fail("자동 신고(시뮬레이션)가 만들어지지 않음")

    def test_page_shows_mock_message_and_sends_nothing(self):
        event_id, page = self.reported_event()
        self.assertIn("모의 신고 메시지", page)
        self.assertIn("실제 119에 전송되지 않았습니다", page)
        self.assertIn('id="mock-report"', page)
        self.assertIn("메시지 복사", page)
        message = html.unescape(re.search(r'<textarea id="mock-report"[^>]*>(.*?)</textarea>', page, re.S).group(1))
        for value in (self.ADDRESS, "- 지병: 시험지병", "본인이 도움을 요청함", "- 보호자 연락처: 미등록",
                      "- 현관 비밀번호: 미등록", "- 낙상자: 확인됨 (등록된 거주자가 1명이라 자동으로 지정)"):
            self.assertIn(value, message)
        for hidden in ("시험할머니", "trip_and_fall", "낙상 유형"):   # 별칭·낙상 유형은 메시지에 없음
            self.assertNotIn(hidden, message)
        lower = page.lower()
        self.assertNotIn("tel:", lower)
        self.assertNotIn("sms:", lower)
        # 메시지·개인정보가 기록 파일과 서버 로그에 새로 저장되지 않음
        time.sleep(1.5)   # events.json 저장 대기
        events_text = (self.server.dir / "events.json").read_text(encoding="utf-8")
        self.assertIn(event_id, events_text)
        for secret in (self.ADDRESS, "시험지병", "모의 신고 메시지", "구급 출동"):
            self.assertNotIn(secret, events_text)
        log = (self.server.dir / "server.log").read_text(encoding="utf-8", errors="replace")
        for secret in (self.ADDRESS, "시험지병", "모의 신고 메시지"):
            self.assertNotIn(secret, log)
        self.assertNotIn("report_detail_sent", events_text)   # 페이지를 열어도 텔레그램 '상세 보기' 전송 없음
        self.assertIn("텔레그램 설정 없음", log)                 # 시험 서버는 텔레그램이 꺼진 상태

    def test_page_needs_token(self):
        event_id, _ = self.reported_event()
        status, _, text = self.server.request("GET", f"/reports/{event_id}")
        self.assertEqual(status, 401)
        self.assertNotIn("시험할머니", text)


if __name__ == "__main__":
    unittest.main()
