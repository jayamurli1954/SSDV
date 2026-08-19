# Shared OfficeMitra install helpers (console + GUI + Inno Setup post-install).

function Get-OfficeMitraRoot {
    $moduleDir = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $moduleDir "pyproject.toml")) {
        return $moduleDir
    }
    return Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Find-Python311 {
    foreach ($candidate in @("py -3.12", "py -3.11", "py -3", "python")) {
        try {
            $verText = Invoke-Expression "$candidate -c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`"" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $verText) { continue }
            $parts = $verText.Trim().Split(".")
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                return @{ Command = $candidate; Version = $verText.Trim() }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Install-OfficeMitraPackages {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$PythonCommand,
        [scriptblock]$OnLog
    )

    function Write-Log([string]$Message) {
        if ($OnLog) { & $OnLog $Message }
    }

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path (Join-Path $Root ".venv"))) {
        Write-Log "Creating virtual environment..."
        Invoke-Expression "$PythonCommand -m venv `"$Root\.venv`"" | Out-Null
    } else {
        Write-Log "Reusing existing virtual environment."
    }

    if (-not (Test-Path $venvPython)) {
        throw "Could not create .venv at $Root"
    }

    Write-Log "Updating pip..."
    & $venvPython -m pip install -U pip | Out-Null

    Write-Log "Installing OfficeMitra (this may take a few minutes)..."
    & $venvPython -m pip install -e "$Root" | Out-Null
    & $venvPython -m pip install -e "${Root}[ui]" | Out-Null

    $ssdvExe = Join-Path $Root ".venv\Scripts\ssdv.exe"
    if (-not (Test-Path $ssdvExe)) {
        throw "Installation failed: ssdv.exe not found."
    }

    & $ssdvExe --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ssdv command failed after install."
    }

    $dataDir = Join-Path $Root "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
    }

    return $ssdvExe
}

function New-OfficeMitraShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ShortcutPath,
        [string]$Description = "OfficeMitra - AI CFO Dashboard",
        [string]$TargetPath = ""
    )

    $launcher = if ($TargetPath) { $TargetPath } else { Join-Path $Root "Start-OfficeMitra.bat" }
    if (-not (Test-Path $launcher)) {
        throw "Launcher not found: $launcher"
    }

    $icon = Join-Path $Root "assets\officemitra.ico"
    if (-not (Test-Path $icon)) {
        $icon = $launcher
    }

    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($ShortcutPath)
    $link.TargetPath = $launcher
    $link.WorkingDirectory = $Root
    $link.IconLocation = $icon
    $link.Description = $Description
    $link.Save()
}

function Install-OfficeMitraShortcuts {
    param([Parameter(Mandatory = $true)][string]$Root)

    $desktop = [Environment]::GetFolderPath("Desktop")
    $programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $folder = Join-Path $programs "OfficeMitra"
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
    }

    New-OfficeMitraShortcut -Root $Root -ShortcutPath (Join-Path $desktop "OfficeMitra.lnk")
    New-OfficeMitraShortcut -Root $Root -ShortcutPath (Join-Path $folder "OfficeMitra.lnk")
    New-OfficeMitraShortcut -Root $Root -ShortcutPath (Join-Path $folder "Install OfficeMitra.lnk") -Description "Repair or reinstall OfficeMitra" -TargetPath (Join-Path $Root "Install-OfficeMitra.bat")
}

function Invoke-OfficeMitraInstall {
    param(
        [string]$Root = (Get-OfficeMitraRoot),
        [switch]$Silent,
        [switch]$SkipShortcuts,
        [scriptblock]$OnLog
    )

    Set-Location $Root

    function Write-Log([string]$Message) {
        if ($OnLog) { & $OnLog $Message } elseif (-not $Silent) { Write-Host $Message }
    }

    Write-Log "Checking Python 3.11+..."
    $python = Find-Python311
    if (-not $python) {
        throw @"
Python 3.11 or newer was not found.

Download from https://www.python.org/downloads/
During install, tick: [x] Add python.exe to PATH
Then run the installer again.

Support: contact@sanmitratech.in
"@
    }

    Write-Log "Found Python $($python.Version) ($($python.Command))"
    Install-OfficeMitraPackages -Root $Root -PythonCommand $python.Command -OnLog $OnLog | Out-Null

    if (-not $SkipShortcuts) {
        Write-Log "Creating desktop and Start Menu shortcuts..."
        Install-OfficeMitraShortcuts -Root $Root
    }

    Write-Log "Installation complete."
    return @{
        Root = $Root
        Python = $python
    }
}

Export-ModuleMember -Function @(
    'Get-OfficeMitraRoot',
    'Find-Python311',
    'Install-OfficeMitraPackages',
    'New-OfficeMitraShortcut',
    'Install-OfficeMitraShortcuts',
    'Invoke-OfficeMitraInstall'
)
