@echo off
rem Daily start: http://127.0.0.1:8100/
rem If port is occupied, an old process is still alive - run scripts\kill.bat first.
cd /d %~dp0..

netstat -ano | findstr ":8100" | findstr "LISTENING" >nul && (
  echo [!] Port 8100 is already in use. Old process may still be running.
  echo     Run scripts\kill.bat first, then start again.
  pause
  exit /b 1
)

echo [Where to Travel] starting... http://127.0.0.1:8100/
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
