# Human Fall Detection Using YOLOv12 and MediaPipe

![Program Preview](https://i.imgur.com/gutgsuN.png)

A real-time fall detection system using computer vision with YOLOv12 for person detection and MediaPipe for pose estimation. The system features an intuitive dashboard for monitoring and analyzing falls.

## 프로젝트 현황 (2026-11-05)

집 안 낙상사고를 AI로 감지해 가족에게 알리는 아이디어를 실제로 구현하고 시연하는 **프로토타입**입니다. 상용 서비스가 목적이 아닙니다.

처음에는 PC 낙상 감지 프로그램이었고, 지금은 Android 앱과 가족용 서비스까지 확장했습니다. 이 섹션 아래의 영어 설명은 주로 PC 프로그램과 초기 구조에 관한 내용입니다.

> **119 안전 규칙:** 이 프로토타입은 119에 전화나 문자를 보내거나 신고를 전달하지 않습니다. 앱의 119 신고는 앱 안의 기록으로만 남고, 서버 시험(`NeverContacts119Test`)으로 이 규칙을 고정해 두었습니다.

### 동작 흐름

1. 휴대폰이 카메라 영상을 기기 안에서 분석합니다.
2. 낙상으로 판단하면 서버에 사고를 만들고, 당사자 앱에 "괜찮으신가요?" 화면을 띄웁니다.
3. 60초 안에 응답이 없으면 가족에게 알립니다. 가족은 사고 사진과 대응 안내를 봅니다.
4. 가족이 맡거나 119 신고를 기록합니다. 가족 알림 뒤 180초 동안 아무도 확인하지 않으면 자동 신고로 기록합니다.
5. 처리 과정은 낙상 이력에 남습니다.

당사자가 "괜찮아요"를 누르면 사고가 끝나고 가족에게 긴급 알림이 가지 않습니다.

### 지금까지 만든 것

| 영역 | 내용 |
|---|---|
| 계정과 가족 | 회원가입, 로그인, 비밀번호 변경, 약관 동의 기록, 가족 그룹과 초대 코드, 사용자별 권한 |
| 집과 대상자 | 집 주소, 현관 출입 방식, 건강 정보, 낙상 대상자 관리 |
| 기기 연결 | 쓰던 휴대폰을 바로 연결하거나, 안 쓰는 휴대폰을 연결 코드로 연결 |
| Android 감지 | CameraX와 MediaPipe로 기기 안에서 분석, 백그라운드 감지 서비스, 카메라 멈춤 자동 복구 |
| 설치 도움 | 사람·전신·밝기 안내, 실루엣 미리보기, 폰 방향 보정, 절전·알림·충전·발열 안내 |
| 사고 대응 | 응답 카운트다운, 도움 요청, 가족 인계, 재감지 알림, 대응 안내, 119 신고 기록 |
| 가족 알림 | 앱 알림 내역, FCM 푸시, 기기 끊김, 배터리 부족, 신고 결과 알림 |
| 개인정보 | 원본 영상은 저장하거나 보내지 않음. 사고 사진은 배경과 사람을 가린 이미지만 사용 |
| 낙상 예방 | 집 안 점검과 생활 수칙 |
| 원격 시연 | Tailscale로 다른 망에서 접속. 공개 HTTPS는 사용하지 않음 |

### 시험 결과

| 시험 | 결과 |
|---|---|
| 서버 | 350개 통과 |
| 판정 로직과 PC 프로그램 | 112개 통과 |
| Android 단위 (JVM) | 72개 통과, 1개 건너뜀 |
| 브라우저 끝까지 시험 | 24개 통과 |
| 에뮬레이터 실제 앱 시험 | 46개 통과 |

2026-11-05에는 빈 시험 DB로 에뮬레이터와 브라우저를 나란히 띄워, 회원가입부터 낙상, 가족 인계, 119 신고 기록, 낙상 이력, 로그아웃과 다시 로그인까지 화면으로 확인했습니다.

모든 결과는 가상 환경 기준입니다. **실제 휴대폰으로는 아직 시험하지 않았습니다.**

### 알려진 한계

- **오탐이 많습니다.** 알림에 쓰는 옛 규칙은 시험한 일상 동작 34개 중 30개를 낙상으로 잡았습니다. 새 규칙(v2)은 기록만 남기며, 실제 휴대폰 시험 결과를 보고 전환을 결정합니다.
- 실제 카메라, 절전, 장시간 동작, 운영 서버 푸시 수신은 확인이 필요합니다.
- 비밀번호 재설정은 문자 인증이 없어 안내 문구만 있습니다.
- 약관은 법률 검토를 받지 않았고, 사고 대응 안내는 공식 원문 확인이 필요합니다.

### 폴더 안내

| 위치 | 내용 |
|---|---|
| `server/` | FastAPI 서버와 SQLite DB 코드 |
| `server/app/next/` | 가족용 웹앱. Android 앱도 이 화면을 사용 |
| `mobile/android/` | Android 앱과 기기 안 낙상 감지 |
| `fall_logic/` | 낙상 판정 규칙 |
| `tools/e2e/` | 브라우저·에뮬레이터 끝까지 시험 |
| `docs/` | 현황과 조사 문서 |

자세한 현황과 다음 작업은 [docs/PROTOTYPE_STATUS.md](docs/PROTOTYPE_STATUS.md), 파일 구분과 정리 기준은 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md), 원격 접속은 [docs/TAILSCALE.md](docs/TAILSCALE.md)에 있습니다.

### 실행 방법

| 대상 | 방법 |
|---|---|
| 서버 | `server` 폴더에 가상환경을 만든 뒤 `server\run_server.bat` 실행. 앱 주소는 `http://localhost:8000/app/next/` |
| PC 프로그램 | `python fall_detection_system.py --mode dashboard` |
| Android 앱 | [mobile/RELEASE.md](mobile/RELEASE.md) 참고 |
| 서버 시험 | `server\venv\Scripts\python.exe -m unittest discover -s server/tests -t server` |
| 판정 로직 시험 | `venv\Scripts\python.exe -m unittest discover -s tests -t .` |
| 끝까지 시험 | [tools/e2e/README.md](tools/e2e/README.md) 참고 |

## Features

- **Real-time Detection**: Process video feeds from webcams or video files in real-time
- **Fall Type Classification**: Distinguishes between four types of falls: step and fall, slip and fall, trip and fall, and stump and fall
- **Modern PyQt5 Dashboard**: User-friendly interface with statistics, charts, and history tracking
- **Multi-person Detection**: Can track and analyze multiple people simultaneously
- **Advanced Pose Analysis**: Monitors key body points (shoulders, hips, feet) to accurately assess falls
- **Adjustable Sensitivity**: Fine-tune detection thresholds for different environments
- **Intelligent Fall Counting**: Prevents duplicate counts with person tracking and cooldown periods
- **Automatic Fall Snapshot**: Captures and stores images when falls are detected
- **Sound Alerts**: Audio notifications when falls are detected
- **Command Line Mode**: Also supports a headless command-line mode for deployments

## Requirements

- Python 3.12 (tested on Windows; MediaPipe 0.10.14 has no wheels for Python 3.13)
- CPU-only PyTorch by default (see GPU note below)
- Exact versions are pinned in `requirements.txt` (detection program) and `server/requirements.txt` (web server)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/rladustn1467-sketch/Human-Fall-Detection-Yolov12-Mediapipe.git
   cd Human-Fall-Detection-Yolov12-Mediapipe
   ```

2. Create a virtual environment for the detection program and install requirements:
   ```
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   `requirements-working.txt` lists the exact version of every package in a tested
   environment and can be used instead to reproduce it exactly.

3. Create a separate virtual environment for the web server:
   ```
   cd server
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Download YOLOv12 model (automatic on first run, or manually place in project root)

**GPU (optional):** the default PyPI build of PyTorch on Windows is CPU-only. To use an
NVIDIA GPU, first install the CUDA build of `torch` and `torchvision` (same versions as in
`requirements.txt`) from the PyTorch index following https://pytorch.org/get-started/locally/,
then install `requirements.txt`. Separate `nvidia-*-cu11` packages are not needed.

**Do not upgrade MediaPipe to 1.x:** it removed the `mp.solutions` API that this project uses.

**Telegram alerts (optional):** the server can send a Telegram message when nobody responds
within the response time limit, when the user asks for help, and a correction when the user
later answers that they are okay. Copy `server/.env.example` to `server/.env` and fill in
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then restart the server. `server/.env` is in
`.gitignore`; never commit it. Without these values the server logs "텔레그램 설정 없음" and
runs without alerts. Each "help" press sends a numbered alert again, except presses within
`HELP_ALERT_COOLDOWN` seconds (default 10) of the previous help alert. "No response" and "help"
alerts include the privacy-processed photo (blurred background, solid silhouette) when the fall
has one; if the photo cannot be sent, the text is sent alone. Alert rules live in
`server/notify_rules.py`, delivery channels in `server/notifiers.py`.

**Guardian escalation and 119 report (simulation only):** "no response" and "help" alerts carry
two Telegram buttons, "확인했어요" (stop the automatic report) and "119 신고해주세요" (report now).
If no guardian presses a button within `GUARDIAN_WAIT_AFTER_TIMEOUT` seconds (default 180) after a
no-response alert, or `GUARDIAN_WAIT_AFTER_HELP` seconds (default 90) after a help alert, the
server records a **simulated** 119 report and tells the guardians, with the photo, the fall time,
the state and `REPORT_ADDRESS` / `REPORT_CONTACT` from `server/.env`. **No real call or report is
ever made.** If the person answers "괜찮아요" before the report, the scheduled report is cancelled;
after the report, guardians get a "cancel request" alert. Several guardians can be listed in
`TELEGRAM_CHAT_ID` separated by commas; one "확인했어요" is enough. Button presses are received
with Telegram `getUpdates` polling (no public address needed), and only presses from listed chat
IDs are accepted. Run only one server per bot token. Rules live in `server/escalation.py`.

**Residents and report contents:** resident profiles (alias, age, conditions, medications, update
date) go in `server/residents.json` (copy `server/residents.example.json`; the real file is in
`.gitignore`). With one resident the fallen person is set automatically; with two or more, guardians
pick "누가 쓰러졌나요?" in Telegram or on the record page (this never stops the automatic report
wait). The simulated report includes the address, door codes (`DOOR_CODE`, `BUILDING_DOOR_CODE`),
guardian contact and the fallen person's medical info; if nobody was picked, medical info is left out
(`REPORT_UNCONFIRMED_MEDICAL=all` includes everyone). Telegram only lists the item names; the values
are shown only on the record page `/reports/<event id>` and are never stored in `events.json`, logs or
messages. `REPORT_PAGE_ACCESS=local` limits that page to this PC. Decided in `server/report119.py`.
The report alert has a "📄 상세 보기" button: a registered guardian who presses it gets the same
details as the report page as a reply in their own chat (useful when the phone cannot reach the
server PC). Turn it off with `SHOW_DETAIL_IN_TELEGRAM=false` before using real information, since
messages stay on Telegram's servers and the phone. A web link is added only when `PUBLIC_BASE_URL`
is set.

**User web app (`/app`, work in progress):** a large-text app for the whole family, served by
the same server from `server/app/` (plain HTML/CSS/JS, no build step). Log in once with
`/login?token=...&next=/app`. Devices are not split into "person" and "guardian": any family member
can be watched by the detector and can also receive alerts. Menus: 홈, 낙상 예방, 낙상 감지, 생활 관리, 설정.
While the app is open, a fall that needs an answer is shown on top of any menu with big "괜찮아요" /
"도움이 필요해요" buttons and the remaining time (no web push yet; Telegram alerts work as before).
Fall prevention content lives in `server/app/content/prevention/` (see its README). Colors and sizes are
in `server/app/css/theme.css`, the polling interval in `server/app/js/config.js`.

**New family web app (`/app/next/`, being connected to the server):** the Genspark design in
`server/app/next/`. It opens without the access token (sign-up must be reachable); its data API
(`/api/v2/...`) is protected per user from stage B on. Real mode (default) uses only server data;
`?mode=test` and `dev.html` use built-in sample data in the browser and never call the server (see
`server/app/next/README.md`). Its data is kept in an SQLite file `server/fall.db` (created on server start,
in `.gitignore`; set `FALL_DB_PATH` to use another file). `events.json` and `residents.json` are not moved
into it yet. Server tests: `server\venv\Scripts\python.exe -m unittest discover -s server/tests -t server`
(they run a copy of the server in a temporary folder and never touch the real data).

**Privacy:** only the processed silhouette image leaves the dashboard; original camera frames
are never sent to the server or saved (the raw fall snapshot option is disabled).

## Usage

### Dashboard Mode (Recommended)

```
python fall_detection_system.py --mode dashboard
```

**Testing without a webcam:** put photos in `test_images/` (ignored by git). In the dashboard,
**F9** creates a fake fall; with no camera frame it uses a random photo from `test_images/` as the
camera frame (with an empty folder it sends a fake fall without a photo). **Shift+F9** lets you
pick the photo. Or start with a photo:

```
python fall_detection_system.py --mode dashboard --test-image test_images/lying.jpg
```

Photo tests follow the real path (person detection, privacy processing, server upload, alerts),
and the processed image is also saved to `test_output/` for checking.

### Command Line Mode

```
python fall_detection_system.py --mode cli --source 0
```

### Options

- `--mode`: Application mode (`dashboard` or `cli`)
- `--model`: Path to YOLOv12 model file (default: `yolov12n1.pt`)
- `--conf`: Detection confidence threshold (0-1)
- `--source`: Video source (0 for webcam, or path to video file)
- `--fall-threshold`: Threshold for fall detection sensitivity (0-1)
- `--angle-threshold`: Threshold for body angle in degrees (0-90)
- `--save-falls`: Save frames when falls are detected
- `--output-dir`: Directory to save fall snapshots

## System Architecture

The system consists of several key components:

1. **YOLOv12 Person Detection**: Identifies people in the video frames
2. **MediaPipe Pose Estimation**: Extracts skeletal data from detected persons
3. **Fall Detection Algorithm**: Analyzes pose data to detect falls with these criteria:
   - Body angle relative to vertical
   - Body aspect ratio (horizontal vs. vertical orientation)
   - Sudden vertical position changes
   - Motion pattern analysis
4. **Person Tracking**: Follows individuals across frames to maintain identity
5. **PyQt5 Dashboard**: Provides real-time monitoring and analytics

## Fall Classification Criteria

- **Step and Fall**: Gradual angle change with moderate velocity
- **Slip and Fall**: Rapid angle change with high velocity
- **Trip and Fall**: Forward momentum with moderate angle change
- **Stump and Fall**: Minimal horizontal movement with significant vertical drop

## Project Structure

```
fall-detection-system/
├── models/
│   └── fall_detector.py        # Core fall detection model
├── dashboard/
│   └── dashboard_app.py        # PyQt5 Dashboard UI application
├── fall_logic/                 # Fall rules shared by the PC program and tests
├── utils/
│   └── utils.py                # Utility functions
├── server/                     # FastAPI server and family web app
├── mobile/                     # Current Android app
├── tools/                      # Evaluation and end-to-end test tools
├── tests/                      # Detection logic tests
├── docs/                       # Status and project documents
├── fall_detection_system.py    # Main application script
├── yolov12n1.pt                # Default YOLO model
├── README.md                   # Project documentation
└── requirements.txt            # Detection program dependencies
```

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for what each part is used for.

## Recent Improvements

- Enhanced fall detection algorithm with stricter criteria
- Added cooldown periods to prevent duplicate fall counts
- Improved sensitivity controls for different environments
- Added comprehensive fall type classification
- Fixed critical point detection for more accurate pose analysis
- Improved error handling for camera access and processing
- Optimized snapshot saving to reduce disk usage
- Migrated from Tkinter to PyQt5 for a more modern interface

## Future Enhancements

- Email notification system for alerting caregivers
- Integration with mobile applications
- Support for distributed camera networks
- Fall risk prediction based on movement patterns
- Cloud integration for remote monitoring
- AI-assisted fall risk prediction

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- YOLOv12 by Ultralytics (https://github.com/ultralytics/ultralytics)
- MediaPipe by Google (https://mediapipe.dev/)
- PyQt5 Dashboard inspiration from modern monitoring applications 
