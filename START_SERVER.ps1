# DTC e-Bus Pass - Server Launcher
# Right-click this file and choose "Run with PowerShell"

$ROOT  = "D:\dtcpass.delhi.gov.in"

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  DTC e-Bus Pass - Local Server Launcher" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# Kill any existing servers on these ports
Write-Host "[*] Clearing ports 5000 and 8000..." -ForegroundColor Yellow
$ports = @(5000, 8000)
foreach ($port in $ports) {
    $pids = netstat -ano 2>$null | Select-String ":$port\s" | ForEach-Object {
        ($_ -split "\s+")[-1]
    } | Where-Object { $_ -match '^\d+$' } | Sort-Object -Unique
    foreach ($procId in $pids) {
        try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
    }
}
Start-Sleep -Seconds 1

# Resolve Python dynamically
$PYEXE = ""
$candidates = @(
    "C:\Users\45059\AppData\Local\Programs\Python\Python314\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
)

foreach ($path in $candidates) {
    if (Test-Path $path) {
        $PYEXE = $path
        break
    }
}

if (-not $PYEXE) {
    $check = Get-Command "python" -ErrorAction SilentlyContinue
    if ($check) {
        $PYEXE = "python"
    }
}

if (-not $PYEXE) {
    Write-Host "[ERROR] Python not found!" -ForegroundColor Red
    Write-Host "        Please make sure Python is installed and added to PATH." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Python found: $PYEXE" -ForegroundColor Green
Write-Host ""

# Start API backend (port 5000) in a new window
Write-Host "[1/2] Starting API backend on port 5000..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k", "title DTC API-Port 5000 && cd /d `"$ROOT`" && `"$PYEXE`" -u backend\api_server.py" `
    -WindowStyle Normal

Start-Sleep -Seconds 3

# Start Frontend server (port 8000) in a new window
Write-Host "[2/2] Starting Frontend server on port 8000..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k", "title DTC Frontend-Port 8000 && cd /d `"$ROOT`" && `"$PYEXE`" -u server.py" `
    -WindowStyle Normal

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  SERVERS ARE RUNNING!" -ForegroundColor Green
Write-Host "" 
Write-Host "  Frontend : http://localhost:8000" -ForegroundColor White
Write-Host "  API      : http://localhost:5000" -ForegroundColor White
Write-Host ""
Write-Host "  Test Pass: http://localhost:8000/viewEBPass.html" -ForegroundColor White
Write-Host "             ?passno=7502032600973" -ForegroundColor White
Write-Host ""
Write-Host "  To STOP: Close the two DTC server CMD windows" -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# Open browser
Write-Host "[*] Opening browser..." -ForegroundColor Green
Start-Process "http://localhost:8000"

Write-Host ""
Write-Host "Press Enter to close this launcher..." -ForegroundColor Gray
Read-Host
