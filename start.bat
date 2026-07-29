@echo off
REM InsightCopilot 一键启动（Windows）
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat || (echo 请先运行 setup.bat & exit /b 1)
cd backend
echo InsightCopilot 启动中 → http://localhost:8000
uvicorn api.main:app --host 0.0.0.0 --port 8000
