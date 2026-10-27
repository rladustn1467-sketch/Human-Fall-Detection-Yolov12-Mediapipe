/* ------------------------------------------------------------------
 * app.js — 앱 시작, 화면 보호(guard), 상태 변경 구독
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const { Store, Router: R, UI, Emergency } = FD;
  const { Sel } = Store;

  /* 예방 탭 — 독립 모듈(prevent.js)의 render(container) 계약만 사용 */
  R.register('/prevent', () => ({
    html: '<div id="prevent-host"></div>',
    mount: el => { if (window.FD_PREVENT) window.FD_PREVENT.render(el.querySelector('#prevent-host')); }
  }), { tab: 'prevent' });

  /* 로그인 · 온보딩 진행 상태에 따라 보낼 곳 결정 */
  R.setGuard(p => {
    const me = Sel.me();
    const inOb = p.startsWith('/ob/') || p.startsWith('/enable/');
    if (!me) return (p === '/ob/signup' || p === '/ob/login' || p === '/ob/join' || p === '/join') ? null : '/ob/login';   // 앱 첫 화면 = 로그인
    if (p === '/ob/login') return '/';   // 이미 로그인한 사람
    if (!me.groupId) return (p === '/ob/group' || p === '/ob/invite' || p === '/ob/join' || p === '/join') ? null : '/ob/group';
    if (me.onboarded === false && !inOb && p !== '/join') return '/ob/ask';
    if (p === '/ob/signup') return '/';
    return null;
  });

  async function boot() {
    try {
      await Store.init();
    } catch (e) {
      console.error(e);
      document.getElementById('view').innerHTML = '<div class="boot"><p>불러오지 못했어요. 새로고침해 주세요.</p></div>';
      return;
    }
    /* 로그인이 풀렸으면(세션 만료·다른 곳에서 세션 삭제 등) 이 휴대폰의 '이 휴대폰으로 감지하기'도 멈춤 (로그아웃과 같은 방법,
       devices.js). 직접 로그아웃·탈퇴는 그 전에 이미 멈춤. 연결 코드로 연결한 감지 전용 휴대폰은 그대로 */
    const stopIfSignedOut = () => {
      if (Sel.me() || !FD.DeviceConnect || !UI.nativeDetector()) return;
      FD.DeviceConnect.self.stopForLogout().then(r => {
        if (!r || !r.self || !r.wasOn) return;
        UI.toast(r.stopped ? '로그인이 풀려 이 휴대폰의 감지를 멈췄어요. 다시 로그인한 뒤 감지 화면에서 켤 수 있어요.'
          : '로그인이 풀렸는데 이 휴대폰의 감지를 멈추지 못했어요. 감지 화면에서 직접 꺼 주세요.');
      });
    };
    stopIfSignedOut();   // 앱이 꺼져 있는 동안 로그인이 풀린 경우
    Store.subscribe(kind => {
      if (kind === 'tick') { UI.tick(document); Emergency.render(false); return; }
      Emergency.render(false);
      if (kind === 'session') { stopIfSignedOut(); Emergency.reset(); R.go(R.path() === '' ? '/' : R.path(), { replace: false }); }
      else {
        R.refresh();
        UI.refreshSheet();
      }
    });
    R.start();
    Emergency.render(true);
  }
  boot();
})();
