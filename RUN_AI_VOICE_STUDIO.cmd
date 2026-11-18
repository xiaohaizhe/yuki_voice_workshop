@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Voice Studio

set "LOG_FILE=%~dp0startup_log.txt"
> "%LOG_FILE%" echo [%date% %time%] AI Voice Studio startup log

echo ========================================
echo        AI Voice Studio Launcher
echo ========================================
echo.
echo [1/4] Checking files and Python...

if not exist "%~dp0app.py" (
  echo ERROR: app.py was not found.
  echo Please unzip the whole package first, then run this file again.
  >> "%LOG_FILE%" echo ERROR: app.py not found
  goto :error
)

if not exist "%~dp0requirements.txt" (
  echo ERROR: requirements.txt was not found.
  echo Please unzip the whole package first, then run this file again.
  >> "%LOG_FILE%" echo ERROR: requirements.txt not found
  goto :error
)

set "PY_EXE="
set "PY_ARGS="

where python >nul 2>nul
if not errorlevel 1 (
  set "PY_EXE=python"
  set "PY_ARGS="
)

if not defined PY_EXE (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3"
  )
)

if not defined PY_EXE (
  echo ERROR: Python was not found.
  echo Please install Python 3.11 or newer, then open this file again.
  >> "%LOG_FILE%" echo ERROR: Python not found
  goto :error
)

echo Python command: %PY_EXE% %PY_ARGS%
>> "%LOG_FILE%" echo Python command: %PY_EXE% %PY_ARGS%
%PY_EXE% %PY_ARGS% --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo ERROR: Python was found but could not run.
  >> "%LOG_FILE%" echo ERROR: Python command failed
  goto :error
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [2/4] Creating local Python environment...
  echo This may take a few minutes on first launch. Please keep this window open.
  %PY_EXE% %PY_ARGS% -m venv "%~dp0.venv" >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    echo ERROR: Failed to create the local Python environment.
    >> "%LOG_FILE%" echo ERROR: venv creation failed
    goto :error
  )
) else (
  echo [2/4] Local Python environment found.
)

echo [3/4] Checking required packages...
"%~dp0.venv\Scripts\python.exe" -c "import flask, openpyxl, requests" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo Installing required packages...
  "%~dp0.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    echo ERROR: Failed to install required packages.
    echo Please check your network, then run this file again.
    >> "%LOG_FILE%" echo ERROR: pip install failed
    goto :error
  )
)

echo [4/4] Starting local web app...
set "APP_PORT="
"%~dp0.venv\Scripts\python.exe" "%~dp0pick_port.py" > "%~dp0.port.tmp" 2>> "%LOG_FILE%"
if errorlevel 1 (
  echo ERROR: Failed to select a local port. See startup_log.txt.
  goto :error
)
set /p "APP_PORT=" < "%~dp0.port.tmp"
del "%~dp0.port.tmp" >nul 2>nul
if not defined APP_PORT (
  echo ERROR: Local port selection returned no result. See startup_log.txt.
  goto :error
)
if "%APP_PORT%"=="0" (
  echo ERROR: No free local port was found between 8765 and 8775.
  echo Please close old AI Voice Studio command windows, then run this file again.
  >> "%LOG_FILE%" echo ERROR: No free local port found
  goto :error
)
set "VOICE_STUDIO_PORT=%APP_PORT%"
echo.
echo The browser should open automatically.
echo If it does not, open this URL manually:
echo http://127.0.0.1:%APP_PORT%
echo.
echo Keep this window open while using the tool.
echo Press Ctrl+C here when you want to stop the tool.
echo.
>> "%LOG_FILE%" echo Starting app.py on port %APP_PORT%
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py" >> "%LOG_FILE%" 2>&1

echo.
echo The app has stopped.
echo If this was unexpected, open startup_log.txt in this folder.
pause
exit /b 0

:error
echo.
echo Startup failed. Details were saved to:
echo %LOG_FILE%
echo.
echo Please send a screenshot of this window or startup_log.txt.
pause
exit /b 1
