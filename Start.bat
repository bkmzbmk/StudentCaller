@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Vyzov k doske

echo === Вызов к доске: запуск ===
echo.

rem ---------------------------------------------------------------
rem 1. Ищем Python 3.8 или новее
rem ---------------------------------------------------------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :have_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :have_python
echo [ОШИБКА] Не найден Python 3.8 или новее.
echo Установите Python с сайта https://www.python.org/downloads/
echo При установке отметьте пункт "Add python.exe to PATH".
goto :fail

:have_python
echo Python найден: %PY%

rem ---------------------------------------------------------------
rem 2. Виртуальное окружение .venv - библиотеки ставятся только туда
rem ---------------------------------------------------------------
set "USE_VENV=1"
set "VPY=%~dp0.venv\Scripts\python.exe"
if exist "%VPY%" goto :venv_ready
echo Создаю виртуальное окружение .venv ...
%PY% -m venv "%~dp0.venv"
if errorlevel 1 goto :no_venv

:venv_ready
"%VPY%" -c "import tkinter; tkinter.Tcl()" >nul 2>&1
if errorlevel 1 goto :no_venv
goto :check_deps

:no_venv
echo [!] Виртуальное окружение недоступно, использую системный Python.
set "USE_VENV=0"
for /f "delims=" %%i in ('%PY% -c "import sys; print(sys.executable)"') do set "VPY=%%i"
"%VPY%" -c "import tkinter; tkinter.Tcl()" >nul 2>&1
if not errorlevel 1 goto :check_deps
echo [ОШИБКА] В установленном Python нет модуля tkinter - он нужен для окна программы.
echo Переустановите Python с python.org и оставьте включённым компонент "tcl/tk and IDLE".
goto :fail

rem ---------------------------------------------------------------
rem 3. Проверяем библиотеки и ставим недостающие
rem ---------------------------------------------------------------
:check_deps
echo.
echo Проверяю библиотеки...
"%VPY%" "%~dp0tools\check_deps.py" "%~dp0requirements.txt"
if not errorlevel 1 goto :run

echo.
echo Устанавливаю недостающие библиотеки...
"%VPY%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if not errorlevel 1 goto :verify
if "%USE_VENV%"=="1" goto :pip_failed
echo Пробую установить для текущего пользователя...
"%VPY%" -m pip install --user --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto :pip_failed

:verify
"%VPY%" "%~dp0tools\check_deps.py" "%~dp0requirements.txt"
if errorlevel 1 goto :pip_failed
goto :run

:pip_failed
echo [ОШИБКА] Не удалось установить библиотеки. Проверьте подключение к интернету
echo и запустите Start.bat ещё раз.
goto :fail

rem ---------------------------------------------------------------
rem 4. Запуск приложения без консольного окна
rem ---------------------------------------------------------------
:run
echo.
echo Запускаю приложение...
set "VPYW=%VPY:python.exe=pythonw.exe%"
if not exist "%VPYW%" set "VPYW=%VPY%"
start "" "%VPYW%" "%~dp0main.py"
exit /b 0

:fail
echo.
pause
exit /b 1
