@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tests\run_live_integration.py
if errorlevel 1 exit /b 1
echo Python and local HTTP checks passed. Hardware and target firmware are separate gates.
pause
