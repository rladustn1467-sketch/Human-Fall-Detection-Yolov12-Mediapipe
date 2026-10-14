// 앱 시작점: 공통 모듈을 준비하고 화면 이동을 시작합니다.
import { CONFIG } from "./config.js";
import { api } from "./api.js";
import { createPoller } from "./poller.js";
import { createRouter } from "./router.js";
import * as roleScreen from "./screens/role.js";
import * as selfScreen from "./screens/self.js";
import * as guardianScreen from "./screens/guardian.js";
import * as settingsScreen from "./screens/settings.js";

// 현재 낙상 상태를 몇 초마다 가져오는 공통 폴링 (가장 최근 낙상 1건)
const statusPoller = createPoller(() => api.latestEvents(1), CONFIG.pollIntervalSeconds);

const router = createRouter({
  screens: { role: roleScreen, self: selfScreen, guardian: guardianScreen, settings: settingsScreen },
  container: document.getElementById("screen"),
  nav: document.getElementById("nav"),
  context: { api, statusPoller, config: CONFIG },
});

statusPoller.start();
router.start();
