Write-Host "[push99] Starting automatic Git stage, commit, and push..." -ForegroundColor Cyan
if (Test-Path "encode_vault.py") {
    Write-Host "[push99] Encrypting passes into 3-layer secure vault (passes.json)..." -ForegroundColor Yellow
    py encode_vault.py
}
git status --short
git add -A
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "update: automatic push99 ($timestamp)"
git push origin main
Write-Host "[push99] Completed successfully!" -ForegroundColor Green
