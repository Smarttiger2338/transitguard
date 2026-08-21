# Windows guide

This guide is for users who just want to run TransitGuard locally.

## Easiest method

1. Extract the ZIP file.
2. Open the extracted `transitguard-v0.1.0-alpha.11` folder.
3. Double-click `setup_windows.bat`.
4. Double-click `start_all_windows.bat`.
5. Open `http://127.0.0.1:8080`.

`setup_windows.bat` avoids the PowerShell script-policy problem because it uses
`activate.bat`/direct Python execution instead of `Activate.ps1`.

## If PowerShell says scripts are disabled

You do not need to activate the environment manually. Use the `.bat` files.

If you still want to use PowerShell, run Python through the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn transitguard.api.app:app --reload
```

## If timezone tests fail

TransitGuard now installs `tzdata` automatically on Windows and also falls back
to fixed KST when `Asia/Seoul` is unavailable. Run:

```cmd
setup_windows.bat
```

If you installed the project before this fix, reinstall dependencies:

```cmd
.venv\Scripts\python.exe -m pip install -e ".[dev,api]"
```

## Live TAGO data

Demo and tests work without a TAGO key. Live TAGO endpoints need `.env`:

```env
TAGO_SERVICE_KEY=your_public_data_service_key

# Optional: Kakao Map browser visualization
KAKAO_MAP_JAVASCRIPT_KEY=your_kakao_javascript_key
```

After starting the API, check setup status here:

```text
http://127.0.0.1:8000/api/setup/check
```


## Kakao Map visualization

Kakao Map is optional. The assessment engine and offline tests work without it.

To enable the browser map:

1. Create a Kakao Developers app.
2. Copy the JavaScript Key.
3. Register `http://127.0.0.1:8080` as a Web platform domain.
4. Put the key in `.env` as `KAKAO_MAP_JAVASCRIPT_KEY`.
5. Restart the API server and open the web demo.
