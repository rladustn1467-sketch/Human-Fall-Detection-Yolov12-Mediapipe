// 앱 시작점: 공통 모듈을 준비하고 화면 이동과 사고 대응 레이어를 시작합니다.
import { CONFIG } from "./config.js";
import { api, AuthError } from "./api.js";
import { startIncidentLayer } from "./incident/layer.js";
import { createPoller } from "./poller.js";
import { createRouter } from "./router.js";
import * as detectionScreen from "./screens/detection.js";
import * as homeScreen from "./screens/home.js";
import * as lifeScreen from "./screens/life.js";
import * as preventionScreen from "./screens/prevention.js";
import * as selfScreen from "./screens/self.js";
import * as settingsScreen from "./screens/settings.js";

// 예전 버전이 브라우저에 저장한 '본인용/보호자용' 역할 값은 더 이상 쓰지 않으므로 지움
try {
  localStorage.removeItem("fallapp.role");
} catch {
  // 저장소를 쓸 수 없는 환경이면 무시
}

// 현재 낙상 상태를 몇 초마다 가져오는 공통 폴링 (가장 최근 낙상 1건)
const statusPoller = createPoller(() => api.latestEvents(1), CONFIG.pollIntervalSeconds);

const router = createRouter({
  screens: {
    home: homeScreen,
    prevention: preventionScreen,
    detection: detectionScreen,
    life: lifeScreen,
    settings: settingsScreen,
    self: selfScreen,
  },
  container: document.getElementById("screen"),
  nav: document.getElementById("nav"),
  context: { api, statusPoller, config: CONFIG },
});

// 앱 전체 안내 줄: 로그인 필요 / 서버 연결 끊김 (이전 정보가 보이고 있을 수 있음을 알림)
const globalNotice = document.getElementById("global-notice");
statusPoller.subscribe(({ error }) => {
  if (error instanceof AuthError) {
    globalNotice.textContent = "로그인이 필요해요. 서버 창에 표시된 로그인 주소(…/login?token=…&next=/app)로 한 번 접속해 주세요.";
  } else if (error) {
    globalNotice.textContent = "서버에 연결할 수 없어요. 화면의 정보는 마지막으로 받은 것일 수 있어요. 다시 시도하고 있어요.";
  }
  globalNotice.hidden = !error;
});

// 사고 대응 레이어: 어느 기기에서든, 어느 메뉴에 있든 확인이 필요한 낙상이 있으면 맨 위에 띄움
startIncidentLayer({
  layer: document.getElementById("incident"),
  banner: document.getElementById("incident-banner"),
  api,
  statusPoller,
  config: CONFIG,
});

statusPoller.start();
router.start();
