@echo off
title BIST PMR Bot
cd /d "%~dp0..\.."

:loop
echo [%DATE% %TIME%] Starting PMR Bot... >> logs\pmr_windows.log
python -m pmr.cli continuous >> logs\pmr_windows.log 2>&1
echo [%DATE% %TIME%] PMR Bot crashed. Restarting in 10 seconds... >> logs\pmr_windows.log
timeout /t 10
goto loop
