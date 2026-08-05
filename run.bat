@echo off
REM ---------------------------------------------------------------
REM  kbrain-chatbot service launcher
REM
REM  - runs sheet polling + slack listener  (backend/service.py)
REM  - appends all output to logs\service.log
REM  - restarts 30s after the process dies
REM  - exit code 3 means another instance already holds the lock,
REM    so this window steps aside instead of looping forever
REM
REM  NOTE: keep this file ASCII-only. Mixing Korean text with
REM  `chcp 65001` breaks line boundaries and truncates commands
REM  (observed 2026-08-04: "uv run python -m ..." lost its head and
REM  cmd reported '-m' as an unknown command).
REM  Korean still shows up in the log because Python writes it.
REM ---------------------------------------------------------------

cd /d "%~dp0"
if not exist logs mkdir logs

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

title kbrain-chatbot service (do not close)
echo ===============================================================
echo  kbrain-chatbot - sheet polling + slack approval
echo.
echo  This window IS the service. Keep it open; minimize it.
echo  Closing this window stops the service.
echo.
echo  Nothing else prints here on purpose - all output goes to:
echo    %~dp0logs\service.log
echo ===============================================================
echo.

:loop
echo. >> logs\service.log
echo ==================== START %date% %time% ==================== >> logs\service.log
uv run python -m backend.service >> logs\service.log 2>&1

if %errorlevel%==3 (
    echo ---- already running elsewhere, this window exits ---- >> logs\service.log
    goto end
)

echo ---- exited with code %errorlevel%, restarting in 30s ---- >> logs\service.log
timeout /t 30 /nobreak > nul
goto loop

:end
