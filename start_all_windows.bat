@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0setup_windows.bat"
)
start "TransitGuard API" cmd /k call "%~dp0start_api.bat"
start "TransitGuard Web Demo" cmd /k call "%~dp0start_web_demo.bat"
echo Opening browser pages...
timeout /t 2 >nul
start http://127.0.0.1:8000/docs
start http://127.0.0.1:8080
