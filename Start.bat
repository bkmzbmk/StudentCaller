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
rem Сначала PATH, затем типичные папки установки Anaconda/Miniconda и python.org
set "PY="
call :try_py py -3
if not defined PY call :try_py python
if not defined PY call :try_py "%ProgramData%\anaconda3\python.exe"
if not defined PY call :try_py "%USERPROFILE%\anaconda3\python.exe"
if not defined PY call :try_py "%LOCALAPPDATA%\anaconda3\python.exe"
if not defined PY call :try_py "%ProgramData%\miniconda3\python.exe"
if not defined PY call :try_py "%USERPROFILE%\miniconda3\python.exe"
if not defined PY call :try_py "%LOCALAPPDATA%\miniconda3\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PY call :try_py "%%~D\python.exe"
if not defined PY for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PY call :try_py "%%~D\python.exe"
if defined PY goto :have_python
echo [ОШИБКА] Не найден Python 3.8 или новее.
echo Установите Python с сайта https://www.python.org/downloads/
echo При установке отметьте пункт "Add python.exe to PATH".
goto :fail

:try_py
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0

:have_python
rem Полный путь к python.exe и его папкам - нужно для Anaconda без активации
%PY% -c "import sys; print(sys.executable)" > "%TEMP%\student_caller_py.txt"
set /p PY_EXE=<"%TEMP%\student_caller_py.txt"
del "%TEMP%\student_caller_py.txt" >nul 2>&1
for %%F in ("%PY_EXE%") do set "PYDIR=%%~dpF"
set "PATH=%PYDIR%;%PYDIR%Library\mingw-w64\bin;%PYDIR%Library\usr\bin;%PYDIR%Library\bin;%PYDIR%Scripts;%PATH%"
echo Python найден: %PY_EXE%

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
set "VPY=%PY_EXE%"
"%VPY%" -c "import tkinter; tkinter.Tcl()" >nul 2>&1
if not errorlevel 1 goto :check_deps
echo [ОШИБКА] В установленном Python нет модуля tkinter - он нужен для окна программы.
echo Переустановите Python с python.org и оставьте включённым компонент "tcl/tk and IDLE".
goto :fail

rem ---------------------------------------------------------------
rem 3. Проверяем библиотеки и ставим недостающие
rem    torch для Silero большой - первая установка может занять несколько минут
rem ---------------------------------------------------------------
:check_deps
echo.
echo Проверяю библиотеки...
"%VPY%" "%~dp0tools\ensure_deps.py" "%~dp0requirements.txt"
if errorlevel 1 goto :pip_failed
goto :run

:pip_failed
echo [ОШИБКА] Не удалось установить обязательные библиотеки. Проверьте подключение
echo к интернету и запустите Start.bat ещё раз.
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
