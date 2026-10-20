/* ------------------------------------------------------------------
 * mode.js — 실제 모드 / 테스트 모드 결정 (다른 스크립트보다 먼저 불러옵니다)
 *
 * 실제 모드 (기본): 서버(/api/v2) 데이터만 씁니다. 예시 데이터·가짜 타이머·시간 배속을 쓰지 않고,
 *   브라우저 저장소에 데이터를 저장하지 않습니다.
 * 테스트 모드: 주소에 ?mode=test 를 붙인 화면, dev.html 과 그 미리보기 창.
 *   브라우저 안의 예시 데이터(api.js)만 쓰고, 서버 API 를 부르지 않습니다 (실제 기록·알림과 무관).
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const isDevConsole = /\/dev\.html$/.test(location.pathname);
  const mode = isDevConsole || new URLSearchParams(location.search).get('mode') === 'test' ? 'test' : 'live';
  Object.defineProperty(FD, 'MODE', { value: mode, enumerable: true });

  /* 실제 모드에서 아직 서버에 연결되지 않은 동작을 누르면 이 오류로 처리를 멈춥니다
     (뒤따르는 '완료했어요' 같은 안내가 잘못 표시되지 않도록). 안내는 store.js 가 보여 줍니다. */
  class NotReadyError extends Error {}
  FD.NotReadyError = NotReadyError;
  const isNotReady = e => e instanceof NotReadyError;
  window.addEventListener('error', e => { if (isNotReady(e.error)) e.preventDefault(); });
  window.addEventListener('unhandledrejection', e => { if (isNotReady(e.reason)) e.preventDefault(); });

  if (mode === 'test') {
    const show = () => {
      const bar = document.createElement('div');
      bar.className = 'mode-banner';
      bar.setAttribute('role', 'note');
      bar.textContent = '테스트 모드 · 예시 데이터 (실제 기록·알림과 무관)';
      // dev.html 은 main.css 를 쓰지 않으므로 모양을 여기서 직접 지정
      bar.style.cssText = 'position:sticky;top:0;z-index:2147483000;padding:6px 12px;background:#ffe08a;'
        + 'color:#3a2a00;border-bottom:2px solid #b38600;font:700 13px/1.4 sans-serif;text-align:center';
      document.body.prepend(bar);
    };
    if (document.body) show(); else document.addEventListener('DOMContentLoaded', show);
  }
})();
