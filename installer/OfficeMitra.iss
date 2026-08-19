; OfficeMitra Windows installer (Inno Setup 6)
; Build on a Windows PC with Inno Setup installed:
;   .\installer\build-installer.ps1

#define MyAppName "OfficeMitra"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SanMitra Technologies"
#define MyAppURL "https://www.sanmitratech.in"
#define MyAppSupport "contact@sanmitratech.in"

[Setup]
AppId={{A7B3C4D5-E6F7-4890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupport}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=OfficeMitra-Setup
SetupIconFile=..\assets\officemitra.ico
UninstallDisplayIcon={app}\assets\officemitra.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".venv\*;.git\*;dist\*;*.sqlite;__pycache__\*;.pytest_cache\*;.tmp_*;*.pyc"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Start-OfficeMitra.bat"; IconFilename: "{app}\assets\officemitra.ico"; WorkingDir: "{app}"
Name: "{group}\Install / Repair"; Filename: "{app}\Install-OfficeMitra.bat"; IconFilename: "{app}\assets\officemitra.ico"; WorkingDir: "{app}"
Name: "{group}\User manual"; Filename: "{app}\docs\CLIENT_MANUAL.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Start-OfficeMitra.bat"; IconFilename: "{app}\assets\officemitra.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"" -Silent"; StatusMsg: "Installing OfficeMitra components (first time may take a few minutes)..."; Flags: waituntilterminated
Filename: "{app}\Start-OfficeMitra.bat"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nYour accounting data stays on this PC. OfficeMitra reads exported books only — it never writes back to Tally, Zoho, or Busy.%n%nSupport: {#MyAppSupport}

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\data"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
