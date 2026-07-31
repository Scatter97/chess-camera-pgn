@echo off
setlocal
cd /d "%~dp0"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release
mkdir release

set "PYTHON_BOOTSTRAP=python"
where python >nul 2>nul
if errorlevel 1 set "PYTHON_BOOTSTRAP=py"

if not exist ".venv-build\Scripts\python.exe" (
    %PYTHON_BOOTSTRAP% -m venv .venv-build
)

.venv-build\Scripts\python.exe -m pip install --upgrade pip
.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
if errorlevel 1 exit /b 1

.venv-build\Scripts\python.exe packaging\prepare_frozen_sources.py
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe packaging\generate_icons.py
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\ChessCamera.spec
if errorlevel 1 exit /b 1

for /f %%i in ('.venv-build\Scripts\python.exe -c "from version import APP_VERSION; print(APP_VERSION)"') do set APP_VERSION=%%i
copy README.md dist\ChessCamera\README.md >nul
powershell -NoProfile -Command "Compress-Archive -Path 'dist\ChessCamera\*' -DestinationPath 'release\ChessCamera-%APP_VERSION%-Windows-x64.zip' -Force"
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo   dist\ChessCamera\ChessCamera.exe
echo   release\ChessCamera-%APP_VERSION%-Windows-x64.zip
echo.
echo Keep ChessCamera.exe beside its _internal folder.
endlocal
