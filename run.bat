@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [1/2] 가상환경 생성 및 패키지 설치 중...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
)

echo [2/2] 서버 시작: http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
