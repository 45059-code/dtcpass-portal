@echo off
echo [push99] Starting automatic Git stage, commit, and push...
cd /d "%~dp0"
if exist "backend\passes_db.json" (
    copy /y "backend\passes_db.json" "passes.json" >nul
    echo [push99] Synced backend\passes_db.json -^> passes.json for instant CDN access!
)
git status --short
git add -A
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set commit_msg=update: automatic push99 %datetime:~0,8%_%datetime:~8,6%
git commit -m "%commit_msg%"
git push origin main
echo [push99] Completed!
