@echo off
setlocal
cd /d "%~dp0"

rem Always use the repository's current environment.  The old launcher only
rem installed dependencies when the venv was first created, so an older venv
rem silently launched the pre-visual-update fallback UI.
if not exist ".venv\Scripts\python.exe" (
    py -m venv .venv
)

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install Knightboard dependencies.
    exit /b 1
)

echo Starting Knightboard v0.50...
.venv\Scripts\python.exe chess_camera.py %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

