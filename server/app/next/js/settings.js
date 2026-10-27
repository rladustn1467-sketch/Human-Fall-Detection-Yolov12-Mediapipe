/* ------------------------------------------------------------------
 * settings.js — T-04 설정, S-09 회원 탈퇴, S-10 내 프로필 수정, S-11 알림 설정
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, toast, field, setError, val, openSheet, closeSheet } = UI;
  const { Sel, Act } = FD.Store;
  const R = FD.Router;
  const LIVE = FD.MODE === 'live';
  const PROFILE_FIELDS = { name: 'pf-name', phone: 'pf-phone' };

  R.register('/settings', () => {
    const me = Sel.me();
    return {
      html: `<header class="tab-head"><div><h1 class="page-title">설정</h1></div></header>
      <div class="page page--tight">
        <button class="card profile-card" style="width:100%;text-align:left" data-action="settings.profile">${UI.avatar(me, 'lg')}
          <span style="flex:1;min-width:0"><span class="profile-card__name" style="display:block">${esc(me.name)}</span><span class="profile-card__meta" style="display:block">${esc(me.phone)}</span>
          <span class="tag ${me.isTarget ? 'tag--ok' : 'tag--info'}" style="margin-top:6px">${me.isTarget ? '감지 대상자' : '알림만 받는 중'}</span></span>${ic('chevron-right', 'chev')}</button>
        <div class="card" style="margin-top:16px">
          <button class="row" data-action="settings.profile"><span class="det-dev__ic">${ic('user')}</span><span class="row__main"><span class="row__title">내 프로필</span></span>${ic('chevron-right', 'chev')}</button>
          <button class="row" data-action="settings.notif"><span class="det-dev__ic">${ic('bell')}</span><span class="row__main"><span class="row__title">알림 설정</span></span>${ic('chevron-right', 'chev')}</button>
        </div>
        ${UI.nativeDetector() ? `<div class="card" style="margin-top:16px">
          <button class="row" data-action="settings.detector"><span class="det-dev__ic">${ic('mobile-screen')}</span><span class="row__main"><span class="row__title">이 휴대폰으로 감지하기</span><span class="row__sub" id="self-det-sub" style="display:block">${SELF_SUB}</span></span>${ic('chevron-right', 'chev')}</button>
        </div>` : ''}
        <div class="card" style="margin-top:16px">
          <button class="row" data-action="settings.logout"><span class="det-dev__ic">${ic('right-from-bracket')}</span><span class="row__main"><span class="row__title">로그아웃</span></span>${ic('chevron-right', 'chev')}</button>
          <button class="row row--danger" data-action="settings.withdraw"><span class="det-dev__ic" style="background:var(--stop-soft);color:var(--stop)">${ic('user-slash')}</span><span class="row__main"><span class="row__title">회원 탈퇴</span></span>${ic('chevron-right', 'chev')}</button>
        </div>
      </div>`,
      mount: root => {
        if (!UI.nativeDetector()) return;
        // 이 휴대폰이 이미 감지 기기로 연결돼 있으면 그 상태를 보여 줌 (휴대폰이 알려 준 값 그대로)
        FD.DeviceConnect.self.status().then(r => {
          const sub = root.querySelector('#self-det-sub'), s = r && r.s;
          if (sub && s && s.paired) sub.textContent = `감지 기기로 연결됨${s.location ? ' · ' + s.location : ''} · 눌러서 감지 상태를 확인해요`;
        });
      }
    };
  }, { tab: 'settings', live: true });
  const SELF_SUB = '연결 코드 없이 내 계정의 집에 이 휴대폰을 바로 연결해요';

  /* 이 휴대폰으로 감지하기 (Android 앱 안에서만): 처음 설정·기기 추가와 같은 흐름 (devices.js) */
  on('settings.detector', () => FD.DeviceConnect.self.start());
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
          ${LIVE ? field({ id: 'pf-phone', label: '휴대전화 번호', type: 'tel', value: me.phone, hint: '휴대전화 번호는 로그인 아이디라서 지금은 바꿀 수 없어요.' })
            : field({ id: 'pf-phone', label: '휴대전화 번호', type: 'tel', inputmode: 'numeric', value: me.phone, oninput: 'phone-fmt' })}
        </form>
        ${me.isTarget ? `<p class="group-label" style="margin-top:6px">건강 정보 <small>그룹 가족에게 공유돼요</small></p>
          <section class="info-item"><div class="info-item__head"><h3>생년월일</h3></div>${UI.birthInput('pf-birth', me.birth)}</section>
          ${listBlock('conditions', '지병', UI.SUGGEST_COND, '지병이 없어요')}${listBlock('medications', '복용약', UI.SUGGEST_MED, '복용하는 약이 없어요')}` : `<div class="notice">${ic('circle-info')}<span>낙상 감지를 켜면 생년월일·지병·복용약을 입력할 수 있어요.</span></div>`}
        <button class="btn btn--primary btn--lg btn--block" style="margin-top:16px" data-action="prof.save">저장</button>
      </div>`,
      mount: root => {
        editors = {};
        if (LIVE) { const ph = root.querySelector('#pf-phone'); if (ph) ph.readOnly = true; }   // 번호 변경은 문자 인증 단계에서
        if (!me.isTarget) return;
        [['conditions', UI.SUGGEST_COND], ['medications', UI.SUGGEST_MED]].forEach(([k, s]) => {
          const el = root.querySelector('#pt-' + k);
          editors[k] = UI.tagEditor(el, { value: Array.isArray(me[k]) ? me[k] : [], suggestions: s, placeholder: '직접 입력' });
        });
      }
    };
  }, { parent: '/settings' });
  on('prof.none', el => { document.getElementById('pt-' + el.dataset.key).hidden = el.checked; });
  on('prof.save', async el => {
    const me = Sel.me(); const name = val('pf-name'), phone = val('pf-phone');
    let ok = true;
    if (name.length < 2) { setError('pf-name', '이름을 입력해 주세요.'); ok = false; } else setError('pf-name', '');
    if (!UI.validPhone(phone)) { setError('pf-phone', '휴대전화 번호를 정확히 입력해 주세요.'); ok = false; } else setError('pf-phone', '');
    const birthEl = document.getElementById('pf-birth');
    const birth = birthEl ? UI.checkBirth(birthEl.value) : null;   // 감지 대상자만 입력칸이 있음
    if (birth && birth.error) { setError('pf-birth', birth.error); ok = false; } else if (birthEl) setError('pf-birth', '');
    if (!ok) return;
    const patch = { name, phone: UI.fmtPhone(phone) };
    if (me.isTarget) {
      patch.birth = birth ? birth.value : null;   // 'YYYY-MM-DD' 또는 빈 값(null)
      ['conditions', 'medications'].forEach(k => {
        const none = document.getElementById('pn-' + k).checked;
        const tags = editors[k] ? editors[k].get() : [];
        patch[k] = none ? [] : (tags.length ? tags : null);
      });
    }
    try {
      await UI.busy(el, () => Act.updateProfile(me.id, patch));
    } catch (e) { UI.showError(e, PROFILE_FIELDS); return; }
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
  on('pref.toggle', async el => {
    const k = el.dataset.key; const me = Sel.me();
    try { await Act.setPref(me.id, k, !(me.prefs[k] !== false)); } catch (e) { UI.showError(e); }
  });

  /* ---------------- 로그아웃 ---------------- */
  on('settings.logout', async el => {
    // 이 휴대폰이 '이 휴대폰으로 감지하기'로 감지 중이면 로그아웃하면서 감지도 멈춤 (devices.js, Android 앱)
    const S = FD.DeviceConnect && FD.DeviceConnect.self;
    const st = S && UI.nativeDetector() ? ((await S.status()) || {}).s : null;
    const selfOn = !!(st && st.paired && st.mode === 'self');
    const ok = await UI.confirm({ title: '로그아웃할까요?',
      body: '이 기기에서 로그아웃해요. 다시 쓰려면 휴대전화 번호와 비밀번호로 로그인해 주세요.'
        + (selfOn ? ' 이 휴대폰으로 하던 낙상 감지도 멈춰요. 다시 로그인한 뒤 감지 화면에서 직접 켜야 다시 감지해요.' : ''),
      ok: '로그아웃', cancel: '취소' });
    if (!ok) return;
    let stop = { self: false };
    try {
      await UI.busy(el, async () => {
        if (S) stop = await S.stopForLogout();
        // 감지를 멈추지 못했으면 로그아웃하지 않음 (멈춘 것처럼 보이지 않도록)
        if (stop.self && !stop.stopped) throw new FD.ApiError(0, '이 휴대폰의 감지를 멈추지 못해 로그아웃하지 않았어요. 다시 시도해 주세요.');
        await Act.signOut();
      });
    } catch (e) {
      if (stop.self && stop.stopped) UI.toast('이 휴대폰의 감지는 멈췄지만 로그아웃하지 못했어요. 다시 시도해 주세요.');
      else UI.showError(e);
      return;
    }
    FD.Onboarding.resetDraft();
    R.go('/ob/login', { replace: true });
    if (stop.self) UI.toast(stop.serverUpdated ? '로그아웃했어요. 이 휴대폰의 감지를 멈췄어요.'
      : '로그아웃했어요. 이 휴대폰의 감지를 멈췄어요 (서버에는 연결되면 알려요).', 'ok');
  });

  /* ---------------- S-09 회원 탈퇴 ---------------- */
  on('settings.withdraw', async () => {
    const ok = await UI.confirm({ title: '정말 탈퇴할까요?', body: '계정과 개인정보가 삭제되고, 그룹에서도 나가요.', ok: '탈퇴하기', cancel: '취소', danger: true });
    if (!ok) return;
    if (LIVE) { withdrawSheet(); return; }
    Act.withdraw(Sel.meId());
    FD.Onboarding.resetDraft();
    R.go('/ob/signup', { replace: true });
  });

  /* 실제 모드: 비밀번호를 한 번 더 확인한 뒤 서버가 삭제 */
  function withdrawSheet() {
    openSheet({
      title: '비밀번호 확인',
      html: `<div class="notice notice--stop" style="margin-bottom:16px">${ic('triangle-exclamation')}<span>탈퇴하면 계정, 로그인 정보, 내 프로필과 건강 정보가 삭제되고 되돌릴 수 없어요. 그룹에 다른 가족이 있으면 그룹과 집 정보는 남아요.</span></div>
        ${field({ id: 'wd-pw', label: '비밀번호', type: 'password', placeholder: '비밀번호 입력', autocomplete: 'current-password', onenter: 'wd.submit' })}
        <button class="btn btn--danger btn--lg btn--block" data-action="wd.submit">탈퇴하기</button>`
    });
    on('wd.submit', async el => {
      const e = document.getElementById('wd-pw'); const pw = e ? e.value : '';   // 비밀번호는 공백 포함 그대로
      if (!pw) { setError('wd-pw', '비밀번호를 입력해 주세요.'); return; }
      // 이 휴대폰이 '이 휴대폰으로 감지하기'로 감지 중이면 탈퇴 전에 감지부터 멈춤 (로그아웃과 같은 방법, devices.js)
      const S = FD.DeviceConnect && FD.DeviceConnect.self;
      let stop = { self: false };
      try {
        await UI.busy(el, async () => {
          if (S) stop = await S.stopForLogout();
          if (stop.self && !stop.stopped) throw new FD.ApiError(0, '이 휴대폰의 감지를 멈추지 못해 탈퇴하지 않았어요. 다시 시도해 주세요.');
          await Act.withdraw(Sel.meId(), pw);
        });
      } catch (err) {
        UI.showError(err, { password: 'wd-pw' });
        if (stop.self && stop.stopped) toast('탈퇴하지 못했어요. 이 휴대폰의 감지는 멈춘 상태예요. 감지 화면에서 다시 켤 수 있어요.');
        return;
      }
      let unpaired = { self: false };
      if (stop.self && S) unpaired = await S.unpairAfterWithdraw();   // 이 휴대폰의 기기 기록·연결 정리
      closeSheet();
      FD.Onboarding.resetDraft();
      toast(stop.self ? (unpaired.removed ? '탈퇴했어요. 이 휴대폰의 감지를 멈추고 기기 연결도 해제했어요.'
        : '탈퇴했어요. 이 휴대폰의 감지를 멈췄어요. 가족 앱의 기기 목록에 남은 이 기기는 가족이 삭제할 수 있어요.')
        : '탈퇴했어요. 그동안 이용해 주셔서 고마워요.');
      R.go('/ob/signup', { replace: true });
    });
  }
})();
