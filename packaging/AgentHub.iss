#ifndef SourceDir
  #error Supply /DSourceDir with the freshly verified package directory.
#endif
#ifndef AppVersion
  #define AppVersion "0.1.3"
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

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\AgentHub.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\AgentHub.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\AgentHub.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
