# 배포용 APK 만들기

고정 HTTPS 주소가 정해진 뒤에 하는 작업이에요. 서버 주소가 앱 안에 들어가기 때문에, **주소가 바뀌면 새로 빌드해서 설치하고 감지 기기도 다시 연결해야 해요.**

## 1. 서명 키 만들기 (처음 한 번)

서명 키는 앱의 신분증이에요. 잃어버리면 같은 앱으로 업데이트할 수 없어요.

- 저장소 밖에 두세요. 예: `C:\Users\Administrator\FallDetectionSecrets\`
- 키 파일과 비밀번호는 Git, 메신저, 로그에 넣지 마세요. 키 파일은 따로 백업해 두세요.

Android Studio 의 **Build > Generate Signed App Bundle or APK** 에서 만들거나, 아래 명령을 써요. 비밀번호는 명령이 물어볼 때 입력해요.

```powershell
& "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe" -genkeypair -v -storetype JKS `
  -keystore "$env:USERPROFILE\FallDetectionSecrets\fall-release.jks" -alias fall -keyalg RSA -keysize 2048 -validity 10000
```

## 2. 서명 설정 파일 만들기

`mobile/android/keystore.properties` 를 만들어요. Git 에 올라가지 않는 파일이에요. 다른 곳에 두려면 환경 변수 `FD_KEYSTORE_PROPERTIES` 에 경로를 넣으세요.

```properties
storeFile=C:/Users/Administrator/FallDetectionSecrets/fall-release.jks
storePassword=정한 비밀번호
keyAlias=fall
keyPassword=정한 비밀번호
```

## 3. 서버 주소 넣고 빌드

```powershell
cd mobile
$env:FD_SERVER_URL = "https://고정주소/app/next/"
npm run sync:release
cd android
.\gradlew assembleRelease
```

`capacitor.settings.gradle` 이 바뀌면 커밋하지 말고 되돌려 주세요.

결과물: `mobile/android/app/build/outputs/apk/release/app-release.apk`

새 버전을 낼 때는 번호를 올려요: `.\gradlew assembleRelease -PfdVersionCode=2 -PfdVersionName=1.1`

## 빌드가 멈추면

빌드는 시작할 때 `checkReleaseConfig` 로 다음을 검사하고, 문제를 모두 모아서 알려 줘요.

| 메시지 | 조치 |
|---|---|
| 서버 주소가 없어요 / HTTPS 가 아니에요 / 이 PC 를 가리켜요 | 3번의 `sync:release` 를 실제 주소로 실행 |
| google-services.json 이 없어요 | `mobile/android/app/` 에 넣기 (보관 폴더에 사본 있음) |
| 서명 설정 파일이 없어요 / 빠진 값이 있어요 / 키 파일을 찾을 수 없어요 | 1, 2번 확인 |

## 빌드 뒤 확인

- 실제 폰에 설치하기 전에 서버 쪽 `FD_DEV_TOOLS`, `FD_DEV_DEVICES` 가 꺼져 있는지 확인해요.
- 시험용 옵션(`mock_frames_dir`, `test_block_frames_seconds` 등)은 배포용 빌드에서 동작하지 않아요.
- 첫 실행은 `docs/DEVICE_HTTPS_READINESS.md` 의 B, C 단계를 따라요.
