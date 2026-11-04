"""Helpers for the end-to-end checks: a throwaway copy of the server. Never touches the production server or database."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class CopyServer:
    """The server's code in a temporary folder with its own database, on 127.0.0.1, without any .env file."""

    def __init__(self, port, extra_env=None):
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.tmp = tempfile.TemporaryDirectory(prefix="fall_e2e_")
        self.dir = Path(self.tmp.name) / "server"
        shutil.copytree(REPO / "server", self.dir, ignore=shutil.ignore_patterns(
            "__pycache__", "venv", "tests", "logs", "images", "backups", ".env", "fall.db*", "events.json",
            "residents.json", "access_token.txt", "telegram_state.json"))
        self.db_path = self.dir / "copy.db"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("TELEGRAM", "FCM"))}
        env.update(FALL_DB_PATH=str(self.db_path), PYTHONIOENCODING="utf-8")
        env.update(extra_env or {})
        self.log = open(self.dir / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                                     cwd=self.dir, env=env, stdout=self.log, stderr=self.log)
        for _ in range(80):
            try:
                urllib.request.urlopen(self.base + "/api/v2/health", timeout=1)
                return
            except Exception:
                time.sleep(0.5)
        self.close()
        raise SystemExit(f"시험 서버가 켜지지 않았어요 (포트 {port}). 서버 venv 의 Python 으로 실행했는지 확인해 주세요.")

    def close(self):
        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        self.proc.wait(timeout=10)
        self.log.close()
        self.tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
