@echo off
chcp 65001 >nul
title InkQuill - Picture to Black and White Line Art
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto nopython

echo Checking dependencies (first run may take a while)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt PySide6
if errorlevel 1 goto pipfail

echo.
echo Starting InkQuill ...
python "%~dp0inkquill.py"
goto end

:nopython
echo.
echo Python not found. Please install Python 3.8+ and tick "Add python.exe to PATH".
echo Download: https://www.python.org/downloads/
pause
exit /b 1

:pipfail
echo.
echo Failed to install dependencies. Check your network and Python install.
pause
exit /b 1

:end
pause
