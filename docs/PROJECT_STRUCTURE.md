# 프로젝트 구조

- **기준일:** 2026-11-05
- 파일 정리의 기준 문서입니다. 삭제 후보는 사용자 확인 전에는 지우지 않습니다.

## 분류

| 분류 | 뜻 | 대상 |
|---|---|---|
| A | 실행에 꼭 필요 | `server/` (시험 제외), `mobile/android/`, `mobile/package*.json`, `mobile/scripts/`, `fall_logic/`, `models/`, `dashboard/`, `utils/`, `fall_detection_system.py`, `yolov12n1.pt`, `requirements.txt` |
| B | 개발과 시험에 필요 | `server/tests/`, `tests/`, `tools/`, `requirements-working.txt`, `server/app/next/dev.html`, `server/app/next/js/dev.js` |
| C | 문서와 참고 자료 | `README.md`, `docs/`, `fall_detection_algorithm.md`, `mobile/RELEASE.md`, `deploy/https/` |
| D | 지금은 안 쓰지만 나중에 필요할 수 있음 | `yolov12m.pt`, `yolov12n.pt`, `yolov8n.pt`, `checkcuda.py`, `server/run_server_behind_proxy.bat` |
| E | 불필요로 판단. 삭제 확인 대기 | 옛 Android 앱 `android/`, 옛 단독 실행 파일 `fall_detection.py` |

## 판단 근거

- **기본 모델은 `yolov12n1.pt` 하나입니다.** 나머지 `.pt` 는 대시보드의 파일 선택이나 `--model` 로만 쓸 수 있습니다.
- **Android 감지는 YOLO 를 쓰지 않습니다.** `pose_landmarker_full.task` 를 빌드 때 받아 `build/generated/poseModel/` 에 둡니다. 저장소에는 없습니다.
- **`android/` 는 첫 Android 앱입니다.** 현재 앱은 `mobile/android/` 이고, 코드 어디에서도 `android/` 를 쓰지 않습니다.
- **`fall_detection.py` 는 `models/fall_detector.py` 이전의 단독 실행 파일입니다.** 다른 코드가 불러오지 않습니다. 내용이 달라 완전한 중복은 아닙니다.
- **`server/app/` 의 옛 화면은 지우면 안 됩니다.** `/app` 경로가 살아 있고 시험도 있습니다.
- **`pyarrow` 는 `requirements.txt` 에 없지만 필요합니다.** `tools/caucafall_prepare.py` 가 불러옵니다.
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

## 배포에 필요한 것

서버 실행에는 `server/` 와 `server/requirements.txt` 만 필요합니다. 앱 설치 파일은 `mobile/` 에서 만듭니다. YOLO 모델, `torch`, `eval_output/`, `tools/` 는 서버 실행에 쓰이지 않습니다.

## 주의

- `mobile/node_modules` 는 작업 폴더마다 링크입니다. `wt-eval` → `wt6` → 메인 폴더 순서로 이어지므로, `wt6` 나 메인 폴더의 `node_modules` 를 지우면 `wt-eval` 빌드가 깨집니다.
- 저장소 크기의 대부분은 모델 4개입니다. 파일을 지워도 Git 기록에 남으므로 기록을 다시 쓰기 전에는 저장소가 줄지 않습니다.
