@echo off
title DTC e-Bus Pass - Local Server
color 0A
cls

echo ============================================================
echo   DTC e-Bus Pass Local Server
echo ============================================================
echo.

:: Kill any existing Python servers on ports 5000 and 8000
echo Stopping any existing servers on ports 5000 and 8000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Try to find python.exe - check common locations
set PYTHON=
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python314\python.exe
) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe
) else (
    :: Try system python
    python --version >nul 2>&1
    if not errorlevel 1 set PYTHON=python
)

if "%PYTHON%"=="" (
    echo ERROR: Python not found!
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo Python found: %PYTHON%
echo.
echo Starting servers...
echo.
echo   Home page : http://localhost:8000/index.htm
echo   ePass     : http://localhost:8000/viewEBPass.html?passno=7502032600973
echo.
echo Open one of the above links in Chrome.
echo ============================================================
echo.

:: Change to the script's directory
cd /d "%~dp0"

:: Start the API Backend (Port 5000) in a new window
echo [1/2] Starting API backend on port 5000...
start "DTC API-Port 5000" /normal cmd.exe /k ""%PYTHON%" -u backend\api_server.py"

:: Wait 3 seconds
timeout /t 3 /nobreak >nul

:: Start the Frontend server (Port 8000)
echo [2/2] Starting Frontend server on port 8000...
"%PYTHON%" server.py

pause
