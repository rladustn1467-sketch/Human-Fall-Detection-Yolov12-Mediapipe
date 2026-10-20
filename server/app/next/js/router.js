/* ------------------------------------------------------------------
 * router.js — 해시 기반 라우터 + 탭바
 * 화면은 FD.Router.register(패턴, 렌더함수, 옵션)으로 등록합니다.
 *   렌더함수(params) → html 문자열 | { html, mount(el) }
 *   옵션: { tab: 'home'|'prevent'|'family'|'settings', live: true(스토어 변경 시 다시 그림), parent: '뒤로 갈 경로' }
 * ------------------------------------------------------------------ */
(function () {
  const FD = (window.FD = window.FD || {});
  const { ic } = FD.UI;
  const routes = [];
  let navs = 0;
  let cur = null;           // { route, params, path }
  let guard = null;
  let backing = false;
  let skip = 0;
  function replaceHash(p) {
    if (location.hash.slice(1) === p || (p === '/' && !location.hash)) { render(false); return; }
    skip++; location.replace('#' + p);
  }

  const TABS = [
    { id: 'home', label: '홈', icon: 'house', path: '/' },
    { id: 'prevent', label: '예방', icon: 'shield-heart', path: '/prevent' },
    { id: 'family', label: '가족', icon: 'user-group', path: '/family' },
    { id: 'settings', label: '설정', icon: 'gear', path: '/settings' }
  ];

  function register(pattern, render, opts) {
    const keys = [];
    const re = new RegExp('^' + pattern.replace(/:[^/]+/g, m => { keys.push(m.slice(1)); return '([^/]+)'; }) + '$');
    routes.push({ pattern, re, keys, render, opts: opts || {} });
  }
  const path = () => { const h = location.hash.slice(1).split('?')[0]; return h ? h : '/'; };
  const query = () => new URLSearchParams(location.hash.split('?')[1] || '');
  function match(p) {
    for (const r of routes) {
      const m = r.re.exec(p);
      if (m) { const params = {}; r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); }); return { route: r, params }; }
    }
    return null;
  }
  function go(p, o) {
    if (o && o.replace) { replaceHash(p); }
    else if (location.hash.slice(1) === p || (p === '/' && !location.hash)) { render(false); }
    else { location.hash = p; }
  }
  function back(fallback) {
    if (navs > 0) { navs--; backing = true; history.back(); return; }
    go(fallback || (cur && cur.route.opts.parent) || '/', { replace: true });
  }

  function renderTabbar(active) {
    const el = document.getElementById('tabbar');
    if (!el) return;
    if (!active) { el.hidden = true; el.innerHTML = ''; return; }
    el.hidden = false;
    const alert = FD.Store.Sel.incidentsFor().some(i => !FD.Store.Sel.isTerminal(i));
    el.innerHTML = TABS.map(t => `<a class="tab${t.id === active ? ' is-active' : ''}" href="#${t.path}" aria-current="${t.id === active ? 'page' : 'false'}">
      ${ic(t.icon)}<span>${t.label}</span>${t.id === 'home' && alert ? '<i class="tab__dot" aria-label="진행 중인 낙상 알림"></i>' : ''}</a>`).join('');
  }

  function render(isRefresh) {
    const p = path();
    if (guard) {
      const redirect = guard(p);
      if (redirect && redirect !== p) { replaceHash(redirect); return; }
    }
    let m = match(p);
    if (!m) { replaceHash('/'); return; }
    const view = document.getElementById('view');
    const prevScroll = window.scrollY;
    const out = m.route.render(m.params, { refresh: !!isRefresh });
    const html = typeof out === 'string' ? out : out.html;
    const tab = m.route.opts.tab || null;
    view.innerHTML = `<div class="view${tab ? ' has-tabbar' : ''}" data-route="${FD.UI.esc(m.route.pattern)}">${html}</div>`;
    cur = { route: m.route, params: m.params, path: p };
    renderTabbar(tab);
    if (out && out.mount) out.mount(view.firstElementChild, m.params);
    FD.UI.tick(view);
    if (isRefresh) window.scrollTo(0, prevScroll); else window.scrollTo(0, 0);
  }

  window.addEventListener('hashchange', () => {
    if (skip > 0) skip--; else if (backing) backing = false; else navs++;
    FD.UI.closeSheet(true);
    render(false);
  });

  function start() { render(false); }
  function refresh() { if (cur && cur.route.opts.live) render(true); else if (cur && cur.route.opts.tab) renderTabbar(cur.route.opts.tab); }
  function setGuard(fn) { guard = fn; }
  function current() { return cur; }

  FD.Router = { register, go, back, start, refresh, setGuard, current, path, query };
})();
