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
