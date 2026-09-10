@echo off
setlocal
cd /d "%~dp0"

rem Local preview is the developer sandbox. Packaged builds keep normal economy rules.
set "TOKENPET_DEVELOPER_MODE=1"
set "TOKENPET_LAUNCH_DEBUG=0"
set "TOKENPET_EXTRA_ARGS="
if /I "%~1"=="debug" (
    set "TOKENPET_DEBUG_WINDOW=1"
    set "TOKENPET_LAUNCH_DEBUG=1"
)
if /I "%~1"=="shop" set "TOKENPET_EXTRA_ARGS=--debug-open-shop"

set "TOKENPET_PYTHON="
set "TOKENPET_PYTHONW="
if exist ".venv\Scripts\python.exe" (
    set "TOKENPET_PYTHON=.venv\Scripts\python.exe"
    if exist ".venv\Scripts\pythonw.exe" set "TOKENPET_PYTHONW=.venv\Scripts\pythonw.exe"
)
if not defined TOKENPET_PYTHON if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    set "TOKENPET_PYTHON=%LOCALAPPDATA%\Python\bin\python.exe"
    if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" set "TOKENPET_PYTHONW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
)
if not defined TOKENPET_PYTHON for %%P in (python.exe) do set "TOKENPET_PYTHON=%%~$PATH:P"
if not defined TOKENPET_PYTHONW for %%P in (pythonw.exe) do set "TOKENPET_PYTHONW=%%~$PATH:P"

if not defined TOKENPET_PYTHON (
    echo [TokenPet] Python 3 was not found.
    echo Install the dependencies from DEVELOPMENT.md, then try again.
    pause
    exit /b 1
)

if "%TOKENPET_LAUNCH_DEBUG%"=="1" (
    "%TOKENPET_PYTHON%" emojinoko_monitor.py --standalone --unity-poc %TOKENPET_EXTRA_ARGS%
    if errorlevel 1 pause
    exit /b
)

if defined TOKENPET_PYTHONW (
    start "" /B "%TOKENPET_PYTHONW%" emojinoko_monitor.py --standalone --unity-poc %TOKENPET_EXTRA_ARGS%
    exit /b 0
)

rem Fallback for unusual Python installations without pythonw.exe.
"%TOKENPET_PYTHON%" emojinoko_monitor.py --standalone --unity-poc %TOKENPET_EXTRA_ARGS%
if errorlevel 1 pause
