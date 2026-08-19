# OfficeMitra — graphical install wizard for Windows (double-click Install-OfficeMitra.bat)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Root = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $PSScriptRoot "OfficeMitra.Install.psm1") -Force

$form = New-Object System.Windows.Forms.Form
$form.Text = "OfficeMitra Setup"
$form.Size = New-Object System.Drawing.Size(560, 490)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false

$iconPath = Join-Path $Root "assets\officemitra.ico"
if (Test-Path $iconPath) {
    $form.Icon = New-Object System.Drawing.Icon($iconPath)
}

$title = New-Object System.Windows.Forms.Label
$title.Location = New-Object System.Drawing.Point(24, 20)
$title.Size = New-Object System.Drawing.Size(500, 32)
$title.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$title.Text = "OfficeMitra Setup"
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Location = New-Object System.Drawing.Point(24, 54)
$subtitle.Size = New-Object System.Drawing.Size(500, 48)
$subtitle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$subtitle.Text = "SanMitra Technologies — your AI CFO dashboard.`nYour accounting data stays on this PC."
$form.Controls.Add($subtitle)

$body = New-Object System.Windows.Forms.Label
$body.Location = New-Object System.Drawing.Point(24, 110)
$body.Size = New-Object System.Drawing.Size(500, 120)
$body.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$body.Text = @"
Welcome!

This wizard will:
  • Check Python 3.11+
  • Install OfficeMitra on this computer
  • Create a desktop shortcut

Click Install to begin.
"@
$form.Controls.Add($body)

$log = New-Object System.Windows.Forms.TextBox
$log.Location = New-Object System.Drawing.Point(24, 240)
$log.Size = New-Object System.Drawing.Size(500, 120)
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = "Vertical"
$log.Font = New-Object System.Drawing.Font("Consolas", 9)
$log.Visible = $false
$form.Controls.Add($log)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(24, 370)
$progress.Size = New-Object System.Drawing.Size(500, 22)
$progress.Style = "Marquee"
$progress.Visible = $false
$form.Controls.Add($progress)

$installBtn = New-Object System.Windows.Forms.Button
$installBtn.Location = New-Object System.Drawing.Point(24, 400)
$installBtn.Size = New-Object System.Drawing.Size(120, 32)
$installBtn.Text = "Install"
$installBtn.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($installBtn)

$launchChk = New-Object System.Windows.Forms.CheckBox
$launchChk.Location = New-Object System.Drawing.Point(160, 406)
$launchChk.Size = New-Object System.Drawing.Size(220, 24)
$launchChk.Text = "Launch OfficeMitra when done"
$launchChk.Checked = $true
$launchChk.Visible = $false
$form.Controls.Add($launchChk)

$closeBtn = New-Object System.Windows.Forms.Button
$closeBtn.Location = New-Object System.Drawing.Point(404, 400)
$closeBtn.Size = New-Object System.Drawing.Size(120, 32)
$closeBtn.Text = "Close"
$closeBtn.Enabled = $false
$form.Controls.Add($closeBtn)

function Append-Log([string]$Message) {
    $log.AppendText("$Message`r`n")
    $log.SelectionStart = $log.Text.Length
    $log.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

$installBtn.Add_Click({
    $installBtn.Enabled = $false
    $body.Visible = $false
    $log.Visible = $true
    $progress.Visible = $true
    $launchChk.Visible = $true
    $installBtn.Visible = $false
    $closeBtn.Enabled = $false

    try {
        $result = Invoke-OfficeMitraInstall -Root $Root -OnLog { param($m) Append-Log $m }
        Append-Log ""
        Append-Log "Done! Use the OfficeMitra icon on your desktop to open the app."
        Append-Log "Support: contact@sanmitratech.in"
        $progress.Visible = $false
        $closeBtn.Enabled = $true
        if ($launchChk.Checked) {
            Start-Process (Join-Path $Root "Start-OfficeMitra.bat")
        }
    } catch {
        Append-Log ""
        Append-Log "ERROR: $($_.Exception.Message)"
        $progress.Visible = $false
        $closeBtn.Enabled = $true
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message,
            "OfficeMitra Setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
})

$closeBtn.Add_Click({ $form.Close() })

[void]$form.ShowDialog()
