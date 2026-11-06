# 끝까지 도는 시험 (복사본 서버 전용)

모든 시험은 임시 폴더의 **서버 복사본**에서 돌아요. 운영 서버와 운영 DB는 건드리지 않고, `.env`도 복사하지 않아요. 119 전화 버튼은 링크만 검사하고 누르지 않아요.

| 시험 | 필요한 것 | 무엇을 확인 |
|---|---|---|
| `server/tests/test_full_flow.py` | 서버 venv | 등록부터 기기 삭제까지 10단계. 서버 시험 전체를 돌릴 때 함께 실행 |
| `run_browser.py` | 서버 venv, Node, Chrome | 화면 자동 갱신, 사고 인계, 모의 신고 뒤 119 링크, 관리자 화면 |
| `run_onboarding.py` | 서버 venv, Node, Chrome | 처음 설정에서 뒤로 돌아가 수정, 다른 집 고르기, 새로고침 |
| `run_emulator.py` | 서버 venv, 켜진 에뮬레이터, debug APK | 실제 앱으로 연결, 낙상, 복구, 로그아웃 |

## 실행

프로젝트 폴더에서 서버 venv 의 Python 으로 실행해요.

```powershell
python tools\e2e\run_browser.py
python tools\e2e\run_onboarding.py
python tools\e2e\run_emulator.py --frames <녹화 프레임 폴더>
```

- `run_emulator.py` 는 APK 안의 서버 주소가 `http://localhost:8012/app/next/` 여야 해요.
- `--frames` 폴더 이름의 낙상 영상 프레임은 저장소에 없어요 (데이터셋). 없으면 낙상 단계를 건너뛰고 그렇게 표시해요.
- 시험을 돌리면 에뮬레이터 앱 데이터가 지워져요.

## 결과를 읽는 법

가상 시험 통과는 서버와 앱 코드가 그 흐름대로 동작한다는 뜻이에요. **실제 휴대폰의 카메라, 절전, 발열, 통신을 보증하지 않아요.** 실제 기기에서만 볼 수 있는 항목은 `docs/DEVICE_HTTPS_READINESS.md` 의 C 단계에 있어요.

debug 빌드의 시험 옵션(`test_block_frames_seconds`, `test_fail_analysis_seconds`, `mock_frames_dir`)은 배포용 빌드에서 동작하지 않아요.
