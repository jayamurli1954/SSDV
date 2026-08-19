# Start OfficeMitra on this PC
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

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
