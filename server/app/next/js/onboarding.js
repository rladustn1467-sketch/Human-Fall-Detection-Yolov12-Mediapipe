/* ------------------------------------------------------------------
 * onboarding.js — O-01 ~ O-09, S-12(감지 켜기: O-06~O-09 흐름 재사용)
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const { esc, ic, on, field, setError, val, toast, openSheet, closeSheet } = FD.UI;
  const UI = FD.UI;
  const { Sel, Act } = FD.Store;
  const R = FD.Router;

  /* 흐름 중 입력값 임시 보관 (마지막 단계에서 한 번에 저장) */
  let draft = null;
  function newDraft() {
    return { info: { birth: undefined, conditions: undefined, medications: undefined }, homeMode: null, homeId: null, address: '', addrBase: '', addrDetail: '',
      central: '', door: '', centralKeep: true, doorKeep: true, devices: [], phoneCamera: false, addrSkipped: false };
  }
  const D = () => (draft = draft || newDraft());

  const STEP_NAMES = ['개인정보', '주소', '비밀번호', '기기'];
  function top(idx, total, opts) {
    opts = opts || {};
    const steps = Array.from({ length: total }, (_, i) => `<i class="${i <= idx ? 'is-done' : ''}"></i>`).join('');
    return `<div class="ob__top">
      ${opts.noBack ? '<span style="width:44px"></span>' : `<button class="icon-btn" data-action="nav.back" aria-label="뒤로">${ic('chevron-left')}</button>`}
      <div class="ob__steps" aria-label="진행 단계 ${idx + 1}/${total}">${steps}</div>
      <span style="width:44px"></span></div>`;
  }
  const page = (inner, foot) => `<main class="ob"><div class="ob__body">${inner}</div>${foot ? `<div class="ob__foot">${foot}</div>` : ''}</main>`;

  /* ---------------- O-01 가입 (휴대전화 번호 + 비밀번호) ---------------- */
  // 비밀번호 규칙: 8~64자, 영문과 숫자를 모두 포함 (서버도 B단계에서 같은 규칙으로 다시 확인)
  const PW_MIN = 8, PW_MAX = 64;
  const pwRule = pw => {
    if (pw.length < PW_MIN || pw.length > PW_MAX) return `비밀번호는 ${PW_MIN}~${PW_MAX}자로 입력해 주세요.`;
    if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return '비밀번호에 영문과 숫자를 모두 넣어 주세요.';
    return '';
  };
  // 비밀번호는 입력한 그대로 읽음 (val() 은 앞뒤 공백을 지우므로 쓰지 않음)
  const rawVal = id => { const e = document.getElementById(id); return e ? e.value : ''; };
  R.register('/ob/signup', () => {
    const html = page(`
      ${top(0, 3, { noBack: true })}
      <div class="brand"><span class="brand__mark">${ic('shield-heart')}</span>지킴이</div>
      <div class="hero-art"><i class="fa-solid fa-house-medical" aria-hidden="true"></i><p>혼자 계셔도,<br>가족이 바로 알아요.</p></div>
      <h1 class="ob__title">계정을 만들어 주세요</h1>
      <p class="ob__sub">사용하시는 분의 이름, 휴대전화 번호, 비밀번호를 입력해 주세요.</p>
      <form class="ob__form" id="signup-form" novalidate>
        ${field({ id: 'su-name', label: '이름', placeholder: '예) 김민준', autocomplete: 'name', maxlength: 20 })}
        ${field({ id: 'su-phone', label: '휴대전화 번호', type: 'tel', inputmode: 'numeric', placeholder: '010-0000-0000', autocomplete: 'tel', oninput: 'phone-fmt' })}
        ${field({ id: 'su-pw', label: '비밀번호', type: 'password', autocomplete: 'new-password', maxlength: PW_MAX, hint: `${PW_MIN}자 이상, 영문과 숫자를 모두 넣어 주세요.` })}
        ${field({ id: 'su-pw2', label: '비밀번호 확인', type: 'password', autocomplete: 'new-password', maxlength: PW_MAX })}
        <label class="check"><input type="checkbox" id="su-agree"><span>서비스 이용약관과 개인정보 수집·이용에 동의해요.</span></label>
        <p class="field__error" id="su-agree-err" role="alert" hidden></p>
      </form>`,
      `<button class="btn btn--primary btn--lg btn--block" data-action="signup.submit">계속하기</button>`);
    return html;
  });
  UI.onInput('phone-fmt', t => { const d = t.value.replace(/\D/g, '').slice(0, 11); t.value = d.length > 7 ? `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}` : d.length > 3 ? `${d.slice(0, 3)}-${d.slice(3)}` : d; });
  on('signup.submit', () => {
    const name = val('su-name'), phone = val('su-phone');
    const password = rawVal('su-pw'), password2 = rawVal('su-pw2');
    let ok = true;
    setError('su-name', name.length < 2 ? '이름을 입력해 주세요.' : ''); if (name.length < 2) ok = false;
    setError('su-phone', !UI.validPhone(phone) ? '휴대전화 번호를 정확히 입력해 주세요.' : ''); if (!UI.validPhone(phone)) ok = false;
    const pwErr = pwRule(password);
    setError('su-pw', pwErr); if (pwErr) ok = false;
    const pw2Err = !pwErr && password !== password2 ? '비밀번호가 서로 달라요. 다시 확인해 주세요.' : '';
    setError('su-pw2', pw2Err); if (pw2Err) ok = false;
    const agreed = document.getElementById('su-agree').checked;
    const ae = document.getElementById('su-agree-err'); ae.hidden = agreed; ae.textContent = agreed ? '' : '약관에 동의해 주세요.';
    if (!agreed) ok = false;
    if (!ok) return;
    draft = null;
    // 비밀번호는 서버로만 보냄 (B단계). 테스트 모드의 예시 저장소에는 저장하지 않음 (store.js createAccount 가 쓰지 않음)
    Act.createAccount({ name, phone: UI.fmtPhone(phone), password });
    R.go('/ob/group');
  });

  /* ---------------- O-02 그룹 선택 ---------------- */
  R.register('/ob/group', () => page(`
    ${top(1, 3, { noBack: true })}
    <h1 class="ob__title">가족 그룹을<br>시작해 볼까요?</h1>
    <p class="ob__sub">같은 그룹의 가족에게 낙상 알림이 전달돼요.</p>
    <div class="stack" style="margin-top:26px">
      <button class="choice" data-action="group.create"><span class="choice__ic">${ic('people-roof')}</span><span><span class="choice__t">우리 가족 그룹 만들기</span><span class="choice__s" style="display:block">처음이라면 새 그룹을 만들고 가족을 초대해요.</span></span></button>
      <button class="choice" data-action="group.join"><span class="choice__ic">${ic('qrcode')}</span><span><span class="choice__t">그룹에 참여하기</span><span class="choice__s" style="display:block">가족에게 받은 QR코드나 초대 코드로 들어가요.</span></span></button>
    </div>`));
  on('group.create', () => {
    const me = Sel.me();
    if (!me.groupId) Act.createGroup(me.id);
    R.go('/ob/invite');
  });
  on('group.join', () => R.go('/ob/join'));

  /* ---------------- O-03 그룹 만들기 · 초대 / S-06 초대 화면 ---------------- */
  function inviteLink(code) { return location.href.split('#')[0] + '#/join?code=' + code; }
  function inviteBlock(g) {
    const inv = g.invite;
    return `<div class="invite-card">
      <div id="inv-qr">${UI.qr(inviteLink(inv.code), 176)}</div>
      <p class="label" style="margin-bottom:8px">초대 코드</p>
      <div class="code-box" id="inv-code" aria-label="초대 코드 ${esc(inv.code)}">${inv.code.split('').map(c => `<span>${esc(c)}</span>`).join('')}</div>
      <p class="expire">${ic('clock')} 24시간 후 만료돼요 · <span id="inv-left" data-left="${inv.expiresAt}"></span></p>
    </div>
    <div class="btn-pair" style="margin-top:14px">
      <button class="btn btn--soft" data-action="invite.copy">${ic('copy')} 코드 복사</button>
      <button class="btn btn--soft" data-action="invite.share">${ic('share-nodes')} 공유하기</button>
    </div>`;
  }
  function inviteMount(root) {
    const me = Sel.me();
    if (!me || !me.groupId) return;
    const inv = Act.regenInvite(me.groupId, me.id);   // 초대할 때마다 새 코드 생성
    const g = Sel.group(me.groupId);
    const card = root.querySelector('#invite-area');
    if (card) { card.innerHTML = inviteBlock(g); UI.tick(card); }
    void inv;
  }
  on('invite.copy', () => { const g = Sel.group(Sel.me().groupId); UI.copy(g.invite.code, '초대 코드를 복사했어요'); });
  on('invite.share', async () => {
    const g = Sel.group(Sel.me().groupId);
    const text = `${Sel.me().name}님이 가족 그룹에 초대했어요. 초대 코드: ${g.invite.code} (24시간 후 만료)`;
    if (navigator.share) { try { await navigator.share({ title: '가족 그룹 초대', text, url: inviteLink(g.invite.code) }); return; } catch (e) { if (e && e.name === 'AbortError') return; } }
    UI.copy(text, '초대 문구를 복사했어요');
  });
  R.register('/ob/invite', () => {
    const me = Sel.me(); const g = me && me.groupId ? Sel.group(me.groupId) : null;
    return {
      html: page(`
        ${top(1, 3)}
        <h1 class="ob__title">가족을 초대해 주세요</h1>
        <p class="ob__sub">QR코드를 보여주거나 초대 코드를 알려주세요. 나중에 가족 탭에서도 초대할 수 있어요.</p>
        <div id="invite-area">${g ? inviteBlock(g) : ''}</div>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="ob.toAsk">다음</button>`),
      mount: inviteMount
    };
  });
  on('ob.toAsk', () => R.go('/ob/ask'));

  /* ---------------- O-04 그룹 참여 ---------------- */
  let scanStream = null;
  function stopScan() { if (scanStream) { scanStream.getTracks().forEach(t => t.stop()); scanStream = null; } }
  R.register('/ob/join', () => {
    const preset = (R.query().get('code') || '').toUpperCase();
    return {
      html: page(`
        ${top(1, 3)}
        <h1 class="ob__title">초대받은 그룹에<br>참여해요</h1>
        <p class="ob__sub">가족의 QR코드를 인식하거나 초대 코드를 입력해 주세요.</p>
        <div class="scanner" id="scanner" style="margin-top:22px"><video id="scan-video" playsinline muted style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover" hidden></video>
          <div class="scanner__frame"></div><p id="scan-msg">QR코드를 사각형 안에 맞춰 주세요</p></div>
        <button class="btn btn--soft btn--block" style="margin-top:12px" data-action="join.scan">${ic('camera')} QR코드 인식하기</button>
        <p class="group-label" style="justify-content:center;margin-top:22px">또는</p>
        <form id="join-form" novalidate>
          ${field({ id: 'join-code', label: '초대 코드', placeholder: '6자리 코드', maxlength: 8, value: preset, onenter: 'join.submit', oninput: 'upper' })}
        </form>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="join.submit">그룹 참여하기</button>`),
      mount: () => { }
    };
  });
  UI.onInput('upper', t => { t.value = t.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); });
  on('join.submit', () => {
    const code = val('join-code');
    if (code.length < 4) { setError('join-code', '초대 코드를 입력해 주세요.'); return; }
    const me = Sel.me();
    const r = Act.joinGroup(me.id, code);
    if (!r.ok) { setError('join-code', r.reason); return; }
    stopScan();
    toast('그룹에 참여했어요', 'ok');
    R.go('/ob/ask');
  });
  on('join.scan', async () => {
    const msg = document.getElementById('scan-msg'), video = document.getElementById('scan-video');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !('BarcodeDetector' in window)) {
      toast('이 기기에서는 QR 인식을 쓸 수 없어요. 초대 코드를 입력해 주세요.'); return;
    }
    try {
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      video.srcObject = scanStream; video.hidden = false; await video.play();
      const det = new window.BarcodeDetector({ formats: ['qr_code'] });
      msg.textContent = 'QR코드를 찾는 중이에요';
      const loop = async () => {
        if (!scanStream) return;
        try {
          const codes = await det.detect(video);
          if (codes.length) {
            const raw = codes[0].rawValue || '';
            const m = /code=([A-Za-z0-9]+)/.exec(raw);
            const code = (m ? m[1] : raw).toUpperCase();
            document.getElementById('join-code').value = code;
            stopScan(); video.hidden = true; msg.textContent = 'QR코드를 인식했어요';
            on_join_after_scan();
            return;
          }
        } catch (e) { /* 다음 프레임 */ }
        setTimeout(loop, 250);
      };
      loop();
    } catch (e) { toast('카메라를 사용할 수 없어요. 초대 코드를 입력해 주세요.'); }
  });
  function on_join_after_scan() { const b = document.querySelector('[data-action="join.submit"]'); if (b) b.click(); }

  /* ---------------- O-05 감지 대상 설정 질문 ---------------- */
  R.register('/ob/ask', () => {
    const me = Sel.me();
    return page(`
      ${top(2, 3)}
      <h1 class="ob__title">이 기기를 사용하는 분을<br>낙상 감지 대상으로<br>설정할까요?</h1>
      <p class="ob__sub">감지 대상이 되면 카메라로 낙상을 살피고, 사고가 나면 가족에게 알려요.</p>
      <div class="notice" style="margin-top:22px">${ic('circle-info')}<span>나중에 홈에서 낙상 감지를 켤 수 있어요.</span></div>`,
      `<button class="btn btn--primary btn--lg btn--block" data-action="ask.yes">예</button>
       <button class="btn btn--ghost btn--lg btn--block" data-action="ask.no">아니요 (알림만 받을게요)</button>`);
  });
  on('ask.yes', () => { draft = newDraft(); R.go('/ob/info'); });
  on('ask.no', () => { Act.updateProfile(Sel.me().id, { onboarded: true }); R.go('/', { replace: true }); });

  /* ---------------- O-06 ~ O-09 (ob / enable 공통) ---------------- */
  function flowBase(flow) { return '/' + flow; }
  function register(flow) {
    const base = flowBase(flow);

    /* O-06 개인정보 */
    R.register(base + '/info', () => {
      const d = D(); const i = d.info;
      const card = (key, title, inner) => `<section class="info-item${i[key] === null ? ' is-skipped' : ''}" id="card-${key}">
        <div class="info-item__head"><h3>${title}</h3><button class="link-btn link-btn--muted" data-action="info.skip" data-key="${key}">${i[key] === null ? '입력하기' : '건너뛰기'}</button></div>
        <div class="info-item__body">${inner}</div><p class="info-item__skipmsg">나중에 입력할게요</p></section>`;
      const listCard = (key, title, sugg, none) => card(key, title, `
        <label class="check" style="margin-bottom:6px"><input type="checkbox" id="none-${key}" data-action="info.none" data-key="${key}" ${Array.isArray(i[key]) && i[key].length === 0 ? 'checked' : ''}><span>${none}</span></label>
        <div id="tags-${key}" ${Array.isArray(i[key]) && i[key].length === 0 ? 'hidden' : ''}></div>`);
      return {
        html: page(`
          ${top(0, 4)}
          <p class="tag tag--primary">${STEP_NAMES[0]} · 1/4</p>
          <h1 class="ob__title" style="margin-top:10px">건강 정보를 알려주세요</h1>
          <p class="ob__sub">그룹 가족에게 공유돼요.</p>
          <div style="margin-top:22px">
            ${card('birth', '생년월일', `<input type="date" id="info-birth" max="${new Date().toISOString().slice(0, 10)}" value="${esc(i.birth || '')}" aria-label="생년월일">`)}
            ${listCard('conditions', '지병', UI.SUGGEST_COND, '지병이 없어요')}
            ${listCard('medications', '복용약', UI.SUGGEST_MED, '복용하는 약이 없어요')}
          </div>`,
          `<button class="btn btn--primary btn--lg btn--block" data-action="info.next">다음</button>`),
        mount: root => {
          const mk = (key, sugg) => {
            const el = root.querySelector('#tags-' + key);
            const ed = UI.tagEditor(el, { value: Array.isArray(i[key]) ? i[key] : [], suggestions: sugg, placeholder: key === 'conditions' ? '직접 입력 (예: 천식)' : '직접 입력' });
            el._ed = ed;
          };
          mk('conditions', UI.SUGGEST_COND); mk('medications', UI.SUGGEST_MED);
        }
      };
    });
    on('info.skip', el => {
      const d = D(), k = el.dataset.key; collectInfo();
      d.info[k] = d.info[k] === null ? undefined : null;
      R.go(R.path(), { replace: false });
    });
    on('info.none', el => {
      const d = D(), k = el.dataset.key; collectInfo();
      d.info[k] = el.checked ? [] : undefined;
      R.go(R.path());
    });
    function collectInfo() {
      const d = D(), i = d.info;
      const b = document.getElementById('info-birth');
      if (b && i.birth !== null) i.birth = b.value || undefined;
      ['conditions', 'medications'].forEach(k => {
        const el = document.getElementById('tags-' + k), none = document.getElementById('none-' + k);
        if (!el || i[k] === null) return;
        if (none && none.checked) i[k] = [];
        else { const t = el._ed ? el._ed.get() : []; i[k] = t.length ? t : undefined; }
      });
    }
    on('info.next', () => {
      collectInfo();
      R.go(base + '/address');
    });

    /* O-07 주소 */
    R.register(base + '/address', () => {
      const me = Sel.me(); const d = D();
      const homes = me.groupId ? Sel.homes(me.groupId).filter(h => h.address) : [];
      const hasHomes = homes.length > 0 && d.homeMode !== 'new';
      return {
        html: page(`
          ${top(1, 4)}
          <p class="tag tag--primary">${STEP_NAMES[1]} · 2/4</p>
          <h1 class="ob__title" style="margin-top:10px">${hasHomes ? '같은 집에 사시나요?' : '사시는 곳의 주소를 입력해 주세요'}</h1>
          <div id="addr-body" style="margin-top:20px"></div>`,
          `<button class="btn btn--ghost btn--block" data-action="addr.skip">건너뛰기</button>`),
        mount: root => { drawAddr(root.querySelector('#addr-body'), homes, hasHomes); }
      };
    });
    function drawAddr(body, homes, hasHomes) {
      const d = D();
      if (hasHomes) {
        body.innerHTML = `<p class="ob__sub" style="margin-top:0">그룹에 등록된 주소가 있어요.</p>
          <div class="stack" style="margin-top:14px">${homes.map(h => `
            <div class="card card--pad"><p style="font-weight:800;font-size:17px">${esc(h.address)}</p>
              <p class="row__sub">이 주소와 같은 집에 사시나요?</p>
              <button class="btn btn--primary btn--block" style="margin-top:12px" data-action="addr.same" data-id="${h.id}">네, 같아요</button></div>`).join('')}
          </div>
          <button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="addr.other">아니요 (다른 주소 입력하기)</button>`;
        return;
      }
      const picked = d.addrBase;
      body.innerHTML = `
        <div class="notice">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 정확한 주소를 입력해 주세요. (동·호수까지) 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
        <div style="margin-top:18px">
          ${picked ? `<div class="addr-picked">${ic('circle-check')}<span style="flex:1">${esc(picked)}</span><button class="link-btn" data-action="addr.change">변경</button></div>
            ${field({ id: 'addr-detail', label: '동·호수', placeholder: '예) 101동 1203호', value: d.addrDetail, onenter: 'addr.next' })}`
            : `<div class="inline-add"><input id="addr-q" type="search" placeholder="도로명, 건물명, 동 이름으로 검색" aria-label="주소 검색" data-onenter="addr.search" autocomplete="off"><button class="btn btn--primary" data-action="addr.search">${ic('magnifying-glass')} 검색</button></div>
               <div class="addr-list" id="addr-results"></div>`}
        </div>
        ${picked ? `<button class="btn btn--primary btn--lg btn--block" style="margin-top:6px" data-action="addr.next">다음</button>` : ''}
        ${homes.length ? `<button class="link-btn" style="margin-top:12px" data-action="addr.back-existing">그룹에 등록된 주소 중에서 고르기</button>` : ''}`;
    }
    let lastResults = [];
    on('addr.same', el => { const d = D(); d.homeMode = 'existing'; d.homeId = el.dataset.id; R.go(base + '/password'); });
    on('addr.other', () => { const d = D(); d.homeMode = 'new'; d.addrBase = ''; drawAddr(document.getElementById('addr-body'), Sel.homes(Sel.me().groupId).filter(h => h.address), false); });
    on('addr.back-existing', () => { const d = D(); d.homeMode = null; drawAddr(document.getElementById('addr-body'), Sel.homes(Sel.me().groupId).filter(h => h.address), true); });
    on('addr.change', () => { const d = D(); d.addrBase = ''; drawAddr(document.getElementById('addr-body'), Sel.homes(Sel.me().groupId).filter(h => h.address), false); });
    on('addr.search', async () => {
      const q = document.getElementById('addr-q').value;
      const box = document.getElementById('addr-results');
      lastResults = await FD.API.searchAddress(q);
      box.innerHTML = lastResults.length
        ? lastResults.map((a, i) => `<button class="addr-item" data-action="addr.pick" data-i="${i}">${ic('location-dot')}<span>${esc(a)}</span></button>`).join('')
        : `<p class="empty" style="padding:18px">검색 결과가 없어요. 건물명이나 도로명을 다시 입력해 보세요.</p>`;
    });
    on('addr.pick', el => {
      const d = D(); d.addrBase = lastResults[+el.dataset.i]; d.homeMode = 'new';
      drawAddr(document.getElementById('addr-body'), Sel.homes(Sel.me().groupId).filter(h => h.address), false);
      const i = document.getElementById('addr-detail'); if (i) i.focus();
    });
    on('addr.next', () => {
      const d = D(); const det = val('addr-detail');
      if (!det) { setError('addr-detail', '동·호수까지 입력해 주세요.'); return; }
      d.addrDetail = det; d.address = d.addrBase + ' ' + det; d.homeMode = 'new'; d.addrSkipped = false;
      R.go(base + '/password');
    });
    on('addr.skip', async () => {
      const ok = await UI.confirm({ title: '주소를 나중에 입력할까요?', body: '주소가 없으면 119 신고 시 위치 전달이 어려울 수 있어요. 나중에 가족 탭의 집 관리에서 언제든 입력할 수 있어요.', ok: '건너뛰기', cancel: '계속 입력' });
      if (!ok) return;
      const d = D(); d.homeMode = 'new'; d.address = ''; d.addrBase = ''; d.addrSkipped = true;
      R.go(base + '/password');
    });

    /* O-08 비밀번호 */
    R.register(base + '/password', () => {
      const d = D();
      const h = d.homeMode === 'existing' ? Sel.home(d.homeId) : null;
      const block = (key, title, reg) => {
        if (h && reg) {
          const keep = d[key + 'Keep'];
          return `<section class="pw-card" id="pw-${key}"><div class="pw-card__head"><h3>${title}</h3><span class="tag tag--ok">${ic('lock')} 등록됨</span></div>
            ${keep ? `<div class="pw-card__actions"><button class="btn btn--soft btn--sm" data-action="pw.keep" data-key="${key}" aria-pressed="true">${ic('check')} 그대로 사용</button><button class="btn btn--ghost btn--sm" data-action="pw.change" data-key="${key}">변경하기</button></div>`
              : `${field({ id: 'pw-' + key + '-in', label: '새 비밀번호', type: 'password', placeholder: '새 비밀번호 입력', value: d[key] })}<div class="pw-card__actions"><button class="btn btn--ghost btn--sm" data-action="pw.keep" data-key="${key}">그대로 사용</button></div>`}
          </section>`;
        }
        return `<section class="pw-card"><div class="pw-card__head"><h3>${title}</h3></div>
          ${field({ id: 'pw-' + key + '-in', type: 'password', placeholder: '비밀번호 입력', value: d[key], autocomplete: 'new-password' })}</section>`;
      };
      return page(`
        ${top(2, 4)}
        <p class="tag tag--primary">${STEP_NAMES[2]} · 3/4</p>
        <h1 class="ob__title" style="margin-top:10px">현관 비밀번호를<br>등록해 주세요</h1>
        <div class="notice notice--lock" style="margin-top:16px">${ic('lock')}<span>낙상 사고 시 119 구급대가 집에 들어갈 수 있도록 비밀번호를 등록해 주세요. 비밀번호는 암호화되어 저장되며, 119 신고가 접수될 때만 구급대에게 전달돼요. 비밀번호는 가족에게도 보이지 않아요.</span></div>
        <div style="margin-top:18px">${block('central', '중앙 현관 비밀번호', h && h.centralPw)}${block('door', '집 현관 비밀번호', h && h.doorPw)}</div>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="pw.next">다음</button>
         <button class="btn btn--ghost btn--block" data-action="pw.skip">건너뛰기</button>`);
    });
    function collectPw() {
      const d = D();
      ['central', 'door'].forEach(k => { const e = document.getElementById('pw-' + k + '-in'); if (e) d[k] = e.value; });
    }
    on('pw.change', el => { collectPw(); D()[el.dataset.key + 'Keep'] = false; R.go(R.path()); });
    on('pw.keep', el => { collectPw(); const d = D(); d[el.dataset.key + 'Keep'] = true; d[el.dataset.key] = ''; R.go(R.path()); });
    on('pw.next', () => { collectPw(); R.go(base + '/device'); });
    on('pw.skip', async () => {
      const ok = await UI.confirm({ title: '비밀번호를 나중에 등록할까요?', body: '비밀번호가 없으면 구급대가 출입하는 데 시간이 걸릴 수 있어요.', ok: '건너뛰기', cancel: '계속 입력' });
      if (!ok) return;
      const d = D(); d.central = ''; d.door = '';
      R.go(base + '/device');
    });

    /* O-09 기기 연결 */
    R.register(base + '/device', () => {
      const d = D();
      return page(`
        ${top(3, 4)}
        <p class="tag tag--primary">${STEP_NAMES[3]} · 4/4</p>
        <h1 class="ob__title" style="margin-top:10px">감지할 카메라를<br>연결해 주세요</h1>
        <div class="notice" style="margin-top:16px">${ic('eye-slash')}<span>영상은 낙상 판단에만 쓰이고 저장되지 않아요. 낙상이 감지되면 배경과 사람을 가린 이미지만 기록돼요.</span></div>
        <div id="dev-added" style="margin-top:18px">${devAddedHtml(d)}</div>
        <div class="stack" style="margin-top:14px">
          <button class="choice" data-action="dev.add"><span class="choice__ic">${ic('video')}</span><span><span class="choice__t">홈캠·CCTV 추가</span><span class="choice__s" style="display:block">집에 설치된 카메라를 연결해요.</span></span></button>
          <button class="choice ${d.phoneCamera ? 'choice--on' : ''}" data-action="dev.phone"><span class="choice__ic">${ic('mobile-screen')}</span><span><span class="choice__t">내 폰 카메라 사용</span><span class="choice__s" style="display:block">${d.phoneCamera ? '내 폰 카메라로 감지하도록 설정했어요.' : '이 휴대전화의 카메라로 감지해요.'}</span></span></button>
        </div>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="flow.finish">${(d.devices.length || d.phoneCamera) ? '완료' : '나중에 연결할게요'}</button>`);
    });
    function devAddedHtml(d) {
      return d.devices.map((x, i) => `<div class="dev-added"><i class="fa-solid fa-${UI.DEVICE_ICON[x.type]} ic" aria-hidden="true"></i><span style="flex:1">${esc(UI.DEVICE_TYPE[x.type])} · ${esc(x.location)}<br><small class="muted">연결됨</small></span><button class="icon-btn" data-action="dev.rm" data-i="${i}" aria-label="삭제">${ic('xmark')}</button></div>`).join('');
    }
    on('dev.rm', el => { const d = D(); d.devices.splice(+el.dataset.i, 1); R.go(R.path()); });
    on('dev.phone', () => { const d = D(); d.phoneCamera = !d.phoneCamera; R.go(R.path()); });
    on('dev.add', () => {
      deviceSheet({ title: '카메라 추가', onSubmit: async (v, api) => {
        api.replace(`<div class="empty"><span class="spinner spinner--dark" style="width:30px;height:30px"></span><p style="margin-top:14px;font-weight:700;color:var(--ink)">${esc(UI.DEVICE_TYPE[v.type])} · ${esc(v.location)} 연결하는 중…</p></div>`);
        await new Promise(r => setTimeout(r, 1100));
        D().devices.push(v); closeSheet(); R.go(R.path());
      } });
    });
    on('flow.finish', () => finishFlow(flow));
  }

  /* 기기 추가 시트 (온보딩, 집 상세 등에서 공통 사용) */
  function deviceSheet(o) {
    let type = (o.value && o.value.type) || 'homecam';
    const locs = ['안방', '거실', '현관', '주방', '작은방'];
    const html = () => `
      <div class="label">기기 종류</div>
      <div class="segmented" style="margin-bottom:16px">
        <button type="button" class="${type === 'homecam' ? 'is-on' : ''}" data-action="ds.type" data-type="homecam">홈캠</button>
        <button type="button" class="${type === 'cctv' ? 'is-on' : ''}" data-action="ds.type" data-type="cctv">CCTV</button>
      </div>
      ${field({ id: 'ds-loc', label: '위치 이름', placeholder: '예) 안방, 거실', maxlength: 12, value: (document.getElementById('ds-loc') && document.getElementById('ds-loc').value) || (o.value && o.value.location) || '', onenter: 'ds.submit' })}
      <div class="chips" style="margin:-6px 0 18px">${locs.map(l => `<button type="button" class="chip" data-action="ds.loc" data-loc="${l}">${l}</button>`).join('')}</div>
      <button class="btn btn--primary btn--lg btn--block" data-action="ds.submit">${esc(o.submit || '연결하기')}</button>`;
    const api = openSheet({ title: o.title, html: html() });
    on('ds.type', el => { type = el.dataset.type; const v = val('ds-loc'); api.replace(html()); const i = document.getElementById('ds-loc'); i.value = v; });
    on('ds.loc', el => { document.getElementById('ds-loc').value = el.dataset.loc; });
    on('ds.submit', () => {
      const loc = val('ds-loc');
      if (!loc) { setError('ds-loc', '위치 이름을 입력해 주세요.'); return; }
      o.onSubmit({ type, location: loc }, api);
    });
  }

  /* 흐름 완료: 임시 입력값을 한 번에 저장 */
  function finishFlow(flow) {
    const d = D(); const me = Sel.me();
    const info = {};
    ['birth', 'conditions', 'medications'].forEach(k => { info[k] = d.info[k] === undefined ? null : d.info[k]; });
    Act.enableTarget(me.id, info);
    let homeId = d.homeId;
    if (d.homeMode === 'existing' && homeId) Act.linkHome(me.id, homeId);
    else homeId = Act.addHome(me.id, d.address || '');
    const patch = {}; let changed = [];
    if (d.central) { patch.centralPw = true; changed.push('중앙 현관 비밀번호'); }
    if (d.door) { patch.doorPw = true; changed.push('집 현관 비밀번호'); }
    if (Object.keys(patch).length) Act.updateHome(homeId, patch, me.id, changed.join('·') + '를 변경했어요');
    d.devices.forEach(x => Act.addDevice(homeId, x, me.id));
    Act.updateProfile(me.id, { phoneCamera: d.phoneCamera, onboarded: true });
    draft = null;
    toast(flow === 'enable' ? '낙상 감지를 켰어요' : '준비가 끝났어요', 'ok');
    R.go('/', { replace: true });
  }

  register('ob');
  register('enable');
  FD.Onboarding = { deviceSheet, resetDraft() { draft = null; }, startEnable() { draft = newDraft(); R.go('/enable/info'); } };
})();
