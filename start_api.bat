@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Running setup first...
  call "%~dp0setup_windows.bat"
)
echo Starting TransitGuard API at http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
".venv\Scripts\python.exe" -m uvicorn transitguard.api.app:app --reload
pause
