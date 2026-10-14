// 이 기기의 역할(본인용/보호자용)을 브라우저에 저장
// 사생활 보호 모드 등으로 저장할 수 없으면 오류 없이 넘어가고, 다음에 다시 고르게 됩니다.

const ROLE_KEY = "fallapp.role";
export const ROLES = { SELF: "self", GUARDIAN: "guardian" };

export function getRole() {
  try {
    const role = localStorage.getItem(ROLE_KEY);
    return role === ROLES.SELF || role === ROLES.GUARDIAN ? role : null;
  } catch {
    return null;
  }
}

export function setRole(role) {
  try {
    localStorage.setItem(ROLE_KEY, role);
  } catch {
    // 저장 실패: 이번 방문 동안만 화면이 유지됨
  }
}

export function clearRole() {
  try {
    localStorage.removeItem(ROLE_KEY);
  } catch {
    // 무시
  }
}
