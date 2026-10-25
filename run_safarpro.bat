@echo off
setlocal EnableExtensions
title Nexora SafarPro - Server (keep this window open)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto nosetup

".venv\Scripts\python.exe" -c "import django, waitress" >nul 2>&1
if errorlevel 1 goto missing

".venv\Scripts\python.exe" launch.py
if errorlevel 1 goto failed
exit /b 0

:nosetup
echo [ERROR] SafarPro is not set up on this PC yet.
echo         Double-click setup_windows.bat first, then run this file again.
pause
exit /b 1

:missing
echo [ERROR] Required packages are missing from the program environment.
echo         Run setup_windows.bat again to repair the installation.
echo         Your data is not affected.
pause
exit /b 1

:failed
echo.
echo SafarPro stopped because of an error (details above).
echo Your saved data has not been changed.
echo Logs: %LOCALAPPDATA%\Nexora\SafarPro\logs
pause
exit /b 1
