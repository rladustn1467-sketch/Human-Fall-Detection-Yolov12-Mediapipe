# 낙상 지킴이 서버

집 안 낙상사고를 감지해 가족에게 알리는 프로토타입의 **서버와 웹앱 배포용 저장소**입니다.

원본은 [Human-Fall-Detection-Yolov12-Mediapipe](https://github.com/rladustn1467-sketch/Human-Fall-Detection-Yolov12-Mediapipe) 입니다. 이 저장소는 그쪽의 `tools/export_deploy.py` 로 만들므로 **여기서 직접 고치지 않습니다.**

> 이 프로토타입은 119에 전화나 문자를 보내거나 신고를 전달하지 않습니다. 앱의 119 신고는 앱 안의 기록으로만 남습니다. 실제 개인정보를 입력하지 마세요.

## 배포

```bash
git clone https://github.com/rladustn1467-sketch/fall app
cd app
deploy
```

`deploy` 가 `requirements.txt` 와 `main.py` 를 보고 FastAPI 앱으로 실행합니다. 첫 화면은 `/app/next/` 입니다.

## 설정

```bash
cp .env.example .env
```

`.env` 를 만든 뒤 `deploy restart` 를 합니다. `.env` 는 GitHub 에 올리지 않습니다.

현관 비밀번호 저장을 켜려면 키를 만들어 `DOOR_CODE_KEY` 에 넣습니다.

```bash
~/.venv/bin/python door_codes.py genkey
```

## 구성

| 위치 | 내용 |
|---|---|
| `main.py` 와 다른 `.py` | FastAPI 서버 |
| `app/next/` | 가족용 웹앱. Android 앱도 이 화면을 불러옵니다 |
| `app/` 의 나머지 | 옛 웹앱 |
| `static/` | 옛 확인 페이지 |

데이터는 처음 실행할 때 만들어지는 `fall.db` 와 `images/` 에 저장됩니다.
