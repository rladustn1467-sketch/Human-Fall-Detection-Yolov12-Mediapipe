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
    if (!me) return (p === '/ob/signup' || p === '/ob/join' || p === '/join') ? null : '/ob/signup';
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
    Store.subscribe(kind => {
      if (kind === 'tick') { UI.tick(document); Emergency.render(false); return; }
      Emergency.render(false);
      if (kind === 'session') { Emergency.reset(); R.go(R.path() === '' ? '/' : R.path(), { replace: false }); }
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
