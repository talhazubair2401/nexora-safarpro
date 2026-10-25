@echo off
setlocal EnableExtensions
title Nexora SafarPro - Restore a backup
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto nosetup

echo ==============================================================
echo   Restore a SafarPro backup
echo ==============================================================
echo  - Close the SafarPro server window before continuing.
echo  - Your CURRENT data is backed up automatically before restoring.
echo  - The backup file is checked before anything is replaced.
echo.
echo Available backups (newest first):
".venv\Scripts\python.exe" manage.py backup_safarpro --list
echo.
echo Backups folder: %LOCALAPPDATA%\Nexora\SafarPro\backups
echo.
set "FILE="
set /p "FILE=Drag the backup .zip file here (or type its full path) and press Enter: "
if not defined FILE goto cancelled
set "FILE=%FILE:"=%"
if not exist "%FILE%" (
  rem Allow just the file name of a backup in the default folder
  if exist "%LOCALAPPDATA%\Nexora\SafarPro\backups\%FILE%" set "FILE=%LOCALAPPDATA%\Nexora\SafarPro\backups\%FILE%"
)
if not exist "%FILE%" goto notfound

echo.
echo Checking the backup ...
".venv\Scripts\python.exe" manage.py restore_safarpro "%FILE%" --validate-only
if errorlevel 1 goto failed

echo.
set "CONFIRM="
set /p "CONFIRM=This REPLACES your current SafarPro data. Type RESTORE to continue: "
if /i not "%CONFIRM%"=="RESTORE" goto cancelled

".venv\Scripts\python.exe" manage.py restore_safarpro "%FILE%" --yes
if errorlevel 1 goto failed
echo.
echo Restore finished. Start SafarPro with run_safarpro.bat.
pause
exit /b 0

:nosetup
echo [ERROR] SafarPro is not set up on this PC. Run setup_windows.bat first.
pause
exit /b 1

:notfound
echo [ERROR] File not found: %FILE%
pause
exit /b 1

:cancelled
echo Restore cancelled. Nothing was changed.
pause
exit /b 0

:failed
echo.
echo [ERROR] Restore did not complete. See the message above.
echo         If the safety backup was created, its name is shown above.
pause
exit /b 1
