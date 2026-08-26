@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 가상환경이 없습니다. 초기 설정을 먼저 실행합니다...
  call "%~dp0setup_windows.bat"
)
echo TransitGuard API를 시작합니다: http://127.0.0.1:8000
echo API 문서: http://127.0.0.1:8000/docs
".venv\Scripts\python.exe" -m uvicorn transitguard.api.app:app --reload
pause

