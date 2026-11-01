@echo off
title Push to GitHub
color 0B
echo ======================================================
echo   DTC e-BusPass - Push Changes to GitHub
echo ======================================================
echo.

cd /d "%~dp0"

echo [*] Checking git status...
git status -s

echo.
echo [*] Staging all changes...
git add -A

echo [*] Committing changes...
git commit -m "fix: eliminate 0.2s date flash and guarantee Base64 photo display"

echo [*] Pushing to origin main...
git push origin main

if %errorlevel% equ 0 (
    echo.
    echo ======================================================
    echo   [SUCCESS] Successfully pushed all changes to GitHub!
    echo ======================================================
) else (
    echo.
    echo ======================================================
    echo   [ERROR] Git push failed. Please check your credentials.
    echo ======================================================
)

echo.
pause

