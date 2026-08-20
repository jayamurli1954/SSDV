# Start OfficeMitra on this PC
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$frozen = Join-Path $Root "dist\OfficeMitra\OfficeMitra.exe"
if (Test-Path $frozen) {
    Start-Process -FilePath $frozen -WorkingDirectory (Split-Path $frozen)
    exit 0
}

$desktopExe = Join-Path $Root ".venv\Scripts\officemitra.exe"
if (Test-Path $desktopExe) {
    & $desktopExe
    exit $LASTEXITCODE
}

$ssdvExe = Join-Path $Root ".venv\Scripts\ssdv.exe"
if (-not (Test-Path $ssdvExe)) {
    Write-Host ""
    Write-Host "OfficeMitra is not installed yet." -ForegroundColor Red
    Write-Host "Run install.ps1 first (right-click → Run with PowerShell)."
    Write-Host ""
    Write-Host "Support: contact@sanmitratech.in"
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "Starting OfficeMitra..." -ForegroundColor Green
Write-Host "Leave this window open while you use the dashboard."
Write-Host "Browser: http://localhost:8501"
Write-Host "Stop: press Ctrl+C in this window."
Write-Host ""

$db = Join-Path $Root "data\ssdv_connect.sqlite"
if (-not (Test-Path $db)) {
    $db = Join-Path $Root "data\ssdv.sqlite"
}

if (Test-Path $db) {
    & $ssdvExe --db $db ui
} else {
    & $ssdvExe ui
}
