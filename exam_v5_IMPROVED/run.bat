@echo off
setlocal
title AI Exam Proctoring System

cd /d "%~dp0"

REM ── If venv missing, tell user to run setup first ─────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Please run setup.bat first!
    pause
    exit /b 1
)

REM ── Quick pip health check — re-run setup silently if broken ──────────────
venv\Scripts\python.exe -c "import pip, PyQt5" >nul 2>&1
if errorlevel 1 (
    echo [FIX] Environment needs repair. Running setup...
    call setup.bat
)

REM ── Activate and launch ────────────────────────────────────────────────────
call venv\Scripts\activate.bat
echo [START] Launching AI Exam Proctoring System...
echo         Keep this window open while the app is running.
echo.
python main_app.py

if errorlevel 1 (
    echo.
    echo [ERROR] App exited with an error. See above for details.
    pause
)
