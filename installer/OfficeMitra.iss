; OfficeMitra Windows installer (Inno Setup 6) — bundled executable, no Python required.
; Build:  .\installer\build-windows.ps1

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
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=OfficeMitra-Setup
SetupIconFile=..\assets\officemitra.ico
UninstallDisplayIcon={app}\OfficeMitra.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
; Bundled app + HOW-TO-INSTALL.txt + docs\*.pdf (copied by build-windows.ps1)
Source: "..\dist\OfficeMitra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\OfficeMitra.exe"; WorkingDir: "{app}"
Name: "{group}\How to install"; Filename: "{app}\HOW-TO-INSTALL.txt"
Name: "{group}\User manual (PDF)"; Filename: "{app}\docs\CLIENT_MANUAL.pdf"
Name: "{group}\Install guide (PDF)"; Filename: "{app}\docs\CLIENT_INSTALL.pdf"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\OfficeMitra.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\OfficeMitra.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nNo Python install is required. Your accounting data stays on this PC. OfficeMitra reads exported books only — it never writes back to Tally, Zoho, or Busy.%n%nSupport: {#MyAppSupport}

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\OfficeMitra\logs"
