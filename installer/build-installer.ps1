# Build OfficeMitra-Setup.exe using Inno Setup 6
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Iss = Join-Path $PSScriptRoot "OfficeMitra.iss"
$Dist = Join-Path $Root "dist"

$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 was not found on this PC." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Inno Setup from: https://jrsoftware.org/isdl.php"
    Write-Host "Then run this script again to build dist\OfficeMitra-Setup.exe"
    Write-Host ""
    Write-Host "For testing without Inno Setup, users can double-click:"
    Write-Host "  Install-OfficeMitra.bat"
    Write-Host ""
    exit 1
}

if (-not (Test-Path (Join-Path $Root "assets\officemitra.ico"))) {
    Write-Host "Missing assets\officemitra.ico — run icon generation first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Dist)) {
    New-Item -ItemType Directory -Path $Dist | Out-Null
}

Write-Host "Building OfficeMitra-Setup.exe..." -ForegroundColor Green
& $iscc $Iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed."
}

$setup = Join-Path $Dist "OfficeMitra-Setup.exe"
Write-Host ""
Write-Host "Done: $setup" -ForegroundColor Green
Write-Host "Upload this file to your download page for customers."
