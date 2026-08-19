@echo off
setlocal enabledelayedexpansion
title Video Downloader Setup
cd /d "%~dp0"

echo ============================================
echo  Video Downloader - Setup and Launch
echo ============================================
echo.

REM --- Find a Python interpreter ---------------------------------------
call :find_python

if not defined PYTHON_CMD (
    echo [INFO] Python 3.8+ not found. Attempting to install it...
    echo.
    call :install_python
    call :refresh_path
    call :find_python
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Couldn't install Python automatically.
    echo.
    echo If you didn't run this as Administrator, right-click this file
    echo and choose "Run as administrator", then try again.
    echo.
    echo Otherwise, install it yourself from https://www.python.org/downloads/
    echo IMPORTANT: on the first setup screen, check the box that says
    echo            "Add python.exe to PATH" before clicking Install.
    echo.
    echo Then run this file again.
    pause
    exit /b 1
)

echo [OK] Using: !PYTHON_CMD!
echo.

REM --- Make sure pip is available ---------------------------------------
!PYTHON_CMD! -m pip --version >nul 2>&1
if not %errorlevel%==0 (
    echo [INFO] pip not found, bootstrapping it...
    !PYTHON_CMD! -m ensurepip --upgrade
)

REM --- Install/upgrade required packages --------------------------------
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found in this folder.
    echo Make sure video_downloader.py, requirements.txt, and this .bat
    echo file are all in the same folder.
    pause
    exit /b 1
)

echo [INFO] Installing/updating required packages...
!PYTHON_CMD! -m pip install --upgrade pip >nul 2>&1
!PYTHON_CMD! -m pip install -r requirements.txt
if not %errorlevel%==0 (
    echo.
    echo [ERROR] Package installation failed. Check the messages above.
    pause
    exit /b 1
)
echo.

REM --- ffmpeg -------------------------------------------------------------
REM The app manages its own ffmpeg copy in a "ffmpeg" folder next to this
REM script, downloading it automatically on first run if it's missing.
REM Nothing to do here.

REM --- Launch the app -----------------------------------------------------
if not exist "video_downloader.py" (
    echo [ERROR] video_downloader.py not found in this folder.
    pause
    exit /b 1
)

echo [INFO] Launching Video Downloader...
echo.
!PYTHON_CMD! video_downloader.py

if not %errorlevel%==0 (
    echo.
    echo [ERROR] The app closed with an error. See the messages above.
    pause
)

endlocal
exit /b 0

REM =========================================================================
REM  Subroutines
REM =========================================================================

:find_python
REM Sets PYTHON_CMD to a working "python" or "py -3" command that satisfies
REM the 3.8+ requirement, or leaves it undefined if nothing usable is found.
set "PYTHON_CMD="

where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)" >nul 2>&1
    if !errorlevel!==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    where py >nul 2>&1
    if !errorlevel!==0 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)" >nul 2>&1
        if !errorlevel!==0 set "PYTHON_CMD=py -3"
    )
)
exit /b 0

:install_python
REM Tries winget first (fastest, keeps itself current). Falls back to
REM downloading the official python.org installer directly and running
REM it silently if winget isn't available or doesn't work. Either path
REM needs the admin rights this app already assumes.
where winget >nul 2>&1
if %errorlevel%==0 (
    for %%V in (Python.Python.3.13 Python.Python.3.12 Python.Python.3.11) do (
        if not defined PYTHON_INSTALLED (
            echo [INFO] Trying winget package %%V...
            winget install --id %%V -e --silent --scope machine --accept-package-agreements --accept-source-agreements
            if !errorlevel!==0 set "PYTHON_INSTALLED=1"
        )
    )
)

if defined PYTHON_INSTALLED exit /b 0

echo [INFO] winget install didn't work, downloading Python directly...
set "PY_INSTALLER=%TEMP%\python-installer.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe' -OutFile '%PY_INSTALLER%' -UseBasicParsing } catch { exit 1 }"
if not %errorlevel%==0 (
    echo [WARNING] Couldn't download the Python installer. Check your internet connection.
    exit /b 1
)

echo [INFO] Running the Python installer silently...
start /wait "" "%PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
del /q "%PY_INSTALLER%" >nul 2>&1
exit /b 0

:refresh_path
REM Pulls the current User + System PATH from the registry so a package
REM just installed by winget/the installer becomes usable in this same
REM window, without needing to close and reopen it.
set "USERPATH="
set "SYSPATH="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USERPATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSPATH=%%B"
if defined SYSPATH if defined USERPATH set "PATH=%SYSPATH%;%USERPATH%"
exit /b 0
