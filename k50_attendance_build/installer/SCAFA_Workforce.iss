#define MyAppName "SCAFA Workforce"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "SCAFA Workforce"
#define MyAppExeName "SCAFA_Workforce.exe"

[Setup]
AppId={{B4D76C88-5A2E-4A71-9F42-1C6C72A50D10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SCAFA Workforce
DefaultGroupName={#MyAppName}
OutputDir=..\..\installer-output
OutputBaseFilename=SCAFA_Workforce_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\SCAFA_Workforce.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SCAFA Workforce"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SCAFA Workforce"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SCAFA Workforce"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Do not delete the user's database in their home folder during uninstall.
