# Build OfficeMitra-Setup.exe using Inno Setup 6
# Prefer installer\build-windows.ps1 which also bundles Python via PyInstaller.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Root "dist\OfficeMitra\OfficeMitra.exe"

if (-not (Test-Path $exe)) {
    Write-Host "Bundled app not found. Running full Windows build (PyInstaller + Inno Setup)..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "build-windows.ps1")
    exit $LASTEXITCODE
}

$Iss = Join-Path $PSScriptRoot "OfficeMitra.iss"
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "Inno Setup was not found. Portable app is in dist\OfficeMitra\OfficeMitra.exe" -ForegroundColor Yellow
    Write-Host "Install Inno Setup 6 or 7 from: https://jrsoftware.org/isdl.php"
    exit 0
}

Write-Host "Building OfficeMitra-Setup.exe..." -ForegroundColor Green
& $iscc $Iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }
Write-Host "Done: $(Join-Path $Root 'dist\OfficeMitra-Setup.exe')" -ForegroundColor Green
