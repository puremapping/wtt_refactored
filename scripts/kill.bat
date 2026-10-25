@echo off
rem Kill the old service process holding port 8100 (routine before restart).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8100" ^| findstr "LISTENING"') do (
  echo Killing old process PID=%%p
  taskkill /PID %%p /F
)
echo Done. Port released.
