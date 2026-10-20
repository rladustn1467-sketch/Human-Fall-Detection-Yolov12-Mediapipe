// 사고 대응 패널: 가장 최근 낙상의 상태에 따라 한 번에 한 가지만 보여 줍니다.
//   질문(괜찮아요·도움이 필요해요) / 도움 요청 보냄 / 괜찮다고 전함 / 진행 중인 확인 요청 없음
// 확인 화면(screens/self.js)과, 모든 메뉴 위에 뜨는 사고 대응 레이어(incident/layer.js)가 함께 씁니다.
// 응답 마감·가족 알림·119(시뮬레이션) 판단은 모두 서버가 하고, 여기서는 서버 상태를 보여 주고 응답만 보냅니다.
import { AuthError } from "../api.js";
import { button, el } from "../ui.js";

// 화면에 보여 줄 상태를 서버 기록 1건으로 정함
export function classify(ev, config, now) {
  if (!ev) return "none";
  const detectedMs = ev.detected_ts ? ev.detected_ts * 1000 : Date.parse(ev.time.replace(" ", "T"));
  const recent = now - detectedMs < config.activeMinutes * 60 * 1000;
  if (ev.status === "awaiting_response") return "ask";
  if (ev.status === "timeout" && recent) return "ask_late";
  if (ev.status === "help_needed" && recent) return "help_sent";
  if (ev.status === "safe" && ev.responded_at) {
    const answeredMs = Date.parse(ev.responded_at.replace(" ", "T"));
    if (now - answeredMs < config.showAnsweredMinutes * 60 * 1000) return "safe_sent";
  }
  return "none";
}

export function reported(ev) {
  return Boolean(ev && ev.escalation && ev.escalation.report);
}

// onState(state, ev): 상태가 바뀔 때마다 알려 줌 (레이어가 보이기/숨기기에 사용)
export function createIncidentPanel({ api, statusPoller, config, onState }) {
  const notice = el("div", { className: "notice", hidden: true });
  const body = el("div");
  const element = el("div", {}, notice, body);

  let shownKey = null;      // 지금 그려진 상태 (바뀔 때만 다시 그림)
  let latest = null;        // 마지막으로 받은 낙상 기록
  let receivedAt = 0;       // 그 기록을 받은 시각 (남은 시간 계산용)
  let sending = false;
  const counters = [];      // 1초마다 갱신할 남은 시간 문구들

  function secondsLeft(serverSeconds) {
    if (serverSeconds === null || serverSeconds === undefined) return null;
    return Math.max(0, serverSeconds - Math.floor((Date.now() - receivedAt) / 1000));
  }

  // 남은 시간 문구 (1초마다 갱신)
  function countdown(makeText, serverSecondsOf) {
    const node = el("p", { className: "lead" });
    const update = () => {
      const left = secondsLeft(serverSecondsOf(latest));
      node.hidden = left === null;
      if (left !== null) node.textContent = makeText(left);
    };
    counters.push(update);
    update();
    return node;
  }

  function reportCountdown() {
    return countdown((s) => `${s}초 뒤 119에 신고해요 (시뮬레이션). 괜찮으면 '괜찮아요'를 누르세요.`,
      (ev) => (ev ? ev.report_in_seconds : null));
  }

  async function answer(response) {
    if (!latest || sending) return;
    sending = true;
    body.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      await api.respond(latest.event_id, response);
    } catch (error) {
      sending = false;
      showNotice(error instanceof AuthError ? "로그인이 필요해요." : "보내지 못했어요. 한 번 더 눌러 주세요.");
      body.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      return;
    }
    sending = false;
    shownKey = null; // 응답 결과 화면으로 다시 그리기
    await statusPoller.refreshNow();
  }

  function answerButtons() {
    return [
      button("괜찮아요", "가족에게 괜찮다고 알려요", { className: "safe", onClick: () => answer("safe") }),
      button("도움이 필요해요", "가족에게 바로 알려요", { className: "help", onClick: () => answer("help_needed") }),
    ];
  }

  function testBadge(ev) {
    return ev && ev.is_test ? el("p", {}, el("span", { className: "badge" }, "테스트")) : null;
  }

  function draw(state, ev) {
    counters.length = 0;
    body.replaceChildren();
    if (state === "none") {
      const checked = el("p", { className: "muted" });
      counters.push(() => {
        if (receivedAt) checked.textContent = `마지막 확인 ${new Date(receivedAt).toLocaleTimeString("ko-KR")}`;
      });
      body.append(el("div", { className: "panel" },
        el("p", { className: "lead" }, "진행 중인 낙상 확인 요청이 없어요"),
        el("p", {}, "낙상이 감지되면 이 화면에 질문이 나타나요. (웹앱을 열어 둔 동안)"),
        checked));
      counters.forEach((update) => update());
      return;
    }
    if (state === "ask" || state === "ask_late") {
      const panel = el("div", { className: "panel alert" }, testBadge(ev),
        el("p", { className: "question" }, "넘어지셨나요?", el("br"), "괜찮으세요?"));
      if (state === "ask") {
        panel.append(countdown((s) => `${s}초 안에 눌러 주세요`, (e) => (e ? e.remaining_seconds : null)));
      } else {
        panel.append(el("p", { className: "lead" }, "응답이 없어서 가족에게 알렸어요. 지금이라도 눌러 주세요."));
        if (reported(ev)) panel.append(el("p", {}, "119 신고(시뮬레이션)를 했어요. 실제 119에는 연락하지 않았어요."));
        else panel.append(reportCountdown());
      }
      body.append(panel, ...answerButtons());
      return;
    }
    if (state === "help_sent") {
      body.append(el("div", { className: "panel help" }, testBadge(ev),
        el("p", { className: "question" }, "도움 요청을 보냈어요"),
        el("p", { className: "lead" }, "가족에게 알렸어요. 움직이지 말고 기다려 주세요."),
        reported(ev) ? el("p", {}, "119 신고(시뮬레이션)를 했어요. 실제 119에는 연락하지 않았어요.") : reportCountdown()),
        button("괜찮아졌어요", "가족에게 괜찮다고 알려요", { className: "safe", onClick: () => answer("safe") }));
      return;
    }
    // safe_sent
    body.append(el("div", { className: "panel safe" }, testBadge(ev),
      el("p", { className: "question" }, "괜찮다고 전했어요"),
      el("p", { className: "lead" }, reported(ev)
        ? "이미 119 신고(시뮬레이션)가 된 뒤라 가족에게 신고 취소를 요청했어요."
        : "가족에게 알렸어요.")),
      button("다시 도움이 필요해요", "가족에게 바로 알려요", { className: "help", onClick: () => answer("help_needed") }));
  }

  function showNotice(text) {
    notice.hidden = !text;
    notice.textContent = text || "";
  }

  // 서버 상태가 올 때마다 (로그인 필요 안내는 앱 전체 안내 줄이 보여 줌: app.js)
  const unsubscribe = statusPoller.subscribe(({ data, error }) => {
    if (error instanceof AuthError) {
      showNotice("");
      return;
    }
    showNotice(error ? "서버에 연결할 수 없어요. 다시 시도하고 있어요." : "");
    if (!data) return;
    latest = data[0] || null;
    receivedAt = Date.now();
    const state = classify(latest, config, Date.now());
    const key = `${state}:${latest ? latest.event_id : ""}:${reported(latest)}`;
    if (key !== shownKey && !sending) {
      shownKey = key;
      draw(state, latest);
      if (onState) onState(state, latest);
    } else {
      counters.forEach((update) => update());
    }
  });

  // 남은 시간을 1초마다 갱신
  const timer = setInterval(() => counters.forEach((update) => update()), 1000);

  return {
    element,
    destroy() {
      unsubscribe();
      clearInterval(timer);
    },
  };
}
