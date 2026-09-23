@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "FIN_PY=.venv\Scripts\python.exe"
) else if exist "..\.venv\Scripts\python.exe" (
  set "FIN_PY=..\.venv\Scripts\python.exe"
) else (
  set "FIN_PY=python"
)
if not exist "data\finance.sqlite" (
  "%FIN_PY%" scripts\generate_data.py
  if errorlevel 1 exit /b 1
)
echo Open http://127.0.0.1:8111
"%FIN_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8111
