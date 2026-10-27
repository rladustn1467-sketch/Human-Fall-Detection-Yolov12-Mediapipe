/* ------------------------------------------------------------------
 * devices.js — 감지 기기 연결 (실제 모드). 처음 설정 4단계, 홈·집 상세의 '기기 추가', 설정·홈의
 * '이 휴대폰으로 감지하기'가 모두 이 흐름을 씀 (서버 devices.py: 연결 코드 → 기기가 코드를 보내 연결)
 *
 *   이 휴대폰       Android 앱 안에서만 (UI.nativeDetector). 로그인한 계정으로 연결 코드를 받아 이 휴대폰의 감지 화면에
 *                   바로 넘김 (코드는 화면에 보이지 않음, 서버가 그 집에 연결된 가족인지 다시 확인)
 *   안 쓰는 휴대폰  연결 코드를 보여 주고, 그 휴대폰의 첫 화면(로그인 화면) 아래 '감지용 휴대전화 연결하기'에서 입력
 *   개발용 (서버 FD_DEV_DEVICES=1 일 때만, state.features.devDevices):
 *     PC 감지 프로그램  개발·시험 도구. 연결 코드를 PC 프로그램의 '연결 코드 입력'에 입력
 *     홈캠·CCTV        시연용 화면 흐름만. 서버에 연결하지 않음 (가짜 연결 코드·연결 성공 표시 없음)
 * '연결됐어요'는 서버 상태에 그 기기가 나타났을 때만 보여 줌.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const UI = FD.UI;
  const { esc, ic, on, field, setError, val, openSheet, closeSheet } = UI;
  const { Sel, Act } = FD.Store;
  const LOCS = ['안방', '거실', '현관', '주방', '작은방'];
  const DEMO = ['homecam', 'cctv'];   // 시연용 (서버에 연결하지 않음)

  const devFeatures = () => !!(FD.Store.state && FD.Store.state.features && FD.Store.state.features.devDevices);

  /* 고를 수 있는 연결 방식 (지금 이 화면에서 실제로 쓸 수 있는 것만) */
  function kinds() {
    const out = [];
    if (UI.nativeDetector()) out.push({ key: 'self', icon: 'mobile-screen', t: '이 휴대폰으로 감지하기', s: '지금 쓰는 이 휴대폰을 연결 코드 없이 바로 연결해요' });
    out.push({ key: 'phone', icon: 'mobile-retro', t: '안 쓰는 휴대폰', s: '안 쓰는 휴대폰을 집 안에 세워 두고 감지 전용으로 써요' });
    if (devFeatures()) {
      out.push({ key: 'homecam', icon: 'video', t: '홈캠', s: '집에 설치된 홈캠을 연결해요' });
      out.push({ key: 'cctv', icon: 'camera', t: 'CCTV', s: '집에 설치된 CCTV를 연결해요' });
      out.push({ key: 'pc', icon: 'desktop', t: 'PC 감지 프로그램 (개발용)', s: '시험 서버에서만 보이는 개발·시험 도구예요' });
    }
    return out;
  }
  const kindOf = key => kinds().find(k => k.key === key);
  const kindName = key => ({ self: '이 휴대폰', phone: '안 쓰는 휴대폰', homecam: '홈캠', cctv: 'CCTV', pc: 'PC 감지 프로그램' })[key] || '기기';

  /* 연결 방식 목록 (처음 설정 4단계는 화면에 바로, 기기 추가는 시트에) */
  function choicesHtml(homeId) {
    return kinds().map(k => `<button class="choice" data-action="dc.pick" data-kind="${k.key}" data-home="${esc(homeId)}">
      <span class="choice__ic">${ic(k.icon)}</span><span><span class="choice__t">${esc(k.t)}</span><span class="choice__s" style="display:block">${esc(k.s)}</span></span></button>`).join('');
  }
  function openChooser(homeId) {
    openSheet({ title: '감지 기기 추가', html: `<div class="stack">${choicesHtml(homeId)}</div>` });
  }
  on('dc.pick', el => start(el.dataset.kind, el.dataset.home));

  function start(key, homeId) {
    if (!kindOf(key)) return;
    if (key === 'self') { Self.start(homeId); return; }
    locationSheet(key, [homeId]);
  }

  /* 위치 고르기 (+ '이 휴대폰'은 연결된 집이 여럿이면 집도) */
  function locationSheet(key, homeIds) {
    const me = Sel.me();
    const homes = homeIds.map(id => Sel.home(id)).filter(Boolean);
    if (!homes.length) return;
    let hid = homes[0].id;
    const self = key === 'self';
    const html = () => `
      ${self ? `<p class="row__sub" style="margin-bottom:16px">이 휴대폰의 카메라로 낙상을 감지해요. 로그인한 계정으로 바로 연결돼서 연결 코드를 입력하지 않아도 돼요.</p>` : ''}
      ${homes.length > 1 ? `<div class="label">감지할 집</div>
      <div class="segmented" style="margin-bottom:16px">${homes.map(h => `<button type="button" class="${h.id === hid ? 'is-on' : ''}" data-action="dc.home" data-id="${h.id}">${esc(Sel.homeName(h, me))}</button>`).join('')}</div>` : ''}
      ${field({ id: 'dc-loc', label: self ? '휴대폰을 둘 위치' : '위치 이름', placeholder: '예) 안방, 거실', maxlength: 12, value: (document.getElementById('dc-loc') && document.getElementById('dc-loc').value) || '', onenter: 'dc.submit' })}
      <div class="chips" style="margin:-6px 0 18px">${LOCS.map(l => `<button type="button" class="chip" data-action="dc.loc" data-loc="${l}">${l}</button>`).join('')}</div>
      ${self ? `<div class="notice">${ic('circle-info')}<span>감지하는 동안에는 휴대폰을 낙상을 볼 수 있는 곳에 세워 두고 충전기를 꽂아 두세요. 다음 화면에서 카메라 권한을 허용하면 감지를 시작해요.</span></div>` : ''}
      <button class="btn btn--primary btn--lg btn--block" style="margin-top:16px" data-action="dc.submit">${self ? '연결하고 감지 시작' : '연결 코드 받기'}</button>`;
    const api = openSheet({ title: self ? '이 휴대폰으로 감지하기' : `${kindName(key)} 추가`, html: html() });
    on('dc.home', el => { hid = el.dataset.id; api.replace(html()); });
    on('dc.loc', el => { document.getElementById('dc-loc').value = el.dataset.loc; setError('dc-loc', ''); });
    on('dc.submit', async el => {
      const location = val('dc-loc');
      if (!location) { setError('dc-loc', '위치 이름을 입력해 주세요.'); return; }
      if (DEMO.includes(key)) { api.replace(demoHtml(key, location)); return; }   // 시연용: 서버에 연결하지 않음
      let p;
      try {
        p = await UI.busy(el, () => Act.startDevicePairing(hid, { type: self ? 'phone' : key, location }));
      } catch (e) { UI.showError(e, { location: 'dc-loc' }); return; }
      if (self) { closeSheet(); await Self.open({ mode: 'self', code: p.code }); return; }
      codeSheet(hid, p);
    });
  }

  /* 홈캠·CCTV 시연: 연결 코드 화면과 같은 자리에, 실제로는 연결할 수 없다는 사실만 (가짜 코드·연결 성공 없음) */
  function demoHtml(key, location) {
    return `<p class="row__sub" style="text-align:center">${esc(kindName(key))} · ${esc(location)}</p>
      <div class="notice" style="margin-top:14px">${ic('circle-info')}<span>이 카메라는 아직 앱과 연결할 수 없어요.</span></div>
      <button class="btn btn--ghost btn--block" style="margin-top:14px" data-action="sheet.close">닫기</button>`;
  }

  /* 연결 코드 (10분, 한 번). 기기가 코드를 보내 연결되면 서버 상태에 나타나고, 그때만 '연결됐어요' */
  const PAIR_WHERE = {
    pc: "PC 감지 프로그램에서 '연결 코드 입력' 버튼을 누르고 이 코드를 입력해 주세요.",
    phone: "감지 전용으로 쓸 휴대폰에 이 앱을 설치해 열고, 첫 화면 아래의 '감지용 휴대전화 연결하기'에서 이 코드를 입력해 주세요. 그 휴대폰은 로그인하지 않아도 돼요."
  };
  function codeSheet(homeId, p) {
    const startedAt = p.expiresAt - 10 * 60 * 1000;
    const joined = () => Sel.devices(homeId).find(d => d.createdAt >= startedAt && d.type === p.type && d.location === p.location);
    const html = () => {
      const d = joined();
      if (d) {
        return `<div class="empty" style="padding-top:8px">${ic('circle-check')}<p style="margin-top:10px;font-weight:800;color:var(--ink)">${esc(UI.deviceName(d))} 연결됐어요</p>
          <p class="row__sub" style="margin-top:6px">${d.status === 'ok' ? '상태 신호를 받고 있어요.' : esc(UI.DEVICE_PROBLEM[d.problem] || '')}</p></div>
          <button class="btn btn--primary btn--lg btn--block" data-action="sheet.close">확인</button>`;
      }
      const left = p.expiresAt - FD.Store.now();
      return `<p class="row__sub" style="text-align:center">${esc(UI.DEVICE_TYPE[p.type])} · ${esc(p.location)}</p>
        <p class="label" style="margin:14px 0 8px;text-align:center">연결 코드</p>
        <div class="code-box" aria-label="연결 코드 ${esc(p.code)}">${p.code.split('').map(c => `<span>${esc(c)}</span>`).join('')}</div>
        <p class="expire" style="text-align:center;margin-top:10px">${ic('clock')} ${left > 0 ? `남은 시간 <b data-cd="${p.expiresAt}">--:--</b>` : '코드가 만료됐어요. 새 코드를 받아 주세요.'}</p>
        <div class="notice" style="margin-top:14px">${ic('circle-info')}<span>${esc(PAIR_WHERE[p.type] || '감지 기기에서 이 연결 코드를 입력해 주세요.')} 코드는 10분 동안 한 번만 쓸 수 있고, 연결되면 이 집의 감지 기기 목록에 나타나요.</span></div>
        <button class="btn btn--ghost btn--block" style="margin-top:14px" data-action="sheet.close">닫기</button>`;
    };
    openSheet({ title: '감지 기기 추가', html: html(), onMount: b => UI.tick(b), refresh: a => { a.replace(html()); UI.tick(a.body()); } });
  }

  /* ---- 이 휴대폰 (Android 앱의 Detector 플러그인) ---- */
  const Self = {
    last: null,   // 마지막으로 휴대폰이 알려 준 연결 상태 (홈 카드 표시용)
    async status() {
      if (!UI.nativeDetector()) return null;
      let s = null;
      try { s = await window.Capacitor.nativePromise('Detector', 'status', {}); } catch (e) { s = null; }
      const changed = JSON.stringify(s) !== JSON.stringify(Self.last);
      Self.last = s;
      return { s, changed };
    },
    async open(opts) {
      try { await window.Capacitor.nativePromise('Detector', 'open', opts || {}); return true; } catch (e) { UI.toast('감지 화면을 열지 못했어요'); return false; }
    },
    /* 로그아웃 전에: 이 휴대폰이 '이 휴대폰으로 감지하기'로 연결돼 있으면 감지를 멈춤 (카메라·감지 서비스 종료,
       서버에도 '꺼짐', 이 휴대폰에서 다시 켤 때까지 유지). 연결 코드로 연결한 감지 전용 휴대폰은 그대로.
       결과 {self, stopped, serverUpdated} (Android 앱이 아니면 self: false) */
    async stopForLogout() {
      if (!UI.nativeDetector()) return { self: false };
      try { return await window.Capacitor.nativePromise('Detector', 'stopForLogout', {}); } catch (e) { return { self: true, stopped: false }; }
    },
    /* 탈퇴한 뒤: '이 휴대폰'이면 서버의 이 기기 기록을 지우고(기기 토큰) 이 휴대폰의 연결도 해제 → 다른 계정이 다시 연결 가능.
       연결 코드로 연결한 감지 전용 휴대폰은 그대로. 결과 {self, removed} */
    async unpairAfterWithdraw() {
      if (!UI.nativeDetector()) return { self: false };
      try { return await window.Capacitor.nativePromise('Detector', 'unpairAfterWithdraw', {}); } catch (e) { return { self: true, removed: false }; }
    },
    /* 감지 전용 기기 화면 (로그인 전 첫 화면에서): 연결 코드 입력 */
    openDedicated() { return Self.open({ mode: 'dedicated' }); },
    /* 이미 연결돼 있으면 감지 상태 화면만, 아니면 위치(와 집)를 고른 뒤 연결 */
    async start(homeId) {
      const r = await Self.status();
      if (r && r.s && r.s.paired) { await Self.open({}); return; }
      const me = Sel.me();
      const ids = homeId ? [homeId] : me.homeIds.slice();
      if (!ids.length) {
        UI.toast(me.isTarget ? '먼저 감지할 집에 연결해 주세요. 가족 탭에서 집을 열면 연결할 수 있어요.'
          : "이 휴대폰으로 감지하려면 먼저 홈 화면에서 '낙상 감지 켜기'를 눌러 집을 등록해 주세요.");
        return;
      }
      locationSheet('self', ids);
    }
  };

  FD.DeviceConnect = { kinds, choicesHtml, openChooser, start, self: Self };
})();
