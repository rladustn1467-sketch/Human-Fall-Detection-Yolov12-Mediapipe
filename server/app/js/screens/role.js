// 역할 선택 화면: 이 기기를 본인용으로 쓸지, 보호자용으로 쓸지 고릅니다.
import { getRole, ROLES, setRole } from "../storage.js";
import { button, el } from "../ui.js";

export function render(container, { go }) {
  const current = getRole();
  container.append(
    el("h1", {}, "이 기기는 누가 쓰나요?"),
    el("p", { className: "muted" }, "한 번 고르면 다음부터 바로 그 화면이 열려요. 나중에 '설정'에서 바꿀 수 있어요."),
    button("이 기기는 본인용이에요", "넘어졌을 때 '괜찮아요'를 누르는 기기", {
      className: current === ROLES.SELF ? "primary" : "",
      onClick: () => choose(ROLES.SELF),
    }),
    button("이 기기는 보호자용이에요", "가족의 낙상 소식을 받는 기기", {
      className: current === ROLES.GUARDIAN ? "primary" : "",
      onClick: () => choose(ROLES.GUARDIAN),
    }),
  );

  function choose(role) {
    setRole(role);
    go(role === ROLES.GUARDIAN ? "guardian" : "self");
  }
}
