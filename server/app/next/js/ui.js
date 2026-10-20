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
  const validPhone = v => /^01\d[-\s]?\d{3,4}[-\s]?\d{4}$/.test(String(v || '').trim());
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
    DEVICE_TYPE, DEVICE_ICON, STATUS_LABEL, RESULT_LABEL, RESPONSE_LABEL, deviceName, ic, avatar, maskPhoto, qr,
    tagEditor, refreshSheet, on, onInput, tick, toast, openSheet, closeSheet, confirm: confirmBox, field, setError, val, toggle, subHeader, copy, lockBody
  };
})();
