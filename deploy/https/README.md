# HTTPS 로 서버 공개하기 (3단계)

배포용 Android 앱은 HTTPS 서버에만 연결돼요 (Android 기본값: HTTP 금지, 공인 인증서만 믿음).
로그인 쿠키, 기기 토큰, 낙상 사진도 HTTPS 로만 오가야 해요. 이 문서는 **준비된 것**, **정해야 할 것**, **적용 순서**를 정리해요.

> 이 문서의 적용 단계(방화벽, 운영 서버 재시작, 도메인·인증서)는 **운영 환경을 바꾸는 작업**이라 승인을 받은 뒤에만 진행해요.

## 1. 지금 환경 (2026-10-26 확인)

| 항목 | 확인한 사실 |
|---|---|
| 서버 위치 | 이 Windows PC. `server/run_server.bat` 으로 `0.0.0.0:8000` (HTTP), 자동 시작 없음 |
| 네트워크 | 이 PC가 **공인 IP를 직접** 받음 (공유기 없음). 고정 IP인지는 모름 (통신사·학교에 확인 필요) |
| 방화벽 | Public 프로필에 `python.exe`(miniconda, 운영 서버가 실제로 쓰는 실행 파일) **모든 포트 허용** 규칙이 있음 → 운영 서버가 인터넷에 HTTP 로 열려 있을 수 있음 (바깥에서 확인하지는 못함) |
| 도메인 | 없음 (`PUBLIC_BASE_URL` 미설정) |
| HTTPS 도구 | Caddy·nginx·cloudflared·tailscale 없음 (설치 안 함) |

## 2. 방식 비교

| | A. 이 PC + 도메인 + Caddy (추천) | B. 터널 서비스 (Cloudflare Tunnel, Tailscale Funnel) | C. 클라우드 서버로 이전 |
|---|---|---|---|
| 비용 | 도메인만 (연 1~2만 원 정도, 무료 DDNS 도 가능) | 무료 요금제 있음 (가입 필요, Cloudflare 는 도메인 필요) | 월 수천~수만 원 + 도메인 |
| 필요한 것 | 도메인, 80·443 포트가 밖에서 열림, PC 항상 켜짐 | 서비스 가입, PC 항상 켜짐 | 서버 설정, DB·사진·비밀 정보 이전 |
| 인증서 | Caddy 가 Let's Encrypt 로 자동 발급·갱신 | 서비스가 자동 | Caddy 로 자동 |
| 장점 | 지금 구조 그대로, 공인 IP 가 이미 있음 | 포트를 열지 않아도 됨, 학교·통신사가 막아도 됨 | PC 를 꺼도 됨, 가장 안정적 |
| 단점 | 통신사·학교망이 80/443 을 막으면 불가, PC·전원 관리 | 외부 서비스에 의존, 주소 형식이 정해짐 | 비용, 이전 작업과 운영 관리 |

**추천: A** — 이 PC 가 이미 공인 IP 를 받고 있어서, 도메인 하나와 Caddy 만 있으면 지금 서버를 그대로 HTTPS 로 공개할 수 있어요.
막혀 있으면(아래 3번 확인) B, 오래 안정적으로 운영하려면 C 로 옮겨요. 어느 방식이든 서버는 **127.0.0.1 에서만** 받고 HTTPS 는 앞단(프록시·터널)이 맡는 구조라, 이번에 만든 설정은 그대로 써요.

## 3. 사용자가 정하거나 해 줄 일

1. **방식 결정** (A / B / C)
2. **도메인**: 구매(예: 가비아·Cloudflare 등) 또는 무료 DDNS. 정한 도메인의 A 레코드를 이 PC 공인 IP 로
3. **이 PC 의 IP 가 고정인지, 80·443 포트가 막혀 있지 않은지** 통신사·학교 전산실에 확인
4. **Caddy 설치 허락** (공식 사이트 또는 `winget install CaddyServer.Caddy`) — 설치 뒤 `caddy validate` 로 `Caddyfile.example` 검사부터

## 4. 이번에 준비해 둔 것 (운영에는 아직 적용 안 함)

| 파일 | 하는 일 |
|---|---|
| `deploy/https/Caddyfile.example` | Caddy 설정: 도메인 HTTPS, 자동 인증서, `127.0.0.1:8000` 으로 전달, HSTS, 접속 기록에서 토큰·쿠키·인증 헤더 제거 (**아직 실제 Caddy 로 검사하지 못함**) |
| `server/run_server_behind_proxy.bat` | 서버를 `127.0.0.1:8000` 에서만 실행, 프록시가 보낸 `X-Forwarded-*` 는 127.0.0.1 에서 온 것만 믿음 |
| `server/main.py` | 시작 안내에 공용 토큰 값을 더 이상 출력하지 않음(파일 위치만), 접속 기록의 `?token=` 가림, 옛 관리자 로그인 쿠키도 HTTPS 면 Secure |
| `mobile/scripts/sync-release.mjs` (`npm run sync:release`) | 배포용 앱 주소 넣기: HTTPS 가 아니거나 localhost 면 거절 |
| `mobile/android/app/build.gradle` (`debugNetworkConfig`) | debug 빌드에만 HTTP(localhost) 허용 + 로컬 시험용 개발 CA 를 localhost 에서만 믿음. release 빌드에는 없음 |
| `tools/dev_tls.py` | 로컬 HTTPS 시험용 개발 CA·인증서 (프로젝트 밖 `%LOCALAPPDATA%\FallDetection\dev-tls`) |

인증서 검사를 끄거나 모든 인증서를 믿게 하는 설정은 어디에도 없어요.

## 5. 적용 순서 (A 방식, 승인 후)

1. 운영 백업 (DB·데이터 파일·`.env`·토큰, 지난번 절차 그대로)
2. 작업 폴더를 `main` 으로 맞추고 운영 서버 재시작 (DB 구조 8 → 9)
3. 운영 서버를 `run_server_behind_proxy.bat` 으로 실행 (127.0.0.1:8000)
4. 방화벽: `python.exe` 의 Public 전체 허용 규칙 끄기 → Caddy 의 80·443 만 허용
5. `Caddyfile.example` → `Caddyfile`, `FD_DOMAIN`·`FD_ACME_EMAIL` 지정, `caddy validate` 후 `caddy run` (자동 실행은 서비스 등록)
6. 확인: `https://도메인/api/v2/health`, 인증서 발급자 Let's Encrypt, `http://도메인` 이 HTTPS 로 넘어가는지
7. Android: `FD_SERVER_URL=https://도메인/app/next/ npm run sync:release` → Android Studio 에서 release 빌드·서명
8. PC 감지 프로그램: `--server-url https://도메인/api/events` 로 실행 → 앱에서 연결 코드로 다시 연결 → 옛 관리자 등록(`legacy_devices.py remove laptop`) 삭제
9. 실제 폰(LTE)에서 앱 접속, 기기 연결, 낙상 시험

**되돌리기**: Caddy 를 끄고 `run_server.bat` 으로 실행, 방화벽 규칙 원래대로. DB 는 백업으로 복구 (MANIFEST.txt 의 순서).

## 6. 로컬 HTTPS 시험 (개발 PC 에서만)

```
server\venv\Scripts\python.exe tools\dev_tls.py
cd <복사본 서버 폴더>
...\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8443 --ssl-keyfile %LOCALAPPDATA%\FallDetection\dev-tls\server.key --ssl-certfile %LOCALAPPDATA%\FallDetection\dev-tls\server.pem
```
- PC 감지 프로그램: `SSL_CERT_FILE=%LOCALAPPDATA%\FallDetection\dev-tls\ca.pem` 을 주고 `--server-url https://localhost:8443/api/events`
- Android(에뮬레이터): `adb reverse tcp:8443 tcp:8443`, `FD_SERVER_URL=https://localhost:8443/app/next/ npm run sync:dev` 후 debug 빌드 (개발 CA 가 있으면 빌드에 자동 포함)

## 7. 남은 보안 메모

- 옛 관리자 로그인(`/login?token=...`)은 공용 토큰을 주소에 넣는 방식이라, 브라우저 기록에 남을 수 있어요. 접속 기록에서는 가렸지만, 외부 공개 뒤에는 이 주소를 공유하지 않거나 다른 로그인 방식으로 바꾸는 것을 권장해요.
- HSTS(1년)는 한 번 적용되면 브라우저가 그 도메인을 HTTPS 로만 열어요. 처음에는 짧게 시험한 뒤 늘리는 것이 안전해요.
