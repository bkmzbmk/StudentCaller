@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Test Silero
rem Проверка голоса Silero. Сначала один раз запустите Start.bat.
rem Можно указать голос: TestVoice.bat baya
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" set "VPY=python"
"%VPY%" "%~dp0tools\test_voice.py" %*
echo.
pause
