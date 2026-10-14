// 화면 이동: 주소 끝의 #/화면이름 (또는 #/화면이름/추가값) 으로 화면을 바꿉니다.
//   예) #/home, #/prevention, #/prevention/exercise, #/settings, #/role
import { getRole, ROLES } from "./storage.js";

// 역할별 하단 메뉴 [화면이름, 메뉴 글자]
const MENUS = {
  [ROLES.SELF]: [
    ["home", "홈"],
    ["prevention", "낙상 예방"],
    ["detection", "낙상 감지"],
    ["life", "생활 관리"],
    ["settings", "설정"],
  ],
  [ROLES.GUARDIAN]: [
    ["guardian", "보호자"],
    ["settings", "설정"],
  ],
};

// 역할별로 열 수 있는 화면 (메뉴에 없는 화면 포함). 역할 선택 화면은 언제나 열 수 있음
const ALLOWED = {
  [ROLES.SELF]: new Set(["home", "prevention", "detection", "life", "settings", "self", "role"]),
  [ROLES.GUARDIAN]: new Set(["guardian", "settings", "role"]),
};

export function homeFor(role) {
  return role === ROLES.GUARDIAN ? "guardian" : "home";
}

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

  function renderNav(name, role) {
    nav.replaceChildren();
    // 역할 선택 화면에는 메뉴를 숨김
    nav.hidden = name === "role" || !role;
    if (nav.hidden) return;
    for (const [item, label] of MENUS[role]) {
      const link = document.createElement("a");
      link.href = `#/${item}`;
      link.textContent = label;
      if (item === name) link.setAttribute("aria-current", "page");
      nav.append(link);
    }
  }

  function render() {
    const role = getRole();
    let { name, params } = parseHash();
    if (!role) {
      // 역할을 아직 고르지 않았으면 역할 선택부터
      name = "role";
      params = [];
    } else if (!screens[name] || !ALLOWED[role].has(name)) {
      // 없는 화면이거나 이 기기의 역할에서 열 수 없는 화면이면 내 역할의 첫 화면으로
      name = homeFor(role);
      params = [];
    }
    const path = [name, ...params].map(encodeURIComponent).join("/");
    if (location.hash !== `#/${path}`) {
      history.replaceState(null, "", `#/${path}`);
    }

    if (current && current.cleanup) current.cleanup();
    container.replaceChildren();
    container.classList.toggle("no-nav", name === "role");
    renderNav(name, role);
    const cleanup = screens[name].render(container, { ...context, go, params });
    current = { name, cleanup };
    container.focus();
  }

  window.addEventListener("hashchange", render);
  return { start: render, go };
}
