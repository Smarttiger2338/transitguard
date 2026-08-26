@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [TransitGuard] Windows 초기 설정
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set PY=py -3
) else (
  set PY=python
)

echo [1/4] 가상환경을 준비합니다...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto error
) else (
  echo 기존 가상환경을 사용합니다.
)

echo [2/4] 필요한 패키지를 설치합니다...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -e ".[dev,api]"
if errorlevel 1 goto error

echo [3/4] 환경변수 파일을 확인합니다...
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo .env 파일을 만들었습니다. TAGO 실데이터 기능을 사용하려면 서비스 키를 입력하세요.
) else (
  echo 기존 .env 파일을 사용합니다.
)

echo [4/4] 자동화 테스트를 실행합니다...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto error

echo.
echo 설정이 완료되었습니다.
echo 다음 단계: start_all_windows.bat을 실행하세요.
goto end

:error
echo.
echo 설정에 실패했습니다. 위 오류 내용을 확인하세요.
exit /b 1

:end
pause

