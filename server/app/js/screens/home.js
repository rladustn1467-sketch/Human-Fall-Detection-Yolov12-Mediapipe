// 홈: 낙상 감지 시스템의 상태와 최근 낙상 감지 기록을 확인하고 다른 메뉴로 이동합니다.
// 확인할 수 없는 상태는 '확인 불가'로 표시하고, "안전" 같은 표현은 쓰지 않습니다.
import { AuthError } from "../api.js";
import { eventPanelClass, eventStatusText } from "../labels.js";
import { button, el, statusList } from "../ui.js";
import { detectionStatusPanel } from "./detection.js";

export function render(container, { statusPoller, go }) {
  const recent = el("div", { className: "panel" }, el("p", { className: "lead" }, "최근 낙상 감지"),
    el("p", { className: "muted" }, "서버에서 확인하는 중이에요..."));

  container.append(
    el("h1", {}, "홈"),
    detectionStatusPanel(),
    button("낙상 감지 화면으로", "감지 상태와 기록을 자세히 봐요", { onClick: () => go("detection") }),
    recent,
    button("낙상 예방 정보 보기", "운동, 집 안 점검, 생활 수칙", { onClick: () => go("prevention") }),
  );

  // 최근 낙상 감지 1건 (공통 폴링 결과 사용)
  return statusPoller.subscribe(({ data, error, fetchedAt }) => {
    const latest = data ? data[0] : undefined;
    recent.replaceChildren(el("p", { className: "lead" }, "최근 낙상 감지"));
    if (latest === undefined) {
      recent.append(el("p", {}, error instanceof AuthError ? "로그인이 필요해요."
        : "서버에 연결할 수 없어 확인하지 못했어요."));
      return;
    }
    if (latest === null) {
      recent.className = "panel";
      recent.append(el("p", {}, "서버에 기록된 낙상 감지가 없어요."));
    } else {
      recent.className = eventPanelClass(latest);
      recent.append(
        latest.is_test ? el("p", {}, el("span", { className: "badge" }, "테스트")) : null,
        statusList([
          ["감지 시각", latest.time],
          ["처리 상태", eventStatusText(latest)],
          ["알림·119", latest.escalation_label || "-"],
          ["감지 기기", latest.device_id],
        ]),
      );
    }
    if (fetchedAt) {
      const stale = error ? " (지금은 서버에 연결할 수 없어 이전 정보예요)" : "";
      recent.append(el("p", { className: "muted" },
        `마지막 확인 ${new Date(fetchedAt).toLocaleTimeString("ko-KR")}${stale}`));
    }
  });
}
