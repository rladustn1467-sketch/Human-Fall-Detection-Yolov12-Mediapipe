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
  const LIVE = FD.MODE === 'live';
  // 주소 검색을 쓸 수 없으면(api-live.js 의 addressSearch 가 false) 또는 사용자가 '직접 입력하기'를 고르면 직접 입력
  const manualAddress = () => FD.API.addressSearch === false || !!(draft && draft.addrManual);
  const NOT_READY_DEVICE = '카메라 연결은 지금 사용할 수 없어요.';

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
      <div class="hero-art"><i class="fa-solid fa-house-medical" aria-hidden="true"></i><p>일상 속 낙상 사고에<br>대비하세요.</p></div>
      <h1 class="ob__title">계정을 만들어 주세요</h1>
      <p class="ob__sub">사용하시는 분의 이름, 휴대전화 번호, 비밀번호를 입력해 주세요.</p>
      <form class="ob__form" id="signup-form" novalidate>
        ${field({ id: 'su-name', label: '이름', placeholder: '예) 홍길동', autocomplete: 'name', maxlength: 20 })}
        ${field({ id: 'su-phone', label: '휴대전화 번호', type: 'tel', inputmode: 'numeric', placeholder: '010-0000-0000', autocomplete: 'tel', oninput: 'phone-fmt' })}
        ${field({ id: 'su-pw', label: '비밀번호', type: 'password', autocomplete: 'new-password', maxlength: PW_MAX, hint: `${PW_MIN}자 이상, 영문과 숫자를 모두 넣어 주세요.` })}
        ${field({ id: 'su-pw2', label: '비밀번호 확인', type: 'password', autocomplete: 'new-password', maxlength: PW_MAX })}
        <label class="check"><input type="checkbox" id="su-agree"><span>서비스 이용약관과 개인정보 수집·이용에 동의해요.</span></label>
        <p class="field__error" id="su-agree-err" role="alert" hidden></p>
      </form>`,
      `<button class="btn btn--primary btn--lg btn--block" data-action="signup.submit">계속하기</button>
       <button class="btn btn--ghost btn--lg btn--block" data-action="go.login">이미 계정이 있어요 · 로그인</button>`);
    return html;
  });
  on('go.login', () => R.go('/ob/login'));
  on('go.signup', () => R.go('/ob/signup'));

  /* ---------------- 로그인 (휴대전화 번호 + 비밀번호) ---------------- */
  R.register('/ob/login', () => page(`
      <div class="brand" style="margin-top:22px"><span class="brand__mark">${ic('shield-heart')}</span>지킴이</div>
      <h1 class="ob__title">다시 오셨네요</h1>
      <p class="ob__sub">가입할 때 쓴 휴대전화 번호와 비밀번호를 입력해 주세요.</p>
      <form class="ob__form" id="login-form" novalidate>
        ${field({ id: 'lg-phone', label: '휴대전화 번호', type: 'tel', inputmode: 'numeric', placeholder: '010-0000-0000', autocomplete: 'tel', oninput: 'phone-fmt' })}
        ${field({ id: 'lg-pw', label: '비밀번호', type: 'password', autocomplete: 'current-password', maxlength: PW_MAX, onenter: 'login.submit' })}
      </form>
      <p style="text-align:center;margin-top:10px"><button type="button" class="btn btn--ghost" data-action="login.forgot">비밀번호를 잊으셨나요?</button></p>`,
    `<button class="btn btn--primary btn--lg btn--block" data-action="login.submit">로그인</button>
     <button class="btn btn--ghost btn--lg btn--block" data-action="go.signup">처음이에요 · 계정 만들기</button>`));
  // 비밀번호 재설정은 문자 인증 단계에서 제공 (지금은 안내만)
  on('login.forgot', () => toast('비밀번호 재설정은 지금 사용할 수 없어요.'));
  on('login.submit', async el => {
    const phone = val('lg-phone'), password = rawVal('lg-pw');
    let ok = true;
    setError('lg-phone', !UI.validPhone(phone) ? '휴대전화 번호를 정확히 입력해 주세요.' : ''); if (!UI.validPhone(phone)) ok = false;
    setError('lg-pw', password ? '' : '비밀번호를 입력해 주세요.'); if (!password) ok = false;
    if (!ok) return;
    try {
      await UI.busy(el, () => Act.signIn({ phone: UI.fmtPhone(phone), password }));
    } catch (e) { UI.showError(e, { phone: 'lg-phone', password: 'lg-pw' }); return; }
    toast('로그인했어요', 'ok');
    R.go('/', { replace: true });
  });
  UI.onInput('phone-fmt', t => { const d = t.value.replace(/\D/g, '').slice(0, 11); t.value = d.length > 7 ? `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}` : d.length > 3 ? `${d.slice(0, 3)}-${d.slice(3)}` : d; });
  on('signup.submit', async el => {
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
    // 비밀번호는 서버로만 보냄. 테스트 모드의 예시 저장소에는 저장하지 않음 (store.js createAccount 가 쓰지 않음)
    try {
      await UI.busy(el, () => Act.createAccount({ name, phone: UI.fmtPhone(phone), password }));
    } catch (e) { UI.showError(e, { name: 'su-name', phone: 'su-phone', password: 'su-pw' }); return; }
    R.go('/ob/group');
  });
  /* 가입 화면: 빨간 안내가 뜬 칸을 다시 입력하면 그 칸의 안내를 지움 (맞는지는 '계속하기'에서 다시 확인) */
  const SIGNUP_FIELDS = ['su-name', 'su-phone', 'su-pw', 'su-pw2'];
  document.addEventListener('input', e => {
    const id = e.target && e.target.id;
    if (!SIGNUP_FIELDS.includes(id)) return;
    setError(id, '');
    if (id === 'su-pw') setError('su-pw2', '');   // 비밀번호를 고치면 '서로 달라요' 안내도 지움
  });
  document.addEventListener('change', e => {
    if (!e.target || e.target.id !== 'su-agree' || !e.target.checked) return;
    const ae = document.getElementById('su-agree-err');
    if (ae) { ae.hidden = true; ae.textContent = ''; }
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
  on('group.create', async el => {
    const me = Sel.me();
    try {
      if (!me.groupId) await UI.busy(el, () => Act.createGroup(me.id));
    } catch (e) { UI.showError(e); return; }
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
  async function inviteMount(root) {
    const me = Sel.me();
    if (!me || !me.groupId) return;
    try {
      await Act.regenInvite(me.groupId, me.id);   // 초대할 때마다 새 코드 생성 (예전 코드는 쓸 수 없게 됨)
    } catch (e) { UI.showError(e); return; }
    const g = Sel.group(Sel.me().groupId);
    const card = root.querySelector('#invite-area');
    if (card && g && g.invite) { card.innerHTML = inviteBlock(g); UI.tick(card); }
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
  /* QR 인식: 브라우저 내장 인식기(BarcodeDetector)가 있으면 쓰고, 없으면 jsQR (버튼을 누를 때만 불러옴).
     카메라는 보안 연결(HTTPS 또는 localhost)에서만 쓸 수 있음. 읽은 초대 코드는 기존 '그룹 참여하기'로 넘겨
     서버가 확인함 (코드·만료·시도 횟수). 카메라는 닫기·인식·화면 이동·앱 숨김 때 반드시 끔 */
  const JSQR_URL = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js';
  const JSQR_SRI = 'sha384-b5Ya4Bq3qCyz39m2ISh+4DxjAIljdeFwK/BsXLuj9gugaNwAcj/ia15fxNZL9Nlx';   // 파일이 바뀌면 불러오지 않음
  const INVITE_CODE_RE = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{6}$/;   // 서버 초대 코드 규칙과 같음 (accounts.py)
  const SCAN_GIVE_UP_MS = 20000;
  const SCAN_MSG = {
    idle: 'QR코드를 사각형 안에 맞춰 주세요',
    insecure: '보안 연결(HTTPS)이 아니라서 카메라를 쓸 수 없어요. 아래에 초대 코드를 입력해 주세요.',
    unsupported: '이 브라우저에서는 카메라를 쓸 수 없어요. 아래에 초대 코드를 입력해 주세요.',
    nolib: 'QR 인식 기능을 불러오지 못했어요. 인터넷 연결을 확인하거나 아래에 초대 코드를 입력해 주세요.',
    denied: '카메라 권한이 거부됐어요. 브라우저 설정에서 카메라를 허용하거나 아래에 초대 코드를 입력해 주세요.',
    nocamera: '사용할 수 있는 카메라가 없어요. 아래에 초대 코드를 입력해 주세요.',
    busy: '다른 앱이 카메라를 쓰고 있어요. 그 앱을 닫고 다시 시도하거나 아래에 초대 코드를 입력해 주세요.',
    starting: '카메라를 켜는 중이에요',
    scanning: 'QR코드를 찾는 중이에요',
    notinvite: '초대 QR코드가 아니에요',   // 카메라 화면 위에 나오므로 한 줄로
    timeout: '20초 동안 QR코드를 찾지 못했어요. 다시 시도하거나 아래에 초대 코드를 입력해 주세요.',
    hidden: '화면을 벗어나서 카메라를 껐어요. 다시 인식하려면 버튼을 눌러 주세요.',
    found: 'QR코드를 읽었어요'   // 사각형 아래 한 줄 (참여 결과는 아래 칸·다음 화면에서)
  };
  const SCAN_ERRORS = ['insecure', 'unsupported', 'nolib', 'denied', 'nocamera', 'busy', 'timeout', 'hidden'];
  let scan = { state: 'idle', stream: null, timer: null, giveUp: null, run: 0 };

  /* QR 내용에서 초대 코드만 꺼냄: 초대 링크(…#/join?code=XXXXXX) 또는 코드 6자리. 규칙에 맞지 않으면 null */
  function inviteCodeFrom(raw) {
    const text = String(raw || '').trim();
    const m = /[?&#]code=([A-Za-z0-9]+)/.exec(text);
    const code = (m ? m[1] : text).toUpperCase();
    return INVITE_CODE_RE.test(code) ? code : null;
  }
  function scanUi() {   // 지금 상태를 화면에 반영 (화면을 다시 그려도 같은 상태로 복원)
    const box = document.getElementById('scanner'); if (!box) return;
    const video = document.getElementById('scan-video'), msg = document.getElementById('scan-msg');
    const close = document.getElementById('scan-close'), btn = document.querySelector('[data-action="join.scan"]');
    const live = !!scan.stream;
    if (live && video.srcObject !== scan.stream) { video.srcObject = scan.stream; video.play().catch(() => {}); }
    video.hidden = !live;                                   // 카메라가 실제로 켜졌을 때만 영상 표시
    close.hidden = !(live || scan.state === 'starting');
    msg.textContent = SCAN_MSG[scan.state] || SCAN_MSG.idle;
    box.classList.toggle('is-live', live);
    box.classList.toggle('is-error', SCAN_ERRORS.includes(scan.state) || scan.state === 'notinvite');
    if (btn) {
      const busy = live || scan.state === 'starting';
      btn.disabled = busy;
      btn.innerHTML = `${ic('camera')} ${busy ? '인식 중이에요' : SCAN_ERRORS.includes(scan.state) ? '다시 인식하기' : 'QR코드 인식하기'}`;
    }
  }
  function setScan(state) { scan.state = state; scanUi(); }
  function stopScan(state) {
    scan.run++;                                             // 진행 중인 인식 반복을 멈춤
    clearTimeout(scan.timer); clearTimeout(scan.giveUp);
    if (scan.stream) { scan.stream.getTracks().forEach(t => t.stop()); scan.stream = null; }
    const video = document.getElementById('scan-video'); if (video) video.srcObject = null;
    if (state) setScan(state); else scanUi();
  }
  function loadJsQR() {
    if (window.jsQR) return Promise.resolve(window.jsQR);
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = JSQR_URL; s.integrity = JSQR_SRI; s.crossOrigin = 'anonymous';
      s.onload = () => (window.jsQR ? resolve(window.jsQR) : reject(new Error('jsQR')));
      s.onerror = () => reject(new Error('jsQR'));
      document.head.appendChild(s);
    });
  }
  /* 내장 인식기가 실제로 읽는지 확인: 직접 만든 작은 QR 한 장을 읽혀 봄.
     (구글 서비스가 없는 기기 등은 '지원함'으로 나와도 아무것도 못 읽음 → 그때는 jsQR) */
  async function builtinWorks(det) {
    if (!window.qrcode) return false;
    const text = 'FD-QR-SELFTEST';
    const q = window.qrcode(0, 'M'); q.addData(text); q.make();
    const n = q.getModuleCount(), k = 6, m = 4;
    const c = document.createElement('canvas'); c.width = c.height = (n + 2 * m) * k;
    const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.fillStyle = '#000';
    for (let r = 0; r < n; r++) for (let cc = 0; cc < n; cc++) if (q.isDark(r, cc)) x.fillRect((cc + m) * k, (r + m) * k, k, k);
    try { return (await det.detect(c)).some(v => v.rawValue === text); } catch (e) { return false; }
  }
  /* 한 장면에서 QR 글자를 읽어 돌려줌 (없으면 null) */
  async function makeReader() {
    if ('BarcodeDetector' in window) {
      try {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (formats.includes('qr_code')) {
          const det = new window.BarcodeDetector({ formats: ['qr_code'] });
          if (await builtinWorks(det)) {
            return async video => { const r = await det.detect(video); return r.length ? r[0].rawValue : null; };
          }
        }
      } catch (e) { /* 아래 jsQR 사용 */ }
    }
    const jsQR = await loadJsQR();
    const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d', { willReadFrequently: true });
    return async video => {
      const w = video.videoWidth, h = video.videoHeight; if (!w || !h) return null;
      const k = Math.min(1, 640 / Math.max(w, h));          // 큰 영상은 줄여서 빠르게 읽음
      canvas.width = Math.round(w * k); canvas.height = Math.round(h * k);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const r = jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
      return r ? r.data : null;
    };
  }
  function cameraError(e) {
    const n = e && e.name;
    if (n === 'NotAllowedError' || n === 'SecurityError' || n === 'PermissionDeniedError') return 'denied';
    if (n === 'NotReadableError' || n === 'TrackStartError' || n === 'AbortError') return 'busy';
    return 'nocamera';   // NotFoundError, OverconstrainedError 등
  }
  async function startScan() {
    stopScan();
    if (!window.isSecureContext) { setScan('insecure'); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { setScan('unsupported'); return; }
    const run = ++scan.run;
    setScan('starting');
    let read;
    try { read = await makeReader(); } catch (e) { if (run === scan.run) setScan('nolib'); return; }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });   // 휴대폰은 후면 카메라 우선
    } catch (e) { if (run === scan.run) setScan(cameraError(e)); return; }
    if (run !== scan.run || R.path() !== '/ob/join') { stream.getTracks().forEach(t => t.stop()); return; }   // 그새 닫았거나 화면을 떠남
    scan.stream = stream;
    setScan('scanning');
    scan.giveUp = setTimeout(() => { if (run === scan.run) stopScan('timeout'); }, SCAN_GIVE_UP_MS);
    const tick = async () => {
      if (run !== scan.run) return;
      let raw = null;
      try { raw = await read(document.getElementById('scan-video')); } catch (e) { /* 다음 장면 */ }
      if (run !== scan.run) return;
      if (raw != null) {
        const code = inviteCodeFrom(raw);
        if (code) {
          stopScan('found');
          const input = document.getElementById('join-code'); input.value = code; setError('join-code', '');
          const b = document.querySelector('[data-action="join.submit"]'); if (b) b.click();   // 서버 확인은 기존 참여 절차 그대로
          return;
        }
        if (scan.state !== 'notinvite') setScan('notinvite');   // 다른 QR: 서버로 보내지 않고 계속 찾음
      }
      scan.timer = setTimeout(tick, 200);
    };
    tick();
  }
  // 다른 화면으로 가거나 앱을 숨기면 카메라를 끔
  window.addEventListener('hashchange', () => { if (R.path() !== '/ob/join') stopScan('idle'); });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && scan.stream) stopScan('hidden'); });

  R.register('/ob/join', () => {
    const preset = (R.query().get('code') || '').toUpperCase();
    return {
      html: page(`
        ${top(1, 3)}
        <h1 class="ob__title">초대받은 그룹에<br>참여해요</h1>
        <p class="ob__sub">가족의 QR코드를 인식하거나 초대 코드를 입력해 주세요.</p>
        <div class="scanner" id="scanner" style="margin-top:22px"><video id="scan-video" playsinline muted style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover" hidden></video>
          <div class="scanner__frame"></div><p id="scan-msg" aria-live="polite">${SCAN_MSG.idle}</p>
          <button type="button" class="scanner__close" id="scan-close" data-action="join.scan-close" aria-label="카메라 닫기" hidden>${ic('xmark')}</button></div>
        <button class="btn btn--soft btn--block" style="margin-top:12px" data-action="join.scan">${ic('camera')} QR코드 인식하기</button>
        <p class="group-label" style="justify-content:center;margin-top:22px">또는</p>
        <form id="join-form" novalidate>
          ${field({ id: 'join-code', label: '초대 코드', placeholder: '6자리 코드', maxlength: 8, value: preset, onenter: 'join.submit', oninput: 'upper' })}
        </form>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="join.submit">그룹 참여하기</button>`),
      mount: () => { scanUi(); }   // 화면을 다시 그려도 카메라·안내 상태 유지
    };
  });
  UI.onInput('upper', t => { t.value = t.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); });
  on('join.submit', async el => {
    const code = val('join-code');
    if (code.length < 4) { setError('join-code', '초대 코드를 입력해 주세요.'); return; }
    const me = Sel.me();
    // 그룹 참여에는 계정이 필요함 (초대 링크로 먼저 들어온 경우)
    if (!me) { toast('먼저 계정을 만들거나 로그인해 주세요.'); R.go('/ob/signup'); return; }
    let r;
    try {
      r = await UI.busy(el, () => Act.joinGroup(me.id, code));
    } catch (e) { UI.showError(e, { code: 'join-code' }); return; }
    if (!r.ok) { setError('join-code', r.reason); return; }
    stopScan();
    toast('그룹에 참여했어요', 'ok');
    R.go('/ob/ask');
  });
  on('join.scan', () => startScan());
  on('join.scan-close', () => stopScan('idle'));

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
  on('ask.no', async el => {
    try {
      await UI.busy(el, () => Act.updateProfile(Sel.me().id, { onboarded: true }));
    } catch (e) { UI.showError(e); return; }
    R.go('/', { replace: true });
  });

  /* ---------------- O-06 ~ O-09 (ob / enable 공통) ---------------- */
  function flowBase(flow) { return '/' + flow; }
  /* 버튼 처리기(on)는 이름마다 하나만 저장되어 register('ob')·register('enable') 중 나중 것이 남음.
     그래서 처리기 안에서는 지금 보고 있는 화면 주소로 흐름을 정함 (처음 설정 /ob/…, 감지 켜기 /enable/…) */
  const curFlow = () => (R.path().startsWith('/enable/') ? 'enable' : 'ob');
  const curBase = () => flowBase(curFlow());
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
            ${card('birth', '생년월일', UI.birthInput('info-birth', i.birth))}
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
      if (b && i.birth !== null) i.birth = b.value.trim() || undefined;   // 입력한 그대로 보관 (확인은 '다음'에서)
      ['conditions', 'medications'].forEach(k => {
        const el = document.getElementById('tags-' + k), none = document.getElementById('none-' + k);
        if (!el || i[k] === null) return;
        if (none && none.checked) i[k] = [];
        else { const t = el._ed ? el._ed.get() : []; i[k] = t.length ? t : undefined; }
      });
    }
    on('info.next', () => {
      collectInfo();
      const i = D().info;
      if (i.birth !== null && i.birth !== undefined) {   // 건너뛰지 않은 생년월일: 실제 있는 날짜인지 확인 후 'YYYY-MM-DD' 로
        const r = UI.checkBirth(i.birth);
        if (r.error) { setError('info-birth', r.error); document.getElementById('info-birth').focus(); return; }
        i.birth = r.value || undefined;
      }
      R.go(curBase() + '/address');
    });

    /* O-07 주소
       그룹에 이미 집이 있으면 먼저 '같은 집에 사시나요?'를 물음 (주소를 아직 입력하지 않은 집도 후보).
       같은 집이면 새 집을 만들지 않고 그 집에 연결. 다른 집을 고른 뒤에만 주소 입력·건너뛰기(새 집) */
    const groupHomes = () => { const me = Sel.me(); return me && me.groupId ? Sel.homes(me.groupId) : []; };
    R.register(base + '/address', () => {
      const d = D();
      const homes = groupHomes();
      const hasHomes = homes.length > 0 && d.homeMode !== 'new';
      return {
        html: page(`
          ${top(1, 4)}
          <p class="tag tag--primary">${STEP_NAMES[1]} · 2/4</p>
          <h1 class="ob__title" style="margin-top:10px">${hasHomes ? '같은 집에 사시나요?' : '사시는 곳의 주소를 입력해 주세요'}</h1>
          <div id="addr-body" style="margin-top:20px"></div>`,
          hasHomes ? '' : `<button class="btn btn--ghost btn--block" data-action="addr.skip">건너뛰기</button>`),
        mount: root => { drawAddr(root.querySelector('#addr-body'), homes, hasHomes); }
      };
    });
    function drawAddr(body, homes, hasHomes) {
      const d = D();
      if (hasHomes) {
        const me = Sel.me();
        body.innerHTML = `<p class="ob__sub" style="margin-top:0">가족이 등록한 집이 있어요.</p>
          <div class="stack" style="margin-top:14px">${homes.map(h => `
            <div class="card card--pad"><p style="font-weight:800;font-size:17px">${esc(h.address || Sel.homeName(h, me))}</p>
              <p class="row__sub">${h.address ? '이 주소와 같은 집에 사시나요?' : '아직 주소를 입력하지 않은 집이에요. 이 집에 함께 사시나요?'}</p>
              <button class="btn btn--primary btn--block" style="margin-top:12px" data-action="addr.same" data-id="${h.id}">네, 같아요</button></div>`).join('')}
          </div>
          <button class="btn btn--ghost btn--block" style="margin-top:12px" data-action="addr.other">아니요, 다른 집이에요</button>`;
        return;
      }
      if (manualAddress()) {
        body.innerHTML = `
          <div class="notice">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 정확한 주소를 입력해 주세요. (동·호수까지) 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
          <div style="margin-top:18px">
            ${field({ id: 'addr-base', label: '주소', placeholder: '예) 서울 마포구 월드컵로 100 한빛아파트', value: d.addrBase, maxlength: 150, autocomplete: 'street-address' })}
            ${field({ id: 'addr-detail', label: '동·호수', placeholder: '예) 101동 1203호', value: d.addrDetail, maxlength: 40, onenter: 'addr.next' })}
          </div>
          <button class="btn btn--primary btn--lg btn--block" style="margin-top:6px" data-action="addr.next">다음</button>
          ${FD.API.addressSearch !== false ? `<button class="link-btn" style="margin-top:12px" data-action="addr.searchmode">주소 검색하기</button>` : ''}
          ${homes.length ? `<button class="link-btn" style="margin-top:12px" data-action="addr.back-existing">가족이 등록한 집 중에서 고르기</button>` : ''}`;
        return;
      }
      const picked = d.addrBase;
      body.innerHTML = `
        <div class="notice">${ic('location-dot')}<span>119 신고가 필요할 때 이 주소가 전달돼요. 정확한 주소를 입력해 주세요. (동·호수까지) 입력한 주소는 그룹 가족에게 공유돼요.</span></div>
        <div style="margin-top:18px">
          ${picked ? `<div class="addr-picked">${ic('circle-check')}<span style="flex:1">${esc(picked)}</span><button class="link-btn" data-action="addr.change">변경</button></div>
            ${field({ id: 'addr-detail', label: '동·호수', placeholder: '예) 101동 1203호', value: d.addrDetail, onenter: 'addr.next' })}`
            : `<div class="inline-add"><input id="addr-q" type="search" placeholder="도로명, 건물명, 동 이름으로 검색" aria-label="주소 검색" data-onenter="addr.search" autocomplete="off"><button class="btn btn--primary" data-action="addr.search">${ic('magnifying-glass')} 검색</button></div>
               <div class="addr-list" id="addr-results"></div>
               ${LIVE ? `<button class="link-btn" style="margin-top:12px" data-action="addr.manual">검색이 안 되나요? 직접 입력하기</button>` : ''}`}
        </div>
        ${picked ? `<button class="btn btn--primary btn--lg btn--block" style="margin-top:6px" data-action="addr.next">다음</button>` : ''}
        ${homes.length ? `<button class="link-btn" style="margin-top:12px" data-action="addr.back-existing">가족이 등록한 집 중에서 고르기</button>` : ''}`;
    }
    let lastResults = [];
    on('addr.same', el => { const d = D(); d.homeMode = 'existing'; d.homeId = el.dataset.id; R.go(curBase() + '/password'); });
    // '다른 집'·'가족이 등록한 집 중에서 고르기'는 화면 전체를 다시 그림 (아래 건너뛰기 버튼이 다른 집일 때만 보이도록)
    on('addr.other', () => { const d = D(); d.homeMode = 'new'; d.homeId = null; d.addrBase = ''; R.go(R.path()); });
    on('addr.back-existing', () => { const d = D(); d.homeMode = null; d.homeId = null; R.go(R.path()); });
    on('addr.change', () => { const d = D(); d.addrBase = ''; drawAddr(document.getElementById('addr-body'), groupHomes(), false); });
    on('addr.search', async () => {
      const q = document.getElementById('addr-q').value;
      const box = document.getElementById('addr-results');
      try {
        lastResults = await FD.API.searchAddress(q);
      } catch (e) { UI.showError(e); return; }   // 검색어 문제·횟수 초과·검색 불가 안내
      box.innerHTML = lastResults.length
        ? lastResults.map((a, i) => `<button class="addr-item" data-action="addr.pick" data-i="${i}">${ic('location-dot')}<span>${esc(a)}</span></button>`).join('')
        : `<p class="empty" style="padding:18px">검색 결과가 없어요. 건물명이나 도로명을 다시 입력해 보세요.</p>`;
    });
    on('addr.manual', () => { const d = D(); d.addrManual = true; d.addrBase = ''; d.homeMode = 'new'; drawAddr(document.getElementById('addr-body'), groupHomes(), false); });
    on('addr.searchmode', () => { const d = D(); d.addrManual = false; d.addrBase = ''; drawAddr(document.getElementById('addr-body'), groupHomes(), false); });
    on('addr.pick', el => {
      const d = D(); d.addrBase = lastResults[+el.dataset.i]; d.homeMode = 'new';
      drawAddr(document.getElementById('addr-body'), groupHomes(), false);
      const i = document.getElementById('addr-detail'); if (i) i.focus();
    });
    on('addr.next', () => {
      const d = D(); const det = val('addr-detail');
      if (manualAddress()) {
        const b = val('addr-base');
        if (!b) { setError('addr-base', '주소를 입력해 주세요.'); return; }
        setError('addr-base', '');
        d.addrBase = b;
      }
      if (!det) { setError('addr-detail', '동·호수까지 입력해 주세요.'); return; }
      d.addrDetail = det; d.address = d.addrBase + ' ' + det; d.homeMode = 'new'; d.addrSkipped = false;
      R.go(curBase() + '/password');
    });
    on('addr.skip', async () => {
      const ok = await UI.confirm({ title: '주소를 나중에 입력할까요?', body: '주소가 없으면 119 신고 시 위치 전달이 어려울 수 있어요. 나중에 가족 탭의 집 관리에서 언제든 입력할 수 있어요.', ok: '건너뛰기', cancel: '계속 입력' });
      if (!ok) return;
      const d = D(); d.homeMode = 'new'; d.address = ''; d.addrBase = ''; d.addrSkipped = true;
      R.go(curBase() + '/password');
    });

    /* O-08 현관 출입 방식 · 비밀번호
       중앙 현관(비밀번호/열쇠/중앙현관 없음)과 집 현관(비밀번호/열쇠/잠금장치 없음)을 따로 고름. 비밀번호일 때만 입력칸.
       입력한 값은 이 흐름의 임시 보관(메모리)에만 두었다가 '완료' 때 서버로 보냄 (실제 모드는 서버가 암호화 저장).
       같은 집을 고른 가족: 지금 방식을 미리 선택. 등록된 비밀번호는 '그대로 사용'이 기본이라 덮어쓰지 않음 */
    function entranceDraft(d, h) {
      const key = d.homeMode === 'existing' ? d.homeId : 'new';
      if (d.entFor !== key) {   // 집을 바꿔 고르면 처음부터
        d.entFor = key; d.entSkipped = false; d.central = ''; d.door = ''; d.centralKeep = true; d.doorKeep = true;
        ['central', 'door'].forEach(k => { d[k + 'Method'] = h ? UI.entrance(h, k).method : null; });
      }
    }
    R.register(base + '/password', () => {
      const d = D();
      const h = d.homeMode === 'existing' ? Sel.home(d.homeId) : null;
      entranceDraft(d, h);
      const block = kind => {
        const now = UI.entrance(h, kind), m = d[kind + 'Method'];
        const seg = `<div class="segmented" style="margin:10px 0 12px">${now.options.map(([v, t]) => `<button type="button" class="${m === v ? 'is-on' : ''}" aria-pressed="${m === v}" data-action="obent.pick" data-kind="${kind}" data-m="${v}">${t}</button>`).join('')}</div>`;
        let inner = '';
        if (m === 'code' && now.registered) {   // 같은 집에 이미 등록된 비밀번호
          inner = d[kind + 'Keep']
            ? `<div class="pw-card__actions"><button class="btn btn--soft btn--sm" data-action="pw.keep" data-key="${kind}" aria-pressed="true">${ic('check')} 그대로 사용</button><button class="btn btn--ghost btn--sm" data-action="pw.change" data-key="${kind}">변경하기</button></div>`
            : `${field({ id: 'pw-' + kind + '-in', label: '현관 비밀번호', type: 'password', inputmode: 'tel', maxlength: 20, value: d[kind] })}<div class="pw-card__actions"><button class="btn btn--ghost btn--sm" data-action="pw.keep" data-key="${kind}">그대로 사용</button></div>`;
        } else if (m === 'code') {
          inner = field({ id: 'pw-' + kind + '-in', type: 'password', inputmode: 'tel', maxlength: 20, value: d[kind] });
        } else if (m && now.registered) {
          inner = `<div class="notice notice--stop">${ic('triangle-exclamation')}<span>완료하면 등록된 ${now.name} 비밀번호가 삭제돼요.</span></div>`;
        }
        return `<section class="pw-card" id="pw-${kind}"><div class="pw-card__head"><h3>${now.name}</h3>${m === 'code' && now.registered ? `<span class="tag tag--ok">${ic('lock')} 등록됨</span>` : ''}</div>${seg}${inner}</section>`;
      };
      return page(`
        ${top(2, 4)}
        <p class="tag tag--primary">${STEP_NAMES[2]} · 3/4</p>
        <h1 class="ob__title" style="margin-top:10px">현관 출입 방식을<br>알려 주세요</h1>
        <div class="notice notice--lock" style="margin-top:16px">${ic('lock')}<span>낙상 사고 시 119 구급대가 집에 들어갈 수 있도록 현관 출입 방식을 알려 주세요. 비밀번호는 암호화되어 저장되며, 119 신고가 접수될 때만 구급대에게 전달돼요. 비밀번호는 가족에게도 보이지 않아요.</span></div>
        <div style="margin-top:18px">${block('central')}${block('door')}</div>`,
        `<button class="btn btn--primary btn--lg btn--block" data-action="pw.next">다음</button>
         <button class="btn btn--ghost btn--block" data-action="pw.skip">건너뛰기</button>`);
    });
    function collectPw() {
      const d = D();
      ['central', 'door'].forEach(k => { const e = document.getElementById('pw-' + k + '-in'); if (e) d[k] = e.value; });
    }
    // 같은 화면을 다시 그릴 때 보던 위치 유지 (라우터는 화면을 그릴 때 맨 위로 올림)
    function redrawHere() { const y = window.scrollY; R.go(R.path()); window.scrollTo(0, y); }
    on('obent.pick', el => {
      collectPw(); const d = D(), k = el.dataset.kind;
      d[k + 'Method'] = el.dataset.m;
      if (el.dataset.m !== 'code') d[k] = '';   // 비밀번호가 아닌 방식이면 입력하던 값은 버림
      redrawHere();
    });
    on('pw.change', el => { collectPw(); D()[el.dataset.key + 'Keep'] = false; redrawHere(); });
    on('pw.keep', el => { collectPw(); const d = D(); d[el.dataset.key + 'Keep'] = true; d[el.dataset.key] = ''; redrawHere(); });
    on('pw.next', async () => {
      collectPw();
      const d = D(); let ok = true;
      ['central', 'door'].forEach(k => {   // 입력한 칸만 규칙 확인 (비워 두면 등록하지 않음)
        if (!document.getElementById('pw-' + k + '-in')) return;
        const problem = d[k] ? UI.doorCodeProblem(d[k]) : '';
        setError('pw-' + k + '-in', problem); if (problem) ok = false;
      });
      if (!ok) return;
      // 같은 집에 등록된 비밀번호를 다른 방식으로 바꾸면 확인을 받음 (그 현관의 비밀번호만 삭제됨)
      const h = d.homeMode === 'existing' ? Sel.home(d.homeId) : null;
      const losing = h ? ['central', 'door'].map(k => UI.entrance(h, k)).filter(e => e.registered && d[e.kind + 'Method'] !== 'code') : [];
      if (losing.length) {
        const names = losing.map(e => e.name).join('·');
        const yes = await UI.confirm({ title: `${names} 비밀번호를 삭제할까요?`, body: `출입 방식을 바꾸면 처음 설정을 완료할 때 등록된 ${names} 비밀번호가 삭제돼요. 다른 현관 정보는 그대로예요.`, ok: '계속', cancel: '취소', danger: true });
        if (!yes) return;
      }
      d.entSkipped = false;
      R.go(curBase() + '/device');
    });
    on('pw.skip', async () => {
      const ok = await UI.confirm({ title: '현관 정보를 나중에 알려 줄까요?', body: '비밀번호가 없으면 구급대가 출입하는 데 시간이 걸릴 수 있어요. 나중에 가족 탭의 집 관리에서 설정할 수 있어요.', ok: '건너뛰기', cancel: '계속 입력' });
      if (!ok) return;
      const d = D(); d.central = ''; d.door = ''; d.entSkipped = true;   // 건너뛰면 현관 정보는 아무것도 바꾸지 않음
      R.go(curBase() + '/device');
    });

    /* O-09 기기 연결 */
    R.register(base + '/device', () => {
      const d = D();
      return page(`
        ${top(3, 4)}
        <p class="tag tag--primary">${STEP_NAMES[3]} · 4/4</p>
        <h1 class="ob__title" style="margin-top:10px">감지할 카메라를<br>연결해 주세요</h1>
        <div class="notice" style="margin-top:16px">${ic('eye-slash')}<span>영상은 낙상 판단에만 쓰이고 저장되지 않아요. 낙상이 감지되면 배경과 사람을 가린 이미지만 기록돼요.</span></div>
        ${LIVE ? `<div class="notice" style="margin-top:10px">${ic('circle-info')}<span>${NOT_READY_DEVICE} '나중에 연결할게요'를 눌러 설정을 마쳐 주세요.</span></div>` : ''}
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
    on('dev.phone', () => {
      if (LIVE) { toast('내 폰 카메라 감지는 지금 사용할 수 없어요'); return; }
      const d = D(); d.phoneCamera = !d.phoneCamera; R.go(R.path());
    });
    on('dev.add', () => {
      if (LIVE) { toast(NOT_READY_DEVICE); return; }   // 연결된 척하지 않도록 시트를 열지 않음
      deviceSheet({ title: '카메라 추가', onSubmit: async (v, api) => {
        api.replace(`<div class="empty"><span class="spinner spinner--dark" style="width:30px;height:30px"></span><p style="margin-top:14px;font-weight:700;color:var(--ink)">${esc(UI.DEVICE_TYPE[v.type])} · ${esc(v.location)} 연결하는 중…</p></div>`);
        await new Promise(r => setTimeout(r, 1100));
        D().devices.push(v); closeSheet(); R.go(R.path());
      } });
    });
    on('flow.finish', el => finishFlow(curFlow(), el));
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

  /* 처음 설정에서 바뀐 현관 정보만 보냄: 고른 방식이 지금과 다르거나 비밀번호를 입력한 현관 (건너뛰기·'그대로 사용'은 보내지 않음) */
  function entrancesToSend(d) {
    if (d.entSkipped || d.entFor === undefined) return null;
    const h = d.homeMode === 'existing' ? Sel.home(d.homeId) : null;
    const out = {};
    ['central', 'door'].forEach(k => {
      const m = d[k + 'Method'], before = h ? UI.entrance(h, k).method : null, code = m === 'code' ? (d[k] || '') : '';
      if (m && (m !== before || code)) out[k] = { method: m, code: code || null };
    });
    return Object.keys(out).length ? out : null;
  }

  /* 흐름 완료: 임시 입력값을 한 번에 저장 */
  async function finishFlow(flow, el) {
    const d = D(); const me = Sel.me();
    const info = {};
    ['birth', 'conditions', 'medications'].forEach(k => { info[k] = d.info[k] === undefined ? null : d.info[k]; });
    if (LIVE) {
      // 서버가 건강 정보 + 집 + 현관 출입 방식·비밀번호를 한 트랜잭션으로 저장 (실패하면 아무것도 저장되지 않음). 기기는 아직 없음
      const home = d.homeMode === 'existing' && d.homeId ? { mode: 'existing', id: d.homeId } : { mode: 'new', address: d.address || '' };
      const entrances = entrancesToSend(d);
      try {
        await UI.busy(el, () => Act.finishSetup({ info, home, entrances }));
      } catch (e) { UI.showError(e); return; }
      draft = null;
      toast(flow === 'enable' ? '낙상 감지 대상으로 등록했어요' : '준비가 끝났어요', 'ok');
      R.go('/', { replace: true });
      return;
    }
    Act.enableTarget(me.id, info);
    let homeId = d.homeId;
    if (d.homeMode === 'existing' && homeId) Act.linkHome(me.id, homeId);
    else homeId = Act.addHome(me.id, d.address || '');
    const entrances = entrancesToSend(d) || {};
    Object.keys(entrances).forEach(k => Act.setEntrance(homeId, k, entrances[k].method, entrances[k].code, me.id));
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
