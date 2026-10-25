@echo off
rem Dev mode: auto-reload on code change.
rem Note: after changing frontend files, hard-refresh browser (Ctrl+Shift+R) if needed.
cd /d %~dp0..

netstat -ano | findstr ":8100" | findstr "LISTENING" >nul && (
  echo [!] Port 8100 already in use. Run scripts\kill.bat first.
  pause
  exit /b 1
)

echo [Where to Travel] dev mode (auto-reload)... http://127.0.0.1:8100/
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
