@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_WINDOWS.bat first, then open START_WINDOWS.bat again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
pause
