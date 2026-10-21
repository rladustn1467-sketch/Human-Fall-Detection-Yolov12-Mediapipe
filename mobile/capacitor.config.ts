import type { CapacitorConfig } from '@capacitor/cli';

// 앱이 불러올 웹앱 주소. 개발할 때만 `npm run sync:dev` 가 FD_SERVER_URL 로 넣어 줌.
// 주소가 없으면 앱 안의 www/index.html (서버 주소가 설정되지 않았다는 안내)만 보임.
const serverUrl = process.env.FD_SERVER_URL;

const config: CapacitorConfig = {
  appId: 'com.humanfall.app',
  appName: '낙상 지킴이',
  webDir: 'www',
  // HTTP 허용은 여기서 켜지 않음 (켜면 모든 빌드에 적용됨).
  // debug 빌드만 android/app/src/debug/res/xml/network_security_config.xml 로 localhost 등에 허용.
  ...(serverUrl ? { server: { url: serverUrl } } : {}),
  plugins: {
    // 뒤로 가기는 MainActivity 가 처리 (이전 화면이 없으면 앱을 백그라운드로)
    App: { disableBackButtonHandler: true },
  },
};

export default config;
