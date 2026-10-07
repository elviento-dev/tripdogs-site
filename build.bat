@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo BUILD ERROR:
    echo Python 3 was not found on this computer.
    echo Install it from https://www.python.org and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

%PY% build.py
if errorlevel 1 (
    echo.
    echo Build FAILED. Read the message above, fix the file and run again.
) else (
    echo.
    echo Done. The site is updated. Open index.html in your browser.
)
echo.
pause
