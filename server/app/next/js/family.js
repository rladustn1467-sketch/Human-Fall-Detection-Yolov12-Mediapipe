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
  const LIVE = FD.MODE === 'live';
  // 주소가 없거나, 현관 출입 방식이 미설정이거나, 비밀번호 방식인데 미등록이면 '입력 필요' (열쇠·없음은 해당 없음)
  const needsInput = h => !h.address || UI.entrance(h, 'central').needsInput || UI.entrance(h, 'door').needsInput;

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
              <span class="row__main"><span class="row__title">${esc(Sel.homeName(h, me))}${needsInput(h) ? ' <span class="tag tag--warn">입력 필요</span>' : ''}</span><span class="row__sub">${esc(UI.addr(h))}</span></span>${ic('chevron-right', 'chev')}</button>`;
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
        ${self ? '' : `<div class="card" style="margin-top:20px"><button class="row row--danger" data-action="member.remove" data-id="${m.id}"><span class="row__main"><span class="row__title">그룹에서 내보내기</span></span>${ic('chevron-right', 'chev')}</button></div>`}
      </div>`;
  }, { parent: '/family' });
  on('member.edit', () => R.go('/settings/profile'));
  /* 다른 구성원 내보내기 (구성원 누구나, 사용자 결정 2026-10-30). 내보내면 초대 코드도 새로 바뀜 */
  on('member.remove', async el => {
    const m = Sel.person(el.dataset.id);
    if (!m) return;
    const ok = await UI.confirm({ title: `${m.name}님을 그룹에서 내보낼까요?`,
      body: '내보내면 이 그룹의 알림과 정보를 볼 수 없어요. 예전 초대 코드는 쓸 수 없게 되고 새 코드가 만들어져요. 다른 가족에게도 알려요.',
      ok: '내보내기', cancel: '취소', danger: true });
    if (!ok) return;
    try {
      await Act.removeMember(Sel.meId(), m.id);
    } catch (e) { UI.showError(e); return; }
    toast(`${m.name}님을 그룹에서 내보냈어요`);
    R.go('/family', { replace: true });
  });

  /* ---------------- S-06 초대 화면 ---------------- */
  R.register('/family/invite', () => {
    const me = Sel.me(); const g = Sel.group(me.groupId);
    return {
      html: `${UI.subHeader('가족 초대하기')}<div class="page page--tight"><p class="ob__sub" style="margin-top:0">QR코드를 보여주거나 초대 코드를 알려주세요.</p><div id="invite-area"></div></div>`,
      mount: async root => {
        let inv;
        try {
          inv = await Act.regenInvite(g.id, me.id);   // 초대할 때마다 새 코드 (예전 코드는 쓸 수 없게 됨)
        } catch (e) { UI.showError(e); return; }
        if (!inv) return;
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
    // 현관: 실제 출입 방식과 비밀번호 등록 여부만 표시 (값은 없음). 수정·삭제는 그 집에 연결된 가족만
    const entRow = kind => { const e = UI.entrance(h, kind);
      return `<div class="kv__row" style="align-items:center"><span class="kv__k">${e.name}</span><span class="kv__v" style="display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px 10px"><span class="tag ${e.needsInput ? 'tag--warn' : 'tag--ok'}" data-entrance="${kind}">${ic(e.icon)} ${e.label}</span>${can ? `<button class="link-btn" data-action="ent.edit" data-id="${h.id}" data-kind="${kind}">${e.method ? '변경' : '설정'}</button>` : ''}${can && e.registered ? `<button class="link-btn" style="color:var(--stop)" data-action="pw.delete" data-id="${h.id}" data-key="${e.pwKey}">삭제</button>` : ''}</span></div>`; };
    return `${UI.subHeader('집 상세')}
      <div class="page page--tight">
        <div class="card card--pad"><div class="kv">
          <div class="kv__row"><span class="kv__k">집 이름</span><span class="kv__v">${esc(Sel.homeName(h, me))}</span></div>
          <div class="kv__row"><span class="kv__k">주소</span><span class="kv__v" style="display:flex;flex-direction:column;align-items:flex-end;gap:4px"><span class="${h.address ? '' : 'muted'}">${esc(UI.addr(h))}</span>${can ? `<button class="link-btn" data-action="addr.edit" data-id="${h.id}">${h.address ? '수정' : '입력'}</button>` : ''}</span></div>
          ${entRow('central')}${entRow('door')}
        </div>
        <div class="notice notice--lock" style="margin-top:8px">${ic('lock')}<span>비밀번호는 가족에게도 보이지 않고, 119 신고가 접수될 때만 구급대에 전달돼요.</span></div></div>
        <section class="section"><div class="section__head"><h2 class="section__title">연결된 사람</h2></div>
          <div class="card">${people.length ? people.map(q => `<button class="row" data-action="member.open" data-id="${q.id}">${UI.avatar(q, 'sm')}<span class="row__main"><span class="row__title">${esc(q.name)}${q.id === me.id ? ' <span class="tag tag--primary">나</span>' : ''}</span></span>${ic('chevron-right', 'chev')}</button>`).join('') : `<div class="empty">연결된 사람이 없어요</div>`}</div></section>
        <section class="section"><div class="section__head"><h2 class="section__title">감지 기기</h2>${can ? `<button class="link-btn" data-action="dev.add-home" data-id="${h.id}">${ic('plus')} 기기 추가</button>` : ''}</div>
          <div class="card">${devs.length ? devs.map(d => `<button class="row" data-action="dev.open" data-id="${d.id}"><span class="det-dev__ic" style="${d.status === 'disconnected' ? 'background:var(--stop-soft);color:var(--stop)' : ''}">${ic(UI.DEVICE_ICON[d.type])}</span>
            <span class="row__main"><span class="row__title">${esc(UI.deviceName(d))}</span></span><span class="tag ${d.status === 'ok' ? 'tag--ok' : d.status === 'off' ? '' : 'tag--stop'}">${UI.STATUS_LABEL[d.status]}</span></button>`).join('') : `<div class="empty">${ic('video-slash')}연결된 기기가 없어요</div>`}</div></section>
        ${can ? '' : `<div class="notice" style="margin-top:20px">${ic('circle-info')}<span>이 집에 연결된 가족만 정보를 수정할 수 있어요.</span></div>`}
        ${can ? `<button class="btn btn--ghost btn--block" style="margin-top:20px" data-action="home.unlink" data-id="${h.id}">이 집에서 나를 연결 해제</button>`
          : me.isTarget ? `<button class="btn btn--soft btn--block" style="margin-top:20px" data-action="home.link" data-id="${h.id}">${ic('link')} 이 집에 나도 연결하기</button>` : ''}
      </div>`;
  }, { parent: '/family', live: true });
  on('pw.edit', el => FD.Sheets.password(el.dataset.id, el.dataset.key));
  on('ent.edit', el => FD.Sheets.entrance(el.dataset.id, el.dataset.kind));
  /* 현관 비밀번호 삭제: 확인한 뒤 (서버도 그 집에 연결된 가족인지 다시 확인) */
  on('pw.delete', async el => {
    const key = el.dataset.key, kind = key === 'centralPw' ? 'central' : 'door';
    const label = kind === 'central' ? '중앙 현관 비밀번호' : '집 현관 비밀번호';
    const ok = await UI.confirm({ title: `${label}를 삭제할까요?`, body: '삭제하면 위급할 때 구급대 출입에 쓸 비밀번호가 없어져요. 다시 등록할 수 있어요.', ok: '삭제', cancel: '취소', danger: true });
    if (!ok) return;
    try {
      await Act.deleteDoorCode(el.dataset.id, kind, Sel.meId());
    } catch (e) { UI.showError(e); return; }
    toast(`${label}를 삭제했어요`);
  });
  on('addr.edit', el => FD.Sheets.editAddress(el.dataset.id));
  on('dev.add-home', el => FD.Sheets.addDevice(el.dataset.id));
  /* 기존 집에 연결: 감지 대상인 사람이 같은 그룹의 다른 집에 함께 사는 경우 (처음 설정에서 다른 집을 고른 뒤 바로잡기 등).
     서버가 다시 확인: 로그인, 같은 그룹의 집, 감지 대상. 지금 연결된 집은 그대로 둠 (해제는 그 집 상세에서) */
  on('home.link', async el => {
    const me = Sel.me(), h = Sel.home(el.dataset.id);
    if (!h) return;
    const others = me.homeIds.filter(id => id !== h.id).length;
    const ok = await UI.confirm({ title: '이 집에 연결할까요?',
      body: `${Sel.homeName(h, me)}에 함께 사시는 경우에만 연결해 주세요. 연결하면 이 집의 감지 대상이 되고, 주소와 현관 정보를 함께 관리할 수 있어요.`
        + (others ? ' 지금 연결된 집은 그대로예요. 그 집에 살지 않으면 그 집 상세에서 연결을 해제해 주세요.' : ''),
      ok: '연결하기', cancel: '취소' });
    if (!ok) return;
    try {
      await UI.busy(el, () => Act.linkHome(me.id, h.id));
    } catch (e) { UI.showError(e); return; }
    toast('이 집에 연결했어요'); R.go(R.path());
  });
  on('home.unlink', async el => {
    const ok = await UI.confirm({ title: '집 연결을 해제할까요?', body: '이 집의 낙상 알림을 감지 대상자로서 더 이상 받지 않아요. 가족 알림은 계속 받아요.', ok: '해제', cancel: '취소', danger: true });
    if (!ok) return;
    try {
      await Act.unlinkHome(Sel.meId(), el.dataset.id);
    } catch (e) { UI.showError(e); return; }
    toast('연결을 해제했어요'); R.go('/family', { replace: true });
  });

  /* ---------------- 주소 수정 시트 ---------------- */
  FD.Sheets.editAddress = function (homeId) {
    const h = Sel.home(homeId); let base = '', results = [];
    let manual = FD.API.addressSearch === false;   // 검색을 쓸 수 없거나 '직접 입력하기'를 고르면 직접 입력
    const draw = api => {
      if (manual) {
        api.replace(`<div class="notice" style="margin-bottom:14px">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 동·호수까지 정확히 입력해 주세요. 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
          ${field({ id: 'ae-base', label: '주소', placeholder: '예) 서울 마포구 월드컵로 100 한빛아파트', maxlength: 150, autocomplete: 'street-address' })}
          ${field({ id: 'ae-detail', label: '동·호수', placeholder: '예) 101동 1203호', maxlength: 40, onenter: 'ae.save' })}
          <button class="btn btn--primary btn--lg btn--block" data-action="ae.save">저장</button>
          ${FD.API.addressSearch !== false ? `<button class="link-btn" style="margin-top:12px" data-action="ae.searchmode">주소 검색하기</button>` : ''}`);
        return;
      }
      api.replace(`${base ? `<div class="addr-picked">${ic('circle-check')}<span style="flex:1">${esc(base)}</span><button class="link-btn" data-action="ae.reset">변경</button></div>
          ${field({ id: 'ae-detail', label: '동·호수', placeholder: '예) 101동 1203호', onenter: 'ae.save' })}
          <button class="btn btn--primary btn--lg btn--block" data-action="ae.save">저장</button>`
        : `<div class="notice" style="margin-bottom:14px">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 동·호수까지 정확히 입력해 주세요. 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
          <div class="inline-add"><input id="ae-q" type="search" placeholder="도로명, 건물명, 동 이름으로 검색" aria-label="주소 검색" data-onenter="ae.search"><button class="btn btn--primary" data-action="ae.search">검색</button></div>
          <div class="addr-list" id="ae-results">${results.map((a, i) => `<button class="addr-item" data-action="ae.pick" data-i="${i}">${ic('location-dot')}<span>${esc(a)}</span></button>`).join('')}</div>
          ${LIVE ? `<button class="link-btn" style="margin-top:12px" data-action="ae.manual">검색이 안 되나요? 직접 입력하기</button>` : ''}`}`);
    };
    const api = openSheet({ title: h && h.address ? '주소 수정' : '주소 입력', html: '' });
    draw(api);
    on('ae.reset', () => { base = ''; results = []; draw(api); });
    on('ae.manual', () => { manual = true; base = ''; results = []; draw(api); });
    on('ae.searchmode', () => { manual = false; base = ''; results = []; draw(api); });
    on('ae.search', async () => {
      try {
        results = await FD.API.searchAddress(document.getElementById('ae-q').value);
      } catch (e) { UI.showError(e); return; }   // 검색어 문제·횟수 초과·검색 불가 안내
      draw(api);
      if (!results.length) document.getElementById('ae-results').innerHTML = '<p class="empty" style="padding:16px">검색 결과가 없어요.</p>';
    });
    on('ae.pick', el => { base = results[+el.dataset.i]; draw(api); document.getElementById('ae-detail').focus(); });
    on('ae.save', async el => {
      if (manual) {
        base = val('ae-base');
        if (!base) { setError('ae-base', '주소를 입력해 주세요.'); return; }
        setError('ae-base', '');
      }
      const d = val('ae-detail'); if (!d) { setError('ae-detail', '동·호수까지 입력해 주세요.'); return; }
      try {
        await UI.busy(el, () => Act.updateHome(homeId, { address: base + ' ' + d }, Sel.meId(), '집 주소를 변경했어요'));
      } catch (e) { UI.showError(e, { address: manual ? 'ae-base' : 'ae-detail' }); return; }
      closeSheet(); toast('주소를 저장했어요', 'ok');
    });
  };

  /* ---------------- S-07 비밀번호 변경 시트 ---------------- */
  /* 현관 출입 방식·비밀번호 시트. 값은 서버가 암호화해 저장하고 화면에는 다시 보내지 않음 (입력칸 가림·자동완성 끔).
     - 비밀번호 방식: 입력칸 표시. 이미 등록돼 있으면 비워 두고 저장해도 그대로 (덮어쓰지 않음)
     - 열쇠·없음: 입력칸 없음. 등록된 비밀번호가 있으면 확인을 받은 뒤 그 현관의 비밀번호만 삭제 */
  FD.Sheets.entrance = function (homeId, kind) {
    const e0 = UI.entrance(Sel.home(homeId), kind);
    let method = e0.method;
    const html = () => `
      <div class="label">출입 방식</div>
      <div class="segmented" style="margin-bottom:16px">${e0.options.map(([m, t]) => `<button type="button" class="${method === m ? 'is-on' : ''}" aria-pressed="${method === m}" data-action="ent.pick" data-m="${m}">${t}</button>`).join('')}</div>
      ${method === 'code' ? `<div class="notice notice--lock" style="margin-bottom:16px">${ic('lock')}<span>비밀번호는 암호화되어 저장되며, 119 신고가 접수될 때만 구급대에게 전달돼요. 가족에게도 보이지 않아요.</span></div>
        ${e0.registered ? `<p class="field__hint" style="margin:-4px 0 12px">등록된 비밀번호가 있어요. 바꿀 때만 입력해 주세요.</p>` : ''}
        ${field({ id: 'pw-new', label: '현관 비밀번호', type: 'password', inputmode: 'tel', maxlength: 20 })}
        ${field({ id: 'pw-new2', label: '비밀번호 확인', type: 'password', inputmode: 'tel', maxlength: 20, placeholder: '한 번 더 입력', onenter: 'ent.save' })}` : ''}
      ${method && method !== 'code' && e0.registered ? `<div class="notice notice--stop" style="margin-bottom:16px">${ic('triangle-exclamation')}<span>저장하면 등록된 ${e0.name} 비밀번호가 삭제돼요.</span></div>` : ''}
      <button class="btn btn--primary btn--lg btn--block" data-action="ent.save" ${method ? '' : 'disabled'}>저장</button>`;
    const api = openSheet({ title: `${e0.name} 출입 방식`, html: html() });
    on('ent.pick', el => { method = el.dataset.m; api.replace(html()); });
    on('ent.save', async el => {
      if (!method) return;
      let code = null;
      if (method === 'code') {
        const a = val('pw-new'), b = val('pw-new2');
        if (a || b) {   // 입력했을 때만 확인·등록 (비워 두면 비밀번호는 그대로)
          const rule = UI.doorCodeProblem(a);
          setError('pw-new', rule);
          setError('pw-new2', !rule && a !== b ? '비밀번호가 서로 달라요.' : '');
          if (rule || a !== b) return;
          code = a;
        }
      }
      if (method === e0.method && !code) { closeSheet(); return; }   // 바뀐 것 없음
      if (method !== 'code' && e0.registered) {
        const ok = await UI.confirm({ title: `${e0.name} 비밀번호를 삭제할까요?`, body: `출입 방식을 바꾸면 등록된 ${e0.name} 비밀번호가 삭제돼요. 다른 현관 정보는 그대로예요.`, ok: '삭제하고 저장', cancel: '취소', danger: true });
        if (!ok) return;
      }
      try {
        await UI.busy(el, () => Act.setEntrance(homeId, kind, method, code, Sel.meId()));
      } catch (err) { UI.showError(err, { code: 'pw-new' }); return; }
      closeSheet();
      toast(code ? `${e0.name} 비밀번호를 ${e0.registered ? '변경' : '등록'}했어요` : `${e0.name} 출입 방식을 저장했어요`, 'ok');
    });
  };
  // 예전 이름 (홈 할 일 등에서 사용): 현관 출입 방식 시트로
  FD.Sheets.password = (homeId, key) => FD.Sheets.entrance(homeId, key === 'centralPw' ? 'central' : 'door');

  /* ---------------- 기기 추가 시트 ---------------- */
  /* 실제 모드: 연결 방식(이 휴대폰·안 쓰는 휴대폰 …)을 고르는 공통 흐름 (devices.js, 처음 설정 4단계와 같음) */
  FD.Sheets.addDevice = function (homeId) {
    if (LIVE) { FD.DeviceConnect.openChooser(homeId); return; }
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
    // 이 휴대폰이 '이 휴대폰으로 감지하기'로 이 그룹의 집을 감지 중이면, 나가기 전에 감지를 멈추고 나간 뒤 기기 연결도 해제
    // (탈퇴와 같은 방법, settings.js). 안 그러면 나간 사람의 휴대폰이 예전 그룹 집으로 계속 낙상을 보냄
    const S = FD.DeviceConnect && FD.DeviceConnect.self;
    const st = S && UI.nativeDetector() ? ((await S.status()) || {}).s : null;
    const selfOn = !!(st && st.paired && st.mode === 'self');
    const ok = await UI.confirm({ title: '그룹을 나갈까요?',
      body: '이 그룹의 알림을 받지 않고 정보를 볼 수 없어요. 계정은 유지돼요.'
        + (selfOn ? ' 이 휴대폰으로 하던 낙상 감지도 멈추고 이 휴대폰의 기기 연결을 해제해요.' : ''),
      ok: '나가기', cancel: '취소', danger: true });
    if (!ok) return;
    let stop = { self: false };
    try {
      if (S) stop = await S.stopForLogout();
      if (stop.self && !stop.stopped) throw new FD.ApiError(0, '이 휴대폰의 감지를 멈추지 못해 그룹에서 나가지 않았어요. 다시 시도해 주세요.');
      await Act.leaveGroup(Sel.meId());
    } catch (e) {
      UI.showError(e);
      if (stop.self && stop.stopped) toast('그룹에서 나가지 못했어요. 이 휴대폰의 감지는 멈춘 상태예요. 감지 화면에서 다시 켤 수 있어요.');
      return;
    }
    let unpaired = { self: false };
    if (stop.self && S) unpaired = await S.unpairAfterWithdraw();   // 이 휴대폰의 기기 기록·연결 정리
    FD.Onboarding.resetDraft();
    toast(stop.self ? (unpaired.removed ? '그룹에서 나갔어요. 이 휴대폰의 감지를 멈추고 기기 연결도 해제했어요.'
      : '그룹에서 나갔어요. 이 휴대폰의 감지를 멈췄어요. 그룹의 기기 목록에 남은 이 기기는 가족이 삭제할 수 있어요.')
      : '그룹에서 나갔어요');
    R.go('/ob/group', { replace: true });
  });
})();
