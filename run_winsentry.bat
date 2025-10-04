@echo off
echo Starting WinSentry...
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Run WinSentry
python run_winsentry.py %*

if errorlevel 1 (
    echo.
    echo WinSentry encountered an error. Please check the logs.
    pause
)
