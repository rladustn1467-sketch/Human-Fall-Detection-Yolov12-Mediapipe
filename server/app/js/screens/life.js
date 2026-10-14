// 생활 관리: 낙상 사고 대응에 쓰이는 거주자 정보를 확인하는 화면입니다.
// 거주자 정보 조회와 '정보가 오래됐을 수 있음' 경고는 다음 단계에서 서버와 연결합니다.
// 이 웹앱에서는 거주자 정보·현관 비밀번호를 입력하거나 고치지 않습니다.
import { el } from "../ui.js";

export function render(container) {
  container.append(
    el("h1", {}, "생활 관리"),
    el("div", { className: "panel" },
      el("p", { className: "lead" }, "거주자 정보"),
      el("p", {}, el("span", { className: "badge" }, "준비 중"),
        " 서버에 등록된 거주자 정보(별칭, 나이, 지병, 복용약, 정보 갱신일)를 여기에서 볼 수 있게 연결할 예정이에요."),
      el("p", { className: "muted" }, "이 화면에서는 정보를 입력하거나 고칠 수 없어요.")),
  );
}
