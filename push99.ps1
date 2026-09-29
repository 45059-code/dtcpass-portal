Write-Host "[push99] Starting automatic Git stage, commit, and push..." -ForegroundColor Cyan
if (Test-Path "backend\passes_db.json") {
    Copy-Item -Path "backend\passes_db.json" -Destination "passes.json" -Force
    Write-Host "[push99] Synced backend\passes_db.json -> passes.json for instant CDN access!" -ForegroundColor Yellow
}
git status --short
git add -A
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "update: automatic push99 ($timestamp)"
git push origin main
Write-Host "[push99] Completed successfully!" -ForegroundColor Green
