/* ------------------------------------------------------------------
 * emergency.js — 긴급 이벤트 화면 E-01 ~ E-07
 *
 * 사고 상태(store 의 incident 객체)만 보고 화면을 결정합니다. 어떤 화면을 보고 있든 그 위에 표시됩니다.
 *   낙상자(감지된 집의 감지 대상자)  : E-01 (감지됨 / 가족 알림 후 / 도움 요청 후 / 가족 확인 중)
 *   가족                            : E-02(응답 없음) · E-03(도움 요청) · E-06(확인 중)
 *   신고하려는 사람                  : E-04(대상자 선택) → E-05(신고 확인)
 *   전원                            : E-07(신고 완료 / 종료)
 * 남은 시간은 저장된 기준 시각(detectedAt, autoReportAt …)에서 매번 계산합니다.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, toast } = UI;
  const { Sel, Act } = FD.Store;
  const S = 1000, M = 60000;

  const mem = {};        // 사고별 사용자 화면 상태 { min, help, lvl }
  let flow = null;       // { id, step: 'pick'|'confirm', selected: [], unknown, from }
  let lastSig = '';

  const root = () => document.getElementById('overlay-root');

  /* ---------- 선택 ---------- */
  function alertLevel(inc, me) {
    if (inc.status !== 'checking') return 0;
    const lv = Sel.reminderLevel(inc);
    if (inc.checkedBy === me.id) return lv;
    return lv >= 3 ? 3 : 0;
  }
  function choose(me) {
    const all = Sel.incidentsFor(me);
    const active = all.filter(i => !Sel.isTerminal(i));
    active.forEach(inc => {
      const m = mem[inc.id] = mem[inc.id] || { min: false, help: 0, lvl: 0 };
      if (inc.helpTimes.length > m.help) { m.help = inc.helpTimes.length; m.min = false; }
      const lv = alertLevel(inc, me);
      if (lv > m.lvl) { m.lvl = lv; m.min = false; }
    });
    const victimActive = active.filter(i => Sel.roleIn(i, me) === 'victim').sort((a, b) => a.detectedAt - b.detectedAt);
    if (victimActive.length) return victimActive[0];
    const fam = active.filter(i => !mem[i.id].min).sort((a, b) => (Sel.deadline(a) - Sel.deadline(b)) || (a.detectedAt - b.detectedAt));
    if (fam.length) return fam[0];
    const ended = all.filter(i => Sel.isTerminal(i)).filter(i => !(Sel.roleIn(i, me) === 'victim' && i.result === 'self')).sort((a, b) => b.closedAt - a.closedAt);
    return ended[0] || null;
  }

  /* ---------- 공통 조각 ---------- */
  function top(label, o) {
    o = o || {};
    return `<div class="ov__top">
      ${o.back ? `<button class="ov__x" data-action="em.back" aria-label="뒤로">${ic('chevron-left')}</button>` : `<span class="ov__badge">${ic(o.icon || 'triangle-exclamation')} ${esc(label)}</span>`}
      ${o.close ? `<button class="ov__x" data-action="em.min" aria-label="닫고 홈으로">${ic('xmark')}</button>` : o.back ? `<span class="ov__badge">${esc(label)}</span>` : '<span></span>'}
    </div>`;
  }
  const wrap = (cls, inner) => `<div class="ov ${cls}" role="alertdialog" aria-modal="true" aria-live="polite">${inner}</div>`;
  const victims = inc => Sel.targets(inc.homeId);
  const victimNames = inc => victims(inc).map(p => p.name).join('·');
  function ring(a, b, big, small) {
    return `<div class="ring" role="timer"><svg viewBox="0 0 210 210" aria-hidden="true"><circle class="ring__bg" cx="105" cy="105" r="98"/><circle class="ring__fg" cx="105" cy="105" r="98" data-ring="${a},${b}"/></svg>
      <div class="ring__num"><span ${big}>--</span><small>${small}</small></div></div>`;
  }

  /* ---------- E-01 낙상자 ---------- */
  function viewVictim(inc, me) {
    const h = Sel.home(inc.homeId);
    const nowT = FD.Store.now();
    const helpN = inc.helpTimes.length;
    let body = '', foot = '', cls = '';
    const btnOk = `<button class="btn btn--white-ok btn--lg" style="background:#fff;color:#1F6B45" data-action="em.ok" data-id="${inc.id}">${ic('thumbs-up')} 괜찮아요</button>`;
    const btn119 = `<button class="btn btn--outline" data-action="em.report-self" data-id="${inc.id}">${ic('truck-medical')} 직접 119에 신고하기</button>`;
    const btnHelp = `<button class="btn btn--white btn--lg" data-action="em.help" data-id="${inc.id}">${ic('hand')} 도움이 필요해요${helpN ? ` (${helpN}회 요청함)` : ''}</button>`;

    if (inc.status === 'detected') {
      body = `<h1 class="ov__title">낙상이 감지되었어요.<br>괜찮으신가요?</h1>
        <p class="ov__lead">${esc(inc.location)}에서 낙상이 감지됐어요. 본인이거나 지금 괜찮은 상황이라면 눌러주세요</p>
        ${ring(inc.detectedAt, inc.detectedAt + 60 * S, `data-secs="${inc.detectedAt + 60 * S}"`, '초 안에 응답해 주세요')}
        <p class="ov-peek">응답이 없으면 가족에게 알려요</p>`;
      foot = `${btnOk}${btnHelp}${btn119}`;
    } else if (inc.status === 'checking') {
      const who = Sel.person(inc.checkedBy);
      cls = 'ov--calm';
      body = `<h1 class="ov__title"><small>${esc(inc.location)} · 낙상 감지</small>${esc(who ? who.name : '가족')}님이<br>확인하고 있어요</h1>
        <p class="ov__lead">가족이 상황을 확인 중이에요. 괜찮다면 아래 버튼을 눌러주세요.</p>
        <span class="ov-state">${ic('user-check')} 감지 후 <span data-el="${inc.detectedAt}">--</span> 경과</span>`;
      foot = `${btnOk}${btn119}`;
    } else {
      body = `<h1 class="ov__title">${inc.status === 'help' ? '가족에게 도움을<br>요청했어요' : '가족에게 알렸어요'}</h1>
        <p class="ov__lead">${esc(inc.location)}에서 낙상이 감지됐어요. ${inc.status === 'help' ? '가족이 곧 확인할 거예요.' : '60초 동안 응답이 없어 가족에게 알렸어요.'} 괜찮으시면 아래 버튼을 눌러주세요.</p>
        <span class="ov-state">${ic('bell')} ${inc.status === 'help' ? `도움 요청 ${helpN}번째 · ` : ''}감지 후 <span data-el="${inc.detectedAt}">--</span></span>
        <div class="big-count"><p class="big-count__label">자동 119 신고까지</p><div class="big-count__num" data-cd="${inc.autoReportAt}">--:--</div><div class="big-count__bar"><b data-bar="${inc.familyNotifiedAt},${inc.autoReportAt}"></b></div></div>
        <p class="ov__small" style="text-align:center">아무도 확인하지 않으면 자동으로 119에 신고돼요.</p>`;
      foot = inc.status === 'help' ? `${btnOk}${btnHelp}${btn119}` : `${btnOk}${btn119}`;
    }
    void h; void nowT;
    return wrap(cls, `${top('긴급 · 낙상 감지', { icon: 'triangle-exclamation' })}<div class="ov__body">${body}</div><div class="ov__foot">${foot}</div>`);
  }

  /* ---------- E-02 / E-03 / E-06 가족 ---------- */
  function viewFamily(inc, me) {
    const h = Sel.home(inc.homeId);
    const hname = Sel.homeName(h, me);
    const name = `${hname} · ${inc.location}`;
    const helpN = inc.helpTimes.length;
    const photo = `<div class="ov-photo">${UI.maskPhoto(inc.id)}</div>`;
    const detected = `<p class="ov__small">낙상 감지 ${UI.clock(inc.detectedAt)} · <span data-el="${inc.detectedAt}" data-suf=" 경과">--</span></p>`;
    const btn119 = `<button class="btn btn--119" data-action="em.report-family" data-id="${inc.id}">${ic('truck-medical')} 119에 신고해주세요</button>`;
    const btnCall = `<button class="btn btn--call" data-action="em.call" data-id="${inc.id}">${ic('phone')} 전화 걸기</button>`;
    const btnMap = `<button class="btn btn--call" data-action="em.map" data-id="${inc.id}">${ic('map-location-dot')} 주소/지도 보기</button>`;
    const contact = `<div class="btn-pair">${btnCall}${btnMap}</div>`;

    if (inc.status === 'checking') {
      const who = Sel.person(inc.checkedBy);
      const mine = inc.checkedBy === me.id;
      const lv = alertLevel(inc, me);
      const alertBox = lv > 0 ? (mine
        ? `<div class="ov-alert">${ic('circle-exclamation')}<span>아직 상황이 끝나지 않았어요. 괜찮으신가요?<br><small>확인 후 <span data-min="${inc.checkedAt}">--</span></small></span></div>`
        : `<div class="ov-alert">${ic('circle-exclamation')}<span>${esc(who ? who.name : '가족')}님이 확인했지만 아직 종료되지 않았어요</span></div>`) : '';
      const body = `<span class="ov-state">${ic('user-check')} ${mine ? '제가 확인 중' : `${esc(who ? who.name : '가족')}님이 확인했어요`}</span>
        <h1 class="ov__title" style="margin-top:12px"><small>${esc(name)}</small>${mine ? '확인 중이에요' : `${esc(who ? who.name : '가족')}님이<br>확인 중이에요`}</h1>
        <p class="ov__lead">${mine ? '직접 상황을 확인하고 있어요. ' : ''}감지 후 <b data-el="${inc.detectedAt}">--</b> 경과</p>
        <p class="ov__small">자동 신고는 멈췄어요. 낙상 감지 ${UI.clock(inc.detectedAt)}</p>
        ${alertBox}${photo}`;
      const foot = `${mine ? `<button class="btn btn--white-calm btn--lg" style="background:#fff;color:var(--primary-d)" data-action="em.close" data-id="${inc.id}">${ic('circle-check')} 괜찮은 걸 확인했어요 (종료)</button>` : ''}${btn119}${contact}`;
      return wrap('ov--calm', `${top('낙상 알림 · 확인 중', { icon: 'user-check', close: true })}<div class="ov__body">${body}</div><div class="ov__foot">${foot}</div>`);
    }

    const isHelp = inc.status === 'help';
    const lastHelp = inc.helpTimes[helpN - 1];
    const body = `<h1 class="ov__title"><small>${isHelp ? `도움 요청 (${helpN}번째)` : '낙상 알림'}</small>${esc(name)}</h1>
      ${photo}
      <p class="ov__lead" style="font-weight:700">${isHelp
        ? `본인이 '도움이 필요해요'라고 응답했어요 (낙상 감지 후 ${UI.secLabel(lastHelp - inc.detectedAt)})`
        : '60초 동안 응답이 없었어요. 확인이 필요해요.'}</p>
      ${isHelp && helpN ? `<div class="ov-help-times" aria-label="요청 시각">${inc.helpTimes.map(t => `<span>${UI.secLabel(t - inc.detectedAt)}</span>`).join('')}</div>` : ''}
      <div class="big-count"><p class="big-count__label">자동 신고까지</p><div class="big-count__num" data-cd="${inc.autoReportAt}">--:--</div><div class="big-count__bar"><b data-bar="${inc.familyNotifiedAt},${inc.autoReportAt}"></b></div></div>
      ${detected}
      <p class="ov-note">${ic('clock')}<span>180초 동안 아무도 누르지 않으면 자동으로 119 신고를 해요.</span></p>`;
    const foot = `<button class="btn btn--white btn--lg" data-action="em.take" data-id="${inc.id}">${ic('hand-holding-heart')} 확인했어요, 제가 처리할게요</button>${btn119}${contact}`;
    return wrap('', `${top(isHelp ? '긴급 · 도움 요청' : '긴급 · 낙상 알림', { close: true })}<div class="ov__body">${body}</div><div class="ov__foot">${foot}</div>`);
  }
  on('em.min', () => { const me = Sel.me(); const inc = choose(me); if (inc) { (mem[inc.id] = mem[inc.id] || {}).min = true; mem[inc.id].lvl = alertLevel(inc, me); } sync(true); });

  /* ---------- E-04 대상자 선택 ---------- */
  function viewPick(inc, me) {
    const h = Sel.home(inc.homeId);
    const vs = victims(inc);
    const rec = inc.recognizedId && vs.find(p => p.id === inc.recognizedId);
    const sel = flow.selected[0];
    return wrap('ov--dark', `${top('119 신고', { back: true })}<div class="ov__body">
      <h1 class="ov__title">${rec ? '낙상 대상자를<br>확인해주세요' : '낙상 대상자가<br>누구인가요?'}</h1>
      <p class="ov__lead">${rec ? `${esc(rec.name)}님이 아니라면 낙상 대상자를 선택해주세요` : `${esc(Sel.homeName(h, me))}에 감지 대상자가 ${vs.length}명 있어요.`}</p>
      <div class="pick-list" role="radiogroup" aria-label="낙상 대상자">${vs.map(p => `<button class="pick${sel === p.id ? ' is-on' : ''}" role="radio" aria-checked="${sel === p.id}" data-action="em.pick" data-id="${p.id}">
        <span class="pick__ph">${UI.maskPhoto(inc.id + p.id, { small: true })}</span>
        <span class="pick__main"><span class="pick__name">${esc(p.name)}${rec && rec.id === p.id ? ' <span class="tag tag--primary">인식됨</span>' : ''}</span><span class="pick__addr">${esc(UI.addr(h))}</span></span>
        <span class="pick__ck">${ic('check')}</span></button>`).join('')}</div>
      <button class="link-btn" style="margin-top:14px;align-self:center;font-size:16px" data-action="em.unknown">잘 모르겠어요</button>
      <p class="ov-peek">잘 모르겠어요를 누르면 이 집의 감지 대상자 ${vs.length}명의 정보가 모두 신고에 포함돼요.</p>
    </div><div class="ov__foot"><button class="btn btn--white btn--lg" ${sel ? '' : 'aria-disabled="true" disabled'} data-action="em.pick-next">선택하고 다음</button></div>`);
  }
  on('em.pick', el => { if (flow) { flow.selected = [el.dataset.id]; flow.unknown = false; sync(true); } });
  on('em.pick-next', () => { if (flow && flow.selected.length) { flow.step = 'confirm'; sync(true); } });
  on('em.unknown', () => { const inc = Sel.incident(flow.id); flow.selected = victims(inc).map(p => p.id); flow.unknown = true; flow.step = 'confirm'; sync(true); });

  /* ---------- E-05 119 신고 확인 ---------- */
  function viewConfirm(inc, me) {
    const h = Sel.home(inc.homeId);
    const people = flow.selected.map(id => Sel.person(id)).filter(Boolean);
    const pw = (label, reg) => `<div class="kv__row"><span class="kv__k">${label}</span><span class="kv__v">${reg ? `<span class="tag tag--ok">${ic('lock')} 등록됨 (구급대에 전달돼요)</span>` : '<span class="muted">미등록</span>'}</span></div>`;
    return wrap('ov--dark', `${top('119 신고 확인', { back: true })}<div class="ov__body">
      <h1 class="ov__title" style="font-size:24px">119에 다음과 같은 내용으로 신고돼요.<br>확인 후 전송을 눌러주세요.</h1>
      <div class="confirm-doc">
        <h3>위치</h3>
        <div class="kv"><div class="kv__row"><span class="kv__k">주소</span><span class="kv__v${h.address ? '' : ' muted'}">${esc(UI.addr(h))}</span></div>
          ${pw('중앙 현관 비밀번호', h.centralPw)}${pw('집 현관 비밀번호', h.doorPw)}
          <div class="kv__row"><span class="kv__k">낙상 위치</span><span class="kv__v">${esc(inc.location)}</span></div></div>
        <h3 style="margin-top:6px">낙상 대상자 ${people.length > 1 ? `(${people.length}명 모두 포함)` : ''}</h3>
        ${people.map(p => `<div class="person-block"><h4>${esc(p.name)}</h4><div class="kv">
          <div class="kv__row"><span class="kv__k">생년월일</span><span class="kv__v${p.birth ? '' : ' muted'}">${p.birth ? UI.birthLabel(p.birth) : '미등록'}</span></div>
          <div class="kv__row"><span class="kv__k">지병</span><span class="kv__v${p.conditions == null ? ' muted' : ''}">${esc(UI.listLabel(p.conditions))}</span></div>
          <div class="kv__row"><span class="kv__k">복용 약</span><span class="kv__v${p.medications == null ? ' muted' : ''}">${esc(UI.listLabel(p.medications))}</span></div></div></div>`).join('')}
        <div class="confirm-doc__msg"><b>119에 보낼 문구</b>낙상이 감지되어 구급 출동을 요청합니다. 위치와 환자 정보는 아래와 같습니다.</div>
      </div>
    </div><div class="ov__foot"><button class="btn btn--119-dark btn--lg" data-action="em.send" data-id="${inc.id}">${ic('paper-plane')} 전송</button></div>`);
  }
  on('em.send', async () => {
    if (!flow) return;
    const me = Sel.me(); const id = flow.id, sel = flow.selected.slice();
    flow = null;
    const ok = Act.report(id, me.id, sel);
    if (!ok) toast('이미 신고되었거나 종료된 사고예요');
    sync(true);
  });

  /* ---------- E-07 신고 완료 / 종료 ---------- */
  function viewEnded(inc, me) {
    const h = Sel.home(inc.homeId); const name = `${Sel.homeName(h, me)} · ${inc.location}`;
    const by = Sel.person(inc.closedBy);
    let cls = 'ov--ended', icon = 'circle-check', title = '', lead = '', time = '', badge = '사고 종료';
    if (inc.status === 'reported') {
      cls = 'ov--dark'; icon = 'truck-medical'; badge = '119 신고됨';
      if (inc.result === 'auto_reported') { title = '자동으로 119에<br>신고됐어요'; lead = '아무도 확인하지 않아 자동으로 신고했어요.'; }
      else { const r = Sel.person(inc.reportedBy); title = '119에 신고됐어요'; lead = `${esc(r ? r.name : '가족')}님이 119에 신고했어요.`; }
      time = `신고 시각 ${UI.clock(inc.reportedAt || inc.closedAt)}`;
    } else if (inc.result === 'self') {
      title = `${esc(by ? by.name : '본인')}님이<br>괜찮다고 응답했어요`; lead = '본인이 괜찮다고 응답해서 사고가 종료됐어요.'; time = `종료 ${UI.clock(inc.closedAt)}`;
    } else {
      title = `${esc(by ? by.name : '가족')}님이<br>괜찮은 것을 확인했어요`; lead = '상황을 확인하고 사고를 종료했어요.'; time = `종료 ${UI.clock(inc.closedAt)}`;
    }
    return wrap(cls, `${top(badge, { icon })}<div class="ov__body">
      <div class="ov-big-ic">${ic(icon)}</div>
      <h1 class="ov__title"><small>${esc(name)}</small>${title}</h1>
      <p class="ov__lead">${lead}</p>
      <span class="ov-state">${ic('clock')} ${time}</span>
      ${inc.status === 'reported' ? `<p class="ov-note">${ic('shield-halved')}<span>이미 신고가 접수되어 추가로 신고할 수 없어요.</span></p>` : ''}
      <div class="ov-photo">${UI.maskPhoto(inc.id)}</div>
      <p class="ov__small">낙상 감지 ${UI.dateTime(inc.detectedAt)}</p>
    </div><div class="ov__foot"><button class="btn btn--white btn--lg" style="color:#1d2f35" data-action="em.dismiss" data-id="${inc.id}">확인</button></div>`);
  }
  on('em.dismiss', el => { Act.dismiss(el.dataset.id, Sel.meId()); sync(true); });

  /* ---------- 동작 ---------- */
  on('em.ok', el => { Act.selfOk(el.dataset.id, Sel.meId()); sync(true); });
  on('em.help', el => {
    const inc = Sel.incident(el.dataset.id); const n = inc ? inc.helpTimes.length + 1 : 1;
    Act.selfHelp(el.dataset.id, Sel.meId());
    toast(n > 1 ? `가족에게 ${n}번째로 요청했어요` : '가족에게 도움을 요청했어요');
    sync(true);
  });
  on('em.take', el => { Act.takeOver(el.dataset.id, Sel.meId()); sync(true); });
  on('em.close', async el => {
    const ok = await UI.confirm({ title: '사고를 종료할까요?', body: '괜찮은 것을 확인했다면 종료해 주세요. 이력에 기록돼요.', ok: '종료', cancel: '취소', top: true });
    if (ok) { Act.closeChecked(el.dataset.id, Sel.meId()); sync(true); }
  });
  on('em.report-self', el => { flow = { id: el.dataset.id, step: 'confirm', selected: [Sel.meId()], unknown: false, from: 'self' }; sync(true); });
  on('em.report-family', el => {
    const inc = Sel.incident(el.dataset.id); const vs = victims(inc);
    if (vs.length === 1) flow = { id: inc.id, step: 'confirm', selected: [vs[0].id], unknown: false, from: 'family' };
    else flow = { id: inc.id, step: 'pick', selected: inc.recognizedId && vs.some(p => p.id === inc.recognizedId) ? [inc.recognizedId] : [], unknown: false, from: 'family' };
    sync(true);
  });
  on('em.back', () => {
    if (!flow) return;
    const inc = Sel.incident(flow.id); const vs = inc ? victims(inc) : [];
    if (flow.step === 'confirm' && flow.from === 'family' && vs.length > 1) { flow.step = 'pick'; flow.unknown = false; }
    else flow = null;
    sync(true);
  });
  on('em.call', el => {
    const inc = Sel.incident(el.dataset.id); const vs = victims(inc);
    if (vs.length === 1) { location.href = 'tel:' + vs[0].phone.replace(/\D/g, ''); return; }
    UI.openSheet({ title: '누구에게 전화할까요?', top: true, html: `<div class="card">${vs.map(p => `<a class="row" href="tel:${esc(p.phone.replace(/\D/g, ''))}">${UI.avatar(p)}<span class="row__main"><span class="row__title">${esc(p.name)}</span><span class="row__sub">${esc(p.phone)}</span></span>${ic('phone')}</a>`).join('')}</div>` });
  });
  on('em.map', el => {
    const inc = Sel.incident(el.dataset.id); const h = Sel.home(inc.homeId);
    UI.openSheet({ title: '낙상 위치', top: true, html: `
      <div class="card card--pad"><p class="label">${esc(Sel.homeName(h, Sel.me()))} · ${esc(inc.location)}</p>
        <p style="font-weight:800;font-size:18px">${esc(UI.addr(h))}</p></div>
      ${h.address ? `<div class="btn-pair" style="margin-top:14px"><a class="btn btn--primary" target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(h.address)}">${ic('map-location-dot')} 지도 열기</a>
        <button class="btn btn--soft" data-action="em.copy-addr" data-addr="${esc(h.address)}">${ic('copy')} 주소 복사</button></div>` : '<div class="notice notice--warn" style="margin-top:14px">등록된 주소가 없어요. 낙상자에게 직접 전화해 위치를 확인해 주세요.</div>'}` });
  });
  on('em.copy-addr', el => UI.copy(el.dataset.addr, '주소를 복사했어요'));

  /* ---------- 렌더 ---------- */
  function render(force) {
    const el = root(); if (!el) return;
    const me = Sel.me();
    let inc = me ? choose(me) : null;
    if (flow && (!inc || inc.id !== flow.id || Sel.isTerminal(inc))) flow = null;
    let html = '', sig = 'none';
    if (inc) {
      const role = Sel.roleIn(inc, me);
      let view;
      if (Sel.isTerminal(inc)) view = 'ended';
      else if (flow) view = flow.step;
      else view = role === 'victim' ? 'victim' : 'family';
      sig = [inc.id, view, inc.status, inc.helpTimes.length, inc.checkedBy, alertLevel(inc, me), flow ? flow.selected.join(',') + flow.unknown : '', me.id, inc.closedAt, inc.reportedBy].join('|');
      if (force || sig !== lastSig) {
        html = view === 'victim' ? viewVictim(inc, me) : view === 'family' ? viewFamily(inc, me) : view === 'pick' ? viewPick(inc, me) : view === 'confirm' ? viewConfirm(inc, me) : viewEnded(inc, me);
      }
    }
    if (sig !== lastSig || force) {
      const prevScroll = el.firstElementChild ? el.firstElementChild.scrollTop : 0;
      const same = el.dataset.sigBase === sig.split('|').slice(0, 2).join('|');
      el.innerHTML = html;
      el.dataset.sigBase = sig.split('|').slice(0, 2).join('|');
      if (same && el.firstElementChild) { el.firstElementChild.style.animation = 'none'; el.firstElementChild.scrollTop = prevScroll; }
      lastSig = sig;
      UI.lockBody(false);
    }
    UI.tick(el);
  }
  function sync(force) { render(force); FD.Router.refresh(); }

  FD.Emergency = {
    open(id) { const m = mem[id] = mem[id] || {}; m.min = false; sync(true); },
    render, sync,
    reset() { flow = null; lastSig = ''; }
  };
})();
