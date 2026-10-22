/* ------------------------------------------------------------------
 * api-live.js — 실제 모드의 데이터 공급 계층 (서버 /api/v2)
 *
 * 실제 모드일 때만 FD.API 를 이 구현으로 바꿉니다. 테스트 모드에서는 아무것도 하지 않으므로
 * api.js 의 예시 데이터가 그대로 쓰입니다.
 * - 데이터는 서버에서만 가져오고, 브라우저 저장소(localStorage)에 저장하지 않습니다.
 * - 로그인은 서버가 주는 쿠키(fd_session, 스크립트에서 읽을 수 없음)로 유지됩니다.
 * - 서버에 연결된 동작: 가입·로그인·로그아웃·그룹 만들기·초대 코드·참여·나가기·처음 설정 완료 (B단계),
 *   내 정보·건강 정보·알림 설정·집 추가/연결/해제/주소·처음 설정 한 번에 저장·회원 탈퇴 (C단계),
 *   낙상 사고 응답·확인·종료·신고(모의)·닫기, 알림 읽음 (D단계). 기기는 F단계에서 추가합니다.
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
    /* 주소: 서버가 도로명주소 검색 API 를 대신 호출 (승인키는 서버 .env 에만). 결과는 도로명 주소 문자열 목록.
       addressSearch 를 false 로 바꾸면 화면이 검색창 대신 주소 입력칸만 보여 줌 (onboarding.js·family.js).
       검색이 안 될 때(서버 설정 없음·API 장애)는 화면의 '직접 입력하기'로 입력 */
    addressSearch: true,
    async searchAddress(q) {
      const data = await call('GET', '/api/v2/address/search?q=' + encodeURIComponent(q || ''));
      return (data && data.results || []).map(r => r.address);
    },

    /* ---- 계정 (B단계) ---- 각 함수는 { authenticated, me_id, state } 를 돌려줌 */
    async signup({ name, phone, password }) { return remember(await call('POST', '/api/v2/auth/signup', { name, phone, password })); },
    async login({ phone, password }) { return remember(await call('POST', '/api/v2/auth/login', { phone, password })); },
    async logout() { return remember(await call('POST', '/api/v2/auth/logout')); },
    async createGroup() { return remember(await call('POST', '/api/v2/groups')); },
    async regenInvite() { return remember(await call('POST', '/api/v2/groups/invite')); },
    async joinGroup(code) { return remember(await call('POST', '/api/v2/groups/join', { code })); },
    async leaveGroup() { return remember(await call('POST', '/api/v2/groups/leave')); },
    async setOnboarded(onboarded) { return remember(await call('POST', '/api/v2/me/onboarded', { onboarded })); },

    /* ---- 내 정보 · 집 · 탈퇴 (C단계) ---- 사람·집 id 는 서버가 로그인한 사람의 그룹 안에서만 찾음 */
    async updateProfile(body) { return remember(await call('POST', '/api/v2/me/profile', body)); },   // { name, birth?, conditions?, medications? }
    async setPref(key, value) { return remember(await call('POST', '/api/v2/me/prefs', { key, value })); },
    async finishSetup(info, home, entrances) { return remember(await call('POST', '/api/v2/me/setup', entrances ? { info, home, entrances } : { info, home })); },
    async linkHome(homeId) { return remember(await call('POST', `/api/v2/homes/${encodeURIComponent(homeId)}/link`)); },
    async unlinkHome(homeId) { return remember(await call('POST', `/api/v2/homes/${encodeURIComponent(homeId)}/unlink`)); },
    async updateHomeAddress(homeId, address) { return remember(await call('POST', `/api/v2/homes/${encodeURIComponent(homeId)}/address`, { address })); },
    async withdraw(password) { return remember(await call('POST', '/api/v2/me/withdraw', { password })); },

    /* ---- 현관 비밀번호 (H단계) ---- 등록·변경·삭제만. 값을 받아 오는 주소는 없음 (응답은 등록 여부만) */
    async setDoorCode(homeId, kind, code) { return remember(await call('PUT', `/api/v2/homes/${encodeURIComponent(homeId)}/door-codes/${encodeURIComponent(kind)}`, { code })); },
    async setEntrance(homeId, kind, method, code) { return remember(await call('PUT', `/api/v2/homes/${encodeURIComponent(homeId)}/entrances/${encodeURIComponent(kind)}`, code ? { method, code } : { method })); },
    async deleteDoorCode(homeId, kind) { return remember(await call('DELETE', `/api/v2/homes/${encodeURIComponent(homeId)}/door-codes/${encodeURIComponent(kind)}`)); },

    /* ---- 낙상 사고 (D단계) ---- action: self-ok · help · take-over · close · report · dismiss.
       같은 그룹의 사고만. 다른 사람이 먼저 처리했으면 409 (store.js 가 최신 상태로 다시 그림).
       119 신고는 서버가 모의 신고로 기록만 함 (실제 119 연락 없음) */
    async incidentAction(id, action, body) { return remember(await call('POST', `/api/v2/incidents/${encodeURIComponent(id)}/${action}`, body)); },
    async readNotifs() { return remember(await call('POST', '/api/v2/notifications/read')); }
  };
})();
