#define MyAppName "K50 Attendance Manager"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "K50 Attendance Manager"
#define MyAppExeName "K50_Attendance_Manager.exe"

[Setup]
AppId={{B4D76C88-5A2E-4A71-9F42-1C6C72A50D10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\K50 Attendance Manager
DefaultGroupName={#MyAppName}
OutputDir=installer-output
OutputBaseFilename=K50_Attendance_Manager_Setup
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
Source: "..\dist\K50_Attendance_Manager.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\K50 Attendance Manager"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\K50 Attendance Manager"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch K50 Attendance Manager"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Do not delete the user's database in their home folder during uninstall.
