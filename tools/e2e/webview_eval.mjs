// 에뮬레이터 앱의 WebView 에서 식 하나를 실행하고 결과를 JSON 으로 출력 (run_emulator.py 가 사용)
const port = process.argv[2], expr = process.argv[3];
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id === 1) { console.log(JSON.stringify(d.result && d.result.result ? d.result.result.value ?? null : null)); process.exit(0); }
});
ws.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: { expression: expr, awaitPromise: true, returnByValue: true } }));
