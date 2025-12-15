@echo off
title BIST Trading Bot
cd /d "%~dp0..\.."
cd core-src

:loop
echo [%DATE% %TIME%] Starting Trading Bot... >> ..\logs\bot_windows.log
python main.py >> ..\logs\bot_windows.log 2>&1
echo [%DATE% %TIME%] Trading Bot crashed. Restarting in 10 seconds... >> ..\logs\bot_windows.log
timeout /t 10
goto loop
