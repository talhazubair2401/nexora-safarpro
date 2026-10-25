@echo off
setlocal EnableExtensions
title Nexora SafarPro - Backup
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto nosetup

echo Creating a verified backup of the database and all documents ...
echo (This is safe while SafarPro is running.)
echo.
".venv\Scripts\python.exe" manage.py backup_safarpro
if errorlevel 1 goto failed

echo.
echo Copy the backup file to a USB drive or cloud folder to protect against disk failure.
echo Opening the backups folder ...
if exist "%LOCALAPPDATA%\Nexora\SafarPro\backups" start "" "%LOCALAPPDATA%\Nexora\SafarPro\backups"
pause
exit /b 0

:nosetup
echo [ERROR] SafarPro is not set up on this PC. Run setup_windows.bat first.
pause
exit /b 1

:failed
echo.
echo [ERROR] The backup was NOT created. See the message above.
pause
exit /b 1
