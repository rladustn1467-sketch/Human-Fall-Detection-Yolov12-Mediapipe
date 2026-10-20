/* ------------------------------------------------------------------
 * prevent.js — T-02 예방 탭 (독립 모듈 자리)
 *
 * 이 파일은 다른 코드에 의존하지 않는 교체용 모듈입니다.
 * 예방 팀은 이 파일 전체를 교체하고, window.FD_PREVENT.render(container) 계약만 지키면 됩니다.
 *   - render(container): 탭이 열릴 때 container(HTMLElement) 안에 화면을 그립니다.
 *   - destroy():         (선택) 탭을 떠날 때 정리할 것이 있으면 구현합니다.
 * 앱 셸(router.js 사용 쪽)은 이 계약 외에는 이 모듈의 내부를 알지 못합니다.
 * ------------------------------------------------------------------ */
(function () {
  window.FD_PREVENT = {
    render(container) {
      container.innerHTML =
        '<header class="tab-head"><div><h1 class="page-title">예방</h1></div></header>' +
        '<section id="prevent-module" aria-label="예방"></section>';
    },
    destroy() { }
  };
})();
