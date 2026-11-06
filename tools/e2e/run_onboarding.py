"""Going back and forth in the first setup with headless Chrome, on a copy of the server. See tools/e2e/README.md.

Run from the project folder with the server venv:  python tools/e2e/run_onboarding.py
"""
import base64
import http.server
import json
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from common import CopyServer

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SERVER_PORT, CHROME_PORT, JUSO_PORT = 8032, 9262, 8033
PW = "Onboard2026pw"
LIB = ("window.w=t=>new Promise(r=>setTimeout(r,t));"
       "window.s=(id,v)=>{const e=document.getElementById(id);e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}))};"
       "window.c=a=>{const e=document.querySelector(`[data-action=\"${a}\"]`);if(!e)throw new Error('no '+a);e.click()};")
results = []


class Juso(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        keyword = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)["keyword"][0]
        reply = {"results": {"common": {"errorCode": "0"}, "juso": [{"roadAddr": f"서울 {keyword} 1", "zipNo": "00000", "bdNm": ""}]}}
        body = json.dumps(reply, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}{' — ' + str(detail)[:150] if detail != '' else ''}", flush=True)


def ev(js):
    r = subprocess.run(["node", str(HERE / "webview_eval.mjs"), str(CHROME_PORT), js], capture_output=True, text=True,
                       encoding="utf-8", timeout=40)
    return json.loads(r.stdout) if r.stdout.strip() else None


def do(js):
    """Run steps in the page, wait for the screen, and return where the app is."""
    return ev(f"(async()=>{{{LIB}{js};await w(900);return location.hash}})()")


def text():
    return ev("document.body.innerText") or ""


def state():
    return ev("fetch('/api/v2/state').then(r=>r.json()).then(j=>j.state)")


def me(s, name):
    return next(p for p in s["people"] if p["name"] == name)


def back():
    return do("c('nav.back')")


def signup(name, phone):
    do(f"location.hash='#/ob/signup';await w(700);s('su-name','{name}');s('su-phone','{phone}');s('su-pw','{PW}');s('su-pw2','{PW}');"
       "document.getElementById('su-agree').click();c('signup.submit');await w(1200)")


def search_address(word, detail):
    do(f"document.getElementById('addr-q').value='{word}';c('addr.search');await w(900);c('addr.pick');await w(300);"
       f"s('addr-detail','{detail}');c('addr.next')")


def logout():
    ev("fetch('/api/v2/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(()=>1)")
    ev("(localStorage.clear(),location.hash='#/ob/login',location.reload(),1)")
    time.sleep(2)


def creator_flow():
    signup("만든사람", "010-0000-3001")
    do("c('group.create');await w(900);c('ob.toAsk')")
    check("초대 화면은 뒤로 가도 그룹을 다시 만들지 않음", do("location.hash='#/ob/group'") == "#/ob/invite")
    do("c('ob.toAsk')")
    do("c('ask.yes')")
    do("s('info-birth','19500315');c('info.next')")
    search_address("월드컵로", "101동")
    check("3단계로 이동", do("") == "#/ob/password")
    check("3단계에서 주소로 돌아가도 입력값 유지", back() == "#/ob/address" and "서울 월드컵로 1" in text())
    do("s('addr-detail','102동');c('addr.next')")
    do("const k=[...document.querySelectorAll('[data-action=\"obent.pick\"][data-m=\"absent\"]')][0];k.click();await w(400);"
       "[...document.querySelectorAll('[data-action=\"obent.pick\"][data-m=\"code\"]')].pop().click();await w(400);"
       "document.querySelector('input[type=password]').value='5831';c('pw.next');await w(1200)")
    check("4단계에 뒤로가기 버튼", ev("!!document.querySelector('[data-action=\"nav.back\"]')") is True)
    s = state()
    home = s["homes"][0]["id"]
    check("집 하나 저장", len(s["homes"]) == 1 and s["homes"][0]["address"] == "서울 월드컵로 1 102동", s["homes"][0]["address"])

    check("4단계에서 3단계로", back() == "#/ob/password")
    check("저장한 현관 비밀번호는 다시 묻지 않음", "그대로 사용" in text())
    check("3단계에서 주소로", back() == "#/ob/address")
    t = text()
    check("내 집이 '가족이 등록한 집'으로 나오지 않음", "가족이 등록한 집" not in t and "같은 집에 사시나요" not in t, t[:60])
    check("저장한 주소를 수정할 수 있음", "서울 월드컵로 1" in t and ev("document.getElementById('addr-detail').value") == "102동")
    do("s('addr-detail','103동');c('addr.next')")
    do("c('pw.next');await w(1200)")
    s = state()
    check("수정하면 같은 집의 주소가 바뀜", len(s["homes"]) == 1 and s["homes"][0]["id"] == home and s["homes"][0]["address"].endswith("103동"),
          s["homes"][0]["address"])

    back(), back()
    do("c('addr.change')")
    search_address("마포대로", "1동")
    do("c('pw.next');await w(1200)")
    s = state()
    check("주소를 새로 검색해도 집은 하나", len(s["homes"]) == 1 and s["homes"][0]["address"] == "서울 마포대로 1 1동", s["homes"][0]["address"])

    back(), back(), back()
    check("개인정보로 돌아가면 입력값 유지", ev("document.getElementById('info-birth').value") in ("1950-03-15", "19500315"))
    back()
    t = text()
    check("저장 뒤에는 '알림만 받을게요'를 고를 수 없음", "알림만 받을게요" not in t)
    do("c('ask.yes')")
    check("'예'를 다시 눌러도 입력값 유지", ev("document.getElementById('info-birth').value") in ("1950-03-15", "19500315"))

    do("c('info.next')")
    do("c('addr.next')")
    do("c('pw.next');await w(1200)")
    ev("(location.reload(),1)")
    time.sleep(2)
    check("새로고침 뒤에도 4단계", "감지할 기기를" in text())
    check("새로고침 뒤 뒤로가기는 3단계로", back() == "#/ob/password")
    check("새로고침 뒤 뒤로가기는 주소로", back() == "#/ob/address")
    check("새로고침 뒤에도 저장한 주소를 보여 줌", ev("document.getElementById('addr-base').value") == "서울 마포대로 1 1동")
    do("s('addr-base','서울 다시 고친 주소 5');c('addr.next')")
    do("c('pw.next');await w(1200)")
    s = state()
    who = me(s, "만든사람")
    check("새로고침 뒤 수정해도 집은 하나", len(s["homes"]) == 1 and s["homes"][0]["address"] == "서울 다시 고친 주소 5", s["homes"][0]["address"])
    check("새로고침 뒤 저장해도 건강 정보 유지", who.get("birth") == "1950-03-15", who.get("birth"))
    do("c('flow.finish');await w(900)")
    return s["groups"][0]["invite"]["code"], home


def member_flow(code, family_home):
    logout()
    signup("같이사는분", "010-0000-3002")
    do(f"c('group.join');await w(700);s('join-code','{code}');await w(200);c('join.submit');await w(1200)")
    do("c('ask.yes')")
    do("c('info.next')")
    t = text()
    check("가족이 등록한 집이 있으면 물어봄", "같은 집에 사시나요" in t)
    do("c('addr.same')")
    do("c('pw.member-next');await w(1200)")
    s = state()
    check("가족의 집에 연결", me(s, "같이사는분")["homeIds"] == [family_home])
    check("4단계에서 3단계로", back() == "#/ob/password")
    check("3단계에서 주소로", back() == "#/ob/address")
    check("가족의 집은 그대로 물어봄", "같은 집에 사시나요" in text())
    do("c('addr.other')")
    search_address("한강대로", "2동")
    do("c('pw.next');await w(1200)")
    s = state()
    mine = me(s, "같이사는분")["homeIds"]
    check("다른 집을 고르면 가족의 집 연결이 풀림", len(mine) == 1 and mine[0] != family_home, mine)
    check("가족의 집은 남아 있음", any(h["id"] == family_home for h in s["homes"]) and len(s["homes"]) == 2)

    back(), back()
    t = text()
    check("방금 만든 내 집은 수정 화면", "서울 한강대로 1" in t and "같은 집에 사시나요" not in t)
    do("c('addr.back-existing')")
    check("가족의 집 중에서 다시 고를 수 있음", "같은 집에 사시나요" in text())
    do("c('addr.same')")
    do("c('pw.member-next');await w(1200)")
    s = state()
    check("가족의 집으로 바꾸면 빈 집은 사라짐", len(s["homes"]) == 1 and me(s, "같이사는분")["homeIds"] == [family_home], len(s["homes"]))


def main():
    juso = http.server.ThreadingHTTPServer(("127.0.0.1", JUSO_PORT), Juso)
    threading.Thread(target=juso.serve_forever, daemon=True).start()
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    env = {"DOOR_CODE_KEY": key, "JUSO_API_KEY": "fake", "JUSO_API_URL": f"http://127.0.0.1:{JUSO_PORT}/"}
    with CopyServer(SERVER_PORT, env) as server, tempfile.TemporaryDirectory(prefix="fall_chrome_") as profile:
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={CHROME_PORT}",
                                   "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}", "--no-first-run",
                                   server.base + "/app/next/"])
        try:
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json", timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            time.sleep(2)
            code, home = creator_flow()
            member_flow(code, home)
        finally:
            subprocess.run(["taskkill", "/PID", str(chrome.pid), "/T", "/F"], capture_output=True)
            juso.shutdown()
            time.sleep(1)
    failed = results.count(False)
    print(f"{results.count(True)} PASS / {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
