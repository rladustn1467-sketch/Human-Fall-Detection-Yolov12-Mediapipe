// 낙상 감지: 감지 시스템의 상태와 과거 낙상 감지 기록을 보여 줍니다.
// 감지는 웹앱이 아니라 PC의 낙상 감지 프로그램이 실행합니다. 웹앱은 서버에 저장된 기록을 받아 보여 줍니다.
import { AuthError } from "../api.js";
import { eventPanelClass, eventStatusText } from "../labels.js";
import { createPoller } from "../poller.js";
import { el, statusList } from "../ui.js";

// 감지 시스템 상태 상자 (홈에서도 사용)
// 서버가 아직 감지 프로그램의 상태 신호를 받지 않으므로, 확인할 근거가 없는 항목은 모두 '확인 불가'로 표시합니다.
export function detectionStatusPanel() {
  return el("div", { className: "panel" },
    el("p", { className: "lead" }, "낙상 감지 시스템"),
    statusList([
      ["감지 모드", "확인 불가"],
      ["감지 프로그램 연결", "확인 불가"],
      ["영상 처리", "확인 불가"],
      ["마지막 정상 신호", "확인 불가"],
    ]),
    el("p", { className: "muted" },
      "감지 프로그램의 상태 신호는 아직 연결되지 않았어요. 그래서 지금은 낙상 감지가 실제로 동작하고 있는지 이 화면에서 확인할 수 없어요."));
}

function eventItem(ev) {
  return el("div", { className: `${eventPanelClass(ev)} event-item` },
    el("p", {}, el("span", { className: "badge" }, ev.is_test ? "테스트" : "실제")),
    statusList([
      ["감지 시각", ev.time],
      ["처리 상태", eventStatusText(ev)],
      ["응답까지", ev.response_seconds === null || ev.response_seconds === undefined ? "-" : `${ev.response_seconds}초`],
      ["알림·119", ev.escalation_label || "-"],
      ["감지 기기", ev.device_id],
    ]));
}

export function render(container, { api, config }) {
  const list = el("div", {}, el("p", { className: "muted" }, "기록을 불러오는 중이에요..."));
  const checked = el("p", { className: "muted" });

  container.append(
    el("h1", {}, "낙상 감지"),
    detectionStatusPanel(),
    el("div", { className: "panel" },
      el("p", { className: "lead" }, "감지 시작·종료"),
      el("p", {}, "웹앱에서 감지를 시작하고 종료하는 기능은 아직 연결되지 않았어요."),
      el("p", { className: "muted" }, "지금은 PC의 낙상 감지 프로그램(대시보드)에서 직접 시작하고 종료해요.")),
    el("h2", {}, "낙상 감지 기록"),
    checked,
    list,
  );

  const poller = createPoller(() => api.latestEvents(config.historyLimit), config.historyPollSeconds);
  const unsubscribe = poller.subscribe(({ data, error, fetchedAt }) => {
    if (error && !data) {
      list.replaceChildren(el("p", {}, error instanceof AuthError ? "로그인이 필요해요."
        : "서버에 연결할 수 없어 기록을 불러오지 못했어요."));
      return;
    }
    if (fetchedAt) {
      checked.textContent = `최근 ${config.historyLimit}건까지 표시 · 마지막 확인 ${new Date(fetchedAt).toLocaleTimeString("ko-KR")}`
        + (error ? " (지금은 서버에 연결할 수 없어 이전 정보예요)" : "");
    }
    if (!data) return;
    list.replaceChildren(...(data.length ? data.map(eventItem) : [el("p", {}, "서버에 기록된 낙상 감지가 없어요.")]));
  });
  poller.start();

  return () => {
    unsubscribe();
    poller.stop();
  };
}
