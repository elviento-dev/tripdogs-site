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

%PY% admin.py
echo.
echo The admin panel has stopped.
pause
