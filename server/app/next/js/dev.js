/* 개발 확인 콘솔 — 낙상 이벤트 발생 / 사용자 전환 / 타이머 배속 / 동시 보기 */
(async function () {
  const FD = window.FD, { Store } = FD, { Sel, Act } = Store;
  await Store.init();
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const pad = n => String(n).padStart(2, '0');
  const fmt = ts => { const d = new Date(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const mmss = ms => { const s = Math.max(0, Math.round(ms / 1000)); return pad(Math.floor(s / 60)) + ':' + pad(s % 60); };
  const framesOn = new Set(['u1', 'u3', 'u4']);

  function homes() { return Store.state.homes; }
  function drawFall() {
    const hs = $('f-home'), prev = hs.value;
    hs.innerHTML = homes().map(h => {
      const names = Sel.targets(h.id).map(p => p.name).join('·') || '대상자 없음';
      return `<option value="${h.id}">${esc(names)} 댁 · ${esc(h.address || '주소 없음')}</option>`;
    }).join('');
    if (prev && homes().some(h => h.id === prev)) hs.value = prev;
    drawLoc();
  }
  function drawLoc() {
    const hid = $('f-home').value;
    const locs = Sel.devices(hid).map(d => d.location);
    const uniq = [...new Set(locs.length ? locs : ['거실'])];
    $('f-loc').innerHTML = uniq.map(l => `<option>${esc(l)}</option>`).join('');
    const ts = Sel.targets(hid);
    $('f-rec').innerHTML = '<option value="">인식 못함</option>' + ts.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    if (ts.length > 1) $('f-rec').value = ts[0].id;
  }
  $('f-home').addEventListener('change', drawLoc);
  $('btn-fall').addEventListener('click', () => {
    const inc = Act.triggerFall($('f-home').value, $('f-loc').value, $('f-rec').value || null);
    if (!inc) alert('이 집에는 이미 진행 중인 사고가 있어요.');
  });
  $('btn-clear').addEventListener('click', () => Act.clearIncidents());
  $('btn-reset').addEventListener('click', () => { if (confirm('임시 데이터를 처음 상태로 되돌릴까요?')) { Act.reset(); drawAll(); } });

  function drawUsers() {
    $('users').innerHTML = Store.state.people.map(p => `<button data-u="${p.id}" class="${Sel.meId() === p.id ? 'on' : ''}">${esc(p.name)}</button>`).join('');
    $('users').querySelectorAll('[data-u]').forEach(b => b.addEventListener('click', () => { Act.switchUser(b.dataset.u); drawUsers(); }));
  }
  function drawSpeeds() {
    const cur = Store.state.clock.speed;
    $('speeds').innerHTML = [1, 5, 10, 30].map(x => `<button data-s="${x}" class="${cur === x ? 'on' : ''}">${x}배속</button>`).join('');
    $('speeds').querySelectorAll('[data-s]').forEach(b => b.addEventListener('click', () => { Act.setSpeed(+b.dataset.s); drawSpeeds(); }));
  }
  document.querySelectorAll('[data-skip]').forEach(b => b.addEventListener('click', () => Act.skip(+b.dataset.skip)));

  function drawFrames() {
    $('frame-pick').innerHTML = Store.state.people.map(p => `<button data-f="${p.id}" class="${framesOn.has(p.id) ? 'on' : ''}">${esc(p.name)}</button>`).join('');
    $('frame-pick').querySelectorAll('[data-f]').forEach(b => b.addEventListener('click', () => {
      framesOn.has(b.dataset.f) ? framesOn.delete(b.dataset.f) : framesOn.add(b.dataset.f); drawFrames();
    }));
    const box = $('frames');
    const want = [...framesOn];
    [...box.children].forEach(c => { if (!want.includes(c.dataset.u)) c.remove(); });
    want.forEach(id => {
      if (box.querySelector(`[data-u="${id}"]`)) return;
      const p = Sel.person(id); if (!p) return;
      const f = document.createElement('div'); f.className = 'frame'; f.dataset.u = id;
      f.innerHTML = `<h3><span>${esc(p.name)}${p.isTarget ? ' · 감지 대상자' : ' · 알림만'}</span></h3><iframe title="${esc(p.name)} 화면" src="index.html?as=${id}#/"></iframe>`;
      box.appendChild(f);
    });
  }

  const STATUS = { detected: '감지됨', no_response: '응답 없음', help: '도움 요청', checking: '확인 중', reported: '신고됨', closed: '종료' };
  function drawState() {
    const t = Store.now();
    $('clock').textContent = fmt(t) + '  ×' + Store.state.clock.speed;
    const list = Store.state.incidents.slice().reverse();
    $('incs').innerHTML = list.length ? list.map(i => {
      const h = Sel.home(i.homeId);
      const left = i.autoReportAt ? ` · 자동 신고까지 ${mmss(i.autoReportAt - t)}` : (i.status === 'detected' ? ` · 응답까지 ${mmss(i.detectedAt + 60000 - t)}` : '');
      return `<div class="inc"><b>${STATUS[i.status]}</b> · ${esc(i.location)} · ${esc(h ? h.address : '')}<br><small>감지 ${fmt(i.detectedAt)}${left}${i.helpTimes.length ? ` · 도움요청 ${i.helpTimes.length}회` : ''}</small></div>`;
    }).join('') : '<p style="margin:0;color:#85939a">진행 중이거나 지난 사고가 없어요.</p>';
    $('json').textContent = JSON.stringify(Store.state.incidents, null, 2);
  }
  function drawAll() { drawFall(); drawUsers(); drawSpeeds(); drawFrames(); drawState(); }
  Store.subscribe(kind => { if (kind === 'tick') drawState(); else { drawUsers(); drawSpeeds(); drawState(); } });
  drawAll();
})();
