// 보호자 화면 (껍데기만: 실제 기능은 다음 단계에서)
import { el } from "../ui.js";

export function render(container) {
  container.append(
    el("h1", {}, "보호자 화면"),
    el("div", { className: "panel" },
      el("p", { className: "lead" }, "준비 중이에요"),
      el("p", { className: "muted" }, "지금은 텔레그램으로 낙상 알림과 버튼을 받아 주세요."),
    ),
  );
}
