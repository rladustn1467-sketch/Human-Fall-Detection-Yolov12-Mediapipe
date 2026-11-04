"""The real app on the emulator against a copy of the server. See tools/e2e/README.md. Clears the app's data.

Run from the project folder with the server venv, emulator on, debug APK built for http://localhost:8012/app/next/:
  python tools/e2e/run_emulator.py --frames <folder of one recorded fall> --fps 30

Passing here says the app and server code follow the flow on an emulator. It does not cover a real phone.
"""
import argparse
import http.cookiejar
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from common import REPO, CopyServer

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
ADB = os.path.join(os.environ["LOCALAPPDATA"], "Android", "Sdk", "platform-tools", "adb.exe")
PKG = "com.humanfall.app"
ACTIVITY = f"{PKG}/.detect.DetectorActivity"
APK = REPO / "mobile/android/app/build/outputs/apk/debug/app-debug.apk"
PORT = 8012
PW = "Emulator2026pw"
results = []


def check(name, ok, detail=""):
    line = f"{'PASS' if ok else 'FAIL'} {name}{' — ' + str(detail)[:170] if detail != '' else ''}"
    results.append(line)
    print(line, flush=True)


def adb(*args):
    return subprocess.run([ADB, *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def wait(condition, seconds, step=2):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(step)
    return bool(condition())


def screen():
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    return " | ".join(n.get("text") for n in ET.fromstring(xml[xml.index("<"):]).iter("node") if n.get("text")) if "<" in xml else ""


def log():
    return adb("logcat", "-d", "-v", "raw", "-s", "DetectionService:*", "AndroidRuntime:E")


def camera_open():
    out = adb("shell", "dumpsys", "media.camera")
    part = out.split("Active Camera Clients:", 1)[1].split("Allowed user IDs", 1)[0] if "Active Camera Clients:" in out else ""
    return f"Client Package Name: {PKG}" in part


def service_running():
    return "DetectionService" in adb("shell", "dumpsys", "activity", "services", PKG)


def web(expression):
    for attempt in range(3):
        pid = adb("shell", "pidof", PKG).strip()
        adb("forward", "tcp:9333", f"localabstract:webview_devtools_remote_{pid}")
        r = subprocess.run(["node", str(HERE / "webview_eval.mjs"), "9333", expression], capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.stdout.strip():
            return json.loads(r.stdout)
        time.sleep(1)
    return None


class Person:
    def __init__(self, base, name):
        self.base, self.name = base, name
        self.jar = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.phone = f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"   # 시험 DB 전용
        self.id = self.call("POST", "/api/v2/auth/signup", {"name": name, "phone": self.phone, "password": PW})[1]["me_id"]

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"Content-Type": "application/json", "Origin": self.base},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.jar.open(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def state(self):
        return self.call("GET", "/api/v2/state")[1]["state"]


def reset_app():
    adb("shell", "am", "force-stop", PKG)
    adb("shell", "pm", "clear", PKG)
    for p in ("CAMERA", "POST_NOTIFICATIONS"):
        adb("shell", "pm", "grant", PKG, f"android.permission.{p}")


def start(*extra):
    adb("shell", "am", "force-stop", PKG)
    adb("logcat", "-c")
    adb("shell", "am", "start", "-n", ACTIVITY, "--ei", "heartbeat_seconds", "5", *extra)


def copy_frames(folder):
    mock = f"/data/data/{PKG}/files/mock"
    adb("shell", "rm", "-rf", "/data/local/tmp/fde2e")
    adb("shell", "mkdir", "-p", "/data/local/tmp/fde2e")
    adb("push", str(folder), "/data/local/tmp/fde2e/video")
    adb("shell", "chmod", "-R", "a+rX", "/data/local/tmp/fde2e")
    adb("shell", "run-as", PKG, "mkdir", "-p", mock)
    adb("shell", "run-as", PKG, "cp", "-r", "/data/local/tmp/fde2e/video", f"{mock}/")
    return f"{mock}/video"


def device_flow(server, args, target, family, home):
    code = target.call("POST", f"/api/v2/homes/{home}/devices/pairing", {"type": "phone", "location": "거실"})[1]["pairing"]["code"]
    device = lambda: target.state()["devices"][0]
    reset_app()
    pair = ("--es", "server", f"http://localhost:{PORT}", "--es", "mode", "dedicated", "--es", "code", code)
    if args.frames:
        start(*pair, "--es", "mock_frames_dir", copy_frames(args.frames), "--ef", "mock_fps", str(args.fps))
        check("연결 코드로 앱 연결", wait(lambda: bool(target.state()["devices"]), 30))
        check("녹화 영상 재생 끝", wait(lambda: "시험용 영상 끝" in log(), 240, 5))
        incidents = target.state()["incidents"]
        check("낙상이 서버 사고가 됨", len(incidents) == 1 and incidents[0]["status"] in ("detected", "no_response"), [i["status"] for i in incidents])
        if incidents:
            inc = incidents[0]
            check("실루엣 사진 연결", bool(inc.get("photos")), len(inc.get("photos") or []))
            if inc.get("photos"):
                photo = inc["photos"][0]["id"]
                with family.jar.open(f"{server.base}/api/v2/incidents/{inc['id']}/photos/{photo}.jpg", timeout=10) as r:
                    check("가족이 사진을 볼 수 있음", r.status == 200 and r.read(3) == bytes((0xff, 0xd8, 0xff)))
            c = sqlite3.connect(server.db_path, timeout=10)
            c.execute("UPDATE incidents SET detected_at = detected_at - 61000 WHERE id = ?", (inc["id"],))
            c.commit()
            c.close()
            check("60초 무응답 뒤 가족 알림", wait(lambda: any("응답이 없어요" in n["text"] for n in family.state()["notifs"]), 10, 1))
            family.call("POST", f"/api/v2/incidents/{inc['id']}/take-over")
            check("가족이 맡고 종료", family.call("POST", f"/api/v2/incidents/{inc['id']}/close")[0] == 200)
        adb("shell", "am", "force-stop", PKG)
        start()
    else:
        print("SKIP 낙상 단계: --frames 없음", flush=True)
        results.append("SKIP 낙상 단계 (--frames 없음)")
        start(*pair)

    check("일반 카메라: '감지 중'", wait(lambda: "감지 중" in screen(), 40), screen()[-70:])
    check("서버에 정상으로 표시", wait(lambda: device()["status"] == "ok", 25), device()["status"])

    start("--ei", "test_block_frames_seconds", "45")
    check("영상 멈춤: 자동 재시작", wait(lambda: "카메라 영상이 없어 다시 시작" in log(), 30))
    check("영상 멈춤: 화면 표시", wait(lambda: "카메라 영상이 멈췄어요" in screen(), 12))
    check("영상 멈춤: 서버에 문제로 표시", wait(lambda: device()["status"] != "ok", 15), device()["status"])
    check("영상이 돌아오면 복구", wait(lambda: "카메라 감지 복구됨" in log(), 60))

    start("--ei", "test_fail_analysis_seconds", "30")
    check("분석 실패: 화면 표시", wait(lambda: "감지가 멈췄어요" in screen(), 20))
    check("분석 실패: 복구", wait(lambda: "카메라 감지 복구됨" in log(), 70))

    device_id = device()["id"]
    check("앱에서 기기 삭제", target.call("DELETE", f"/api/v2/devices/{device_id}")[0] == 200)
    check("삭제되면 감지 서비스 종료", wait(lambda: not service_running(), 30))


def start_own_phone(person):
    reset_app()
    adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(9)
    web(f"(()=>{{const s=(id,v)=>{{const e=document.getElementById(id);e.value=v;e.dispatchEvent(new Event('input',{{bubbles:true}}))}};"
        f"s('lg-phone','{person.phone}');s('lg-pw','{PW}');document.querySelector('[data-action=\"login.submit\"]').click();return 1}})()")
    time.sleep(5)
    web("(async()=>{location.hash='#/settings';await new Promise(r=>setTimeout(r,1500));document.querySelector('[data-action=\"settings.detector\"]').click();"
        "await new Promise(r=>setTimeout(r,1500));document.getElementById('dc-loc').value='거실';document.querySelector('[data-action=\"dc.submit\"]').click();return 1})()")
    check("이 휴대폰으로 감지 시작", wait(camera_open, 30) and service_running())


def logout_flow(person):
    start_own_phone(person)
    adb("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(3)
    r = web("(async()=>{const w=t=>new Promise(r=>setTimeout(r,t));location.hash='#/settings';await w(1500);"
            "document.querySelector('[data-action=\"settings.logout\"]').click();await w(1200);"
            "const y=document.querySelector('[data-action=\"confirm.yes\"]');if(y)y.click();"
            "for(let i=0;i<40&&location.hash!=='#/ob/login';i++)await w(250);return location.hash})()")
    check("로그아웃", r == "#/ob/login", r)
    check("로그아웃하면 카메라 닫힘", wait(lambda: not camera_open(), 8))
    check("로그아웃하면 감지 서비스 종료", wait(lambda: not service_running(), 8))


def removal_flow(server, person, family):
    """A person removed from the group: their own phone stops by itself, without opening the app."""
    start_own_phone(person)
    adb("shell", "input", "keyevent", "HOME")
    c = sqlite3.connect(server.db_path, timeout=10)
    own = c.execute("SELECT COUNT(*) FROM devices WHERE self_user_id = ?", (person.id,)).fetchone()[0]
    c.close()
    check("서버가 이 사람의 휴대폰으로 기억", own >= 1, own)
    check("가족이 내보냄", family.call("POST", f"/api/v2/groups/members/{person.id}/remove")[0] == 200)
    c = sqlite3.connect(server.db_path, timeout=10)
    left = c.execute("SELECT COUNT(*) FROM devices WHERE self_user_id = ?", (person.id,)).fetchone()[0]
    c.close()
    check("그 사람의 기기가 서버에서 바로 삭제", left == 0, left)
    check("앱을 열지 않아도 다음 상태 신호에서 감지 종료", wait(lambda: not service_running(), 80, 3))
    check("카메라 닫힘", wait(lambda: not camera_open(), 8))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--frames", type=Path, help="녹화 낙상 영상의 프레임 폴더 (없으면 낙상 단계를 건너뜀)")
    p.add_argument("--fps", type=float, default=30)
    args = p.parse_args()
    if "emulator-" not in adb("devices"):
        raise SystemExit("에뮬레이터가 켜져 있지 않아요.")
    with CopyServer(PORT) as server:
        adb("logcat", "-G", "8M")
        adb("reverse", f"tcp:{PORT}", f"tcp:{PORT}")
        print("설치:", adb("install", "-r", str(APK)).strip()[-10:], flush=True)
        target = Person(server.base, "대상자에이")
        invite = target.call("POST", "/api/v2/groups")[1]["state"]["groups"][0]["invite"]["code"]
        home = target.call("POST", "/api/v2/me/setup", {"info": {}, "home": {"mode": "new", "address": ""}})[1]["state"]["homes"][0]["id"]
        family = Person(server.base, "가족비")
        family.call("POST", "/api/v2/groups/join", {"code": invite})
        family.call("POST", "/api/v2/me/onboarded", {"onboarded": True})
        try:
            device_flow(server, args, target, family, home)
            logout_flow(target)
            removal_flow(server, target, family)
        finally:
            adb("shell", "am", "force-stop", PKG)
            check("크래시 없음", "FATAL" not in log())
    failed = sum(line.startswith("FAIL") for line in results)
    print(f"{sum(line.startswith('PASS') for line in results)} PASS / {failed} FAIL / {sum(line.startswith('SKIP') for line in results)} SKIP")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
