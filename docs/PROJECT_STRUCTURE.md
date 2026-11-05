# 프로젝트 구조

- **기준일:** 2026-11-05
- 저장소 구성과 파일 정리의 기준 문서입니다.

## 저장소 구성

| 저장소 | 역할 | 수정 |
|---|---|---|
| `Human-Fall-Detection-Yolov12-Mediapipe` | 전체 개발 원본 | 여기서 고칩니다 |
| [`fall`](https://github.com/rladustn1467-sketch/fall) | 학교 서버 배포 전용 (서버 + 웹앱) | 직접 고치지 않습니다 |

서버 하나가 웹앱 화면과 API 를 함께 제공하므로 공개 주소는 하나입니다. Android 앱은 서버가 아니라 APK 로 폰에 설치되며, 이 주소를 찾아갑니다.

## 폴더

```text
저장소
├─ server/      서버 + 웹앱 (server/app/next/)
├─ mobile/      Android 앱과 기기 안 낙상 감지
├─ pc/          PC 프로그램, YOLO 모델, PC용 설치 목록
├─ fall_logic/  판정 규칙의 Python 구현. 시험과 평가 도구가 사용
├─ tools/       평가 도구, 끝까지 시험(e2e), 배포 복사(export_deploy.py)
├─ tests/       판정 로직과 도구 시험
├─ deploy/      school/ 학교 서버 배포 파일, https/ 직접 HTTPS 구성 참고 자료
└─ docs/        현황과 조사 문서
```

- 웹앱과 서버는 같은 서버가 제공하므로 `server/` 에 함께 둡니다.
- Android 앱 화면은 서버의 웹앱을 불러옵니다. 카메라 감지만 앱 안에서 합니다.

## 배포 절차

1. 원본 저장소에서 고치고 시험합니다.
2. 배포용 저장소로 복사합니다. git 에 등록된 파일만 복사하고, 비밀 값으로 보이는 내용이 있으면 실패합니다.

   ```powershell
   python tools\export_deploy.py <fall 저장소 폴더>
   ```

3. `fall` 저장소에서 커밋하고 푸시합니다.
4. 학교 서버에서 `git pull` 뒤 `deploy restart` 를 합니다. 처음에는 `deploy` 를 합니다.

학교 서버 설정은 `deploy/school/env.example` 을 보세요.

## 분류

| 분류 | 뜻 | 대상 |
|---|---|---|
| A | 실행에 꼭 필요 | `server/` (시험 제외), `mobile/`, `pc/dashboard/`, `pc/models/`, `pc/utils/`, `pc/fall_detection_system.py`, `pc/yolov12n1.pt`, `pc/requirements.txt` |
| B | 개발과 시험에 필요 | `server/tests/`, `tests/`, `tools/`, `fall_logic/`, `pc/requirements-working.txt`, `server/app/next/dev.html`, `server/app/next/js/dev.js` |
| C | 문서와 참고 자료 | `README.md`, `docs/`, `mobile/RELEASE.md`, `deploy/https/` |
| D | 지금은 안 쓰지만 나중에 필요할 수 있음 | `pc/yolov12m.pt`, `pc/yolov12n.pt`, `pc/yolov8n.pt`, `pc/checkcuda.py`, `server/run_server_behind_proxy.bat` |

옛 Android 앱 `android/` 와 옛 단독 실행 파일 `fall_detection.py` 는 2026-11-05 에 삭제했습니다. Git 기록에는 남아 있습니다.

## 판단 근거

- **기본 모델은 `yolov12n1.pt` 하나입니다.** 나머지 `.pt` 는 대시보드의 파일 선택이나 `--model` 로만 쓸 수 있습니다.
- **Android 감지는 YOLO 를 쓰지 않습니다.** `pose_landmarker_full.task` 를 빌드 때 받아 `build/generated/poseModel/` 에 둡니다. 저장소에는 없습니다.
- **`server/app/` 의 옛 화면은 지우면 안 됩니다.** `/app` 경로가 살아 있고 시험도 있습니다.
- **`pyarrow` 는 설치 목록에 없지만 필요합니다.** `tools/caucafall_prepare.py` 가 불러옵니다.
- **NVIDIA 용 PyTorch 는 지워도 되는 패키지가 아닙니다.** 이 PC 의 PC 프로그램이 GPU 로 YOLO 를 돌립니다.
- **불러오는 코드가 없는 함수:** `dashboard_app.py` 의 `save_fall_snapshot`, `fall_detector.py` 의 `_check_critical_points_ratio`. PC 프로그램 원본과 비교하는 시험의 기준 코드라 그대로 둡니다.

## Git 에 올리는 것과 로컬에만 두는 것

| 구분 | 내용 |
|---|---|
| Git | 소스 코드, 시험, 문서, 설정 예시, 모델 4개 |
| 로컬 전용 | 비밀 값(`server/.env`, `server/access_token.txt`, `google-services.json`, 서명 키), 사용자 데이터(`server/fall.db`, `events.json`, `residents.json`, `server/images/`, `server/backups/`) |
| 다시 만들 수 있음 | `venv/`, `server/venv/`, `mobile/node_modules/`, `mobile/android/**/build/`, `.gradle/`, `__pycache__/` |
| 시간이 많이 드는 결과물 | `eval_output/`. 규칙 평가와 골든 파일 생성의 입력이라 지우지 않습니다 |
| 저장소 밖 | `../datasets/` (시험용 영상 데이터) |

## 주의

- `mobile/node_modules` 는 작업 폴더마다 링크입니다. `wt-eval` → `wt6` → 메인 폴더 순서로 이어지므로, `wt6` 나 메인 폴더의 `node_modules` 를 지우면 `wt-eval` 빌드가 깨집니다.
- 저장소 크기의 대부분은 모델 4개입니다. 파일을 지워도 Git 기록에 남으므로 기록을 다시 쓰기 전에는 저장소가 줄지 않습니다.
