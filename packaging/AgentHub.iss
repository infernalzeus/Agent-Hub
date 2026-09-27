#ifndef SourceDir
  #error Supply /DSourceDir with the freshly verified package directory.
#endif
#ifndef AppVersion
  ; Always supplied by Build-Release.ps1 (/DAppVersion). Erroring here rather
  ; than defaulting means the installer can never claim a stale version.
  #error Supply /DAppVersion with the version being built.
#endif
; Three modes:
;   TestOnly   - separate app, obviously not the real thing
;   Candidate  - the real installer, for installing and testing. NOT publishable.
;   (neither)  - public release; requires completed clean-machine evidence.
;
; Candidate exists because the evidence file asserts that clean-machine testing has
; already passed, which is the testing you do BY installing. Gating the build on it
; made the real installer impossible to produce for the purpose of validating it.
; The gate belongs on publishing, and that is where it stays.
#ifdef TestOnly
  #define AppName "Agent Hub Test"
  #define InstallDir "Agent Hub Test"
  #define InstallerName "Agent-Hub-TEST-ONLY-Setup"
  #define InstanceId "A7AA71A8-39CE-4D86-8A62-3D38CB7A1238"
  #if !FileExists(SourceDir + "\TEST-ONLY.txt")
    #error Test package must contain TEST-ONLY.txt.
  #endif
#else
  ; A test package can never become a real installer, in either remaining mode.
  #if FileExists(SourceDir + "\TEST-ONLY.txt")
    #error A test package cannot become a real installer.
  #endif
  #ifndef Candidate
    #ifndef ReleaseEvidence
      #error Public installer requires completed clean-machine ReleaseEvidence, or /DCandidate to build one for testing.
    #endif
    #if !FileExists(ReleaseEvidence)
      #error Release evidence file not found.
    #endif
  #endif
  #define AppName "Agent Hub"
  #define InstallDir "Agent Hub"
  #define InstallerName "Agent-Hub-Setup"
  #define InstanceId "A7AA71A8-39CE-4D86-8A62-3D38CB7A1237"
#endif

[Setup]
AppId={{{#InstanceId}}
AppName={#AppName}
AppVersion={#AppVersion}
; The asset filename has to stay fixed — releases/latest/download resolves by
; exact name, so versioning it would break every download link on the site. Put
; the version in the FILE instead: right-click the installer, Properties,
; Details. Add/Remove Programs reads these too.
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany=InfernalZeus
VersionInfoDescription={#AppName} {#AppVersion} installer
AppPublisher=InfernalZeus
DefaultDirName={localappdata}\{#InstallDir}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#SourceDir}\..
OutputBaseFilename={#InstallerName}
SetupIconFile=..\favicon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AgentHub.exe
CloseApplications=yes
RestartApplications=no
; Whoever runs the installer sees what changed, from the same notes that
; become the GitHub Release description.
#if FileExists(SourceDir + "\RELEASE-NOTES.md")
  InfoBeforeFile={#SourceDir}\RELEASE-NOTES.md
#endif

[Registry]
; Where the hub keeps worktrees, mission records and downloads. locations.py
; reads this and derives every folder default from it. Removed on uninstall, so
; an uninstall leaves no setting behind - the data itself is never touched.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "AGENTHUB_WORK_ROOT"; \
  ValueData: "{code:GetDataDir}"; Flags: uninsdeletevalue

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\AgentHub.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AgentHub.exe"; Tasks: desktopicon
; Starting with Windows is the point of an always-on hub: your phone can only
; reach it while it is running, so a hub you have to remember to launch is a hub
; that is down whenever you need it. Offered, never forced.
Name: "{userstartup}\{#AppName}"; Filename: "{app}\AgentHub.exe"; Tasks: startupicon

[Tasks]
; Ticked by default. This is a program you open daily from several devices, not
; a tool you run once, so hiding it in the Start menu is the wrong default.
Name: "desktopicon"; Description: "Create a &desktop shortcut"
Name: "startupicon"; Description: "Start Agent Hub when I sign in (so your other devices can always reach it)"

[Run]
Filename: "{app}\AgentHub.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
var DataDirPage: TInputDirWizardPage;

procedure InitializeWizard;
var Default: String;
begin
  { The program is small and belongs on the system drive; the data grows without
    limit, so it is offered separately rather than assumed to live beside it. }
  Default := ExpandConstant('{sd}\AgentHub');
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Where should Agent Hub keep your data?',
    'Working copies of your projects, mission records and downloads.',
    'This is separate from the program itself, because it grows: every mission an agent runs' + #13#10 +
    'makes a private copy of the repository it is working on. Pick a drive with room.' + #13#10#13#10 +
    'You can change this later in Agent Hub under LOCATIONS.',
    False, '');
  DataDirPage.Add('');
  DataDirPage.Values[0] := Default;
end;

function GetDataDir(Param: String): String;
begin
  Result := DataDirPage.Values[0];
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DataDirPage.ID then
  begin
    if Trim(DataDirPage.Values[0]) = '' then
    begin
      MsgBox('Choose a folder for Agent Hub''s data.', mbError, MB_OK);
      Result := False;
    end
    else if not ForceDirectories(DataDirPage.Values[0]) then
    begin
      MsgBox('That folder could not be created. Pick another one.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
