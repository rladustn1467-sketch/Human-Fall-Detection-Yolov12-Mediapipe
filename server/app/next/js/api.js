/* ------------------------------------------------------------------
 * api.js — 데이터 공급 계층
 * 화면 코드는 이 파일의 함수만 통해 데이터를 읽고 씁니다.
 * 지금은 임시 데이터 + localStorage 로 동작하며, 이후 실제 서버 API 호출로
 * loadSnapshot / readSnapshot / writeSnapshot / searchAddress 를 교체하면 됩니다.
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const KEY = 'fd.state.v2';
  const SESSION_KEY = 'fd.session.v2';
  const H = 3600000, D = 86400000, M = 60000, S = 1000;

  function uid(prefix) {
    return (prefix || 'id') + '_' + Math.random().toString(36).slice(2, 9);
  }

  /* 낙상 이력(과거) — 현재 시각 기준 상대 값으로 만들어 항상 "최근"으로 보이게 함 */
  function seedHistory(now) {
    function mk(id, ageMs, homeId, location, personId, response, result, o, log) {
      const at = now - ageMs;
      return Object.assign({
        id, seed: true, groupId: 'g1', homeId, location, personId, detectedAt: at,
        response, result, checkedBy: null, checkedAt: null, closedBy: null, closedAt: null,
        reportedBy: null, helpCount: 0,
        log: log.map(l => ({ at: at + l[0], text: l[1] }))
      }, o(at));
    }
    return [
      mk('hs1', 26 * H, 'h1', '안방', 'u2', 'within60', 'self',
        at => ({ closedBy: 'u2', closedAt: at + 22 * S }),
        [[0, '낙상이 감지됐어요'], [22 * S, '이서연님이 괜찮다고 응답했어요']]),
      mk('hs2', 98 * H, 'h2', '거실', 'u3', 'none', 'auto_reported',
        at => ({ reportedBy: 'auto', closedAt: at + 240 * S, closedBy: 'auto' }),
        [[0, '낙상이 감지됐어요'], [60 * S, '60초 동안 응답이 없어 가족에게 알렸어요'], [240 * S, '아무도 확인하지 않아 자동으로 119에 신고했어요']]),
      mk('hs3', 6 * D - 5 * H, 'h2', '거실', 'u3', 'none', 'family',
        at => ({ checkedBy: 'u4', checkedAt: at + 95 * S, closedBy: 'u4', closedAt: at + 7 * M }),
        [[0, '낙상이 감지됐어요'], [60 * S, '60초 동안 응답이 없어 가족에게 알렸어요'], [95 * S, '김민호님이 확인했어요'], [7 * M, '김민호님이 괜찮은 것을 확인하고 종료했어요']]),
      mk('hs4', 15 * D, 'h1', '거실', 'u1', 'after60', 'self',
        at => ({ closedBy: 'u1', closedAt: at + 74 * S }),
        [[0, '낙상이 감지됐어요'], [60 * S, '60초 동안 응답이 없어 가족에게 알렸어요'], [74 * S, '김민준님이 괜찮다고 응답했어요']]),
      mk('hs5', 33 * D, 'h2', '안방', 'u3', 'within60', 'reported',
        at => ({ helpCount: 1, reportedBy: 'u1', closedBy: 'u1', closedAt: at + 110 * S }),
        [[0, '낙상이 감지됐어요'], [15 * S, '박순자님이 도움이 필요하다고 응답했어요 (1번째)'], [110 * S, '김민준님이 119에 신고했어요']]),
      mk('hs6', 52 * D, 'h1', '현관', 'u2', 'within60', 'self',
        at => ({ closedBy: 'u2', closedAt: at + 9 * S }),
        [[0, '낙상이 감지됐어요'], [9 * S, '이서연님이 괜찮다고 응답했어요']])
    ];
  }

  function buildSeed(now) {
    const defaultPrefs = { device: true, member: true, home: true };
    return {
      version: 2,
      anchoredAt: now,
      clock: { realBase: Date.now(), virtBase: now, speed: 1 },
      groups: [{
        id: 'g1', name: '김민준님의 가족',
        invite: { code: 'K7M2QX', createdAt: now, expiresAt: now + 24 * H, createdBy: 'u1' }
      }],
      people: [
        { id: 'u1', name: '김민준', phone: '010-1234-5678', email: '', groupId: 'g1', isTarget: true,
          birth: '1985-03-12', conditions: [], medications: [], homeIds: ['h1'], phoneCamera: false, prefs: { ...defaultPrefs } },
        { id: 'u2', name: '이서연', phone: '010-2345-6789', email: '', groupId: 'g1', isTarget: true,
          birth: '1987-11-23', conditions: null, medications: null, homeIds: ['h1'], phoneCamera: true, prefs: { ...defaultPrefs } },
        { id: 'u3', name: '박순자', phone: '010-3456-7890', email: '', groupId: 'g1', isTarget: true,
          birth: '1951-07-08', conditions: ['고혈압', '당뇨'], medications: ['혈압약', '당뇨약'], homeIds: ['h2'], phoneCamera: false, prefs: { ...defaultPrefs } },
        { id: 'u4', name: '김민호', phone: '010-4567-8901', email: '', groupId: 'g1', isTarget: false,
          birth: null, conditions: null, medications: null, homeIds: [], phoneCamera: false, prefs: { ...defaultPrefs } }
      ],
      homes: [
        { id: 'h1', groupId: 'g1', address: '서울 OO구 OO아파트 101동 1203호', centralPw: true, doorPw: true },
        { id: 'h2', groupId: 'g1', address: 'OO시 OO동 OO아파트 205동 502호', centralPw: false, doorPw: true }
      ],
      devices: [
        { id: 'd1', homeId: 'h1', type: 'homecam', location: '안방', status: 'ok', since: now },
        { id: 'd2', homeId: 'h1', type: 'homecam', location: '거실', status: 'ok', since: now },
        { id: 'd3', homeId: 'h1', type: 'cctv', location: '현관', status: 'ok', since: now },
        { id: 'd4', homeId: 'h2', type: 'homecam', location: '거실', status: 'disconnected', since: now - 3 * H, seedAgoMs: 3 * H },
        { id: 'd5', homeId: 'h2', type: 'homecam', location: '안방', status: 'ok', since: now }
      ],
      incidents: [],
      history: seedHistory(now),
      notifs: []
    };
  }

  /* 주소 검색 — 실제 주소 검색 API 로 교체 예정 */
  const ADDRESS_BOOK = [
    '서울 OO구 OO로 12 OO아파트', '서울 마포구 월드컵로 100 한빛아파트', '서울 송파구 올림픽로 300 푸른마을',
    '서울 강서구 공항대로 55 햇살빌라', '경기 성남시 분당구 정자로 21 가온마을', '경기 수원시 영통구 광교로 7 광교호수마을',
    'OO시 OO동 OO아파트', '부산 해운대구 해운대로 88 바다마을', '대구 수성구 달구벌대로 150 수성힐스',
    '인천 연수구 센트럴로 12 송도더샵', '대전 유성구 대학로 99 은하수아파트', '광주 북구 첨단로 31 첨단리슈빌'
  ];

  FD.API = {
    KEY, SESSION_KEY, uid,
    seedHistory,
    async loadSnapshot() {
      const cur = this.readSnapshot();
      if (cur && cur.version === 2) return cur;
      const seed = buildSeed(Date.now());
      this.writeSnapshot(seed);
      return seed;
    },
    readSnapshot() {
      try { const raw = localStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; } catch (e) { return null; }
    },
    writeSnapshot(state) {
      try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { console.error(e); }
    },
    resetSnapshot() {
      const seed = buildSeed(Date.now());
      this.writeSnapshot(seed);
      return seed;
    },
    readSession() { try { return localStorage.getItem(SESSION_KEY) || null; } catch (e) { return null; } }, // '__none__' = 로그아웃 상태
    writeSession(id) {
      try { if (id) localStorage.setItem(SESSION_KEY, id); else localStorage.removeItem(SESSION_KEY); } catch (e) { /* noop */ }
    },
    async searchAddress(q) {
      q = (q || '').trim();
      if (!q) return [];
      const key = q.replace(/\s+/g, '').toLowerCase();
      return ADDRESS_BOOK.filter(a => a.replace(/\s+/g, '').toLowerCase().includes(key)).slice(0, 6);
    }
  };
})();
