// 앱 설정값 (여기서 바꾸면 앱 전체에 적용됩니다)
export const CONFIG = {
  // 서버에서 현재 낙상 상태를 가져오는 간격(초)
  pollIntervalSeconds: 3,
  // 본인 화면: 이 시간(분)보다 오래된 낙상은 '진행 중'으로 보지 않음
  activeMinutes: 30,
  // 본인 화면: '괜찮아요'를 누른 뒤 확인 문구를 보여 주는 시간(분)
  showAnsweredMinutes: 3,
};
