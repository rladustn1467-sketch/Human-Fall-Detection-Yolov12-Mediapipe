"""Small safety fixes from the 2026-10-29 audit (docs/system_audit_2026-10-29.md), on a COPY of the server:
security headers, no home address in the access log, startup warnings for missing settings, and background
steps that can not stop each other.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import time
import unittest
import urllib.parse
import uuid

import background
from tests.test_api_v2 import ServerCopy
from tests.test_auth_api import PW, Browser

HEADERS = {"x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "same-origin"}


class HardeningApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def log(self):
        time.sleep(0.5)
        return (self.server.dir / "server.log").read_text(encoding="utf-8", errors="replace")

    def test_security_headers_on_pages_and_api(self):
        for path in ("/api/v2/health", "/app/next/index.html", "/api/v2/state"):
            status, headers, _ = self.server.request("GET", path)
            self.assertEqual(status, 200, path)
            for k, v in HEADERS.items():
                self.assertEqual(headers.get(k), v, (path, k))
        status, headers, _ = self.server.request("GET", "/no-such-page")
        self.assertEqual(headers.get("x-frame-options"), "DENY")                     # 오류 응답에도

    def test_address_search_words_stay_out_of_the_access_log(self):
        b = Browser(self.server)
        self.assertEqual(b.call("POST", "/api/v2/auth/signup", {"name": "주소시험", "phone": "010-" + str(uuid.uuid4().int)[:4]
                                                                + "-" + str(uuid.uuid4().int)[:4], "password": PW})[0], 200)
        words = urllib.parse.quote("마포구월드컵로백번지")
        b.call("GET", f"/api/v2/address/search?q={words}")                            # 키가 없어 503 이어도 기록은 남음
        b.call("GET", "/api/v2/address/search?q=%EC%84%B8%EC%A2%85%EB%8C%80%EB%A1%9C")   # 세종대로 (주소창 인코딩)
        log = self.log()
        self.assertIn("/api/v2/address/search?q=***", log)
        self.assertNotIn(words, log)
        self.assertNotIn("%EC%84%B8%EC%A2%85", log)

    def test_startup_warns_about_missing_settings(self):
        log = self.log()
        for key in ("DOOR_CODE_KEY", "JUSO_API_KEY", "FCM_SERVICE_ACCOUNT_FILE"):
            self.assertIn(f"[설정 확인] {key}", log)


class BackgroundStepsTest(unittest.TestCase):
    def test_one_failing_step_does_not_stop_the_others(self):
        done = []

        def boom():
            raise RuntimeError("tick broke")

        errors = background.run_each([("사고 시간 처리", boom), ("문자", lambda: done.append("sms")),
                                      ("푸시", lambda: done.append("push"))], log=lambda line: done.append(line))
        self.assertEqual(done[-2:], ["sms", "push"])                                  # 앞 단계 오류와 상관없이 실행
        self.assertEqual(errors, 1)
        self.assertIn("사고 시간 처리", done[0])
        self.assertIn("RuntimeError", done[0])


if __name__ == "__main__":
    unittest.main()
