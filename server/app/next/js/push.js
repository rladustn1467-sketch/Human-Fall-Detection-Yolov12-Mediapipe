/* ------------------------------------------------------------------
 * push.js — 가족 휴대폰 푸시 알림 (실제 모드, Android 앱 안에서만: Push 플러그인 mobile/ push/)
 *
 *  - 로그인하면 이 휴대폰의 알림 토큰을 서버에 등록 (서버는 이 로그인 세션에 묶음: 로그아웃·탈퇴하면 함께 삭제)
 *  - 처음 한 번 안드로이드 알림 권한을 물어봄. 거부·끈 경우는 설정 → 알림 설정에서 안내
 *  - 낙상 알림을 눌러 앱을 열면 그 사고 화면으로 (진행 중이면 긴급 화면, 끝났으면 이력 상세)
 *  - 앱이 화면에 떠 있을 때 온 푸시는 시스템 알림을 띄우지 않고(앱이 긴급 화면을 보여 줌) 서버 상태만 바로 다시 읽음
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const R = FD.Router;
  const LIVE = FD.MODE === 'live';
  const wait = ms => new Promise(r => setTimeout(r, ms));

  const available = () => {
    const cap = window.Capacitor;
    return !!(LIVE && cap && cap.isNativePlatform && cap.isNativePlatform() && cap.nativePromise
      && (cap.PluginHeaders || []).some(p => p.name === 'Push'));
  };
  const native = (method, opts) => window.Capacitor.nativePromise('Push', method, opts || {});
  const Sel = () => FD.Store.Sel;

  let lastToken = null;       // 이 휴대폰의 토큰 (로그아웃 때 서버에서 지우려고 기억)
  let registeredFor = null;   // 이미 등록한 '사람+토큰' (같은 것을 계속 보내지 않음)
  let asked = false;          // 이번 실행에서 권한을 이미 물었는지

  async function status() {
    if (!available()) return null;
    try { return await native('status'); } catch (e) { return null; }
  }

  /* 로그인한 상태에서: (처음이면) 권한 묻기 → 토큰 → 서버 등록. 권한이 없어도 토큰은 등록 (나중에 켜면 바로 받음) */
  async function register() {
    if (!available() || !Sel().me()) return;
    const st = await status();
    if (st && st.permission === 'prompt' && !asked) {
      asked = true;
      try { await native('requestPermission'); } catch (e) { /* 거부해도 앱은 그대로 */ }
    }
    try {
      const { token } = await native('getToken');
      if (!token) return;
      lastToken = token;
      const key = Sel().meId() + ':' + token;
      if (registeredFor === key) return;
      await FD.API.registerPushToken(token);
      registeredFor = key;
    } catch (e) { /* 토큰을 받지 못함(네트워크·Play 서비스): 다음에 앱을 열 때 다시 */ }
  }

  /* 로그아웃·탈퇴 전에: 이 휴대폰 토큰을 서버에서 지움 (서버도 세션이 끝나면 지우지만, 먼저 확실히) */
  async function unregister() {
    if (!available() || !lastToken) return;
    try { await FD.API.unregisterPushToken(lastToken); } catch (e) { /* 세션 삭제로 서버가 함께 지움 */ }
    registeredFor = null;
  }

  /* 알림으로 연 사고: 서버 상태에 나타날 때까지 잠시 기다린 뒤 (내 그룹 사고만 보임) */
  async function openIncident(id) {
    if (!id || !Sel().me()) return;
    for (let i = 0; i < 10 && !Sel().incident(id); i++) { await FD.Store.refresh(); await wait(500); }
    const inc = Sel().incident(id);
    if (!inc) { R.go('/notifications'); return; }
    if (Sel().isTerminal(inc)) R.go('/history/' + inc.id);
    else if (FD.Emergency) FD.Emergency.open(inc.id);
  }
  async function takeOpened() {
    if (!available() || !Sel().me()) return;   // 로그인 전이면 로그인한 뒤에 엶
    try {
      const r = await native('takeOpenedIncident');
      if (r && r.incidentId) await openIncident(r.incidentId);
    } catch (e) { /* 없음 */ }
  }

  function start() {
    if (!available()) return;
    /* 서버 주소를 여는 앱이라 @capacitor/core 의 registerPlugin 이 없음: 앱이 넣어 준 Capacitor.Plugins 를 씀 */
    const Push = window.Capacitor.Plugins && window.Capacitor.Plugins.Push;
    try {
      Push.addListener('incidentOpened', e => openIncident(e && e.incidentId));
      Push.addListener('received', () => FD.Store.refresh());
      Push.addListener('tokenChanged', () => { registeredFor = null; register(); });
    } catch (e) { console.error(e); }   // 이벤트를 못 받아도 로그인 때 등록, 앱을 열 때 사고 화면은 동작
    FD.Store.subscribe(kind => {
      if (kind !== 'session') return;
      if (Sel().me()) { register(); takeOpened(); } else registeredFor = null;
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') { register(); takeOpened(); }
    });
    register();
    takeOpened();
  }

  FD.Push = {
    available, status, register, unregister, start,
    requestPermission: () => native('requestPermission'),
    openSettings: () => native('openSettings')
  };
})();
