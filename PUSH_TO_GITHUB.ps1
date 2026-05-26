# DTC e-BusPass - GitHub Uploader using PowerShell (Windows native networking)
# Right-click > Run with PowerShell

$TOKEN     = "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"
$OWNER     = "45059-code"
$REPO      = "dtcpass-portal"
$BRANCH    = "main"
$ROOT      = "D:\dtcpass.delhi.gov.in"

$FILES = @(
    @{ local = "$ROOT\backend\requirements.txt"; repo = "backend/requirements.txt" },
    @{ local = "$ROOT\backend\api_server.py";    repo = "backend/api_server.py"    },
    @{ local = "$ROOT\render.yaml";              repo = "render.yaml"              }
)

$COMMIT_MSG = "fix: crash-proof startup, remove dotenv, fix host binding for Render"
$HEADERS = @{
    "Authorization" = "token $TOKEN"
    "Accept"        = "application/vnd.github.v3+json"
    "User-Agent"    = "dtcpass-ps-uploader/1.0"
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  DTC e-BusPass - GitHub Uploader (PowerShell)" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

function Upload-File($localPath, $repoPath) {
    Write-Host "[*] Uploading: $repoPath" -ForegroundColor Yellow

    if (-not (Test-Path $localPath)) {
        Write-Host "    [SKIP] File not found: $localPath" -ForegroundColor Gray
        return $false
    }

    # Read file and encode to base64
    $bytes   = [System.IO.File]::ReadAllBytes($localPath)
    $content = [Convert]::ToBase64String($bytes)

    # Get existing file SHA (needed to update existing files)
    $apiUrl = "https://api.github.com/repos/$OWNER/$REPO/contents/$repoPath`?ref=$BRANCH"
    $sha    = $null
    try {
        $existing = Invoke-RestMethod -Uri $apiUrl -Headers $HEADERS -Method Get -ErrorAction Stop
        $sha      = $existing.sha
        Write-Host "    (updating, sha=$($sha.Substring(0,10))...)" -ForegroundColor Gray
    } catch {
        Write-Host "    (creating new file)" -ForegroundColor Gray
    }

    # Build payload
    $body = @{
        message = $COMMIT_MSG
        content = $content
        branch  = $BRANCH
    }
    if ($sha) { $body["sha"] = $sha }
    $bodyJson = $body | ConvertTo-Json -Depth 3

    # PUT to GitHub
    $putUrl = "https://api.github.com/repos/$OWNER/$REPO/contents/$repoPath"
    try {
        Invoke-RestMethod -Uri $putUrl -Headers $HEADERS -Method Put -Body $bodyJson -ContentType "application/json" -ErrorAction Stop | Out-Null
        Write-Host "    [OK] Uploaded!" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "    [FAIL] $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

$ok = 0
foreach ($f in $FILES) {
    if (Upload-File $f.local $f.repo) { $ok++ }
    Start-Sleep -Milliseconds 500
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
if ($ok -eq $FILES.Count) {
    Write-Host "  SUCCESS! All $ok files pushed to GitHub." -ForegroundColor Green
    Write-Host "  Render will auto-redeploy in ~2 minutes." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Check deploy: https://dashboard.render.com" -ForegroundColor White
} else {
    Write-Host "  Done: $ok / $($FILES.Count) files uploaded." -ForegroundColor Yellow
    Write-Host "  Check errors above." -ForegroundColor Yellow
}
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
