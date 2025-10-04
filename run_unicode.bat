@echo off
REM Batch file to run Python applications with Unicode support

REM Set console code page to UTF-8
chcp 65001 >nul 2>&1

REM Set environment variables for Unicode support
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=1

REM Run the Python script with Unicode support
python -X utf8 %*

REM If the above fails, try with the Unicode handler script
if errorlevel 1 (
    echo Trying with Unicode handler...
    python run_with_unicode.py %*
)
