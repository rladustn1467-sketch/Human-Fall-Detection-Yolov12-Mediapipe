// 낙상 기록의 처리 상태를 웹앱에서 보여 줄 문구
// "안전" 처럼 사용자가 안전하다고 오해할 수 있는 말 대신, 실제로 일어난 일(누가 무엇을 눌렀는지)만 씁니다.
// (서버의 status_label 은 텔레그램·기록 페이지용이라 그대로 두고, 웹앱에서만 이 문구를 씁니다)

export function eventStatusText(ev) {
  const late = ev.late_response ? "시간 초과 후 " : "";
  switch (ev.status) {
    case "detected":
    case "awaiting_response":
      return "본인 응답 대기";
    case "timeout":
      return "응답 없음 (시간 초과)";
    case "safe":
      return `${late}본인이 '괜찮아요'라고 응답`;
    case "help_needed":
      return `${late}본인이 '도움이 필요해요'라고 응답`;
    default:
      return ev.status_label || ev.status;
  }
}

// 상자 색: 응답 대기·응답 없음은 주의, 도움 요청은 강조, 그 밖은 기본
export function eventPanelClass(ev) {
  if (ev.status === "help_needed") return "panel help";
  if (ev.status === "awaiting_response" || ev.status === "detected" || ev.status === "timeout") return "panel alert";
  return "panel";
}
