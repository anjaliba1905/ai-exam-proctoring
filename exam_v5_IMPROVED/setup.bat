@echo off
setlocal EnableDelayedExpansion
title AI Exam Proctoring - Setup Wizard

echo ============================================
echo  AI Exam Proctoring - Setup Wizard
echo ============================================
echo.

cd /d "%~dp0"

REM ── Python check ──────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.10 or newer from https://www.python.org
    echo IMPORTANT: Check "Add Python to PATH" during install!
    pause
    exit /b 1
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo [OK] %PYVER% found.

REM ── Delete broken venv if pip is missing or corrupted ─────────────────────
if exist "venv\Scripts\pip.exe" (
    venv\Scripts\python.exe -c "import pip" >nul 2>&1
    if errorlevel 1 (
        echo [FIX] Corrupted venv detected. Deleting and rebuilding...
        rmdir /s /q venv
    )
) else if exist "venv" (
    echo [FIX] Incomplete venv detected. Deleting and rebuilding...
    rmdir /s /q venv
)

REM ── Create fresh venv ─────────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create venv. Check Python installation.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment OK.
)

REM ── Activate venv ──────────────────────────────────────────────────────────
call venv\Scripts\activate.bat

REM ── Fix pip using ensurepip (bypasses broken pip.exe entirely) ────────────
echo [SETUP] Bootstrapping pip...
python -m ensurepip --upgrade >nul 2>&1
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [WARN] pip upgrade had issues, continuing anyway...
)
echo [OK] pip ready.

REM ── Install all requirements ───────────────────────────────────────────────
echo [SETUP] Installing packages (may take 3-5 minutes on first run)...
echo         Installing: PyQt5, OpenCV, MediaPipe, sounddevice, psutil...
echo.

python -m pip install PyQt5 --quiet
if errorlevel 1 ( echo [WARN] PyQt5 install issue ) else ( echo [OK] PyQt5 installed )

python -m pip install opencv-python --quiet
if errorlevel 1 ( echo [WARN] opencv-python install issue ) else ( echo [OK] opencv-python installed )

python -m pip install mediapipe --quiet
if errorlevel 1 ( echo [WARN] mediapipe install issue ) else ( echo [OK] mediapipe installed )

python -m pip install sounddevice --quiet
if errorlevel 1 ( echo [WARN] sounddevice install issue ) else ( echo [OK] sounddevice installed )

python -m pip install psutil --quiet
if errorlevel 1 ( echo [WARN] psutil install issue ) else ( echo [OK] psutil installed )

python -m pip install numpy scipy Pillow PyMuPDF PyQtWebEngine --quiet
if errorlevel 1 ( echo [WARN] some optional packages had issues ) else ( echo [OK] optional packages installed )

REM ── Verify PyQt5 actually works ───────────────────────────────────────────
echo.
echo [CHECK] Verifying PyQt5...
python -c "from PyQt5.QtWidgets import QApplication; print('[OK] PyQt5 working correctly')"
if errorlevel 1 (
    echo [ERROR] PyQt5 verification failed. Try running setup.bat again.
    pause
    exit /b 1
)

REM ── Initialise database ────────────────────────────────────────────────────
echo [SETUP] Initialising database...
python -c "from database import init_db, init_exam_config; init_db(); init_exam_config(); print('[OK] Database ready.')"

echo.
echo ============================================
echo  Setup complete!
echo  Run the app anytime with:  run.bat
echo ============================================
echo.
pause
