// 사고 대응 레이어: 어느 메뉴를 보고 있든, 확인이 필요한 낙상이 있으면 화면 맨 위에 띄웁니다.
// 웹앱을 열어 둔 동안에만 동작합니다 (웹 푸시 없음). 브라우저가 닫혀 있어도 서버의 응답 마감과
// 가족 텔레그램 알림은 그대로 진행됩니다.
import { button, el } from "../ui.js";
import { createIncidentPanel } from "./panel.js";

// 질문 중(응답이 필요할 때)에는 레이어를 숨길 수 없음
const MUST_ANSWER = new Set(["ask", "ask_late"]);

// 기기 역할을 나누지 않으므로, 웹앱을 연 기기라면 누구의 기기든 띄웁니다 (가족 누구나 응답 가능)
export function startIncidentLayer({ layer, banner, api, statusPoller, config }) {
  let current = { state: "none", key: "" };
  let hiddenKey = null; // '다른 화면 보기'를 누른 사고·상태 (사고나 상태가 바뀌면 다시 띄움)

  const panel = createIncidentPanel({
    api, statusPoller, config,
    onState(state, ev) {
      current = { state, key: `${ev ? ev.event_id : ""}:${state}` };
      update();
    },
  });

  const hideButton = button("다른 화면 보기", "위쪽 알림 줄에서 이 화면을 다시 열 수 있어요", {
    onClick: () => { hiddenKey = current.key; update(); },
  });
  layer.append(el("div", { className: "incident-inner" },
    el("p", { className: "incident-title", id: "incident-title" }, "낙상 확인"),
    panel.element,
    hideButton));

  const openButton = el("button", { type: "button" }, "열기");
  openButton.addEventListener("click", () => { hiddenKey = null; update(); });
  banner.append(el("span", {}, "진행 중인 낙상 대응이 있어요"), openButton);

  function update() {
    const active = current.state !== "none";
    const canHide = !MUST_ANSWER.has(current.state);
    const hidden = canHide && hiddenKey === current.key;
    const wasHidden = layer.hidden;
    hideButton.hidden = !canHide;
    layer.hidden = !active || hidden;
    banner.hidden = !active || !hidden;
    document.body.classList.toggle("incident-open", !layer.hidden);
    if (wasHidden && !layer.hidden) layer.focus();
  }

  update();
}
