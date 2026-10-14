# Android 앱 (개발 중)

기존 Python 낙상 감지 프로그램·서버와 별도인 Android 앱입니다. 지금 되는 것:

- **테스트 낙상 → 기존 서버 전송 → 본인 확인 화면 → 응답이 서버에 반영** (기존 API 그대로 사용)
- 1단계 검사: MediaPipe Pose Landmarker가 기기에서 관절 좌표를 돌려주는지 (`PoseCheckActivity`)

**실제 낙상 감지(카메라·자세·판정)는 아직 연결되지 않았습니다.**

## 구조

| 위치 | 역할 |
|---|---|
| `ui/MainActivity` | 첫 화면: 서버 정보, "테스트 낙상 보내기", 설정 |
| `ui/ConfirmActivity` | 큰 버튼 "괜찮아요 / 도움이 필요해요". 서버 상태를 3초마다 확인(/app 과 같은 간격), 남은 시간 표시 |
| `ui/SettingsActivity` | 서버 주소, 접근 토큰, 기기 이름(기본 `android-emulator`). 기기 안에만 저장 |
| `net/EventApi` | `POST /api/events`, `GET /api/events/{id}`, `POST /api/events/{id}/response` (헤더 `X-Access-Token`). 전송 실패 시 1·2·4초 뒤 같은 event_id로 재시도, 401은 재시도 안 함 |
| `events/FallReporter` | "낙상 발생 → 서버 전송" 창구. 지금은 테스트 버튼, 나중에 낙상 감지가 같은 함수를 부름 |
| `src/debug/...network_security_config.xml` | **debug 빌드만** `10.0.2.2`·`127.0.0.1` 에 HTTP 허용 (실제 배포는 HTTPS 필요) |

응답 마감·알림·보호자 단계·119(시뮬레이션) 판단은 모두 서버(`server/main.py`)가 합니다. 앱은 같은 일을 하지 않습니다.

## 서버에 연결해 시험하기

1. 서버를 실행합니다 (실제 서버: `server\run_server.bat`, 포트 8000).
2. 앱의 **서버 설정**에서
   - 서버 주소: `http://10.0.2.2:8000` (에뮬레이터 안에서 `10.0.2.2` = 이 PC)
   - 접근 토큰: `server\access_token.txt` 의 값 (다른 사람에게 보여 주지 마세요)
3. **저장하고 연결 확인** → "연결 성공"이 나오면 **테스트 낙상 보내기**.
4. 테스트 낙상도 서버에서는 실제 흐름과 같이 처리됩니다: 텔레그램이 설정되어 있으면 보호자에게 `[테스트]` 알림이 갑니다.
   알림 없이 시험하려면 서버 코드만 다른 폴더에 복사해 `.env` 없이 다른 포트(예: 8001)로 실행하고 그 폴더의 토큰을 쓰세요.

단위 테스트 (서버·에뮬레이터 없이): `.\gradlew.bat testDebugUnitTest`

에뮬레이터에서 키보드(Gboard)의 "Try out your stylus" 안내가 뜨면 **Cancel** 을 누르세요 (입력이 그 안내창으로 들어감).

## 이 PC의 개발 환경 (2026-10-14 설치)

| 항목 | 값 |
|---|---|
| Android Studio | 2026.2.1.8 (`C:\Program Files\Android\Android Studio`, JDK 25 포함) |
| Android SDK | `%LOCALAPPDATA%\Android\Sdk` (platform 36, build-tools 36.0.0, emulator, platform-tools) |
| 가상 기기 | `fall_api36` (Android 16 / API 36, Google APIs, x86_64, RAM 2GB) |
| 빌드 | Gradle 9.8.1 (wrapper), Android Gradle Plugin 9.4.1, Java 17 소스 |
| MediaPipe | `com.google.mediapipe:tasks-vision:1.1.0` |

**전역 `JAVA_HOME`은 eGovFrame의 JDK 8 그대로 둡니다.** 명령줄 빌드 때만 그 창에서 Android Studio의 JDK를 지정합니다.

## 모델 파일 (저장소에 올리지 않음)

`app/src/main/assets/pose_landmarker_full.task` 에 공식 모델을 넣습니다 (`.gitignore` 로 제외):

- 출처: MediaPipe Pose Landmarker 공식 문서의 Models 항목
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
- 받은 파일: 9,398,198 bytes, MD5 `5a9ad88919b2231d02b1fdf4a54090ec` (서버 값과 일치), 서버 수정일 2023-04-28
- 모델 카드: https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf
- 라이선스: 문서 페이지는 CC BY 4.0(글), Apache 2.0(예제 코드)이라고 밝히지만 **모델 파일 자체의 라이선스 문구는 확인하지 못함**.
  배포(앱 출시) 전에 모델 카드를 직접 확인할 것.

## 빌드와 검사 (PowerShell, `android` 폴더에서)

```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"   # 이 창에서만
.\gradlew.bat assembleDebug

$sdk = "$env:LOCALAPPDATA\Android\Sdk"
& "$sdk\emulator\emulator.exe" -avd fall_api36 -no-snapshot -memory 2048   # 별도 창
$adb = "$sdk\platform-tools\adb.exe"
& $adb install -r app\build\outputs\apk\debug\app-debug.apk
& $adb shell am start -n com.humanfall.falldetect/.PoseCheckActivity        # 저장 폴더 생성
& $adb push ..\test_images\standing.jpg /sdcard/Android/data/com.humanfall.falldetect/files/pose_check.jpg
& $adb shell am force-stop com.humanfall.falldetect
& $adb shell am start -n com.humanfall.falldetect/.PoseCheckActivity
& $adb pull /sdcard/Android/data/com.humanfall.falldetect/files/pose_check_result.json
```

결과 JSON: 기기·ABI, 초기화/추론 시간(ms), 감지 인원, 사람마다 관절 33개 `[x, y, z, visibility]`
(**사진 전체 기준 0~1 정규화** — PC 감지기의 "사람 박스 기준"과 다름).
