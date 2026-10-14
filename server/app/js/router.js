// 화면 이동: 주소 끝의 #/self, #/guardian, #/settings, #/role 로 화면을 바꿉니다.
import { getRole, ROLES } from "./storage.js";

// 화면마다 하단 메뉴에 보일 이름
const NAV_LABELS = { self: "본인", guardian: "보호자", settings: "설정" };

export function createRouter({ screens, container, nav, context }) {
  let current = null; // { name, cleanup }

  function homeFor(role) {
    return role === ROLES.GUARDIAN ? "guardian" : "self";
  }

  function go(name) {
    if (location.hash !== `#/${name}`) location.hash = `#/${name}`;
    else render();
  }

  function renderNav(name, role) {
    nav.replaceChildren();
    // 역할 선택 화면에는 메뉴를 숨김. 메뉴는 '내 역할 화면'과 '설정' 두 개만 (한 화면에 한 가지 일)
    nav.hidden = name === "role";
    if (nav.hidden) return;
    for (const item of [homeFor(role), "settings"]) {
      const link = document.createElement("a");
      link.href = `#/${item}`;
      link.textContent = NAV_LABELS[item];
      if (item === name) link.setAttribute("aria-current", "page");
      nav.append(link);
    }
  }

  function render() {
    const role = getRole();
    let name = location.hash.replace(/^#\//, "");
    if (!role) {
      // 역할을 아직 고르지 않았으면 역할 선택부터
      name = "role";
    } else if (!screens[name] || ((name === "self" || name === "guardian") && name !== homeFor(role))) {
      // 없는 화면이거나, 본인용 기기에서 보호자 화면(또는 반대)으로 가려 하면 내 역할 화면으로
      name = homeFor(role);
    }
    if (location.hash !== `#/${name}`) {
      history.replaceState(null, "", `#/${name}`);
    }

    if (current && current.cleanup) current.cleanup();
    container.replaceChildren();
    container.classList.toggle("no-nav", name === "role");
    renderNav(name, role);
    const cleanup = screens[name].render(container, { ...context, go });
    current = { name, cleanup };
    container.focus();
  }

  window.addEventListener("hashchange", render);
  return { start: render, go };
}
