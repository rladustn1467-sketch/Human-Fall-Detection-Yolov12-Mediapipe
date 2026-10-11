@echo off
rem 같은 Wi-Fi의 핸드폰에서도 접속할 수 있도록 모든 네트워크 인터페이스(0.0.0.0)에서 실행
cd /d %~dp0
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
