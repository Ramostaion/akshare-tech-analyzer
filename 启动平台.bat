@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "URL=http://127.0.0.1:8000"

if not exist "%PYTHON%" goto bootstrap
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto bootstrap
goto dependencies

:bootstrap
echo Virtual environment is missing or cannot run on this system.
echo Looking for Python 3.11 or newer...
set "BOOTSTRAP_PYTHON="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP_PYTHON=py -3"
if defined BOOTSTRAP_PYTHON goto create_venv
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP_PYTHON=python"
if defined BOOTSTRAP_PYTHON goto create_venv

echo [ERROR] Python 3.11 or newer is not installed.
echo Install 64-bit Python and enable "Add Python to PATH", then run this file again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:create_venv
echo Creating project virtual environment...
%BOOTSTRAP_PYTHON% -m venv --clear "%VENV_DIR%"
if errorlevel 1 goto setup_failed

:dependencies
"%PYTHON%" -c "import akshare, fastapi, jinja2, numpy, pandas, plotly, pydantic, requests, uvicorn" >nul 2>&1
if errorlevel 1 goto install_dependencies
"%PYTHON%" -m pip check >nul 2>&1
if errorlevel 1 goto install_dependencies
goto environment_ready

:install_dependencies
echo Installing project dependencies. This may take several minutes on the first run...
"%PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto setup_failed
"%PYTHON%" -m pip install -e .
if errorlevel 1 goto setup_failed
goto environment_ready

:setup_failed
echo.
echo [ERROR] Environment setup failed. Check the network or proxy, then run this file again.
pause
exit /b 1

:environment_ready
if /I "%~1"=="--check" (
    echo Environment check passed: %PYTHON%
    exit /b 0
)

if not exist "%~dp0cache" mkdir "%~dp0cache"
if not exist "%~dp0reports" mkdir "%~dp0reports"
if not exist "%~dp0logs" mkdir "%~dp0logs"

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    echo The platform is already running at %URL%
    start "" "%URL%"
    exit /b 0
)

echo Starting AKShare Technical Analyzer...
echo Open %URL% in your browser.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "$u='%URL%'; for($i=0; $i -lt 30; $i++){try{Invoke-WebRequest -UseBasicParsing ($u+'/health') -TimeoutSec 1 | Out-Null; Start-Process $u; exit}catch{Start-Sleep -Seconds 1}}; Start-Process $u"
"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo The platform has stopped.
pause
