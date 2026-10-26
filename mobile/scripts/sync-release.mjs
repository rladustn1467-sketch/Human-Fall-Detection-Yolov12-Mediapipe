// 배포용 동기화: 앱이 HTTPS 서버의 웹앱을 불러오도록 주소를 넣고 `cap sync android` 실행.
// 사용: FD_SERVER_URL=https://도메인/app/next/ npm run sync:release   (그다음 Android Studio 에서 release 빌드·서명)
// HTTPS 가 아닌 주소는 거절함: 배포용 빌드는 HTTP 를 허용하지 않아서(network security 기본값) 앱이 열리지 않고,
// 로그인 쿠키·기기 토큰이 암호화 없이 오가게 되기 때문. 개발용은 sync:dev (HTTP localhost) 를 씀
import { spawnSync } from 'node:child_process';

const url = (process.env.FD_SERVER_URL || '').trim();
let parsed = null;
try {
  parsed = new URL(url);
} catch {
  /* 아래에서 안내 */
}
if (!parsed || parsed.protocol !== 'https:') {
  console.error('[sync:release] FD_SERVER_URL 에 HTTPS 주소를 넣어 주세요. 예) FD_SERVER_URL=https://fall.example.com/app/next/');
  process.exit(2);
}
if (['localhost', '127.0.0.1', '10.0.2.2'].includes(parsed.hostname)) {
  console.error('[sync:release] 배포용에는 실제 서버 도메인을 넣어 주세요 (localhost 는 개발용 sync:dev).');
  process.exit(2);
}
console.log(`[sync:release] 서버 주소: ${parsed.href}`);
const r = spawnSync('npx', ['cap', 'sync', 'android'], {
  stdio: 'inherit',
  shell: true,
  env: { ...process.env, FD_SERVER_URL: parsed.href },
});
process.exit(r.status ?? 1);
