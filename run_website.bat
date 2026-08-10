@echo off
title India Election Analytics
cd /d "%~dp0"

echo ============================================
echo   INDIA ELECTION ANALYTICS - STARTUP
echo ============================================
echo.

REM --- Check Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- Create virtual environment if missing ---
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
)

REM --- Activate virtual environment ---
call venv\Scripts\activate.bat

REM --- Install dependencies ---
echo [INFO] Installing dependencies (first run may take a few minutes)...
pip install -r requirements.txt >nul 2>nul

REM --- Open browser and start the website ---
echo [INFO] Starting website at http://127.0.0.1:5000 ...
timeout /t 1 >nul
start "" http://127.0.0.1:5000
python app.py

echo.
echo Website stopped. Press any key to close.
pause >nul
