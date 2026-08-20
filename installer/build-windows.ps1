# Build Windows OfficeMitra.exe and optionally OfficeMitra-Setup.exe.

[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "Using Python: $python" -ForegroundColor Green
& $python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"
if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required to build OfficeMitra." }

Write-Host "Installing package + UI + PyInstaller..." -ForegroundColor Green
& $python -m pip install -U pip
& $python -m pip install -e ".[ui]" pyinstaller

$spec = Join-Path $PSScriptRoot "OfficeMitra.spec"
$pyiArgs = @("--noconfirm", $spec)
if (-not $SkipClean) { $pyiArgs = @("--noconfirm", "--clean", $spec) }

Write-Host "Running PyInstaller (this can take several minutes)..." -ForegroundColor Green
& $python -m PyInstaller @pyiArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$distApp = Join-Path $Root "dist\OfficeMitra"
$exe = Join-Path $distApp "OfficeMitra.exe"
if (-not (Test-Path $exe)) {
    throw "Expected $exe after PyInstaller."
}

# Customer-facing notes + PDF manuals (visible after unzip / install)
$howto = Join-Path $PSScriptRoot "HOW-TO-INSTALL.txt"
Copy-Item $howto (Join-Path $distApp "HOW-TO-INSTALL.txt") -Force

$docsDest = Join-Path $distApp "docs"
New-Item -ItemType Directory -Path $docsDest -Force | Out-Null
$manuals = @(
    "CLIENT_INSTALL.pdf",
    "CLIENT_MANUAL.pdf",
    "USER_MANUAL.pdf",
    "CLIENT_INSTALL.md",
    "CLIENT_MANUAL.md"
)
foreach ($name in $manuals) {
    $src = Join-Path $Root "docs\$name"
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $docsDest $name) -Force
    } else {
        Write-Host "Warning: missing docs\$name (not added to package)" -ForegroundColor Yellow
    }
}
$missingPdf = @("CLIENT_INSTALL.pdf", "CLIENT_MANUAL.pdf", "USER_MANUAL.pdf") |
    Where-Object { -not (Test-Path (Join-Path $docsDest $_)) }
if ($missingPdf.Count -gt 0) {
    Write-Host "Tip: regenerate PDFs with: python scripts\build_docs_pdf.py" -ForegroundColor Yellow
}

$zip = Join-Path $Root "dist\OfficeMitra-windows.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Push-Location $distApp
try {
    & tar.exe -a -cf $zip *
    if ($LASTEXITCODE -ne 0) { throw "Failed to create zip with tar.exe" }
} finally {
    Pop-Location
}
Write-Host "Portable folder: $distApp"
Write-Host "Zip: $zip (includes HOW-TO-INSTALL.txt and docs\*.pdf)"

if ($SkipInstaller) {
    Write-Host "Skipping Inno Setup (-SkipInstaller)."
    exit 0
}

$iss = Join-Path $PSScriptRoot "OfficeMitra.iss"
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "Inno Setup not found. Portable zip is ready; install Inno Setup 6 or 7 to build OfficeMitra-Setup.exe." -ForegroundColor Yellow
    Write-Host "https://jrsoftware.org/isdl.php"
    exit 0
}

Write-Host "Building OfficeMitra-Setup.exe..." -ForegroundColor Green
& $iscc $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

Write-Host ""
Write-Host "Done. Customer files:" -ForegroundColor Green
Write-Host "  dist\OfficeMitra-Setup.exe   (recommended installer)"
Write-Host "  dist\OfficeMitra-windows.zip (portable)"
