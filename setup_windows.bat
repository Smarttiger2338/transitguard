@echo off
setlocal
cd /d "%~dp0"

echo [TransitGuard] Windows setup
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set PY=py -3
) else (
  set PY=python
)

echo [1/4] Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 goto error
) else (
  echo Virtual environment already exists.
)

echo [2/4] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -e ".[dev,api]"
if errorlevel 1 goto error

echo [3/4] Creating .env if missing...
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env. Add TAGO_SERVICE_KEY later if you want live TAGO data.
) else (
  echo .env already exists.
)

echo [4/4] Running tests...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto error

echo.
echo Setup complete.
echo Next: double-click start_api.bat, then start_web_demo.bat.
goto end

:error
echo.
echo Setup failed. Copy the error above and ask for help.
exit /b 1

:end
pause
