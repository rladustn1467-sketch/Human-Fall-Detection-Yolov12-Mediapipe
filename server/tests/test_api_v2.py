"""New web app API (/api/v2) and /app/next file serving, on a COPY of the server.

The server code (not its data) is copied to a temporary folder and started on a free port:
no .env (so no Telegram), its own new token, its own database and events file.
The real server/ data (events.json, residents.json, access_token.txt, .env, fall.db) is never used.

Run from the project folder with the server venv:
  server\\venv\\Scripts\\python.exe -m unittest discover -s server/tests -t server
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

import db

SERVER_DIR = Path(__file__).resolve().parents[1]
CODE_FILES = ["main.py", "db.py", "accounts.py", "people.py", "address_search.py", "report_message.py", "door_codes.py", "incidents.py", "alerts.py", "legacy_devices.py", "devices.py", "push.py", "escalation.py", "notify_rules.py", "notifiers.py", "report119.py", "residents.py", "background.py"]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerCopy:
    def __init__(self, extra_env=None, extra_args=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name in CODE_FILES:
            shutil.copy2(SERVER_DIR / name, self.dir / name)
        shutil.copytree(SERVER_DIR / "app", self.dir / "app")
        shutil.copytree(SERVER_DIR / "static", self.dir / "static")
        self.port = free_port()
        self.db_path = self.dir / "copy.db"
        env = dict(os.environ, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="", FALL_DB_PATH=str(self.db_path),
                   PYTHONIOENCODING="utf-8")
        env.update(extra_env or {})   # 시험별 설정 (예: 가짜 도로명주소 API 주소)
        self.log = open(self.dir / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(self.port), *(extra_args or [])],
            cwd=self.dir, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            self.close()
            raise RuntimeError("test server did not start")
        self.token = (self.dir / "access_token.txt").read_text(encoding="utf-8").strip()

    def request(self, method, path, body=None, token=None, headers=None):
        """Raw request (the path is sent exactly as given, ../ included). Returns (status, headers, text).
        Response header names are lower case."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = dict(headers or {})
        if token:
            headers["X-Access-Token"] = token
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        res = conn.getresponse()
        text = res.read().decode("utf-8", errors="replace")
        conn.close()
        return res.status, {k.lower(): v for k, v in res.getheaders()}, text

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()
        self.tmp.cleanup()


class ApiV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerCopy()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    # ---- 새 API ----
    def test_health(self):
        status, headers, text = self.server.request("GET", "/api/v2/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text), {"ok": True, "db": "ok", "schema_version": db.MIGRATIONS[-1][0]})
        self.assertEqual(headers.get("cache-control"), "no-store")

    def test_state_is_empty_and_not_logged_in(self):
        status, _, text = self.server.request("GET", "/api/v2/state")
        self.assertEqual(status, 200)
        data = json.loads(text)
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["me_id"])
        state = data["state"]
        self.assertEqual(state["version"], 2)
        self.assertTrue(state["live"])
        for key in ("groups", "people", "homes", "devices", "incidents", "history", "notifs"):
            self.assertEqual(state[key], [], key)

    def test_database_is_the_copy_file(self):
        self.assertTrue(self.server.db_path.is_file())
        self.assertFalse((self.server.dir / "fall.db").exists())

    # ---- /app/next 화면 파일: 로그인 없이 열림 ----
    def test_next_folder_address_opens_index(self):
        status, headers, text = self.server.request("GET", "/app/next/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        self.assertIn("js/mode.js", text)

    def test_next_without_slash_redirects(self):
        status, headers, _ = self.server.request("GET", "/app/next")
        self.assertEqual(status, 307)
        self.assertEqual(headers.get("location"), "/app/next/")

    def test_next_files_need_no_login(self):
        for path in ("/app/next/index.html", "/app/next/dev.html", "/app/next/js/store.js", "/app/next/css/main.css"):
            status, _, _ = self.server.request("GET", path)
            self.assertEqual(status, 200, path)

    # ---- 기존 보호는 그대로 ----
    def test_old_app_still_needs_login(self):
        self.assertEqual(self.server.request("GET", "/app/")[0], 401)
        self.assertEqual(self.server.request("GET", "/app/js/app.js")[0], 401)
        self.assertEqual(self.server.request("GET", "/app/", token=self.server.token)[0], 200)
        self.assertEqual(self.server.request("GET", "/app/icons/icon-192.png")[0], 200)  # 기존처럼 공개

    def test_dot_dot_cannot_bypass_login(self):
        for path in ("/app/next/../index.html", "/app/next/../js/app.js", "/app/icons/../index.html",
                     "/app/next/%2e%2e/index.html"):
            status, _, _ = self.server.request("GET", path)
            self.assertNotEqual(status, 200, path)

    def test_outside_app_folder_is_not_found(self):
        self.assertEqual(self.server.request("GET", "/app/../main.py")[0], 404)
        self.assertEqual(self.server.request("GET", "/app/next/../../main.py")[0], 404)

    def test_old_event_api_unchanged(self):
        self.assertEqual(self.server.request("GET", "/api/events")[0], 401)
        event_id = uuid.uuid4().hex
        status, _, text = self.server.request("POST", "/api/events", {
            "event_id": event_id, "device_id": "unittest", "fall_type": "slip_and_fall", "is_test": True},
            token=self.server.token)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(text)["ok"])
        status, _, text = self.server.request("POST", f"/api/events/{event_id}/response", {"response": "safe"},
                                              token=self.server.token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["status"], "safe")
        status, _, text = self.server.request("GET", "/api/events?limit=5", token=self.server.token)
        self.assertEqual(status, 200)
        self.assertIn(event_id, text)


if __name__ == "__main__":
    unittest.main()
