; Inno Setup 6 script - Daily Money Transfer Manager 2026
; Build:  ISCC.exe /DMyAppVersion=1.0.0 installer.iss
; Input:  dist\DailyMoneyTransferManager\   (PyInstaller one-folder output)
; Output: dist\installer\DailyMoneyTransferManager-Setup.exe
;
; Per-user installation (no administrator rights). User data lives in
; %LOCALAPPDATA%\DailyMoneyTransferManager and is NEVER touched by the
; installer or the uninstaller.

#define MyAppName "Daily Money Transfer Manager 2026"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "Daily Money Transfer Manager"
#define MyAppExeName "DailyMoneyTransferManager.exe"
#define MyAppFolder "DailyMoneyTransferManager"
#define MyAppMutex "Local\DailyMoneyTransferManager2026.SingleInstance"

[Setup]
AppId={{A3C8D1F2-6B4E-4F7A-9D2C-1E5B7F9A0C34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} Setup
DefaultDirName={localappdata}\Programs\{#MyAppFolder}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=dist\installer
OutputBaseFilename=DailyMoneyTransferManager-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex={#MyAppMutex}
; keep installer size reasonable; the payload is ~300 MB uncompressed
LZMAUseSeparateProcess=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Manage daily money transfers"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only files the installer created. The data folder
; (%LOCALAPPDATA%\DailyMoneyTransferManager) is deliberately left in place.
Type: filesandordirs; Name: "{app}\_internal"

[Code]
const
  WebView2Key = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Key64 = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, WebView2Key64, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := True
  else if RegQueryStringValue(HKLM, WebView2Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := True
  else if RegQueryStringValue(HKCU, WebView2Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0') then
    Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WebView2Installed() then
  begin
    MsgBox('The Microsoft Edge WebView2 Runtime was not found on this computer.' + #13#10 + #13#10 +
           'It is part of Windows 11 and of Windows 10 with Microsoft Edge installed. ' +
           'The application window needs it. You can continue the installation now and install ' +
           'the runtime afterwards from:' + #13#10 +
           'https://developer.microsoft.com/microsoft-edge/webview2/', mbInformation, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#MyAppFolder}');
    if DirExists(DataDir) then
      MsgBox('Your transaction database and backups were kept in:' + #13#10 + DataDir + #13#10 + #13#10 +
             'Delete that folder yourself if you no longer need the data.', mbInformation, MB_OK);
  end;
end;
