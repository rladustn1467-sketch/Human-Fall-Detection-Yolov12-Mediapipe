// 설정 화면: 이 기기의 역할을 보여 주고 바꿀 수 있게 합니다.
import { getRole, ROLES } from "../storage.js";
import { button, el } from "../ui.js";

export function render(container, { go, config, statusPoller }) {
  const roleName = getRole() === ROLES.GUARDIAN ? "보호자용" : "본인용";
  const connection = el("p", { className: "muted" });

  container.append(
    el("h1", {}, "설정"),
    el("div", { className: "panel" },
      el("p", { className: "lead" }, `이 기기: ${roleName}`),
      button("역할 다시 고르기", "본인용 / 보호자용을 바꿔요", { onClick: () => go("role") }),
    ),
    el("div", { className: "panel" },
      el("p", {}, `서버 상태 확인 간격: ${config.pollIntervalSeconds}초`),
      connection,
    ),
  );

  // 서버 연결 상태 표시 (공통 폴링 결과 사용)
  return statusPoller.subscribe(({ error, fetchedAt }) => {
    if (error) connection.textContent = "서버에 연결할 수 없어요. 다시 시도하고 있어요.";
    else if (fetchedAt) connection.textContent = `서버 연결 정상 (마지막 확인 ${new Date(fetchedAt).toLocaleTimeString("ko-KR")})`;
  });
}
