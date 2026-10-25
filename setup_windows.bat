@echo off
setlocal EnableExtensions
title Nexora SafarPro - Setup
cd /d "%~dp0"

echo ==============================================================
echo   Nexora SafarPro - one-time setup
echo ==============================================================
echo.
echo This prepares SafarPro on this PC. It never deletes existing data.
echo Your data folder is: %LOCALAPPDATA%\Nexora\SafarPro
echo.

rem ---------- 1. Find Python 3.10 or newer ----------
set "PY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto havepy
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto havepy
goto nopy

:havepy
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [OK] Python %PYVER% found.

rem ---------- 2. Create the virtual environment ----------
if exist ".venv\Scripts\python.exe" goto havevenv
echo Creating the program environment in .venv ...
%PY% -m venv .venv
if errorlevel 1 goto venvfail
:havevenv
set "VPY=%~dp0.venv\Scripts\python.exe"
echo [OK] Program environment ready.

rem ---------- 3. Install the required packages ----------
echo Installing required packages (Django, waitress) ...
if exist "%~dp0wheels\" goto offlinewheels
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pipfail
goto pipdone
:offlinewheels
echo Using the offline package folder "wheels" ...
"%VPY%" -m pip install --disable-pip-version-check --no-index --find-links "%~dp0wheels" -r requirements.txt
if errorlevel 1 goto pipfail
:pipdone
echo [OK] Packages installed.

rem ---------- 4. Prepare the database (safe: backs up first if data exists) ----------
"%VPY%" manage.py safe_migrate
if errorlevel 1 goto dbfail
"%VPY%" manage.py check
if errorlevel 1 goto dbfail
echo [OK] Database ready.

rem ---------- 5. Desktop shortcut (optional) ----------
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Nexora SafarPro.lnk'); $s.TargetPath='%~dp0run_safarpro.bat'; $s.WorkingDirectory='%~dp0'; $s.Description='Start Nexora SafarPro'; $s.Save()" >nul 2>&1
if errorlevel 1 (echo [INFO] Could not create a desktop shortcut. Start SafarPro with run_safarpro.bat.) else (echo [OK] Desktop shortcut "Nexora SafarPro" created.)

echo.
echo ==============================================================
echo   Setup complete.
echo   Double-click run_safarpro.bat to start SafarPro.
echo   The first time, the browser shows a setup page where you
echo   create your administrator account.
echo ==============================================================
pause
exit /b 0

:nopy
echo [ERROR] Python 3.10 or newer was not found.
echo         1. Download Python from https://www.python.org/downloads/windows/
echo         2. During installation tick "Add python.exe to PATH".
echo         3. Run setup_windows.bat again.
pause
exit /b 1

:venvfail
echo [ERROR] Could not create the program environment in the .venv folder.
echo         Check that this folder is not read-only, then try again.
pause
exit /b 1

:pipfail
echo [ERROR] Package installation failed.
echo         Setup needs an internet connection once to download Django and waitress,
echo         or a "wheels" folder with the downloaded packages (see README.md).
pause
exit /b 1

:dbfail
echo [ERROR] Database preparation failed. Your existing data was NOT changed.
echo         See the log in %LOCALAPPDATA%\Nexora\SafarPro\logs
pause
exit /b 1
