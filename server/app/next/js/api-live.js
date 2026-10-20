/* ------------------------------------------------------------------
 * api-live.js — 실제 모드의 데이터 공급 계층 (서버 /api/v2)
 *
 * 실제 모드일 때만 FD.API 를 이 구현으로 바꿉니다. 테스트 모드에서는 아무것도 하지 않으므로
 * api.js 의 예시 데이터가 그대로 쓰입니다.
 * - 데이터는 서버에서만 가져오고, 브라우저 저장소(localStorage)에 저장하지 않습니다.
 * - 동작(가입, 그룹, 집, 기기, 사고 대응 …)의 서버 연결은 B단계부터 하나씩 추가합니다.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  if (FD.MODE !== 'live') return;

  let snapshot = null;   // 서버에서 받은 마지막 상태 (메모리에만)
  let session = null;    // 로그인한 사람 id (B단계부터 서버 로그인과 연결)

  async function getJson(path) {
    const res = await fetch(path, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`서버 오류 (HTTP ${res.status})`);
    return res.json();
  }

  FD.API = {
    live: true,
    KEY: null,           // 실제 모드는 브라우저 저장소를 쓰지 않음
    SESSION_KEY: null,
    uid(prefix) { return (prefix || 'id') + '_' + Math.random().toString(36).slice(2, 9); },
    seedHistory() { return []; },
    async loadSnapshot() {
      const data = await getJson('/api/v2/state');
      snapshot = data.state;
      session = data.me_id || null;
      return snapshot;
    },
    readSnapshot() { return snapshot; },
    writeSnapshot(state) { snapshot = state; },   // 메모리만. 서버 반영은 동작별 API 로 (B단계부터)
    resetSnapshot() { throw new FD.NotReadyError('실제 모드에서는 데이터를 초기화할 수 없어요'); },
    readSession() { return session || '__none__'; },
    writeSession(id) { session = id || null; },
    async searchAddress() {                        // 주소 검색 API 는 H단계에서 연결
      // 빈 결과를 돌려주면 '검색 결과 없음'으로 보이므로, 준비 중임을 알리고 멈춤
      if (FD.UI) FD.UI.toast('주소 검색은 아직 서버와 연결 중이에요');
      throw new FD.NotReadyError('searchAddress');
    }
  };
})();
