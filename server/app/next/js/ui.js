/* ------------------------------------------------------------------
 * ui.js — 공통 UI 도구: 포맷터, 아이콘, 시트/확인창/토스트, 이벤트 위임, 타이머 텍스트 갱신
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const S = 1000, M = 60000, H = 3600000, D = 86400000;
  const WD = ['일', '월', '화', '수', '목', '금', '토'];

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pad = n => String(n).padStart(2, '0');
  const nowTs = () => (FD.Store ? FD.Store.now() : Date.now());

  /* ---------- 시간 포맷 ---------- */
  function mmss(ms) { const s = Math.max(0, Math.ceil(ms / 1000)); return pad(Math.floor(s / 60)) + ':' + pad(s % 60); }
  function elapsed(ms) { const s = Math.max(0, Math.floor(ms / 1000)); const m = Math.floor(s / 60); return m > 0 ? `${m}분 ${s % 60}초` : `${s}초`; }
  function ago(ms) {
    if (ms < 60 * S) return '방금';
    if (ms < H) return Math.floor(ms / M) + '분 전';
    if (ms < D) return Math.floor(ms / H) + '시간 전';
    return Math.floor(ms / D) + '일 전';
  }
  function clock(ts) { const d = new Date(ts); const h = d.getHours(); return `${h < 12 ? '오전' : '오후'} ${h % 12 || 12}:${pad(d.getMinutes())}`; }
  function hm24(ts) { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  function dateLabel(ts) {
    const n = new Date(nowTs()), d = new Date(ts);
    const dn = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
    const dd = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diff = Math.round((dn - dd) / D);
    if (diff === 0) return '오늘';
    if (diff === 1) return '어제';
    return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WD[d.getDay()]})`;
  }
  function dateTime(ts) { return `${dateLabel(ts)} ${clock(ts)}`; }
  function secLabel(ms) { const s = Math.round(ms / 1000); return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분 ${s % 60}초`; }
  function age(birth) {
    if (!birth) return null;
    const b = new Date(birth), n = new Date(nowTs());
    let a = n.getFullYear() - b.getFullYear();
    if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) a--;
    return a;
  }
  function birthLabel(birth) {
    if (!birth) return '미등록';
    const [y, m, d] = birth.split('-');
    return `${y}년 ${+m}월 ${+d}일 (만 ${age(birth)}세)`;
  }
  function listLabel(arr) { if (arr == null) return '미등록'; if (!arr.length) return '없음'; return arr.join(', '); }
  function fmtPhone(v) {
    const d = String(v || '').replace(/\D/g, '');
    if (d.length === 11) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
    if (d.length === 10) return `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}`;
    return v;
  }
  /* ---------- 생년월일: 숫자 8자리(YYYYMMDD) 입력 → 다 입력하면 1999-01-01 로 표시 ----------
     저장 형식은 그대로 'YYYY-MM-DD' (서버도 같은 범위 1900-01-01 ~ 오늘을 다시 확인) */
  const BIRTH_MIN = '1900-01-01';
  const BIRTH_HINT = '숫자 8자리로 입력해 주세요 (예: 19990101)';
  const birthDigits = v => String(v || '').replace(/\D/g, '').slice(0, 8);
  const birthText = d => (d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : d);
  /* { value: 'YYYY-MM-DD' 또는 null(빈 값), error: '' 또는 안내 문구 } */
  function checkBirth(text) {
    const raw = String(text || '').trim();
    if (!raw) return { value: null, error: '' };
    const d = raw.replace(/\D/g, '');
    if (d.length !== 8) return { value: null, error: '생년월일 8자리를 모두 입력해 주세요. (예: 19990101)' };
    const y = +d.slice(0, 4), m = +d.slice(4, 6), day = +d.slice(6);
    const dt = new Date(y, m - 1, day);
    if (m < 1 || m > 12 || dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== day) {
      return { value: null, error: '없는 날짜예요. 년·월·일을 다시 확인해 주세요.' };
    }
    const iso = birthText(d);
    const n = new Date();
    const today = `${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`;
    if (iso < BIRTH_MIN) return { value: null, error: '1900년 1월 1일 이후 날짜로 입력해 주세요.' };
    if (iso > today) return { value: null, error: '오늘 이후 날짜는 입력할 수 없어요.' };
    return { value: iso, error: '' };
  }
  function birthInput(id, value) {
    return `<input id="${id}" type="text" class="birth-input" inputmode="numeric" pattern="[0-9]*" maxlength="10" autocomplete="bday"
        placeholder="예) 19990101" aria-label="생년월일 (숫자 8자리)" value="${esc(value || '')}" data-oninput="birth-fmt">
      <p class="field__hint">${BIRTH_HINT}</p>
      <p class="field__error" id="${id}-err" role="alert" hidden></p>`;
  }
  const validPhone = v => /^01\d[-\s]?\d{3,4}[-\s]?\d{4}$/.test(String(v || '').trim());
  /* 현관 비밀번호 규칙: 숫자, *, # 만 3~20자 (서버 door_codes.py 와 같음). 맞으면 '', 아니면 안내 문구 */
  const DOOR_CODE_RULE = '현관 비밀번호는 숫자와 *, # 만 써서 3~20자로 입력해 주세요.';
  const doorCodeProblem = v => (/^[0-9*#]{3,20}$/.test(String(v == null ? '' : v)) ? '' : DOOR_CODE_RULE);
  /* 현관 출입 방식 (서버 door_codes.py 와 같은 값). 중앙현관 없음 = 'absent', 집 현관 잠금장치 없음 = 'unlocked' */
  const ENTRANCES = {
    central: { name: '중앙 현관', pwKey: 'centralPw', accessKey: 'centralAccess', options: [['code', '비밀번호'], ['key', '열쇠'], ['absent', '중앙현관 없음']] },
    door: { name: '집 현관', pwKey: 'doorPw', accessKey: 'doorAccess', options: [['code', '비밀번호'], ['key', '열쇠'], ['unlocked', '잠금장치 없음']] }
  };
  /* 집의 한 현관 정보: { method(null=미설정), registered, label, icon, needsInput } — 값(비밀번호)은 없음 */
  function entrance(h, kind) {
    const e = ENTRANCES[kind], reg = !!(h && h[e.pwKey]);
    let method = h ? h[e.accessKey] : null;
    if (method === undefined) method = reg ? 'code' : null;   // 테스트 모드 예시 데이터: 등록돼 있으면 비밀번호 방식
    const registered = method === 'code' && reg;
    const optLabel = (e.options.find(o => o[0] === method) || [])[1];
    const label = !method ? '미설정' : method === 'code' ? `비밀번호 · ${registered ? '등록됨' : '미등록'}` : optLabel;
    const icon = !method ? 'circle-question' : method === 'code' ? (registered ? 'lock' : 'lock-open') : method === 'key' ? 'key' : 'door-open';
    return { kind, name: e.name, pwKey: e.pwKey, options: e.options, method, registered, label, icon,
      needsInput: !method || (method === 'code' && !registered) };   // 할 일·'입력 필요'는 미설정·비밀번호 미등록일 때만
  }
  const validEmail = v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || '').trim());

  /* ---------- 라벨 ---------- */
  const DEVICE_TYPE = { homecam: '홈캠', cctv: 'CCTV' };
  const DEVICE_ICON = { homecam: 'video', cctv: 'camera' };
  const STATUS_LABEL = { ok: '정상', disconnected: '연결 안 됨', off: '꺼짐' };
  const RESULT_LABEL = { self: '본인 응답', family: '가족 확인', reported: '신고됨', auto_reported: '자동 신고됨' };
  const RESPONSE_LABEL = { within60: '60초 내 응답', after60: '60초 후 응답', none: '무응답으로 가족 알림' };
  const deviceName = d => `${DEVICE_TYPE[d.type] || '기기'} · ${d.location}`;
  const ic = (name, cls) => `<i class="fa-solid fa-${name}${cls ? ' ' + cls : ''}" aria-hidden="true"></i>`;

  /* ---------- 아바타 ---------- */
  const AV = ['#2F7F86', '#C26A4A', '#6A7FB5', '#8A6BA8', '#4E8F5E', '#B08A2E'];
  function avatar(p, size) {
    if (!p) return '';
    let n = 0; for (const c of p.id) n += c.charCodeAt(0);
    return `<span class="avatar${size ? ' avatar--' + size : ''}" style="background:${AV[n % AV.length]}" aria-hidden="true">${esc(p.name.slice(0, 1))}</span>`;
  }

  /* ---------- 가려진 낙상 이미지 (배경 블러 + 사람 실루엣) ---------- */
  function maskPhoto(key, opts) {
    opts = opts || {};
    const k = String(key || '');
    let n = 0; for (const c of k) n += c.charCodeAt(0);
    const themes = [
      ['#d9c8ad', '#b8a284', '#8b9aa6'],
      ['#c6d1c8', '#9fb3a8', '#c9b79b'],
      ['#cdc3d6', '#a79bb8', '#b9b09c'],
      ['#d6c3c0', '#b79c97', '#98a8b6']
    ];
    const t = themes[n % themes.length];
    const flip = n % 2 ? ' mask-photo--flip' : '';
    return `<figure class="mask-photo${flip}${opts.small ? ' mask-photo--sm' : ''}" aria-label="배경과 사람을 가린 낙상 감지 이미지">
      <div class="mask-photo__bg" style="--c1:${t[0]};--c2:${t[1]};--c3:${t[2]}"><i></i><i></i><i></i></div>
      <svg class="mask-photo__fig" viewBox="0 0 240 120" aria-hidden="true">
        <ellipse cx="120" cy="104" rx="84" ry="7" fill="rgba(20,30,38,.18)"/>
        <g fill="rgba(24,34,42,.9)">
          <circle cx="58" cy="84" r="13"/>
          <rect x="68" y="76" width="92" height="22" rx="11" transform="rotate(-3 68 76)"/>
          <rect x="150" y="82" width="52" height="12" rx="6" transform="rotate(12 150 82)"/>
          <rect x="146" y="92" width="48" height="11" rx="5.5" transform="rotate(-8 146 92)"/>
          <rect x="74" y="64" width="38" height="11" rx="5.5" transform="rotate(-28 74 64)"/>
        </g>
      </svg>
      <figcaption class="mask-photo__tag">${ic('eye-slash')} 배경·인물 가림 처리</figcaption>
    </figure>`;
  }

  /* ---------- 사고 사진 ----------
     실제 모드: 감지 기기가 가공해 보낸 실루엣 사진만 보여줌 (서버가 같은 그룹에만 줌). 없으면 '사진 없음'.
     그려 넣은 예시 그림(maskPhoto)은 테스트 모드에서만 씀. opts.all = 연결된 사진을 모두 (이력 상세) */
  function incidentPhoto(inc, opts) {
    opts = opts || {};
    if (FD.MODE !== 'live') return maskPhoto(inc.id);
    const photos = inc.photos || [];
    if (!photos.length) {
      return `<figure class="mask-photo mask-photo--none"><span>${ic('image')} 이 낙상에는 사진이 없어요</span></figure>`;
    }
    const one = p => `<figure class="mask-photo mask-photo--real">
      <img src="/api/v2/incidents/${encodeURIComponent(inc.id)}/photos/${encodeURIComponent(p.id)}.jpg" alt="배경과 사람을 가린 낙상 감지 사진" loading="lazy">
      <figcaption class="mask-photo__tag">${ic('eye-slash')} 배경·인물 가림 처리${opts.all && photos.length > 1 ? ` · ${clock(p.at)}:${pad(new Date(p.at).getSeconds())}` : ''}</figcaption>
    </figure>`;
    return opts.all ? `<div class="photo-list">${photos.map(one).join('')}</div>` : one(photos[0]);
  }

  /* ---------- QR ---------- */
  function qr(text, size) {
    try {
      if (window.qrcode) {
        const q = window.qrcode(0, 'M'); q.addData(text); q.make();
        const n = q.getModuleCount();
        let d = '';
        for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c},${r}h1v1h-1z`;
        const svg = `<svg viewBox="0 0 ${n} ${n}" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg"><path d="${d}" fill="#14282D"/></svg>`;
        return `<div class="qr" role="img" aria-label="초대 QR 코드" style="width:${size || 176}px;height:${size || 176}px">${svg}</div>`;
      }
    } catch (e) { console.error(e); }
    return `<div class="qr qr--none" style="width:${size || 176}px;height:${size || 176}px">${ic('qrcode')}</div>`;
  }

  /* ---------- 이벤트 위임 ---------- */
  const actions = {};
  function on(name, fn) { actions[name] = fn; }
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-action]');
    if (!el || el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    const fn = actions[el.dataset.action];
    if (fn) fn(el, e);
  });
  document.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[role="button"][data-action]')) {
      e.preventDefault(); e.target.click();
    }
    if (e.key === 'Escape') closeSheet();
  });
  const inputActions = {};
  function onInput(name, fn) { inputActions[name] = fn; }
  document.addEventListener('input', e => { const t = e.target; if (t.dataset && t.dataset.oninput && inputActions[t.dataset.oninput]) inputActions[t.dataset.oninput](t, e); });
  /* 생년월일 입력: 숫자만 남기고, 8자리가 되면 1999-01-01 로 바꿈. 커서는 '앞에 있던 숫자 개수' 기준으로 되돌려
     중간 수정·붙여넣기에도 튀지 않게 함. 1999-01-01 상태에서 '-' 바로 뒤를 지우면 그 앞 숫자를 지움 */
  onInput('birth-fmt', (t, e) => {
    const old = t.value;
    const caret = t.selectionStart == null ? old.length : t.selectionStart;
    let before = old.slice(0, caret).replace(/\D/g, '').length;
    let d = old.replace(/\D/g, '');
    const prev = t._birthDigits != null ? t._birthDigits : birthDigits(t.defaultValue);   // 처음 수정이면 화면에 있던 값 기준
    if (e && e.inputType === 'deleteContentBackward' && d === prev && before > 0) {
      d = d.slice(0, before - 1) + d.slice(before); before -= 1;
    }
    d = d.slice(0, 8);
    before = Math.min(before, d.length);
    const next = birthText(d);
    if (next !== old) {
      t.value = next;
      let pos = 0, seen = 0;
      while (pos < next.length && seen < before) { if (/\d/.test(next[pos])) seen++; pos++; }
      try { t.setSelectionRange(pos, pos); } catch (err) { /* 일부 브라우저 */ }
    }
    t._birthDigits = d;
    setError(t.id, d.length === 8 ? checkBirth(next).error : '');   // 다 입력했을 때만 검증, 입력 중에는 안내 숨김
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const t = e.target;
    if (t.dataset && t.dataset.onenter && actions[t.dataset.onenter]) { e.preventDefault(); actions[t.dataset.onenter](t, e); }
  });

  /* ---------- 카운트다운 / 경과 텍스트 갱신 ---------- */
  function tick(root) {
    root = root || document;
    const t = nowTs();
    root.querySelectorAll('[data-cd]').forEach(e => { e.textContent = mmss(+e.dataset.cd - t); });
    root.querySelectorAll('[data-secs]').forEach(e => { e.textContent = Math.max(0, Math.ceil((+e.dataset.secs - t) / 1000)); });
    root.querySelectorAll('[data-el]').forEach(e => { e.textContent = elapsed(t - +e.dataset.el) + (e.dataset.suf || ''); });
    root.querySelectorAll('[data-ago]').forEach(e => { e.textContent = ago(t - +e.dataset.ago) + (e.dataset.suf || ''); });
    root.querySelectorAll('[data-min]').forEach(e => {
      const m = Math.floor((t - +e.dataset.min) / M);
      e.textContent = m < 1 ? '1분 미만 경과' : `${m}분 경과`;
    });
    root.querySelectorAll('[data-left]').forEach(e => {
      const ms = +e.dataset.left - t;
      if (ms <= 0) { e.textContent = '만료됐어요'; return; }
      const h = Math.floor(ms / H), m = Math.floor((ms % H) / M);
      e.textContent = (h > 0 ? `${h}시간 ` : '') + `${m}분 남음`;
    });
    root.querySelectorAll('[data-bar]').forEach(e => {
      const [a, b] = e.dataset.bar.split(',').map(Number);
      e.style.width = (Math.min(1, Math.max(0, (b - t) / (b - a))) * 100) + '%';
    });
    root.querySelectorAll('[data-ring]').forEach(e => {
      const [a, b] = e.dataset.ring.split(',').map(Number);
      const frac = Math.min(1, Math.max(0, (b - t) / (b - a)));
      const r = +e.getAttribute('r'); const c = 2 * Math.PI * r;
      e.style.strokeDasharray = c; e.style.strokeDashoffset = c * (1 - frac);
    });
  }

  /* ---------- 토스트 ---------- */
  let toastTimer = null;
  function toast(msg, kind) {
    const root = document.getElementById('toast-root'); if (!root) return;
    root.innerHTML = `<div class="toast${kind ? ' toast--' + kind : ''}" role="status">${esc(msg)}</div>`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { root.innerHTML = ''; }, 2600);
  }

  /* ---------- 바텀시트 ---------- */
  let sheetEl = null, sheetClose = null, sheetRefresh = null;
  function refreshSheet() { if (sheetEl && sheetRefresh) sheetRefresh(); }
  function lockBody(on) { document.body.classList.toggle('is-locked', on || !!document.querySelector('.ov')); }
  function openSheet(o) {
    closeSheet(true);
    const root = document.getElementById('sheet-root');
    const w = document.createElement('div');
    w.className = 'sheet-wrap' + (o.top ? ' sheet-wrap--top' : '');
    w.innerHTML = `<div class="sheet-scrim" data-action="sheet.close"></div>
      <div class="sheet${o.center ? ' sheet--center' : ''}" role="dialog" aria-modal="true" aria-label="${esc(o.title || '')}">
        <div class="sheet__grab" aria-hidden="true"></div>
        ${o.title ? `<header class="sheet__head"><h2>${esc(o.title)}</h2><button class="icon-btn" data-action="sheet.close" aria-label="닫기">${ic('xmark')}</button></header>` : ''}
        <div class="sheet__body">${o.html || ''}</div>
      </div>`;
    root.appendChild(w);
    sheetEl = w; sheetClose = o.onClose || null;
    const api = {
      el: w,
      body: () => w.querySelector('.sheet__body'),
      replace(html, mount) { const b = w.querySelector('.sheet__body'); b.innerHTML = html; if (mount) mount(b); },
      close: () => closeSheet()
    };
    sheetRefresh = o.refresh ? () => o.refresh(api) : null;
    requestAnimationFrame(() => w.classList.add('is-open'));
    lockBody(true);
    if (o.onMount) o.onMount(w.querySelector('.sheet__body'), api);
    return api;
  }
  function closeSheet(silent) {
    if (!sheetEl) return;
    const el = sheetEl, cb = sheetClose;
    sheetEl = null; sheetClose = null; sheetRefresh = null;
    el.classList.remove('is-open');
    setTimeout(() => el.remove(), silent ? 0 : 180);
    if (silent) el.remove();
    lockBody(false);
    if (cb && !silent) cb();
  }
  on('sheet.close', () => closeSheet());

  /* 확인 창 → Promise<boolean>. 다른 시트 위에 별도로 쌓이며, 기존 시트는 닫지 않음 */
  function confirmBox(o) {
    return new Promise(resolve => {
      const root = document.getElementById('sheet-root');
      const w = document.createElement('div');
      w.className = 'sheet-wrap sheet-wrap--top';
      w.innerHTML = `<div class="sheet-scrim" data-action="confirm.no"></div>
        <div class="sheet sheet--center" role="alertdialog" aria-modal="true" aria-label="${esc(o.title || '')}">
          <div class="sheet__grab" aria-hidden="true"></div>
          <header class="sheet__head"><h2>${esc(o.title || '')}</h2></header>
          <div class="sheet__body">${o.body ? `<p class="confirm__body">${esc(o.body)}</p>` : ''}
            <div class="confirm__actions">
              ${o.cancel === false ? '' : `<button class="btn btn--ghost btn--block" data-action="confirm.no">${esc(o.cancel || '취소')}</button>`}
              <button class="btn ${o.danger ? 'btn--danger' : 'btn--primary'} btn--block" data-action="confirm.yes">${esc(o.ok || '확인')}</button>
            </div></div></div>`;
      root.appendChild(w);
      requestAnimationFrame(() => w.classList.add('is-open'));
      let done = false;
      const finish = v => { if (done) return; done = true; w.classList.remove('is-open'); setTimeout(() => w.remove(), 180); resolve(v); };
      on('confirm.yes', () => finish(true));
      on('confirm.no', () => finish(false));
    });
  }

  /* ---------- 폼 조각 ---------- */
  function field(o) {
    return `<div class="field">
      ${o.label ? `<label for="${o.id}">${esc(o.label)}</label>` : ''}
      <input id="${o.id}" name="${o.id}" type="${o.type || 'text'}" ${o.inputmode ? `inputmode="${o.inputmode}"` : ''} ${o.maxlength ? `maxlength="${o.maxlength}"` : ''}
        ${o.autocomplete ? `autocomplete="${o.autocomplete}"` : 'autocomplete="off"'} placeholder="${esc(o.placeholder || '')}" value="${esc(o.value || '')}" ${o.oninput ? `data-oninput="${o.oninput}"` : ''} ${o.onenter ? `data-onenter="${o.onenter}"` : ''}>
      ${o.hint ? `<p class="field__hint">${o.hint}</p>` : ''}
      <p class="field__error" id="${o.id}-err" role="alert" hidden></p>
    </div>`;
  }
  function setError(id, msg) {
    const e = document.getElementById(id + '-err'), i = document.getElementById(id);
    if (e) { e.textContent = msg || ''; e.hidden = !msg; }
    if (i) i.classList.toggle('is-invalid', !!msg);
  }
  const val = id => { const e = document.getElementById(id); return e ? e.value.trim() : ''; };
  /* 서버 오류 표시 (실제 모드). fields: 서버의 칸 이름 → 화면 입력 칸 id (예: { phone: 'su-phone' }).
     맞는 칸이 있으면 그 칸 아래에, 없으면 안내창으로. '준비 중' 오류는 이미 안내했으므로 그냥 넘어감 */
  function showError(err, fields) {
    if (FD.NotReadyError && err instanceof FD.NotReadyError) return;
    if (FD.ApiError && err instanceof FD.ApiError) {
      const id = fields && err.field ? fields[err.field] : null;
      if (id && document.getElementById(id)) setError(id, err.message); else toast(err.message);
      return;
    }
    console.error(err);
    toast('문제가 생겼어요. 잠시 후 다시 시도해 주세요.');
  }
  /* 버튼을 누른 뒤 서버 응답이 올 때까지 같은 버튼을 다시 누를 수 없게 함 */
  async function busy(el, fn) {
    if (el) el.disabled = true;
    try { return await fn(); } finally { if (el) el.disabled = false; }
  }
  function toggle(on, action, extra) {
    return `<button type="button" class="switch${on ? ' is-on' : ''}" role="switch" aria-checked="${on ? 'true' : 'false'}" data-action="${action}" ${extra || ''}><span></span></button>`;
  }

  /* ---------- 페이지 헤더 ---------- */
  function subHeader(title, o) {
    o = o || {};
    return `<header class="sub-head">
      <button class="icon-btn" data-action="nav.back" aria-label="뒤로">${ic('chevron-left')}</button>
      <h1>${esc(title)}</h1>
      <div class="sub-head__right">${o.right || ''}</div>
    </header>`;
  }
  on('nav.back', () => FD.Router.back());

  /* ---------- 태그 입력 (지병·복용약) ---------- */
  function tagEditor(el, o) {
    let tags = (o.value || []).slice();
    const sugg = o.suggestions || [];
    function draw() {
      const custom = tags.filter(t => !sugg.includes(t));
      el.innerHTML = `<div class="chips">` +
        sugg.map(s => `<button type="button" class="chip${tags.includes(s) ? ' is-on' : ''}" data-t="${esc(s)}">${ic(tags.includes(s) ? 'check' : 'plus')} ${esc(s)}</button>`).join('') +
        custom.map(s => `<button type="button" class="chip is-on" data-t="${esc(s)}" aria-label="${esc(s)} 삭제">${esc(s)} ${ic('xmark')}</button>`).join('') +
        `</div><div class="inline-add"><input type="text" placeholder="${esc(o.placeholder || '직접 입력')}" aria-label="${esc(o.placeholder || '직접 입력')}" maxlength="30"><button type="button" class="btn btn--soft btn--sm" data-add>추가</button></div>`;
      el.querySelectorAll('[data-t]').forEach(b => b.addEventListener('click', () => {
        const t = b.dataset.t; tags = tags.includes(t) ? tags.filter(x => x !== t) : tags.concat(t); draw();
      }));
      const inp = el.querySelector('input');
      const add = () => { const v = inp.value.trim(); if (v && !tags.includes(v)) { tags.push(v); draw(); el.querySelector('input').focus(); } };
      el.querySelector('[data-add]').addEventListener('click', add);
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); add(); } });
    }
    draw();
    return { get: () => tags.slice() };
  }

  /* 복사 */
  async function copy(text, msg) {
    try { await navigator.clipboard.writeText(text); } catch (e) {
      const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select();
      try { document.execCommand('copy'); } catch (err) { /* noop */ }
      t.remove();
    }
    toast(msg || '복사했어요');
  }

  const addr = h => (h && h.address) ? h.address : '주소 미등록';
  const pwLabel = v => v ? '등록됨' : '미등록';
  const SUGGEST_COND = ['고혈압', '당뇨', '심장질환', '골다공증', '관절염', '치매'];
  const SUGGEST_MED = ['혈압약', '당뇨약', '혈전용해제', '골다공증약'];

  FD.UI = {
    addr, pwLabel, SUGGEST_COND, SUGGEST_MED,
    esc, pad, mmss, elapsed, ago, clock, hm24, dateLabel, dateTime, secLabel, age, birthLabel, listLabel, fmtPhone, validPhone, validEmail,
    checkBirth, birthInput, doorCodeProblem, entrance,
    DEVICE_TYPE, DEVICE_ICON, STATUS_LABEL, RESULT_LABEL, RESPONSE_LABEL, deviceName, ic, avatar, maskPhoto, incidentPhoto, qr,
    tagEditor, refreshSheet, on, onInput, tick, toast, openSheet, closeSheet, confirm: confirmBox, field, setError, val, toggle, subHeader, copy, lockBody,
    showError, busy
  };
})();
