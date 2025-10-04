@echo off
echo WinSentry Installation Script
echo ============================

echo.
echo Installing WinSentry and dependencies...
pip install -e .

echo.
echo Testing imports...
python test_imports.py

echo.
echo Running installation test...
python test_installation.py

echo.
echo Installation complete!
echo.
echo To start WinSentry, run:
echo   winsentry
echo   or
echo   python run_winsentry.py
echo   or
echo   run_winsentry.bat
echo.
echo Then open your browser to: http://localhost:8888
echo.
echo Note: WinSentry requires Administrator privileges for service management.
pause
