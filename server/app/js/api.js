// 서버와 통신하는 공통 코드
// 로그인은 기존 방식 그대로: /login?token=... 으로 한 번 접속하면 브라우저에 쿠키가 저장되고,
// 이후 요청에 그 쿠키가 자동으로 함께 갑니다 (토큰을 코드에 쓰지 않음).

// 로그인이 안 되어 있을 때 (서버가 401 응답)
export class AuthError extends Error {}

async function request(method, path, body) {
  const options = { method, credentials: "same-origin", cache: "no-store", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (response.status === 401) throw new AuthError("로그인이 필요합니다");
  if (!response.ok) throw new Error(`서버 오류 (HTTP ${response.status})`);
  return response.json();
}

// 화면들이 쓰는 API 목록 (기존 서버 API 그대로)
export const api = {
  // 최근 낙상 기록 (가장 최근 것이 맨 앞)
  latestEvents: (limit = 1) => request("GET", `/api/events?limit=${limit}`),
  // 낙상 1건
  getEvent: (eventId) => request("GET", `/api/events/${encodeURIComponent(eventId)}`),
  // 본인 응답: "safe"(괜찮아요) 또는 "help_needed"(도움이 필요해요)
  respond: (eventId, response) =>
    request("POST", `/api/events/${encodeURIComponent(eventId)}/response`, { response }),
};
