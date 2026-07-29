@echo off
REM Monthly regulation change detection - called by Windows Task Scheduler.
REM Uses %~dp0 (this file location) so the Korean folder name never appears
REM in the script; a hardcoded path breaks depending on the console codepage.
setlocal
cd /d "%~dp0" || exit /b 1
if not exist "output\_reports" mkdir "output\_reports"
set "LOG=output\_reports\cron.log"
echo ====== %DATE% %TIME% START ====== >> "%LOG%"
python check_updates.py --cron >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo ====== %DATE% %TIME% END exit=%RC% ====== >> "%LOG%"
endlocal & exit /b %RC%
