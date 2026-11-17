#define MyAppName "SCAFA Workforce"
#ifndef MyAppVersion
  #define MyAppVersion "1.2.3"
#endif
#define MyAppPublisher "SCAFA Workforce"
#define MyAppExeName "SCAFA_Workforce.exe"

[Setup]
AppId={{B4D76C88-5A2E-4A71-9F42-1C6C72A50D10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SCAFA Workforce
DefaultGroupName={#MyAppName}
OutputDir=..\..\installer-output
OutputBaseFilename=SCAFA_Workforce_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\SCAFA_Workforce\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\scafa-updater.exe"; Flags: dontcopy

[Icons]
Name: "{group}\SCAFA Workforce"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SCAFA Workforce"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SCAFA Workforce"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; Do not delete the user's database in their home folder during uninstall.


[Code]
const
  MonitorTaskName = 'SCAFA Workforce Attendance Monitor';

var
  MonitorWasRunning: Boolean;
  MonitorRestored: Boolean;
  SetupSucceeded: Boolean;
  MonitorHelperPath: String;

function RunMonitorPowerShell(const Script: String; var OutputText, ErrorText: String): Boolean;
var
  ResultCode: Integer;
  I: Integer;
  Captured: TExecOutput;
  Params: String;
begin
  OutputText := '';
  ErrorText := '';
  Captured.Error := False;
  SetArrayLength(Captured.StdOut, 0);
  SetArrayLength(Captured.StdErr, 0);
  if MonitorHelperPath = '' then begin
    ErrorText := 'The bounded Task Scheduler command helper has not been initialized.';
    Result := False;
    Exit;
  end;
  if not FileExists(MonitorHelperPath) then begin
    ErrorText := 'The bounded Task Scheduler command helper is missing: ' + MonitorHelperPath;
    Result := False;
    Exit;
  end;

  Params := '--installer-powershell-script "' + Script + '"';

  try
    Result := ExecAndCaptureOutput(
      MonitorHelperPath,
      Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode, Captured);
  except
    ErrorText := GetExceptionMessage;
    Result := False;
    Exit;
  end;

  if not Result then begin
    ErrorText := SysErrorMessage(ResultCode);
    Exit;
  end;

  if Captured.Error then begin
    ErrorText := 'PowerShell output capture failed.';
    Result := False;
    Exit;
  end;

  for I := 0 to GetArrayLength(Captured.StdOut) - 1 do
    OutputText := OutputText + Captured.StdOut[I];

  for I := 0 to GetArrayLength(Captured.StdErr) - 1 do begin
    if ErrorText <> '' then
      ErrorText := ErrorText + #13#10;
    ErrorText := ErrorText + Captured.StdErr[I];
  end;

  if ResultCode <> 0 then begin
    if ErrorText = '' then
      ErrorText := Format('PowerShell exited with code %d.', [ResultCode]);
    Result := False;
    Exit;
  end;

  Result := True;
end;

function ReadMonitorTaskState(var State, ErrorText: String): Boolean;
var
  OutputText: String;
  Script: String;
begin
  Script :=
    '$ErrorActionPreference=''Stop''; $taskName=''SCAFA Workforce Attendance Monitor''; ' +
    'try { $task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop; ' +
    '[Console]::Out.Write($task.State.ToString()) } catch { ' +
    'if ($_.FullyQualifiedErrorId -like ''NoMatchingTasksFound*'') { [Console]::Out.Write(''Missing''); exit 0 }; ' +
    '[Console]::Error.WriteLine($_.Exception.Message); exit 2 }';

  Result := RunMonitorPowerShell(Script, OutputText, ErrorText);
  if Result then begin
    State := Trim(OutputText);
    if State = '' then begin
      ErrorText := 'Task Scheduler returned an empty monitor state.';
      Result := False;
    end;
  end;
end;

function StopMonitorTask(var Outcome, ErrorText: String): Boolean;
var
  Script: String;
begin
  Script :=
    '$ErrorActionPreference=''Stop''; $taskName=''SCAFA Workforce Attendance Monitor''; ' +
    'try { $task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop; ' +
    'if ($task.State -ne ''Running'') { [Console]::Out.Write(''NotRunning:'' + $task.State.ToString()); exit 0 }; ' +
    'Stop-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop | Out-Null; ' +
    '$deadline=(Get-Date).AddSeconds(15); do { Start-Sleep -Milliseconds 250; ' +
    '$task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop } ' +
    'while (($task.State -eq ''Running'' -or $task.State -eq ''Queued'') -and (Get-Date) -lt $deadline); ' +
    'if ($task.State -eq ''Running'' -or $task.State -eq ''Queued'') { ' +
    '[Console]::Error.WriteLine(''Timed out waiting for the monitor task to stop.''); exit 3 }; ' +
    '[Console]::Out.Write(''Stopped:'' + $task.State.ToString()) } catch { ' +
    '[Console]::Error.WriteLine($_.Exception.Message); exit 2 }';

  Result := RunMonitorPowerShell(Script, Outcome, ErrorText);
  if Result then begin
    Outcome := Trim(Outcome);
    Result :=
      (CompareText(Outcome, 'Stopped:Ready') = 0) or
      (CompareText(Outcome, 'Stopped:Disabled') = 0) or
      (CompareText(Outcome, 'NotRunning:Ready') = 0) or
      (CompareText(Outcome, 'NotRunning:Disabled') = 0);
    if not Result then
      ErrorText := 'Task Scheduler returned an unexpected monitor stop state: ' + Outcome;
  end;
end;

function StartMonitorTask(var ErrorText: String): Boolean;
var
  OutputText: String;
  Script: String;
begin
  Script :=
    '$ErrorActionPreference=''Stop''; $taskName=''SCAFA Workforce Attendance Monitor''; ' +
    'try { $task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop; ' +
    'if ($task.State -eq ''Running'') { [Console]::Out.Write(''Running''); exit 0 }; ' +
    'if ($task.State -ne ''Ready'') { [Console]::Error.WriteLine(''Monitor task is not ready to restart: '' + $task.State.ToString()); exit 3 }; ' +
    'Start-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop | Out-Null; ' +
    '$deadline=(Get-Date).AddSeconds(15); do { Start-Sleep -Milliseconds 250; ' +
    '$task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop } ' +
    'while ($task.State -ne ''Running'' -and (Get-Date) -lt $deadline); ' +
    'if ($task.State -ne ''Running'') { [Console]::Error.WriteLine(''Timed out waiting for the monitor task to start.''); exit 3 }; ' +
    '[Console]::Out.Write(''Running'') } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 2 }';

  Result := RunMonitorPowerShell(Script, OutputText, ErrorText);
  if Result and (CompareText(Trim(OutputText), 'Running') <> 0) then begin
    ErrorText := 'Task Scheduler did not confirm that the monitor is running.';
    Result := False;
  end;
end;

function RestoreMonitorTask(var ErrorText: String): Boolean;
var
  State: String;
begin
  Result := ReadMonitorTaskState(State, ErrorText);
  if not Result then
    Exit;

  if CompareText(State, 'Running') = 0 then begin
    MonitorRestored := True;
    Exit;
  end;

  if CompareText(State, 'Ready') <> 0 then begin
    ErrorText := 'The monitor task cannot be safely restarted from state "' + State + '".';
    Result := False;
    Exit;
  end;

  Result := StartMonitorTask(ErrorText);
  if Result then
    MonitorRestored := True;
end;

function RemoveMonitorTask(var ErrorText: String): Boolean;
var
  OutputText: String;
  Script: String;
begin
  Script :=
    '$ErrorActionPreference=''Stop''; $taskName=''SCAFA Workforce Attendance Monitor''; ' +
    'try { $task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop; ' +
    'if ($task.State -eq ''Running'') { ' +
    'Stop-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop | Out-Null; ' +
    '$deadline=(Get-Date).AddSeconds(15); do { Start-Sleep -Milliseconds 250; ' +
    '$task=Get-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -ErrorAction Stop } ' +
    'while (($task.State -eq ''Running'' -or $task.State -eq ''Queued'') -and (Get-Date) -lt $deadline) }; ' +
    'if ($task.State -eq ''Running'' -or $task.State -eq ''Queued'') { ' +
    '[Console]::Error.WriteLine(''Monitor task is still active; uninstall was not allowed to continue.''); exit 3 }; ' +
    'if ($task.State -ne ''Ready'' -and $task.State -ne ''Disabled'') { ' +
    '[Console]::Error.WriteLine(''Monitor task state is indeterminate: '' + $task.State.ToString()); exit 3 }; ' +
    'Unregister-ScheduledTask -TaskName $taskName -TaskPath ([string][char]92) -Confirm:$false -ErrorAction Stop | Out-Null; ' +
    '[Console]::Out.Write(''Removed'') } catch { ' +
    'if ($_.FullyQualifiedErrorId -like ''NoMatchingTasksFound*'') { [Console]::Out.Write(''Missing''); exit 0 }; ' +
    '[Console]::Error.WriteLine($_.Exception.Message); exit 2 }';

  Result := RunMonitorPowerShell(Script, OutputText, ErrorText);
  if Result then begin
    OutputText := Trim(OutputText);
    Result :=
      (CompareText(OutputText, 'Removed') = 0) or
      (CompareText(OutputText, 'Missing') = 0);
    if not Result then
      ErrorText := 'Task Scheduler returned an unexpected uninstall result: ' + OutputText;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  State: String;
  Outcome: String;
  ErrorText: String;
  RestoreError: String;
begin
  Result := '';
  MonitorHelperPath := ExpandConstant('{tmp}\scafa-updater.exe');
  try
    if not FileExists(MonitorHelperPath) then
      ExtractTemporaryFile('scafa-updater.exe');
  except
    ErrorText := GetExceptionMessage;
    Result := 'SCAFA Workforce could not prepare its bounded background-monitor command helper.' +
      #13#10 + ErrorText;
    Exit;
  end;
  if not FileExists(MonitorHelperPath) then begin
    Result := 'SCAFA Workforce could not extract its bounded background-monitor command helper.';
    Exit;
  end;

  if not ReadMonitorTaskState(State, ErrorText) then begin
    Result := 'SCAFA Workforce cannot safely inspect its background monitor task. ' +
      'Installation was stopped before replacing files.' + #13#10 + ErrorText;
    Exit;
  end;

  if CompareText(State, 'Running') = 0 then begin
    MonitorWasRunning := True;
    if not StopMonitorTask(Outcome, ErrorText) then begin
      if RestoreMonitorTask(RestoreError) then
        MonitorWasRunning := False;
      Result := 'SCAFA Workforce could not confirm that its background monitor stopped. ' +
        'Installation was stopped before replacing files.' + #13#10 + ErrorText;
      if RestoreError <> '' then
        Result := Result + #13#10 + 'Monitor recovery: ' + RestoreError;
      Exit;
    end;

    if (CompareText(Outcome, 'Stopped:Ready') <> 0) then
      MonitorWasRunning := False;
  end else if
    (CompareText(State, 'Ready') <> 0) and
    (CompareText(State, 'Disabled') <> 0) and
    (CompareText(State, 'Missing') <> 0) then begin
    Result := 'SCAFA Workforce found an unexpected background monitor state: ' + State +
      '. Installation was stopped to avoid replacing files while task state is uncertain.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    SetupSucceeded := True;
end;

procedure DeinitializeSetup;
var
  ErrorText: String;
  MessageText: String;
begin
  if MonitorWasRunning and not MonitorRestored then begin
    if not RestoreMonitorTask(ErrorText) then begin
      if SetupSucceeded then
        MessageText := 'SCAFA Workforce was installed, but its previously running attendance monitor could not be restarted.'
      else
        MessageText := 'Setup ended before completion, and the previously running attendance monitor could not be restored.';
      MsgBox(MessageText + #13#10#13#10 + ErrorText, mbError, MB_OK);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ErrorText: String;
begin
  if CurUninstallStep = usUninstall then begin
    MonitorHelperPath := ExpandConstant('{app}\scafa-updater.exe');
    if not FileExists(MonitorHelperPath) then begin
      MsgBox(
        'SCAFA Workforce could not locate its bounded Task Scheduler command helper. ' +
        'Uninstallation has been cancelled so the background task is not left pointing to a removed executable.',
        mbError, MB_OK);
      Abort;
    end;
    if not RemoveMonitorTask(ErrorText) then begin
      MsgBox(
        'SCAFA Workforce could not safely stop and remove its background attendance task. ' +
        'Uninstallation has been cancelled so the task is not left pointing to a removed executable.' + #13#10#13#10 + ErrorText,
        mbError, MB_OK);
      Abort;
    end;
  end;
end;
