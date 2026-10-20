/* ------------------------------------------------------------------
 * settings.js — T-04 설정, S-09 회원 탈퇴, S-10 내 프로필 수정, S-11 알림 설정
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, toast, field, setError, val } = UI;
  const { Sel, Act } = FD.Store;
  const R = FD.Router;

  R.register('/settings', () => {
    const me = Sel.me();
    return `<header class="tab-head"><div><h1 class="page-title">설정</h1></div></header>
      <div class="page page--tight">
        <button class="card profile-card" style="width:100%;text-align:left" data-action="settings.profile">${UI.avatar(me, 'lg')}
          <span style="flex:1;min-width:0"><span class="profile-card__name" style="display:block">${esc(me.name)}</span><span class="profile-card__meta" style="display:block">${esc(me.phone)}</span>
          <span class="tag ${me.isTarget ? 'tag--ok' : 'tag--info'}" style="margin-top:6px">${me.isTarget ? '감지 대상자' : '알림만 받는 중'}</span></span>${ic('chevron-right', 'chev')}</button>
        <div class="card" style="margin-top:16px">
          <button class="row" data-action="settings.profile"><span class="det-dev__ic">${ic('user')}</span><span class="row__main"><span class="row__title">내 프로필</span></span>${ic('chevron-right', 'chev')}</button>
          <button class="row" data-action="settings.notif"><span class="det-dev__ic">${ic('bell')}</span><span class="row__main"><span class="row__title">알림 설정</span></span>${ic('chevron-right', 'chev')}</button>
        </div>
        <div class="card" style="margin-top:16px">
          <button class="row row--danger" data-action="settings.withdraw"><span class="det-dev__ic" style="background:var(--stop-soft);color:var(--stop)">${ic('user-slash')}</span><span class="row__main"><span class="row__title">회원 탈퇴</span></span>${ic('chevron-right', 'chev')}</button>
        </div>
      </div>`;
  }, { tab: 'settings', live: true });
  on('settings.profile', () => R.go('/settings/profile'));
  on('settings.notif', () => R.go('/settings/notifications'));

  /* ---------------- S-10 내 프로필 수정 ---------------- */
  let editors = {};
  R.register('/settings/profile', () => {
    const me = Sel.me();
    const listBlock = (key, title, sugg, none) => {
      const v = me[key];
      return `<section class="info-item" id="p-${key}"><div class="info-item__head"><h3>${title}</h3></div>
        <label class="check" style="margin-bottom:6px"><input type="checkbox" id="pn-${key}" ${Array.isArray(v) && v.length === 0 ? 'checked' : ''} data-action="prof.none" data-key="${key}"><span>${none}</span></label>
        <div id="pt-${key}" ${Array.isArray(v) && v.length === 0 ? 'hidden' : ''}></div></section>`;
    };
    return {
      html: `${UI.subHeader('내 프로필')}<div class="page page--tight">
        <form id="profile-form" novalidate>
          ${field({ id: 'pf-name', label: '이름', value: me.name, maxlength: 20, autocomplete: 'name' })}
          ${field({ id: 'pf-phone', label: '휴대전화 번호', type: 'tel', inputmode: 'numeric', value: me.phone, oninput: 'phone-fmt' })}
        </form>
        ${me.isTarget ? `<p class="group-label" style="margin-top:6px">건강 정보 <small>그룹 가족에게 공유돼요</small></p>
          <section class="info-item"><div class="info-item__head"><h3>생년월일</h3></div><input type="date" id="pf-birth" value="${esc(me.birth || '')}" max="${new Date().toISOString().slice(0, 10)}" aria-label="생년월일"></section>
          ${listBlock('conditions', '지병', UI.SUGGEST_COND, '지병이 없어요')}${listBlock('medications', '복용약', UI.SUGGEST_MED, '복용하는 약이 없어요')}` : `<div class="notice">${ic('circle-info')}<span>낙상 감지를 켜면 생년월일·지병·복용약을 입력할 수 있어요.</span></div>`}
        <button class="btn btn--primary btn--lg btn--block" style="margin-top:16px" data-action="prof.save">저장</button>
      </div>`,
      mount: root => {
        editors = {};
        if (!me.isTarget) return;
        [['conditions', UI.SUGGEST_COND], ['medications', UI.SUGGEST_MED]].forEach(([k, s]) => {
          const el = root.querySelector('#pt-' + k);
          editors[k] = UI.tagEditor(el, { value: Array.isArray(me[k]) ? me[k] : [], suggestions: s, placeholder: '직접 입력' });
        });
      }
    };
  }, { parent: '/settings' });
  on('prof.none', el => { document.getElementById('pt-' + el.dataset.key).hidden = el.checked; });
  on('prof.save', () => {
    const me = Sel.me(); const name = val('pf-name'), phone = val('pf-phone');
    let ok = true;
    if (name.length < 2) { setError('pf-name', '이름을 입력해 주세요.'); ok = false; } else setError('pf-name', '');
    if (!UI.validPhone(phone)) { setError('pf-phone', '휴대전화 번호를 정확히 입력해 주세요.'); ok = false; } else setError('pf-phone', '');
    if (!ok) return;
    const patch = { name, phone: UI.fmtPhone(phone) };
    if (me.isTarget) {
      const b = document.getElementById('pf-birth').value; patch.birth = b || null;
      ['conditions', 'medications'].forEach(k => {
        const none = document.getElementById('pn-' + k).checked;
        const tags = editors[k] ? editors[k].get() : [];
        patch[k] = none ? [] : (tags.length ? tags : null);
      });
    }
    Act.updateProfile(me.id, patch);
    toast('저장했어요', 'ok'); R.back('/settings');
  });

  /* ---------------- S-11 알림 설정 ---------------- */
  R.register('/settings/notifications', () => {
    const me = Sel.me(); const p = me.prefs;
    const row = (key, title, sub) => `<div class="row"><span class="row__main"><span class="row__title">${title}</span><span class="row__sub">${sub}</span></span>${UI.toggle(p[key] !== false, 'pref.toggle', `data-key="${key}" aria-label="${title}"`)}</div>`;
    return `${UI.subHeader('알림 설정')}<div class="page page--tight">
      <div class="notice notice--stop">${ic('triangle-exclamation')}<span>낙상 알림은 안전을 위해 끌 수 없어요.</span></div>
      <div class="card" style="margin-top:16px">
        ${row('device', '기기 연결 끊김 알림', '감지 기기의 연결이 끊어지면 알려드려요')}
        ${row('member', '새 구성원 참여 알림', '가족이 그룹에 참여하면 알려드려요')}
        ${row('home', '집 정보 변경 알림', '같은 집의 주소·비밀번호·기기가 바뀌면 알려드려요')}
      </div></div>`;
  }, { parent: '/settings', live: true });
  on('pref.toggle', el => { const k = el.dataset.key; const me = Sel.me(); Act.setPref(me.id, k, !(me.prefs[k] !== false)); });

  /* ---------------- S-09 회원 탈퇴 ---------------- */
  on('settings.withdraw', async () => {
    const ok = await UI.confirm({ title: '정말 탈퇴할까요?', body: '계정과 개인정보가 삭제되고, 그룹에서도 나가요.', ok: '탈퇴하기', cancel: '취소', danger: true });
    if (!ok) return;
    Act.withdraw(Sel.meId());
    FD.Onboarding.resetDraft();
    R.go('/ob/signup', { replace: true });
  });
})();
