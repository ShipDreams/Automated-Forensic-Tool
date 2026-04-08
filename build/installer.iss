; Inno Setup Script for Android Automated Forensic Tool
; Compile with: iscc build/installer.iss

#define MyAppName "Android Automated Forensic Tool"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Forensic Team"
#define MyAppExeName "ForensicTool.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=ForensicTool_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=resources\app.ico
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main application files (PyInstaller output)
Source: "..\dist\ForensicTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; WebView2 Bootstrapper
Source: "resources\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

; Database config example
Source: "..\config\database.json.example"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Install WebView2 Runtime if needed (before launching app)
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; \
  Parameters: "/silent /install"; \
  StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; \
  Flags: waituntilterminated; \
  Check: NeedsWebView2

; Launch app after install
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(#MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[Code]
function NeedsWebView2(): Boolean;
var
  RegKey: String;
  Value: String;
begin
  // Check if WebView2 Runtime is installed
  // Registry key for WebView2 Evergreen Runtime
  RegKey := 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6A2E75E11}';
  Result := True;  // Default: needs installation

  if RegQueryStringValue(HKLM, RegKey, 'pv', Value) then
  begin
    // If registry key exists and has a version, WebView2 is installed
    if Length(Value) > 0 then
    begin
      Log('WebView2 Runtime found: version ' + Value);
      Result := False;  // Already installed
    end;
  end;

  // Also check 64-bit registry on 64-bit systems
  if Result then
  begin
    RegKey := 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6A2E75E11}';
    if RegQueryStringValue(HKLM, RegKey, 'pv', Value) then
    begin
      if Length(Value) > 0 then
      begin
        Log('WebView2 Runtime found (64-bit): version ' + Value);
        Result := False;
      end;
    end;
  end;

  if Result then
    Log('WebView2 Runtime not found, will install');
end;

// Create default database.json from example if it doesn't exist
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir: String;
  DbConfig: String;
  DbExample: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigDir := ExpandConstant('{app}\config');
    DbConfig := ConfigDir + '\database.json';
    DbExample := ConfigDir + '\database.json.example';

    if not FileExists(DbConfig) then
    begin
      if FileExists(DbExample) then
      begin
        FileCopy(DbExample, DbConfig, False);
        Log('Created database.json from example');
      end;
    end;
  end;
end;
