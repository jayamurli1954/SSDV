# OfficeMitra / SSDV — guided install for Windows
# Right-click → Run with PowerShell, or run silently from OfficeMitra-Setup.exe

param(
    [switch]$Silent,
    [switch]$SkipShortcuts
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
Import-Module (Join-Path $Root "installer\OfficeMitra.Install.psm1") -Force

function Write-Step([string]$Number, [string]$Text) {
    if ($Silent) { return }
    Write-Host ""
    Write-Host "=== Step $Number ===" -ForegroundColor Cyan
    Write-Host $Text
}

function Pause-Continue([string]$Message = "Press Enter to continue...") {
    if ($Silent) { return }
    Read-Host $Message | Out-Null
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "OfficeMitra — Installation wizard" -ForegroundColor Green
    Write-Host "SanMitra Technologies — https://www.sanmitratech.in"
    Write-Host "Support: contact@sanmitratech.in"
    Write-Host ""
    Write-Host "This installer sets up OfficeMitra on THIS computer."
    Write-Host "Your accounting data stays on this PC."
    Write-Host ""
    Pause-Continue
}

try {
    Write-Step "1" "Checking Python and installing components..."
    $onLog = if ($Silent) { $null } else { { param($m) Write-Host $m } }
    Invoke-OfficeMitraInstall -Root $Root -Silent:$Silent -SkipShortcuts:$SkipShortcuts -OnLog $onLog | Out-Null
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    if (-not $Silent) { Pause-Continue "Press Enter to close..." }
    exit 1
}

if (-not $Silent) {
    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Double-click the OfficeMitra icon on your desktop"
    Write-Host "  2. Connect your accounts data in the setup screen"
    Write-Host "  3. Read docs\CLIENT_MANUAL.md for the full guide"
    Write-Host ""
    Write-Host "Support: contact@sanmitratech.in  |  https://www.sanmitratech.in"
    Write-Host ""
    Pause-Continue "Press Enter to finish..."
}
