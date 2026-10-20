// 화면 이동: 주소 끝의 #/화면이름 (또는 #/화면이름/추가값) 으로 화면을 바꿉니다.
//   예) #/home, #/prevention, #/prevention/exercise, #/settings
// 기기마다 '본인용/보호자용' 같은 역할을 나누지 않습니다. 가족 누구나 같은 메뉴를 씁니다.

// 하단 메뉴 [화면이름, 메뉴 글자]
const MENU = [
  ["home", "홈"],
  ["prevention", "낙상 예방"],
  ["detection", "낙상 감지"],
  ["life", "생활 관리"],
  ["settings", "설정"],
];
const HOME = "home";

function parseHash() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  return { name: parts[0] || "", params: parts.slice(1) };
}

export function createRouter({ screens, container, nav, context }) {
  let current = null; // { name, cleanup }

  // go("prevention") 또는 go("prevention/exercise")
  function go(path) {
    if (location.hash !== `#/${path}`) location.hash = `#/${path}`;
    else render();
  }

  function renderNav(name) {
    nav.replaceChildren();
    nav.hidden = false;
    for (const [item, label] of MENU) {
      const link = document.createElement("a");
      link.href = `#/${item}`;
      link.textContent = label;
      if (item === name) link.setAttribute("aria-current", "page");
      nav.append(link);
    }
  }

  function render() {
    let { name, params } = parseHash();
    if (!screens[name]) {
      // 없는 화면이면 (예전 주소 #/role, #/guardian 포함) 홈으로
      name = HOME;
      params = [];
    }
    const path = [name, ...params].map(encodeURIComponent).join("/");
    if (location.hash !== `#/${path}`) {
      history.replaceState(null, "", `#/${path}`);
    }

    if (current && current.cleanup) current.cleanup();
    container.replaceChildren();
    renderNav(name);
    const cleanup = screens[name].render(container, { ...context, go, params });
    current = { name, cleanup };
    container.focus();
  }

  window.addEventListener("hashchange", render);
  return { start: render, go };
}
