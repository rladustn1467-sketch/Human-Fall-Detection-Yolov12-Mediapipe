/* ------------------------------------------------------------------
 * home.js — T-01 홈, S-01 기기 상세, S-02 낙상 이력 목록, S-03 낙상 이력 상세
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, openSheet, closeSheet, toast } = UI;
  const { Sel, Act } = FD.Store;
  const R = FD.Router;

  const openState = {};      // 집별 펼침 상태 (사용자가 직접 바꾼 값)
  let restOpen = false;      // "나머지 N곳" 펼침

  /* ------------------------------------------------------------
   * 홈 구성 요소
   * ---------------------------------------------------------- */
  function incidentBanner(inc, me) {
    const h = Sel.home(inc.homeId);
    const name = Sel.homeName(h, me);
    const role = Sel.roleIn(inc, me);
    let cls = '', icon = 'triangle-exclamation', t = '', s = '';
    if (inc.status === 'detected') {
      t = `${esc(name)} · ${esc(inc.location)} 낙상 감지`;
      s = `응답까지 <b data-cd="${inc.detectedAt + 60000}">--:--</b>`;
    } else if (inc.status === 'checking') {
      const who = Sel.person(inc.checkedBy);
      cls = ' incident-banner--calm'; icon = 'user-check';
      t = `${esc(who ? who.name : '가족')}님 확인 중`;
      s = `${esc(name)} · ${esc(inc.location)} · <span data-min="${inc.detectedAt}">--</span>`;
    } else {
      t = `${esc(name)} · ${esc(inc.location)} ${inc.status === 'help' ? '도움 요청' : '낙상 알림'}`;
      s = `자동 신고까지 <b data-cd="${inc.autoReportAt}">--:--</b>`;
    }
    void role;
    return `<button class="incident-banner${cls}" data-action="incident.open" data-id="${inc.id}" aria-label="진행 중인 낙상 사고 열기">
      <span class="incident-banner__ic">${ic(icon)}</span>
      <span class="incident-banner__main"><span class="incident-banner__t" style="display:block">${t}</span><span class="incident-banner__s" style="display:block">${s}</span></span>
      ${ic('chevron-right', 'chev')}</button>`;
  }
  on('incident.open', el => FD.Emergency.open(el.dataset.id));

  function devRow(d, canEdit) {
    const bad = d.status === 'disconnected', off = d.status === 'off';
    const cls = bad ? ' det-dev--bad' : off ? ' det-dev--off' : '';
    const t = FD.Store.now();
    let fix = '';
    if (bad) {
      fix = `<div class="det-dev__fix"><span>${UI.ago(t - d.since).replace('방금', '방금')}부터 · 전원/와이파이 확인</span>${canEdit ? `<button class="btn btn--soft btn--sm" data-action="dev.reconnect" data-id="${d.id}">다시 연결</button>` : ''}</div>`;
    } else if (off) {
      fix = `<div class="det-dev__fix"><span>${UI.ago(t - d.since)}부터 감지를 쉬고 있어요</span>${canEdit ? `<button class="btn btn--soft btn--sm" data-action="dev.quick-on" data-id="${d.id}">감지 켜기</button>` : ''}</div>`;
    }
    return `<div class="det-dev${cls}">
      <button class="det-dev__row" data-action="dev.open" data-id="${d.id}" aria-label="${esc(UI.deviceName(d))} ${UI.STATUS_LABEL[d.status]}">
        <span class="det-dev__ic">${ic(UI.DEVICE_ICON[d.type])}</span>
        <span class="det-dev__name">${esc(UI.deviceName(d))}</span>
        <span class="det-dev__state">${UI.STATUS_LABEL[d.status]}</span>
      </button>${fix}</div>`;
  }

  function homeCard(h, me, activeIncs) {
    const sum = Sel.homeSummary(h);
    const abnormal = sum.kind !== 'ok';
    const incident = activeIncs.find(i => i.homeId === h.id);
    const isOpen = openState[h.id] !== undefined ? openState[h.id] : (abnormal || !!incident);
    const devs = Sel.devices(h.id).slice().sort((a, b) => (a.status === 'ok') - (b.status === 'ok'));
    const canEdit = Sel.canEditHome(h.id, me);
    const icon = sum.kind === 'ok' ? 'shield-check' : sum.kind === 'warn' ? 'triangle-exclamation' : 'circle-pause';
    const summary = sum.kind === 'ok' ? `${sum.title} · ${sum.detail}` : sum.kind === 'warn' ? `${sum.title} · ${sum.detail}` : `${sum.title} · ${sum.detail}`;
    return `<section class="det-home det-home--${incident ? 'incident' : sum.kind}${isOpen ? ' is-open' : ''}" aria-label="${esc(Sel.homeName(h, me))} 감지 현황">
      <button class="det-home__head" data-action="home.toggle" data-id="${h.id}" aria-expanded="${isOpen}">
        <span class="det-ic det-ic--${incident ? 'stop' : sum.kind}">${ic(incident ? 'bell' : icon)}</span>
        <span style="flex:1;min-width:0"><span class="det-home__name" style="display:block">${esc(Sel.homeName(h, me))}</span>
        <span class="det-home__sum k-${incident ? 'stop' : sum.kind}" style="display:block">${incident ? '낙상 사고 진행 중' : esc(summary)}</span></span>
        ${ic('chevron-down', 'det-home__caret')}</button>
      <div class="det-home__devs">${devs.length ? devs.map(d => devRow(d, canEdit)).join('') : `<div class="det-dev"><div class="det-dev__fix" style="margin:0"><span>연결된 기기가 없어요</span>${canEdit ? `<button class="btn btn--soft btn--sm" data-action="home.add-device" data-id="${h.id}">기기 추가</button>` : ''}</div></div>`}</div>
    </section>`;
  }
  on('home.toggle', el => {
    const id = el.dataset.id; const card = el.closest('.det-home');
    const now = !card.classList.contains('is-open');
    openState[id] = now; card.classList.toggle('is-open', now); el.setAttribute('aria-expanded', now);
  });
  on('home.rest', el => {
    restOpen = !restOpen;
    const box = document.getElementById('rest-list'); if (box) box.style.display = restOpen ? 'block' : 'none';
    el.querySelector('.det-home__caret').style.transform = restOpen ? 'rotate(180deg)' : '';
  });
  on('home.add-device', el => FD.Sheets.addDevice(el.dataset.id));

  function homesSection(me) {
    if (!me.groupId) return '';
    const all = Sel.homes(me.groupId);
    if (!all.length) {
      return `<div class="card card--pad empty" style="margin-bottom:12px">${ic('house-circle-exclamation')}등록된 집이 없어요.<br>가족 탭에서 집 정보를 입력할 수 있어요.</div>`;
    }
    const active = Sel.incidentsFor(me).filter(i => !Sel.isTerminal(i));
    const info = all.map(h => ({ h, sum: Sel.homeSummary(h), inc: active.some(i => i.homeId === h.id), mine: me.homeIds.includes(h.id) }));
    const rank = x => x.inc ? 0 : x.sum.kind !== 'ok' ? 1 : x.mine ? 2 : 3;
    info.sort((a, b) => rank(a) - rank(b));
    const normals = info.filter(x => rank(x) >= 2);
    const lead = info.filter(x => rank(x) < 2);
    let html = lead.map(x => homeCard(x.h, me, active)).join('');
    if (normals.length > 2) {
      const first = normals[0], rest = normals.slice(1);
      html += homeCard(first.h, me, active);
      html += `<button class="det-more" data-action="home.rest" aria-expanded="${restOpen}"><span class="det-ic det-ic--ok">${ic('shield-check')}</span><span style="flex:1">나머지 ${rest.length}곳 · 모두 정상</span>${ic('chevron-down', 'det-home__caret')}</button>
        <div id="rest-list" style="display:${restOpen ? 'block' : 'none'}">${rest.map(x => homeCard(x.h, me, active)).join('')}</div>`;
    } else html += normals.map(x => homeCard(x.h, me, active)).join('');
    return html;
  }

  function phoneCard(me) {
    if (!me.isTarget) {
      return `<div class="phone-card"><span class="phone-card__ic">${ic('bell')}</span><span class="phone-card__main"><span class="phone-card__t" style="display:block">알림만 받는 중</span><span class="phone-card__s" style="display:block">가족의 낙상 알림을 받고 있어요</span></span>
        <button class="btn btn--primary btn--sm" data-action="home.enable">낙상 감지 켜기</button></div>`;
    }
    if (me.phoneCamera) {
      return `<div class="phone-card is-on"><span class="phone-card__ic">${ic('mobile-screen')}</span><span class="phone-card__main"><span class="phone-card__t" style="display:block"><i class="live-dot"></i>내 폰 카메라로 감지 중</span><span class="phone-card__s" style="display:block">이 휴대전화 카메라를 사용하고 있어요</span></span>
        <button class="btn btn--sm" style="background:rgba(255,255,255,.2);color:#fff" data-action="phone.off">중지</button></div>`;
    }
    return `<div class="phone-card"><span class="phone-card__ic">${ic('mobile-screen')}</span><span class="phone-card__main"><span class="phone-card__t" style="display:block">내 폰 카메라로 감지하기</span><span class="phone-card__s" style="display:block">꺼짐</span></span>
      <button class="btn btn--primary btn--sm" data-action="phone.on">감지하기</button></div>`;
  }
  on('home.enable', () => FD.Onboarding.startEnable());
  on('phone.on', () => { Act.phoneCamera(Sel.meId(), true); toast('내 폰 카메라로 감지를 시작했어요', 'ok'); });
  on('phone.off', async () => {
    const ok = await UI.confirm({ title: '감지를 중지할까요?', body: '감지를 끄면 이 공간에서 낙상이 발생해도 알림이 가지 않아요. 끌까요?', ok: '중지', cancel: '취소', danger: true });
    if (ok) { Act.phoneCamera(Sel.meId(), false); toast('내 폰 카메라 감지를 중지했어요'); }
  });

  /* 설정 미완료 항목 */
  function todos(me) {
    const out = [];
    me.homeIds.map(id => Sel.home(id)).filter(Boolean).forEach(h => {
      const nm = Sel.homeName(h, me);
      if (!h.address) out.push({ t: `${nm} 주소를 입력해 주세요`, a: 'todo.address', id: h.id });
      if (!h.centralPw) out.push({ t: `${nm} 중앙 현관 비밀번호를 등록해 주세요`, a: 'todo.pw', id: h.id, key: 'centralPw' });
      if (!h.doorPw) out.push({ t: `${nm} 집 현관 비밀번호를 등록해 주세요`, a: 'todo.pw', id: h.id, key: 'doorPw' });
    });
    if (me.isTarget) {
      const missing = [];
      if (!me.birth) missing.push('생년월일');
      if (me.conditions == null) missing.push('지병');
      if (me.medications == null) missing.push('복용약');
      if (missing.length) out.push({ t: `${missing.join('·')}을(를) 입력해 주세요`, a: 'todo.profile' });
    }
    return out;
  }
  on('todo.address', el => FD.Sheets.editAddress(el.dataset.id));
  on('todo.pw', el => FD.Sheets.password(el.dataset.id, el.dataset.key));
  on('todo.profile', () => R.go('/settings/profile'));

  function recentSection(me) {
    const t = FD.Store.now();
    const items = Sel.history().filter(x => x.groupId === me.groupId && t - x.detectedAt <= 7 * 86400000).slice(0, 3);
    return `<section class="section" aria-labelledby="recent-h">
      <div class="section__head"><h2 class="section__title" id="recent-h">최근 알림</h2><button class="link-btn" data-action="hist.list">더보기</button></div>
      <div class="card">${items.length ? items.map(historyRow).join('') : `<div class="empty">${ic('bell-slash')}최근 낙상 알림이 없어요</div>`}</div>
    </section>`;
  }
  on('hist.list', () => R.go('/history'));

  function resultIcon(r) { return { self: 'user-check', family: 'people-group', reported: 'truck-medical', auto_reported: 'robot' }[r] || 'bell'; }
  function historyRow(x) {
    const h = Sel.home(x.homeId);
    const name = h ? Sel.homeName(h) : '집';
    return `<button class="recent-item" data-action="hist.open" data-id="${x.id}">
      <span class="recent-ic recent-ic--${x.result}">${ic(resultIcon(x.result))}</span>
      <span style="flex:1;min-width:0"><span class="row__title" style="display:block">${esc(name)} · ${esc(x.location)}</span>
      <span class="row__sub" style="display:block">${UI.dateTime(x.detectedAt)}</span></span>
      <span class="tag ${x.result === 'self' ? 'tag--ok' : x.result === 'family' ? 'tag--info' : 'tag--stop'}">${UI.RESULT_LABEL[x.result]}</span></button>`;
  }
  on('hist.open', el => R.go('/history/' + el.dataset.id));

  /* ------------------------------------------------------------
   * T-01 홈
   * ---------------------------------------------------------- */
  R.register('/', () => {
    const me = Sel.me();
    const incs = Sel.incidentsFor(me).filter(i => !Sel.isTerminal(i)).sort((a, b) => (Sel.deadline(a) - Sel.deadline(b)) || (a.detectedAt - b.detectedAt));
    const td = todos(me);
    const hr = new Date(FD.Store.now()).getHours();
    const hello = hr < 6 ? '늦은 시간이에요' : hr < 12 ? '좋은 아침이에요' : hr < 18 ? '안녕하세요' : '편안한 저녁이에요';
    return `<header class="home-head"><p class="home-head__hello">${hello}, ${esc(me.name)}님</p><h1 class="home-head__title">${esc(Sel.group(me.groupId) ? Sel.group(me.groupId).name : '낙상 감지')}</h1></header>
      <div class="home-body">
        ${incs.map(i => incidentBanner(i, me)).join('')}
        <section aria-labelledby="det-h"><div class="section__head"><h2 class="section__title" id="det-h">감지 현황</h2></div>${homesSection(me)}</section>
        ${phoneCard(me)}
        ${td.length ? `<section class="todo-card" aria-label="설정 미완료"><p class="todo-card__head">${ic('list-check')} 아직 입력하지 않은 정보가 있어요</p>
          ${td.map(x => `<button class="todo-item" data-action="${x.a}" data-id="${x.id || ''}" data-key="${x.key || ''}"><span>${esc(x.t)}</span>${ic('chevron-right', 'chev')}</button>`).join('')}</section>` : ''}
        ${recentSection(me)}
      </div>`;
  }, { tab: 'home', live: true });

  /* ------------------------------------------------------------
   * S-01 기기 상세 (바텀시트)
   * ---------------------------------------------------------- */
  function deviceHtml(d, editing) {
    const me = Sel.me();
    const canEdit = Sel.canEditHome(d.homeId, me);
    const h = Sel.home(d.homeId);
    const t = FD.Store.now();
    const tagCls = d.status === 'ok' ? 'tag--ok' : d.status === 'off' ? '' : 'tag--stop';
    if (editing && canEdit) {
      return `<div class="label">기기 종류</div>
        <div class="segmented" style="margin-bottom:16px">
          <button type="button" class="${editing.type === 'homecam' ? 'is-on' : ''}" data-action="devs.type" data-type="homecam">홈캠</button>
          <button type="button" class="${editing.type === 'cctv' ? 'is-on' : ''}" data-action="devs.type" data-type="cctv">CCTV</button>
        </div>
        ${UI.field({ id: 'devs-loc', label: '위치 이름', value: editing.location, maxlength: 12, onenter: 'devs.save' })}
        <div class="confirm__actions"><button class="btn btn--ghost btn--block" data-action="devs.cancel">취소</button><button class="btn btn--primary btn--block" data-action="devs.save">저장</button></div>`;
    }
    return `<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
        <span class="det-ic det-ic--${d.status === 'ok' ? 'ok' : d.status === 'off' ? 'warn' : 'stop'}" style="width:54px;height:54px;border-radius:16px;font-size:22px">${ic(UI.DEVICE_ICON[d.type])}</span>
        <div><p style="font-weight:800;font-size:19px">${esc(UI.deviceName(d))}</p><p class="row__sub">${esc(Sel.homeName(h, me))}</p></div>
        <span class="tag ${tagCls}" style="margin-left:auto">${UI.STATUS_LABEL[d.status]}</span></div>
      ${d.status !== 'ok' ? `<p class="row__sub" style="margin-bottom:12px">${UI.ago(t - d.since)}부터 ${d.status === 'off' ? '감지를 쉬고 있어요' : '연결되지 않았어요'}</p>` : ''}
      ${d.status === 'disconnected' ? `<div class="notice notice--warn" style="margin-bottom:14px">${ic('wrench')}<div><b>이렇게 확인해 보세요</b><br>1. 기기 전원이 켜져 있는지 확인해 주세요.<br>2. 와이파이 연결 상태를 확인해 주세요.<br>3. 그래도 안 되면 공유기와 기기를 껐다 켜 주세요.</div></div>` : ''}
      ${canEdit ? `<div class="stack">
          ${d.status === 'disconnected' ? `<button class="btn btn--primary btn--lg btn--block" data-action="devs.reconnect" data-id="${d.id}">다시 연결</button>` : ''}
          ${d.status === 'ok' ? `<button class="btn btn--ghost btn--block" data-action="devs.off" data-id="${d.id}">${ic('power-off')} 감지 끄기</button>` : ''}
          ${d.status === 'off' ? `<button class="btn btn--primary btn--lg btn--block" data-action="devs.on" data-id="${d.id}">감지 켜기</button>` : ''}
          <div class="btn-pair"><button class="btn btn--soft" data-action="devs.edit">${ic('pen')} 이름·위치 수정</button><button class="btn btn--danger-ghost" data-action="devs.remove" data-id="${d.id}">${ic('trash')} 기기 삭제</button></div>
        </div>`
        : `<div class="notice">${ic('lock')}<span>이 집에 연결된 가족만 설정을 바꿀 수 있어요. 상태는 그룹 가족 모두 볼 수 있어요.</span></div>`}`;
  }

  let devSheet = null, devEditing = null, devId = null;
  function openDevice(id) {
    devId = id; devEditing = null;
    const d = Sel.device(id); if (!d) return;
    devSheet = openSheet({
      title: '기기 상세', html: deviceHtml(d, null),
      refresh: api => { const x = Sel.device(devId); if (!x) { api.close(); return; } if (!devEditing) api.replace(deviceHtml(x, null)); },
      onClose: () => { devSheet = null; devId = null; }
    });
  }
  const redrawDev = () => { const d = Sel.device(devId); if (d && devSheet) devSheet.replace(deviceHtml(d, devEditing)); };
  on('dev.open', el => openDevice(el.dataset.id));

  async function reconnect(id, fromSheet) {
    const btn = document.querySelector(`[data-id="${id}"][data-action="${fromSheet ? 'devs.reconnect' : 'dev.reconnect'}"]`);
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner spinner--dark"></span> 연결하는 중'; }
    await new Promise(r => setTimeout(r, 1300));
    Act.updateDevice(id, { status: 'ok' });
    toast('다시 연결했어요', 'ok');
  }
  on('dev.reconnect', el => reconnect(el.dataset.id, false));
  on('devs.reconnect', el => reconnect(el.dataset.id, true));
  on('dev.quick-on', el => { Act.updateDevice(el.dataset.id, { status: 'ok' }); toast('감지를 켰어요', 'ok'); });
  on('devs.on', el => { Act.updateDevice(el.dataset.id, { status: 'ok' }); toast('감지를 켰어요', 'ok'); });
  on('devs.off', async el => {
    const ok = await UI.confirm({ title: '감지를 끌까요?', body: '감지를 끄면 이 공간에서 낙상이 발생해도 알림이 가지 않아요. 끌까요?', ok: '끄기', cancel: '취소', danger: true });
    if (ok) { Act.updateDevice(el.dataset.id, { status: 'off' }); toast('감지를 껐어요'); }
  });
  on('devs.edit', () => { const d = Sel.device(devId); devEditing = { type: d.type, location: d.location }; redrawDev(); });
  on('devs.cancel', () => { devEditing = null; redrawDev(); });
  on('devs.type', el => { devEditing.location = UI.val('devs-loc'); devEditing.type = el.dataset.type; redrawDev(); });
  on('devs.save', () => {
    const loc = UI.val('devs-loc');
    if (!loc) { UI.setError('devs-loc', '위치 이름을 입력해 주세요.'); return; }
    Act.updateDevice(devId, { type: devEditing.type, location: loc });
    devEditing = null; redrawDev(); toast('저장했어요', 'ok');
  });
  on('devs.remove', async el => {
    const ok = await UI.confirm({ title: '기기를 삭제할까요?', body: '삭제하면 이 기기로는 더 이상 낙상을 감지하지 않아요.', ok: '삭제', cancel: '취소', danger: true });
    if (ok) { Act.removeDevice(el.dataset.id); closeSheet(); toast('기기를 삭제했어요'); }
  });

  /* ------------------------------------------------------------
   * S-02 낙상 이력 목록
   * ---------------------------------------------------------- */
  const filt = { home: 'all', person: 'all' };
  R.register('/history', () => {
    const me = Sel.me();
    const homes = Sel.homes(me.groupId);
    const targets = Sel.people(me.groupId).filter(p => p.isTarget);
    let list = Sel.history().filter(x => x.groupId === me.groupId);
    if (filt.home !== 'all') list = list.filter(x => x.homeId === filt.home);
    if (filt.person !== 'all') list = list.filter(x => (x.personIds || [x.personId]).includes(filt.person));
    let lastDate = '';
    const rows = list.map(x => {
      const dl = UI.dateLabel(x.detectedAt);
      const head = dl !== lastDate ? `<p class="hist-date">${dl}</p>` : ''; lastDate = dl;
      return head + `<div class="card" style="margin:0 18px 8px">${historyRow(x)}</div>`;
    }).join('');
    return `${UI.subHeader('낙상 이력')}
      <div class="filter-bar" role="group" aria-label="집 필터" style="padding-top:12px;padding-bottom:4px">
        <button class="chip${filt.home === 'all' ? ' is-on' : ''}" data-action="hist.fh" data-v="all">전체 집</button>
        ${homes.map(h => `<button class="chip${filt.home === h.id ? ' is-on' : ''}" data-action="hist.fh" data-v="${h.id}">${esc(Sel.homeName(h, me))}</button>`).join('')}</div>
      <div class="filter-bar" role="group" aria-label="대상자 필터">
        <button class="chip${filt.person === 'all' ? ' is-on' : ''}" data-action="hist.fp" data-v="all">전체 대상자</button>
        ${targets.map(p => `<button class="chip${filt.person === p.id ? ' is-on' : ''}" data-action="hist.fp" data-v="${p.id}">${esc(p.name)}</button>`).join('')}</div>
      <div style="padding-bottom:30px">${rows || `<div class="empty" style="margin-top:30px">${ic('bell-slash')}해당하는 낙상 이력이 없어요</div>`}</div>`;
  }, { live: true, parent: '/' });
  on('hist.fh', el => { filt.home = el.dataset.v; R.go('/history'); });
  on('hist.fp', el => { filt.person = el.dataset.v; R.go('/history'); });

  /* ------------------------------------------------------------
   * S-03 낙상 이력 상세
   * ---------------------------------------------------------- */
  R.register('/history/:id', p => {
    const x = Sel.historyItem(p.id);
    if (!x) return `${UI.subHeader('낙상 이력')}<div class="empty" style="margin-top:60px">이력을 찾을 수 없어요</div>`;
    const h = Sel.home(x.homeId);
    const ids = x.personIds || [x.personId];
    const who = ids.map(i => Sel.person(i)).filter(Boolean).map(q => q.name).join('·');
    let ender = '';
    if (x.checkedBy) {
      const c = Sel.person(x.checkedBy);
      ender = `${esc(c ? c.name : '가족')}님이 ${UI.hm24(x.checkedAt)}에 확인${x.closedAt && x.closedBy === x.checkedBy ? ` → ${UI.hm24(x.closedAt)} 종료` : ''}`;
    } else if (x.result === 'self') {
      const c = Sel.person(x.closedBy); ender = `${esc(c ? c.name : '본인')}님이 ${UI.hm24(x.closedAt)}에 괜찮다고 응답하고 종료`;
    } else if (x.result === 'reported') {
      const c = Sel.person(x.reportedBy); ender = `${esc(c ? c.name : '가족')}님이 ${UI.hm24(x.reportedAt || x.closedAt)}에 119에 신고`;
    } else if (x.result === 'auto_reported') {
      ender = `${UI.hm24(x.reportedAt || x.closedAt)}에 자동으로 119 신고`;
    }
    return `${UI.subHeader('낙상 이력')}
      <div class="page page--tight">
        ${UI.maskPhoto(x.id)}
        <div class="card card--pad" style="margin-top:14px"><div class="kv">
          <div class="kv__row"><span class="kv__k">감지 시각</span><span class="kv__v">${UI.dateTime(x.detectedAt)}</span></div>
          <div class="kv__row"><span class="kv__k">집 · 위치</span><span class="kv__v">${esc(h ? Sel.homeName(h) : '집')} · ${esc(x.location)}</span></div>
          <div class="kv__row"><span class="kv__k">대상자</span><span class="kv__v">${esc(who || '-')}</span></div>
          <div class="kv__row"><span class="kv__k">응답 방식</span><span class="kv__v">${UI.RESPONSE_LABEL[x.response] || '-'}</span></div>
          <div class="kv__row"><span class="kv__k">결과</span><span class="kv__v"><span class="tag ${x.result === 'self' ? 'tag--ok' : x.result === 'family' ? 'tag--info' : 'tag--stop'}">${UI.RESULT_LABEL[x.result]}</span></span></div>
          ${ender ? `<div class="kv__row"><span class="kv__k">처리</span><span class="kv__v">${ender}</span></div>` : ''}
        </div></div>
        <section class="section"><div class="section__head"><h2 class="section__title">진행 기록</h2></div>
          <div class="card card--pad"><ul class="timeline" style="margin:0">${(x.log || []).map((l, i, a) => `<li class="${i === a.length - 1 ? 'is-end' : ''}"><time>${UI.clock(l.at)}</time><p>${esc(l.text)}</p></li>`).join('')}</ul></div></section>
      </div>`;
  }, { parent: '/history' });

  FD.Home = { openDevice };
  FD.Sheets = FD.Sheets || {};
  FD.Sheets.device = openDevice;
})();
