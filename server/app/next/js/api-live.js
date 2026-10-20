/* ------------------------------------------------------------------
 * api-live.js — 실제 모드의 데이터 공급 계층 (서버 /api/v2)
 *
 * 실제 모드일 때만 FD.API 를 이 구현으로 바꿉니다. 테스트 모드에서는 아무것도 하지 않으므로
 * api.js 의 예시 데이터가 그대로 쓰입니다.
 * - 데이터는 서버에서만 가져오고, 브라우저 저장소(localStorage)에 저장하지 않습니다.
 * - 로그인은 서버가 주는 쿠키(fd_session, 스크립트에서 읽을 수 없음)로 유지됩니다.
 * - 서버에 연결된 동작: 가입·로그인·로그아웃·그룹 만들기·초대 코드·참여·나가기·처음 설정 완료 (B단계).
 *   나머지 동작은 C단계부터 하나씩 추가합니다.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  if (FD.MODE !== 'live') return;

  let snapshot = null;   // 서버에서 받은 마지막 상태 (메모리에만)
  let session = null;    // 로그인한 사람 id (서버 쿠키 기준, 화면 표시용)

  async function call(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body)
      });
    } catch (e) {
      throw new FD.ApiError(0, '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* 내용 없음 */ }
    if (!res.ok) {
      const message = data && typeof data.message === 'string' ? data.message : `요청을 처리하지 못했어요 (HTTP ${res.status}).`;
      throw new FD.ApiError(res.status, message, data && data.field);
    }
    return data;
  }

  // 서버 응답 { authenticated, me_id, state } 를 기억하고 그대로 돌려줌
  function remember(data) {
    snapshot = data.state;
    session = data.me_id || null;
    return data;
  }

  FD.API = {
    live: true,
    KEY: null,           // 실제 모드는 브라우저 저장소를 쓰지 않음
    SESSION_KEY: null,
    uid(prefix) { return (prefix || 'id') + '_' + Math.random().toString(36).slice(2, 9); },
    seedHistory() { return []; },
    async loadSnapshot() { return remember(await call('GET', '/api/v2/state')).state; },
    async fetchState() { return remember(await call('GET', '/api/v2/state')); },   // { authenticated, me_id, state }
    readSnapshot() { return snapshot; },
    writeSnapshot(state) { snapshot = state; },   // 메모리만
    resetSnapshot() { throw new FD.NotReadyError('실제 모드에서는 데이터를 초기화할 수 없어요'); },
    readSession() { return session || '__none__'; },
    writeSession(id) { session = id || null; },
    async searchAddress() {                        // 주소 검색 API 는 H단계에서 연결
      // 빈 결과를 돌려주면 '검색 결과 없음'으로 보이므로, 준비 중임을 알리고 멈춤
      if (FD.UI) FD.UI.toast('주소 검색은 아직 서버와 연결 중이에요');
      throw new FD.NotReadyError('searchAddress');
    },

    /* ---- 계정 (B단계) ---- 각 함수는 { authenticated, me_id, state } 를 돌려줌 */
    async signup({ name, phone, password }) { return remember(await call('POST', '/api/v2/auth/signup', { name, phone, password })); },
    async login({ phone, password }) { return remember(await call('POST', '/api/v2/auth/login', { phone, password })); },
    async logout() { return remember(await call('POST', '/api/v2/auth/logout')); },
    async createGroup() { return remember(await call('POST', '/api/v2/groups')); },
    async regenInvite() { return remember(await call('POST', '/api/v2/groups/invite')); },
    async joinGroup(code) { return remember(await call('POST', '/api/v2/groups/join', { code })); },
    async leaveGroup() { return remember(await call('POST', '/api/v2/groups/leave')); },
    async setOnboarded(onboarded) { return remember(await call('POST', '/api/v2/me/onboarded', { onboarded })); }
  };
})();
