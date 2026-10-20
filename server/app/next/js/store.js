/* ------------------------------------------------------------------
 * store.js — 앱 전체 상태 · 선택자(selector) · 동작(action)
 *
 * - 모든 화면은 하나의 상태 객체(state)를 읽기만 하고, 변경은 Store 의 동작을 통해서만 합니다.
 * - 낙상 사고(incident)는 "기준 시각"(detectedAt / familyNotifiedAt / autoReportAt …)만 저장하고
 *   남은 시간은 항상 (예정 시각 - 현재 시각)으로 계산합니다. 같은 사고를 보는 모든 화면이 같은 마감 시각을 공유합니다.
 * - advance() 는 서버가 맡을 "시간 경과에 따른 상태 전이"(60초 무응답, 자동 119 신고)를 대신하는 자리입니다.
 *   실제 서버가 붙으면 이 함수를 제거하고 서버 데이터를 setState 로 주입하세요.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const API = FD.API;
  const S = 1000, M = 60000, H = 3600000, D = 86400000;
  const SELF_WINDOW = 60 * S;      // 낙상자 응답 대기
  const AUTO_REPORT = 180 * S;     // 가족 알림 후 자동 신고까지
  const TERMINAL = ['reported', 'closed'];

  let state = null;
  let meId = null;
  let fixedUser = null;   // URL ?as= 로 고정된 화면(개발 확인용 동시 보기)에서만 사용
  const subs = new Set();
  let started = false;

  /* ---------- 시계 (배속 지원) ---------- */
  function clockNow(st) {
    const c = st.clock;
    return c.virtBase + (Date.now() - c.realBase) * c.speed;
  }
  function now() { return clockNow(state); }

  /* ---------- 유틸 ---------- */
  const isTerminal = inc => TERMINAL.includes(inc.status);
  function logAdd(inc, at, text) { inc.log.push({ at, text }); }
  function person(st, id) { return st.people.find(p => p.id === id); }
  function home(st, id) { return st.homes.find(h => h.id === id); }
  function targetsOf(st, homeId) { return st.people.filter(p => p.isTarget && p.homeIds.includes(homeId)); }

  function terminate(st, inc, o) {
    inc.status = o.status;           // 'reported' | 'closed'
    inc.result = o.result;           // self | family | reported | auto_reported
    inc.closedAt = o.at;
    inc.closedBy = o.by;
    inc.autoReportAt = null;
    if (!inc.response) inc.response = 'none';
    logAdd(inc, o.at, o.text);
  }

  /* 서버 대행: 시간 경과 전이 (결정적 — 여러 탭에서 동시에 돌아도 같은 결과) */
  function advance(st) {
    const t = clockNow(st);
    let changed = false;
    st.incidents.forEach(inc => {
      if (isTerminal(inc)) return;
      if (inc.status === 'detected' && t >= inc.detectedAt + SELF_WINDOW) {
        inc.status = 'no_response';
        inc.familyNotifiedAt = inc.detectedAt + SELF_WINDOW;
        inc.autoReportAt = inc.familyNotifiedAt + AUTO_REPORT;
        logAdd(inc, inc.familyNotifiedAt, '60초 동안 응답이 없어 가족에게 알렸어요');
        changed = true;
      }
      if ((inc.status === 'no_response' || inc.status === 'help') && inc.autoReportAt && t >= inc.autoReportAt) {
        inc.reportedBy = 'auto';
        inc.reportedAt = inc.autoReportAt;
        inc.reportedTargetIds = targetsOf(st, inc.homeId).map(p => p.id);
        terminate(st, inc, { status: 'reported', result: 'auto_reported', by: 'auto', at: inc.autoReportAt, text: '아무도 확인하지 않아 자동으로 119에 신고했어요' });
        changed = true;
      }
    });
    return changed;
  }

  function save() { API.writeSnapshot(state); }
  function notifySubs(kind) { subs.forEach(fn => { try { fn(kind); } catch (e) { console.error(e); } }); }

  function commit(mut) {
    const latest = API.readSnapshot();
    if (latest && latest.version === 2) state = latest;
    advance(state);
    const r = mut(state);
    advance(state);
    save();
    notifySubs('commit');
    return r;
  }

  /* 알림(푸시 대용) 기록 */
  function pushNotif(st, o) {
    const g = o.groupId;
    const to = st.people.filter(p => p.groupId === g && p.id !== o.actorId && (!o.pref || p.prefs[o.pref] !== false)).map(p => p.id);
    if (!to.length) return;
    st.notifs.push({ id: API.uid('n'), groupId: g, to, text: o.text, at: clockNow(st) });
    if (st.notifs.length > 60) st.notifs.splice(0, st.notifs.length - 60);
  }

  /* ---------- 초기화 ---------- */
  async function init() {
    state = await API.loadSnapshot();
    const params = new URLSearchParams(location.search);
    const as = params.get('as');
    if (as && person(state, as)) fixedUser = as;
    const sess = API.readSession();
    if (fixedUser) meId = fixedUser;
    else if (sess === '__none__') meId = null;
    else if (sess && person(state, sess)) meId = sess;
    else {
      const first = state.people.find(p => p.id === 'u1') || state.people[0];
      meId = first ? first.id : null;
      API.writeSession(meId);
    }
    advance(state); save();
    if (!started) {
      started = true;
      window.addEventListener('storage', e => {
        if (e.key === API.KEY && e.newValue) {
          try { state = JSON.parse(e.newValue); } catch (err) { return; }
          if (meId && !person(state, meId)) meId = null;
          notifySubs('remote');
        } else if (e.key === API.SESSION_KEY) {
          if (!fixedUser) { meId = e.newValue && e.newValue !== '__none__' && person(state, e.newValue) ? e.newValue : null; notifySubs('session'); }
        }
      });
      setInterval(() => {
        if (advance(state)) { save(); notifySubs('commit'); }
        notifySubs('tick');
      }, 500);
    }
    return state;
  }

  /* ---------- 선택자 ---------- */
  const Sel = {
    now,
    me: () => (state && meId ? person(state, meId) : null),
    meId: () => meId,
    person: id => person(state, id),
    home: id => home(state, id),
    people(groupId) { return state.people.filter(p => p.groupId === groupId); },
    homes(groupId) { return state.homes.filter(h => h.groupId === groupId); },
    group(id) { return state.groups.find(g => g.id === id); },
    devices(homeId) { return state.devices.filter(d => d.homeId === homeId); },
    device: id => state.devices.find(d => d.id === id),
    targets: homeId => targetsOf(state, homeId),
    linked: homeId => state.people.filter(p => p.homeIds.includes(homeId)),
    canEditHome(homeId, p) { p = p || Sel.me(); return !!p && p.homeIds.includes(homeId); },
    isMine: (homeId, p) => { p = p || Sel.me(); return !!p && p.homeIds.includes(homeId); },

    /* 집 이름: 내 집 = 우리 집 / 그 외 = OO·OO님 댁 */
    homeName(h, viewer) {
      viewer = viewer || Sel.me();
      if (viewer && viewer.homeIds.includes(h.id)) return '우리 집';
      const ts = targetsOf(state, h.id);
      const ls = ts.length ? ts : Sel.linked(h.id);
      if (!ls.length) return '등록된 집';
      return ls.map(p => p.name).join('·') + '님 댁';
    },

    /* 감지 현황 요약 */
    homeSummary(h) {
      const ds = Sel.devices(h.id);
      const working = ds.filter(d => d.status === 'ok').length;
      const total = ds.length;
      if (total === 0) return { kind: 'stop', working, total, title: '감지 중단', detail: '연결된 기기가 없어요' };
      if (working === 0) return { kind: 'stop', working, total, title: '감지 중단', detail: '작동 중인 기기가 없어요' };
      if (working === total) return { kind: 'ok', working, total, title: '감지 중', detail: `기기 ${total}대 모두 정상` };
      return { kind: 'warn', working, total, title: '주의', detail: `${working}/${total} 작동 중` };
    },

    /* 사고 */
    incident: id => state.incidents.find(i => i.id === id),
    activeIncidents: () => state.incidents.filter(i => !isTerminal(i)),
    isTerminal,
    /* 내가 알림을 받는 대상인가: 'victim' | 'family' | null */
    roleIn(inc, p) {
      p = p || Sel.me();
      if (!p || p.groupId !== inc.groupId) return null;
      if (p.isTarget && p.homeIds.includes(inc.homeId)) return 'victim';
      if (inc.familyNotifiedAt) return 'family';
      return null;
    },
    /* 내게 보이는 사고 (진행 중 + 최근 종료되었으나 아직 확인하지 않은 것) */
    incidentsFor(p) {
      p = p || Sel.me();
      if (!p) return [];
      const t = now();
      return state.incidents.filter(inc => {
        if (!Sel.roleIn(inc, p)) return false;
        if (!isTerminal(inc)) return true;
        if (inc.dismissed && inc.dismissed[p.id]) return false;
        return t - inc.closedAt < H;
      });
    },
    /* 마감 빠른 순 정렬용 */
    deadline(inc) { return inc.autoReportAt || Infinity; },
    reminderLevel(inc, t) {
      if (inc.status !== 'checking' || !inc.checkedAt) return 0;
      t = t || now();
      return Math.min(3, Math.floor((t - inc.checkedAt) / (5 * M)));
    },

    /* 이력 */
    history() {
      const mapped = state.incidents.filter(isTerminal).map(inc => Object.assign({}, inc, {
        personIds: inc.reportedTargetIds && inc.reportedTargetIds.length ? inc.reportedTargetIds : targetsOf(state, inc.homeId).map(p => p.id)
      }));
      return state.history.concat(mapped).sort((a, b) => b.detectedAt - a.detectedAt);
    },
    historyItem: id => Sel.history().find(h => h.id === id),
    notifsFor(p) { return state.notifs.filter(n => n.to.includes(p.id)); }
  };

  /* ---------- 동작 ---------- */
  const Act = {
    /* 시계 */
    setSpeed(x) { commit(st => { const t = clockNow(st); st.clock = { realBase: Date.now(), virtBase: t, speed: x }; }); },
    skip(ms) { commit(st => { st.clock.virtBase += ms; }); },
    reset() { state = API.resetSnapshot(); API.writeSession('u1'); if (!fixedUser) meId = 'u1'; notifySubs('commit'); },
    switchUser(id) { if (!person(state, id)) return; meId = id; if (!fixedUser) API.writeSession(id); notifySubs('session'); },

    signOut() { API.writeSession('__none__'); fixedUser = null; meId = null; notifySubs('session'); },

    /* 계정 · 그룹 */
    createAccount({ name, phone, email }) {
      let id;
      commit(st => {
        id = API.uid('u');
        st.people.push({ id, name, phone, email: email || '', groupId: null, onboarded: false, isTarget: false, birth: null, conditions: null, medications: null, homeIds: [], phoneCamera: false, prefs: { device: true, member: true, home: true } });
      });
      meId = id;
      if (!fixedUser) API.writeSession(id);
      notifySubs('session');
      return id;
    },
    createGroup(personId) {
      let g;
      commit(st => {
        const p = person(st, personId);
        g = { id: API.uid('g'), name: p.name + '님의 가족', invite: null };
        g.invite = { code: Act._code(), createdAt: clockNow(st), expiresAt: clockNow(st) + D, createdBy: personId };
        st.groups.push(g);
        p.groupId = g.id;
      });
      return g;
    },
    _code() { const c = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; let s = ''; for (let i = 0; i < 6; i++) s += c[Math.floor(Math.random() * c.length)]; return s; },
    regenInvite(groupId, byId) {
      let inv;
      commit(st => {
        const g = st.groups.find(x => x.id === groupId);
        inv = { code: Act._code(), createdAt: clockNow(st), expiresAt: clockNow(st) + D, createdBy: byId };
        g.invite = inv;
      });
      return inv;
    },
    /* 코드로 참여. 성공: {ok:true, group} / 실패: {ok:false, reason} */
    joinGroup(personId, code) {
      code = (code || '').trim().toUpperCase().replace(/\s+/g, '');
      let res;
      commit(st => {
        const g = st.groups.find(x => x.invite && x.invite.code === code);
        if (!g) { res = { ok: false, reason: '초대 코드를 확인해 주세요.' }; return; }
        if (g.invite.expiresAt < clockNow(st)) { res = { ok: false, reason: '만료된 초대 코드예요. 새 코드를 요청해 주세요.' }; return; }
        const p = person(st, personId);
        p.groupId = g.id;
        const inviter = person(st, g.invite.createdBy);
        pushNotif(st, { groupId: g.id, actorId: personId, pref: 'member', text: `${inviter ? inviter.name : '가족'}님의 초대로 ${p.name}님이 참여했어요` });
        res = { ok: true, group: g };
      });
      return res;
    },
    leaveGroup(personId) {
      commit(st => {
        const p = person(st, personId);
        const gid = p.groupId;
        p.groupId = null; p.onboarded = false; p.isTarget = false; p.homeIds = []; p.phoneCamera = false;
        p.birth = null; p.conditions = null; p.medications = null;
        if (gid) pushNotif(st, { groupId: gid, actorId: personId, pref: 'member', text: `${p.name}님이 그룹에서 나갔어요` });
      });
    },
    withdraw(personId) {
      commit(st => {
        const i = st.people.findIndex(p => p.id === personId);
        if (i >= 0) st.people.splice(i, 1);
      });
      API.writeSession('__none__');
      fixedUser = null;
      meId = null;
      notifySubs('session');
    },

    /* 프로필 · 감지 대상자 */
    updateProfile(personId, patch) { commit(st => Object.assign(person(st, personId), patch)); },
    setPref(personId, key, val) { commit(st => { person(st, personId).prefs[key] = val; }); },
    enableTarget(personId, info) {
      commit(st => {
        const p = person(st, personId);
        p.isTarget = true;
        if (info) Object.assign(p, info);
      });
    },
    phoneCamera(personId, on) { commit(st => { person(st, personId).phoneCamera = on; }); },

    /* 집 */
    addHome(personId, address) {
      let id;
      commit(st => {
        const p = person(st, personId);
        id = API.uid('h');
        st.homes.push({ id, groupId: p.groupId, address, centralPw: false, doorPw: false });
        p.homeIds.push(id);
      });
      return id;
    },
    linkHome(personId, homeId) {
      commit(st => { const p = person(st, personId); if (!p.homeIds.includes(homeId)) p.homeIds.push(homeId); });
    },
    unlinkHome(personId, homeId) {
      commit(st => { const p = person(st, personId); p.homeIds = p.homeIds.filter(x => x !== homeId); });
    },
    updateHome(homeId, patch, actorId, note) {
      commit(st => {
        const h = home(st, homeId);
        Object.assign(h, patch);
        const a = person(st, actorId);
        if (note && a) {
          const to = st.people.filter(p => p.homeIds.includes(homeId) && p.id !== actorId && p.prefs.home !== false).map(p => p.id);
          if (to.length) st.notifs.push({ id: API.uid('n'), groupId: h.groupId, to, text: `${a.name}님이 ${note}`, at: clockNow(st) });
        }
      });
    },

    /* 기기 */
    addDevice(homeId, { type, location }, actorId) {
      let id;
      commit(st => {
        id = API.uid('d');
        st.devices.push({ id, homeId, type, location, status: 'ok', since: clockNow(st) });
        const a = person(st, actorId);
        const to = st.people.filter(p => p.homeIds.includes(homeId) && p.id !== actorId && p.prefs.home !== false).map(p => p.id);
        if (a && to.length) st.notifs.push({ id: API.uid('n'), groupId: home(st, homeId).groupId, to, text: `${a.name}님이 감지 기기(${location})를 추가했어요`, at: clockNow(st) });
      });
      return id;
    },
    updateDevice(id, patch) {
      commit(st => {
        const d = st.devices.find(x => x.id === id);
        if (!d) return;
        if (patch.status && patch.status !== d.status) patch.since = clockNow(st);
        Object.assign(d, patch);
      });
    },
    removeDevice(id) { commit(st => { st.devices = st.devices.filter(d => d.id !== id); }); },

    /* ---------- 낙상 사고 ---------- */
    /* 개발 확인용 경로(dev.html)에서만 호출. 실제로는 카메라/서버가 만든 이벤트로 대체 */
    triggerFall(homeId, location, recognizedId) {
      let created = null;
      commit(st => {
        if (st.incidents.some(i => i.homeId === homeId && !isTerminal(i))) return;
        const t = clockNow(st);
        created = {
          id: API.uid('inc'), groupId: home(st, homeId).groupId, homeId, location,
          detectedAt: t, status: 'detected', response: null,
          familyNotifiedAt: null, helpTimes: [], autoReportAt: null,
          checkedBy: null, checkedAt: null,
          closedAt: null, closedBy: null, result: null,
          reportedBy: null, reportedAt: null, reportedTargetIds: [],
          recognizedId: recognizedId || null,
          dismissed: {}, log: [{ at: t, text: '낙상이 감지됐어요' }]
        };
        st.incidents.push(created);
      });
      return created;
    },
    /* E-01 [괜찮아요] */
    selfOk(id, pid) {
      return commit(st => {
        const inc = st.incidents.find(i => i.id === id);
        if (!inc || isTerminal(inc)) return false;
        const p = person(st, pid), t = clockNow(st);
        if (!inc.response) inc.response = (t - inc.detectedAt) < SELF_WINDOW ? 'within60' : 'after60';
        terminate(st, inc, { status: 'closed', result: 'self', by: pid, at: t, text: `${p.name}님이 괜찮다고 응답했어요` });
        return true;
      });
    },
    /* E-01 [도움이 필요해요] — 여러 번 눌러도 마감 시각은 처음 요청 기준 유지 */
    selfHelp(id, pid) {
      return commit(st => {
        const inc = st.incidents.find(i => i.id === id);
        if (!inc || isTerminal(inc) || inc.status === 'checking') return false;
        const p = person(st, pid), t = clockNow(st);
        inc.helpTimes.push(t);
        if (!inc.response) inc.response = (t - inc.detectedAt) < SELF_WINDOW ? 'within60' : 'after60';
        if (inc.status === 'detected') {
          inc.status = 'help';
          inc.familyNotifiedAt = t;
          inc.autoReportAt = t + AUTO_REPORT;
        } else if (inc.status === 'no_response') {
          inc.status = 'help';           // 이미 정해진 마감 시각은 그대로 유지
        }
        logAdd(inc, t, `${p.name}님이 도움이 필요하다고 응답했어요 (${inc.helpTimes.length}번째)`);
        return true;
      });
    },
    /* E-02/03 [확인했어요, 제가 처리할게요] */
    takeOver(id, pid) {
      return commit(st => {
        const inc = st.incidents.find(i => i.id === id);
        if (!inc || isTerminal(inc) || inc.status === 'checking' || inc.status === 'detected') return false;
        const p = person(st, pid), t = clockNow(st);
        inc.status = 'checking'; inc.checkedBy = pid; inc.checkedAt = t; inc.autoReportAt = null;
        logAdd(inc, t, `${p.name}님이 확인했어요`);
        return true;
      });
    },
    /* E-06 [괜찮은 걸 확인했어요 (종료)] */
    closeChecked(id, pid) {
      return commit(st => {
        const inc = st.incidents.find(i => i.id === id);
        if (!inc || isTerminal(inc) || inc.checkedBy !== pid) return false;
        const p = person(st, pid);
        terminate(st, inc, { status: 'closed', result: 'family', by: pid, at: clockNow(st), text: `${p.name}님이 괜찮은 것을 확인하고 종료했어요` });
        return true;
      });
    },
    /* E-05 [전송] — 이미 신고/종료되었으면 false (중복 방지) */
    report(id, pid, targetIds) {
      return commit(st => {
        const inc = st.incidents.find(i => i.id === id);
        if (!inc || isTerminal(inc)) return false;
        const p = person(st, pid), t = clockNow(st);
        inc.reportedBy = pid; inc.reportedAt = t;
        inc.reportedTargetIds = targetIds && targetIds.length ? targetIds : targetsOf(st, inc.homeId).map(x => x.id);
        terminate(st, inc, { status: 'reported', result: 'reported', by: pid, at: t, text: `${p.name}님이 119에 신고했어요` });
        return true;
      });
    },
    dismiss(id, pid) {
      commit(st => { const inc = st.incidents.find(i => i.id === id); if (inc) { inc.dismissed = inc.dismissed || {}; inc.dismissed[pid] = true; } });
    },
    clearIncidents() { commit(st => { st.incidents = []; }); }
  };

  /* 구독 */
  function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }

  FD.Store = { init, subscribe, commit, Sel, Act, now, get state() { return state; }, consts: { S, M, H, D, SELF_WINDOW, AUTO_REPORT } };
})();
