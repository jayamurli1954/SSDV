; Optional: source-tree installer that still requires Python 3.11+ (developers).
; Preferred customer installer is OfficeMitra.iss (bundled .exe).

#define MyAppName "OfficeMitra"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SanMitra Technologies"
#define MyAppURL "https://www.sanmitratech.in"
#define MyAppSupport "contact@sanmitratech.in"

[Setup]
AppId={{A7B3C4D5-E6F7-4890-ABCD-EF1234567891}
AppName={#MyAppName} (source)
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}Source
DefaultGroupName={#MyAppName} Source
OutputDir=..\dist
OutputBaseFilename=OfficeMitra-Source-Setup
SetupIconFile=..\assets\officemitra.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".venv\*;.git\*;dist\*;build\*;*.sqlite;__pycache__\*;.pytest_cache\*;.tmp_*;*.pyc"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Start-OfficeMitra.bat"; IconFilename: "{app}\assets\officemitra.ico"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName} (source)"; Filename: "{app}\Start-OfficeMitra.bat"; IconFilename: "{app}\assets\officemitra.ico"; WorkingDir: "{app}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"" -Silent"; Flags: waituntilterminated
Filename: "{app}\Start-OfficeMitra.bat"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked
