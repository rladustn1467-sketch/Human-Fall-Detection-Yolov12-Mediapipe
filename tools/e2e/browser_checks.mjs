// 브라우저로 보는 회귀 시험 (run_browser.py 가 실행). 119 버튼은 링크만 검사하고 누르지 않음.
// 사용: node browser_checks.mjs <서버 주소> <크롬 포트>
const BASE = process.argv[2], PORT = process.argv[3];
const PW = "Check2026pwx";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rnd = () => String(Math.floor(1000 + Math.random() * 8999));
const results = [];
const check = (n, ok, d = "") => { const l = `${ok ? "PASS" : "FAIL"} ${n}${d !== "" ? " — " + JSON.stringify(d).slice(0, 200) : ""}`; results.push(l); console.log(l); };

function person() {
  let cookie = "";
  const call = async (method, path, body) => {
    const r = await fetch(BASE + path, { method, headers: { "Content-Type": "application/json", Origin: BASE, Cookie: cookie },
      body: body === undefined ? undefined : JSON.stringify(body) });
    const c = r.headers.get("set-cookie"); if (c) cookie = c.split(";")[0];
    return [r.status, await r.json().catch(() => ({}))];
  };
  return call;
}
async function signup(name, code) {
  const s = person(), phone = `010-${rnd()}-${rnd()}`;
  const [st, data] = await s("POST", "/api/v2/auth/signup", { name, phone, password: PW });
  if (st !== 200) throw new Error("signup " + JSON.stringify(data));
  if (code) await s("POST", "/api/v2/groups/join", { code });
  return { s, phone, id: data.me_id, name };
}
const stateOf = async (p) => (await p.s("GET", "/api/v2/state"))[1].state;

const page = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let seq = 0; const waiting = new Map();
ws.addEventListener("message", (m) => { const d = JSON.parse(m.data); if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); } });
const cdp = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
async function ev(expr) {
  const d = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (d.result && d.result.exceptionDetails) throw new Error("page: " + JSON.stringify(d.result.exceptionDetails).slice(0, 300));
  return d.result && d.result.result ? d.result.result.value : undefined;
}
await cdp("Network.enable");
async function open(url) {
  await cdp("Page.navigate", { url: "about:blank" }); await sleep(300);
  await cdp("Page.navigate", { url });
  for (let i = 0; i < 60; i++) { await sleep(250); try { if (await ev("!!(window.FD && FD.Store && document.querySelector('#view') && document.querySelector('#view').children.length)")) break; } catch {} }
  await sleep(800);
}
async function browserAs(p, hash) {
  await cdp("Network.clearBrowserCookies");
  await open(BASE + "/app/next/#/ob/login");
  await ev(`fetch('/api/v2/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:'${p.phone}',password:'${PW}'})}).then(r=>r.status)`);
  await open(BASE + "/app/next/" + hash);
}
const body = () => ev("document.body.innerText");
async function waitFor(expr, ms = 10000) { for (let t = 0; t < ms; t += 400) { if (await ev(expr)) return true; await sleep(400); } return false; }

const a = await signup("관리자에이");
await a.s("POST", "/api/v2/groups");
const code = (await stateOf(a)).groups[0].invite.code;
const home = (await a.s("POST", "/api/v2/me/setup", { info: {}, home: { mode: "new", address: "" } }))[1].state.homes[0].id;
const m = await signup("구성원엠", code);
await m.s("POST", "/api/v2/me/setup", { info: {}, home: { mode: "existing", id: home } });
const f = await signup("가족에프", code), e = await signup("가족이", code);
for (const p of [f, e]) await p.s("POST", "/api/v2/me/onboarded", { onboarded: true });

// 화면 자동 갱신: 서버 내용이 바뀌면 새로고침 없이 그려짐 (2026-10-30 회귀)
await browserAs(a, "#/family");
const before = await body();
await signup("새가족지", (await stateOf(a)).groups[0].invite.code);
const seen = await waitFor(`document.body.innerText.includes('새가족지')`, 9000);
check("자동 갱신: 다른 사람이 들어오면 새로고침 없이 화면에 나옴", seen && !before.includes("새가족지"));

await browserAs(m, "#/");
let t = await body();
check("구성원 홈: 현관 할 일이 안 보임", !t.includes("출입 방식을 알려 주세요"), t.slice(0, 120));
await browserAs(a, "#/");
t = await body();
check("관리자 홈: 현관 할 일이 보임", t.includes("출입 방식을 알려 주세요"));

await browserAs(f, "#/");
const fall = () => a.s("POST", "/api/v2/dev/falls", { homeId: home, location: "거실", agoSeconds: 61 });
await fall();
await sleep(2200);
let inc = (await stateOf(a)).incidents.find((i) => i.status === "no_response");
await e.s("POST", `/api/v2/incidents/${inc.id}/take-over`);
check("맡은 가족 탈퇴", (await e.s("POST", "/api/v2/me/withdraw", { password: PW }))[0] === 200);
await sleep(2500);
let cur = (await stateOf(f)).incidents.find((i) => i.id === inc.id);
check("탈퇴 뒤 사고가 가족 대기로 돌아옴", cur.status === "no_response", cur.status);
check("남은 가족에게 알림", JSON.stringify(await stateOf(f)).includes("확인하던 가족이 그룹을 떠났어요"));
const shown = await waitFor(`!!document.querySelector('[data-action="em.take"]')`, 9000);
check("남은 가족 화면에 '제가 처리할게요' 버튼", shown);
if (shown) {
  await ev(`document.querySelector('[data-action="em.take"]').click()`);
  await sleep(1500);
  cur = (await stateOf(f)).incidents.find((i) => i.id === inc.id);
  check("남은 가족이 맡을 수 있음", cur.status === "checking" && cur.checkedBy === f.id, [cur.status, cur.checkedBy]);
  check("맡은 가족 화면에 할 일 안내", (await body()).includes("무리하게 일으키지 마세요"));
  await ev(`document.querySelector('[data-action="em.min"]').click()`);
  await sleep(600);
  const closed = !(await ev(`!!document.querySelector('[data-action="em.close"]')`));
  await a.s("POST", "/api/v2/dev/falls", { homeId: home, location: "거실" });
  const back = await waitFor(`!!document.querySelector('[data-action="em.close"]')`, 9000);
  check("다시 넘어지면 닫아 둔 화면이 다시 뜸", closed && back, [closed, back]);
  check("재감지 안내 표시", (await body()).includes("다시 넘어짐이 감지됐어요"));
  check("남은 가족이 종료할 수 있음", (await f.s("POST", `/api/v2/incidents/${inc.id}/close`))[0] === 200);
}

await sleep(1000);
await f.s("POST", `/api/v2/incidents/${inc.id}/dismiss`);
await fall();
await sleep(2200);
inc = (await stateOf(a)).incidents.find((i) => i.status === "no_response");
check("119 신고 기록", (await f.s("POST", `/api/v2/incidents/${inc.id}/report`, { targets: [] }))[0] === 200);
await browserAs(f, "#/");
await waitFor(`!!document.querySelector('[data-call119]')`, 9000);
const link = await ev(`(() => { const x = document.querySelector('[data-call119]'); return x ? x.getAttribute('href') : null })()`);
check("신고 뒤 119 전화 링크 (href 만 확인)", link === "tel:119", link);
t = await body();
check("신고 화면에 모의 표시 없음", !/모의|실제 119/.test(t) && t.includes("이미 신고가 접수되어"));
await ev(`document.querySelector('[data-action="em.dismiss"]').click()`);
await sleep(800);
await open(BASE + "/app/next/#/history");
t = await body();
check("낙상 이력에 모의 표시 없음", !/모의|실제 119/.test(t) && t.includes("신고됨"), t.slice(0, 100));
await open(BASE + `/app/next/#/history/${inc.id}`);
t = await body();
check("낙상 상세에 모의 표시 없음", !/모의|실제 119/.test(t) && t.includes("119"), t.slice(0, 100));
const notifs = (await stateOf(a)).notifs.map((n) => n.text);
check("다른 가족 알림에 모의 표시 없음", notifs.some((x) => x.includes("119에 신고했어요")) && !notifs.some((x) => /모의|실제 119/.test(x)), notifs.slice(-1));
await open(BASE + "/app/next/#/prevent");
t = await body();
check("낙상 예방 탭에 내용", t.includes("집 안 점검") && t.includes("생활 수칙"), t.slice(0, 80));
await open(BASE + "/app/next/#/settings");
const pw = "New" + PW;
const changed = await ev(`(async()=>{const w=t=>new Promise(r=>setTimeout(r,t));document.querySelector('[data-action="settings.password"]').click();await w(600);
  const s=(i,v)=>{document.getElementById(i).value=v};s('pc-cur','${PW}');s('pc-new','${pw}');s('pc-new2','${pw}');
  document.querySelector('[data-action="pc.submit"]').click();await w(2000);return document.body.innerText.includes('비밀번호를 바꿨어요')})()`);
check("설정에서 비밀번호 변경", changed === true);
check("새 비밀번호로 로그인", (await person()("POST", "/api/v2/auth/login", { phone: f.phone, password: pw }))[0] === 200);
await cdp("Network.clearBrowserCookies");
await open(BASE + "/app/next/#/ob/signup");
const terms = await ev(`(async()=>{const b=document.querySelector('[data-action="terms.open"]');if(!b)return '';b.click();await new Promise(r=>setTimeout(r,800));const s=document.querySelector('.sheet');return s?s.innerText:''})()`);
check("가입 화면에서 약관 보기", terms.includes("무엇을 저장하나요") && terms.includes("의료기기가 아니에요"), terms.slice(0, 80));

for (const name of ["family.js", "onboarding.js"]) {
  const src = await (await fetch(`${BASE}/app/next/js/${name}`)).text();
  check(`${name}: 119 전달 문구 유지 (의도된 문구)`, /구급대(에|에게) 전달돼요/.test(src) && /이 주소가 전달돼요/.test(src));
}
const failed = results.filter((l) => l.startsWith("FAIL")).length;
console.log(`${results.length - failed} PASS / ${failed} FAIL`);
process.exit(failed ? 1 : 0);
