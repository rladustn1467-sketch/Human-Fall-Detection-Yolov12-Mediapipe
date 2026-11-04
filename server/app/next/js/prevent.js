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
      const list = (title, items) => '<p class="group-label" style="margin-top:18px">' + title + '</p><div class="card"><ul class="prevent-list">'
        + items.map(t => '<li>' + t + '</li>').join('') + '</ul></div>';
      container.innerHTML =
        '<header class="tab-head"><div><h1 class="page-title">예방</h1></div></header>'
        + '<section id="prevent-module" aria-label="예방"><div class="page page--tight">'
        + '<p class="row__sub">넘어지는 일은 집 안에서 많이 일어나요. 할 수 있는 것부터 하나씩 살펴보세요.</p>'
        + list('집 안 점검', ['다니는 길의 전선과 물건을 치워요.', '밀리는 깔개는 고정하거나 치워요.', '욕실에 미끄럼 방지 매트를 깔고 손잡이를 달아요.',
          '밤에 다니는 길에 조명을 켜 둬요.', '계단은 밝게 하고 손잡이를 잡고 다녀요.'])
        + list('생활 수칙', ['앉았다가 일어날 때는 천천히 일어나요.', '집 안에서도 미끄럽지 않은 신발이나 양말을 신어요.', '자주 쓰는 물건은 손이 닿는 곳에 둬요.',
          '어지러운 약을 먹고 있다면 의사나 약사와 상의해요.', '시력을 정기적으로 확인해요.'])
        + '</div></section>';
    },
    destroy() { }
  };
})();
