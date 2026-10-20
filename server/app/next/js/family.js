/* ------------------------------------------------------------------
 * family.js — T-03 가족, S-04 구성원, S-05 집 상세, S-06 초대, S-07 비밀번호 변경,
 *             S-08 그룹 나가기, 주소/기기 추가 시트
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, openSheet, closeSheet, toast, field, setError, val } = UI;
  const { Sel, Act } = FD.Store;
  const R = FD.Router;
  FD.Sheets = FD.Sheets || {};

  /* ------------------------------------------------------------
   * 가족 T-03
   * ---------------------------------------------------------- */
  function memberRow(p, me) {
    const sub = [];
    if (p.id === me.id) sub.push('나');
    if (p.isTarget) {
      const a = UI.age(p.birth);
      if (a != null) sub.push(`만 ${a}세`);
    }
    return `<button class="row" data-action="member.open" data-id="${p.id}">
      ${UI.avatar(p)}<span class="row__main"><span class="row__title">${esc(p.name)}${p.id === me.id ? ' <span class="tag tag--primary">나</span>' : ''}</span>
      <span class="row__sub">${p.isTarget ? '감지 대상자' : '알림만 받는 분'}${p.isTarget && UI.age(p.birth) != null ? ` · 만 ${UI.age(p.birth)}세` : ''}</span></span>${ic('chevron-right', 'chev')}</button>`;
  }
  on('member.open', el => R.go('/family/member/' + el.dataset.id));

  R.register('/family', () => {
    const me = Sel.me();
    const people = Sel.people(me.groupId);
    const homes = Sel.homes(me.groupId);
    const g = Sel.group(me.groupId);
    const placed = new Set();
    const sections = homes.map(h => {
      const ms = people.filter(p => p.isTarget && p.homeIds.includes(h.id) && !placed.has(p.id));
      ms.forEach(p => placed.add(p.id));
      if (!ms.length) return '';
      return `<p class="group-label">${ic('house')} ${esc(Sel.homeName(h, me))} <small>${esc(UI.addr(h))}</small></p><div class="card">${ms.map(p => memberRow(p, me)).join('')}</div>`;
    }).join('');
    const noHome = people.filter(p => p.isTarget && !placed.has(p.id));
    const viewers = people.filter(p => !p.isTarget);
    return `<header class="tab-head"><div><h1 class="page-title">가족</h1><p class="page-sub">${esc(g ? g.name : '')} · ${people.length}명</p></div></header>
      <div class="page page--tight">
        <section aria-label="구성원"><div class="section__head" style="margin-bottom:0"><h2 class="section__title">구성원</h2></div>
          ${sections}
          ${noHome.length ? `<p class="group-label">${ic('house-circle-exclamation')} 집 정보 없음</p><div class="card">${noHome.map(p => memberRow(p, me)).join('')}</div>` : ''}
          ${viewers.length ? `<p class="group-label">${ic('bell')} 알림만 받는 분</p><div class="card">${viewers.map(p => memberRow(p, me)).join('')}</div>` : ''}
        </section>
        <button class="invite-btn" data-action="family.invite">${ic('user-plus')} 초대하기</button>
        <section class="section" aria-label="집 관리"><div class="section__head"><h2 class="section__title">집 관리</h2></div>
          <div class="card">${homes.length ? homes.map(h => {
            const sum = Sel.homeSummary(h);
            return `<button class="row" data-action="home.open" data-id="${h.id}"><span class="det-ic det-ic--${sum.kind}" style="width:42px;height:42px">${ic('house')}</span>
              <span class="row__main"><span class="row__title">${esc(Sel.homeName(h, me))}${(!h.address || !h.centralPw || !h.doorPw) ? ' <span class="tag tag--warn">입력 필요</span>' : ''}</span><span class="row__sub">${esc(UI.addr(h))}</span></span>${ic('chevron-right', 'chev')}</button>`;
          }).join('') : `<div class="empty">${ic('house')}등록된 집이 없어요</div>`}</div></section>
        <section class="section" aria-label="그룹 설정"><div class="section__head"><h2 class="section__title">그룹 설정</h2></div>
          <div class="card"><button class="row row--danger" data-action="group.leave"><span class="row__main"><span class="row__title">그룹 나가기</span></span>${ic('chevron-right', 'chev')}</button></div></section>
      </div>`;
  }, { tab: 'family', live: true });
  on('family.invite', () => R.go('/family/invite'));
  on('home.open', el => R.go('/family/home/' + el.dataset.id));

  /* ---------------- S-04 구성원 상세 ---------------- */
  R.register('/family/member/:id', p => {
    const m = Sel.person(p.id), me = Sel.me();
    if (!m) return `${UI.subHeader('구성원')}<div class="empty" style="margin-top:60px">구성원을 찾을 수 없어요</div>`;
    const self = m.id === me.id;
    const homes = m.homeIds.map(id => Sel.home(id)).filter(Boolean);
    return `${UI.subHeader('구성원')}
      <div class="page page--tight">
        <div class="member-hero">${UI.avatar(m, 'lg')}<h2>${esc(m.name)}</h2><p class="page-sub">${self ? '나 · ' : ''}${m.isTarget ? '감지 대상자' : '알림만 받는 분'}</p></div>
        ${m.isTarget ? `<div class="card card--pad"><div class="kv">
          <div class="kv__row"><span class="kv__k">생년월일</span><span class="kv__v${m.birth ? '' : ' muted'}">${UI.birthLabel(m.birth)}</span></div>
          <div class="kv__row"><span class="kv__k">지병</span><span class="kv__v${m.conditions == null ? ' muted' : ''}">${esc(UI.listLabel(m.conditions))}</span></div>
          <div class="kv__row"><span class="kv__k">복용약</span><span class="kv__v${m.medications == null ? ' muted' : ''}">${esc(UI.listLabel(m.medications))}</span></div>
          ${homes.length ? `<div class="kv__row"><span class="kv__k">거주</span><span class="kv__v">${homes.map(h => esc(UI.addr(h))).join('<br>')}</span></div>` : ''}
        </div></div>` : ''}
        <div class="stack" style="margin-top:16px">
          ${self ? '' : `<a class="btn btn--primary btn--lg btn--block" href="tel:${esc(m.phone.replace(/\D/g, ''))}">${ic('phone')} 전화 걸기</a>`}
          ${self ? `<button class="btn btn--soft btn--block" data-action="member.edit">${ic('pen')} 내 정보 수정</button>` : ''}
        </div>
        ${self ? '' : `<p class="field__hint" style="text-align:center;margin-top:12px">개인정보는 본인만 수정할 수 있어요.</p>`}
      </div>`;
  }, { parent: '/family' });
  on('member.edit', () => R.go('/settings/profile'));

  /* ---------------- S-06 초대 화면 ---------------- */
  R.register('/family/invite', () => {
    const me = Sel.me(); const g = Sel.group(me.groupId);
    return {
      html: `${UI.subHeader('가족 초대하기')}<div class="page page--tight"><p class="ob__sub" style="margin-top:0">QR코드를 보여주거나 초대 코드를 알려주세요.</p><div id="invite-area"></div></div>`,
      mount: root => {
        const inv = Act.regenInvite(g.id, me.id);
        const link = location.href.split('#')[0] + '#/join?code=' + inv.code;
        root.querySelector('#invite-area').innerHTML = `<div class="invite-card">
          ${UI.qr(link, 176)}
          <p class="label" style="margin-bottom:8px">초대 코드</p>
          <div class="code-box">${inv.code.split('').map(c => `<span>${esc(c)}</span>`).join('')}</div>
          <p class="expire">${ic('clock')} 24시간 후 만료돼요 · <span data-left="${inv.expiresAt}"></span></p></div>
          <div class="btn-pair" style="margin-top:14px"><button class="btn btn--soft" data-action="invite.copy">${ic('copy')} 코드 복사</button><button class="btn btn--soft" data-action="invite.share">${ic('share-nodes')} 공유하기</button></div>
          <p class="field__hint" style="text-align:center;margin-top:14px">초대할 때마다 새 코드가 만들어져요.</p>`;
        UI.tick(root);
      }
    };
  }, { parent: '/family' });

  /* 링크로 들어온 초대 (#/join?code=) */
  R.register('/join', () => {
    const code = (R.query().get('code') || '').toUpperCase();
    return { html: '<div class="boot"><i class="fa-solid fa-circle-notch"></i></div>', mount: () => {
      const me = Sel.me();
      if (!me) { R.go('/ob/join?code=' + code, { replace: true }); return; }
      R.go(me.groupId ? '/family' : '/ob/join?code=' + code, { replace: true });
    } };
  });

  /* ---------------- S-05 집 상세 ---------------- */
  R.register('/family/home/:id', p => {
    const h = Sel.home(p.id), me = Sel.me();
    if (!h) return `${UI.subHeader('집 상세')}<div class="empty" style="margin-top:60px">집을 찾을 수 없어요</div>`;
    const can = Sel.canEditHome(h.id, me);
    const people = Sel.linked(h.id);
    const devs = Sel.devices(h.id);
    const pw = (label, reg, key) => `<div class="kv__row" style="align-items:center"><span class="kv__k">${label}</span><span class="kv__v" style="display:flex;align-items:center;gap:10px"><span class="tag ${reg ? 'tag--ok' : 'tag--warn'}">${ic(reg ? 'lock' : 'lock-open')} ${UI.pwLabel(reg)}</span>${can ? `<button class="link-btn" data-action="pw.edit" data-id="${h.id}" data-key="${key}">${reg ? '변경' : '등록'}</button>` : ''}</span></div>`;
    return `${UI.subHeader('집 상세')}
      <div class="page page--tight">
        <div class="card card--pad"><div class="kv">
          <div class="kv__row"><span class="kv__k">집 이름</span><span class="kv__v">${esc(Sel.homeName(h, me))}</span></div>
          <div class="kv__row"><span class="kv__k">주소</span><span class="kv__v" style="display:flex;flex-direction:column;align-items:flex-end;gap:4px"><span class="${h.address ? '' : 'muted'}">${esc(UI.addr(h))}</span>${can ? `<button class="link-btn" data-action="addr.edit" data-id="${h.id}">${h.address ? '수정' : '입력'}</button>` : ''}</span></div>
          ${pw('중앙 현관 비밀번호', h.centralPw, 'centralPw')}${pw('집 현관 비밀번호', h.doorPw, 'doorPw')}
        </div>
        <div class="notice notice--lock" style="margin-top:8px">${ic('lock')}<span>비밀번호는 가족에게도 보이지 않고, 119 신고가 접수될 때만 구급대에 전달돼요.</span></div></div>
        <section class="section"><div class="section__head"><h2 class="section__title">연결된 사람</h2></div>
          <div class="card">${people.length ? people.map(q => `<button class="row" data-action="member.open" data-id="${q.id}">${UI.avatar(q, 'sm')}<span class="row__main"><span class="row__title">${esc(q.name)}${q.id === me.id ? ' <span class="tag tag--primary">나</span>' : ''}</span></span>${ic('chevron-right', 'chev')}</button>`).join('') : `<div class="empty">연결된 사람이 없어요</div>`}</div></section>
        <section class="section"><div class="section__head"><h2 class="section__title">감지 기기</h2>${can ? `<button class="link-btn" data-action="dev.add-home" data-id="${h.id}">${ic('plus')} 기기 추가</button>` : ''}</div>
          <div class="card">${devs.length ? devs.map(d => `<button class="row" data-action="dev.open" data-id="${d.id}"><span class="det-dev__ic" style="${d.status === 'disconnected' ? 'background:var(--stop-soft);color:var(--stop)' : ''}">${ic(UI.DEVICE_ICON[d.type])}</span>
            <span class="row__main"><span class="row__title">${esc(UI.deviceName(d))}</span></span><span class="tag ${d.status === 'ok' ? 'tag--ok' : d.status === 'off' ? '' : 'tag--stop'}">${UI.STATUS_LABEL[d.status]}</span></button>`).join('') : `<div class="empty">${ic('video-slash')}연결된 기기가 없어요</div>`}</div></section>
        ${can ? '' : `<div class="notice" style="margin-top:20px">${ic('circle-info')}<span>이 집에 연결된 가족만 정보를 수정할 수 있어요.</span></div>`}
        ${can ? `<button class="btn btn--ghost btn--block" style="margin-top:20px" data-action="home.unlink" data-id="${h.id}">이 집에서 나를 연결 해제</button>` : (me.isTarget ? '' : '')}
      </div>`;
  }, { parent: '/family', live: true });
  on('pw.edit', el => FD.Sheets.password(el.dataset.id, el.dataset.key));
  on('addr.edit', el => FD.Sheets.editAddress(el.dataset.id));
  on('dev.add-home', el => FD.Sheets.addDevice(el.dataset.id));
  on('home.unlink', async el => {
    const ok = await UI.confirm({ title: '집 연결을 해제할까요?', body: '이 집의 낙상 알림을 감지 대상자로서 더 이상 받지 않아요. 가족 알림은 계속 받아요.', ok: '해제', cancel: '취소', danger: true });
    if (ok) { Act.unlinkHome(Sel.meId(), el.dataset.id); toast('연결을 해제했어요'); R.go('/family', { replace: true }); }
  });

  /* ---------------- 주소 수정 시트 ---------------- */
  FD.Sheets.editAddress = function (homeId) {
    const h = Sel.home(homeId); let base = '', results = [];
    const draw = api => {
      api.replace(`${base ? `<div class="addr-picked">${ic('circle-check')}<span style="flex:1">${esc(base)}</span><button class="link-btn" data-action="ae.reset">변경</button></div>
          ${field({ id: 'ae-detail', label: '동·호수', placeholder: '예) 101동 1203호', onenter: 'ae.save' })}
          <button class="btn btn--primary btn--lg btn--block" data-action="ae.save">저장</button>`
        : `<div class="notice" style="margin-bottom:14px">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 동·호수까지 정확히 입력해 주세요. 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
          <div class="inline-add"><input id="ae-q" type="search" placeholder="도로명, 건물명, 동 이름으로 검색" aria-label="주소 검색" data-onenter="ae.search"><button class="btn btn--primary" data-action="ae.search">검색</button></div>
          <div class="addr-list" id="ae-results">${results.map((a, i) => `<button class="addr-item" data-action="ae.pick" data-i="${i}">${ic('location-dot')}<span>${esc(a)}</span></button>`).join('')}</div>`}`);
    };
    const api = openSheet({ title: h && h.address ? '주소 수정' : '주소 입력', html: '' });
    draw(api);
    on('ae.reset', () => { base = ''; results = []; draw(api); });
    on('ae.search', async () => {
      results = await FD.API.searchAddress(document.getElementById('ae-q').value); draw(api);
      if (!results.length) document.getElementById('ae-results').innerHTML = '<p class="empty" style="padding:16px">검색 결과가 없어요.</p>';
    });
    on('ae.pick', el => { base = results[+el.dataset.i]; draw(api); document.getElementById('ae-detail').focus(); });
    on('ae.save', () => {
      const d = val('ae-detail'); if (!d) { setError('ae-detail', '동·호수까지 입력해 주세요.'); return; }
      Act.updateHome(homeId, { address: base + ' ' + d }, Sel.meId(), '집 주소를 변경했어요');
      closeSheet(); toast('주소를 저장했어요', 'ok');
    });
  };

  /* ---------------- S-07 비밀번호 변경 시트 ---------------- */
  FD.Sheets.password = function (homeId, key) {
    const h = Sel.home(homeId); const label = key === 'centralPw' ? '중앙 현관 비밀번호' : '집 현관 비밀번호';
    openSheet({
      title: `${label} ${h[key] ? '변경' : '등록'}`,
      html: `<div class="notice notice--lock" style="margin-bottom:16px">${ic('lock')}<span>비밀번호는 암호화되어 저장되며, 119 신고가 접수될 때만 구급대에게 전달돼요. 가족에게도 보이지 않아요.</span></div>
        ${field({ id: 'pw-new', label: '새 비밀번호', type: 'password', placeholder: '새 비밀번호 입력', autocomplete: 'new-password' })}
        ${field({ id: 'pw-new2', label: '새 비밀번호 확인', type: 'password', placeholder: '한 번 더 입력', autocomplete: 'new-password', onenter: 'pw.save' })}
        <button class="btn btn--primary btn--lg btn--block" data-action="pw.save">저장</button>`
    });
    on('pw.save', () => {
      const a = val('pw-new'), b = val('pw-new2');
      let ok = true;
      if (!a) { setError('pw-new', '비밀번호를 입력해 주세요.'); ok = false; } else setError('pw-new', '');
      if (a && a !== b) { setError('pw-new2', '비밀번호가 서로 달라요.'); ok = false; } else setError('pw-new2', '');
      if (!ok) return;
      const patch = {}; patch[key] = true;
      Act.updateHome(homeId, patch, Sel.meId(), `${label}를 ${h[key] ? '변경' : '등록'}했어요`);
      closeSheet(); toast('비밀번호를 저장했어요', 'ok');
    });
  };

  /* ---------------- 기기 추가 시트 ---------------- */
  FD.Sheets.addDevice = function (homeId) {
    FD.Onboarding.deviceSheet({
      title: '카메라 추가',
      onSubmit: async (v, api) => {
        api.replace(`<div class="empty"><span class="spinner spinner--dark" style="width:30px;height:30px"></span><p style="margin-top:14px;font-weight:700;color:var(--ink)">${esc(UI.DEVICE_TYPE[v.type])} · ${esc(v.location)} 연결하는 중…</p></div>`);
        await new Promise(r => setTimeout(r, 1100));
        Act.addDevice(homeId, v, Sel.meId());
        closeSheet(); toast('기기를 연결했어요', 'ok');
      }
    });
  };

  /* ---------------- S-08 그룹 나가기 ---------------- */
  on('group.leave', async () => {
    const ok = await UI.confirm({ title: '그룹을 나갈까요?', body: '이 그룹의 알림을 받지 않고 정보를 볼 수 없어요. 계정은 유지돼요.', ok: '나가기', cancel: '취소', danger: true });
    if (!ok) return;
    Act.leaveGroup(Sel.meId());
    FD.Onboarding.resetDraft();
    toast('그룹에서 나갔어요');
    R.go('/ob/group', { replace: true });
  });
})();
