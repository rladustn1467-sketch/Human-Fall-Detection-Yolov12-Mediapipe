"""Browser regression checks on a copy of the server with headless Chrome. See tools/e2e/README.md.

Run from the project folder with the server venv:  python tools/e2e/run_browser.py
"""
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from common import CopyServer

HERE = Path(__file__).resolve().parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SERVER_PORT, CHROME_PORT = 8031, 9261


def main():
    with CopyServer(SERVER_PORT, {"FD_DEV_TOOLS": "1"}) as server, tempfile.TemporaryDirectory(prefix="fall_chrome_") as profile:
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CHROME_PORT}",
                                   "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}",
                                   "--no-first-run", "about:blank"])
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json", timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            return subprocess.run(["node", str(HERE / "browser_checks.mjs"), server.base, str(CHROME_PORT)], timeout=240).returncode
        finally:
            subprocess.run(["taskkill", "/PID", str(chrome.pid), "/T", "/F"], capture_output=True)
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
