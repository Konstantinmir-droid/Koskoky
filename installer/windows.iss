#define AppName "LocalDocRenamer"
#define AppVersion "0.1.0"
#if !FileExists("..\dist\LocalDocRenamer\LocalDocRenamer.exe")
#error Build the complete Windows distribution first.
#endif
[Setup]
AppId={{540F15AA-576D-47B3-887C-D13BB1BCB8F4}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=LocalDocRenamer-Setup-Windows-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\LocalDocRenamer.exe
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: unchecked
[Files]
Source: "..\dist\LocalDocRenamer\*"; DestDir: "{app}"; Excludes: "portable.flag,state\*"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\LocalDocRenamer.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\LocalDocRenamer.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\LocalDocRenamer.exe"; Description: "Запустить программу"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\_internal\unblock-network.ps1"" -Directory ""{app}"""; Flags: runhidden waituntilterminated

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\_internal\block-network.ps1') + '" -Directory "' + ExpandConstant('{app}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      RaiseException('Не удалось включить запрет исходящих соединений. Приложение не сможет обрабатывать документы.');
  end;
end;
