// 개발용 동기화: 앱이 PC의 시험 서버(기본 복사본 8001)를 불러오도록 설정을 넣고 `cap sync android` 실행.
// 다른 주소: FD_SERVER_URL=http://localhost:8000/app/next/ npm run sync:dev
// 에뮬레이터·USB 연결 폰에서 localhost 가 PC를 가리키도록 먼저: adb reverse tcp:8001 tcp:8001
import { spawnSync } from 'node:child_process';

const url = process.env.FD_SERVER_URL || 'http://localhost:8001/app/next/';
console.log(`[sync:dev] 서버 주소: ${url}`);
const r = spawnSync('npx', ['cap', 'sync', 'android'], {
  stdio: 'inherit',
  shell: true,
  env: { ...process.env, FD_SERVER_URL: url },
});
process.exit(r.status ?? 1);
