# PC 낙상 감지 프로그램

YOLO 와 MediaPipe 로 웹캠이나 영상을 분석하는 PC 프로그램입니다. 개발과 시험에 쓰며, 서버 배포와 Android 앱에는 필요하지 않습니다.

프로젝트 맨 위 폴더에서 실행합니다.

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r pc\requirements.txt
venv\Scripts\python.exe pc\fall_detection_system.py --mode dashboard
```

| 위치 | 내용 |
|---|---|
| `fall_detection_system.py` | 실행 파일 |
| `dashboard/` | PyQt5 화면과 서버 연결 |
| `models/fall_detector.py` | 낙상 판정 |
| `utils/` | 저조도 보정, 실루엣, 기타 |
| `yolov12n1.pt` | 기본 모델 |
| `yolov12m.pt`, `yolov12n.pt`, `yolov8n.pt` | 비교용 모델. `--model` 로 지정 |
| `requirements.txt` | 설치 목록 |
| `requirements-working.txt` | 시험한 환경의 전체 버전 |
| `checkcuda.py` | GPU 확인 |

시험 사진 폴더 `test_images/` 와 결과 폴더 `test_output/` 은 프로젝트 맨 위에 둡니다.
