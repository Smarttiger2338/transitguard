@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 가상환경이 없습니다. 초기 설정을 먼저 실행합니다...
  call "%~dp0setup_windows.bat"
)
echo 웹 데모를 시작합니다: http://127.0.0.1:8080
echo 데모를 사용하는 동안 이 창을 닫지 마세요.
cd web-demo
"..\.venv\Scripts\python.exe" -m http.server 8080
pause

