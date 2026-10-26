@echo off
rem HTTPS 리버스 프록시(Caddy 등) 뒤에서 실행: 이 컴퓨터 안(127.0.0.1)에서만 접속을 받음 (밖에서는 프록시의 HTTPS 로만)
rem 프록시가 보내는 X-Forwarded-Proto / X-Forwarded-For 는 127.0.0.1 에서 온 것만 믿음
rem   → HTTPS 로 접속한 사람의 로그인 쿠키에 Secure, 실패 횟수 제한은 실제 접속 주소 기준
rem 자세한 절차: deploy/https/README.md  (기존 run_server.bat 은 0.0.0.0 HTTP 그대로)
cd /d %~dp0
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
pause
