@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0setup_windows.bat"
)
start "TransitGuard API" cmd /k call "%~dp0start_api.bat"
start "TransitGuard 웹 데모" cmd /k call "%~dp0start_web_demo.bat"
echo API 문서와 웹 데모를 엽니다...
timeout /t 2 >nul
start http://127.0.0.1:8000/docs
start http://127.0.0.1:8080

