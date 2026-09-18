@echo off
chcp 65001 >nul
title Build InkQuill.exe
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto nopython

echo Installing dependencies (first run may take a while)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt PySide6 pyinstaller
if errorlevel 1 goto fail

echo.
echo Building exe, this may take a few minutes...
python "%~dp0build.py"
if errorlevel 1 goto fail

echo.
echo Done! Output file: dist\inkquill.exe
pause
exit /b 0

:nopython
echo.
echo Python not found. Please install Python 3.8+ first.
echo Download: https://www.python.org/downloads/
pause
exit /b 1

:fail
echo.
echo Build failed. See messages above.
pause
exit /b 1
