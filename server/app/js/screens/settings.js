// 설정 화면: 이 기기에서 쓸 수 있는 기능과 서버 연결 상태를 보여 줍니다.
// 기기마다 '본인용/보호자용' 역할을 고르지 않습니다. 가족 누구나 낙상 감지 대상이면서 알림을 받는 사람일 수 있습니다.
import { el, statusList } from "../ui.js";

export function render(container, { config, statusPoller }) {
  const connection = el("p", { className: "muted" });

  container.append(
    el("h1", {}, "설정"),
    el("div", { className: "panel" },
      el("p", { className: "lead" }, "이 기기에서 되는 일"),
      statusList([
        ["낙상 확인 요청", "웹앱을 열어 둔 동안, 확인이 필요한 낙상이 있으면 어느 화면에서든 보여 줘요. 가족 누구나 응답할 수 있어요."],
        ["낙상 감지 실행", "이 웹앱(브라우저)은 낙상 감지를 실행하지 않아요. 감지는 PC의 낙상 감지 프로그램이 해요."],
        ["낙상 알림 받기", "텔레그램 알림은 서버에 등록된 가족에게 가요. 이 화면에서는 바꿀 수 없어요."],
      ]),
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
