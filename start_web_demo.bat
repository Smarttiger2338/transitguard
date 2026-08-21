@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Running setup first...
  call "%~dp0setup_windows.bat"
)
echo Starting web demo at http://127.0.0.1:8080
echo Keep this window open while using the demo.
cd web-demo
"..\.venv\Scripts\python.exe" -m http.server 8080
pause
