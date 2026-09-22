#ifndef SourceDir
  #error Supply /DSourceDir with the freshly verified package directory.
#endif
#ifndef AppVersion
  #define AppVersion "0.1.3"
#endif
#ifdef TestOnly
  #define AppName "Agent Hub Test"
  #define InstallDir "Agent Hub Test"
  #define InstallerName "Agent-Hub-TEST-ONLY-Setup"
  #define InstanceId "A7AA71A8-39CE-4D86-8A62-3D38CB7A1238"
  #if !FileExists(SourceDir + "\TEST-ONLY.txt")
    #error Test package must contain TEST-ONLY.txt.
  #endif
#else
  #ifndef ReleaseEvidence
    #error Public installer requires completed clean-Windows ReleaseEvidence.
  #endif
  #if !FileExists(ReleaseEvidence)
    #error Release evidence file not found.
  #endif
  #if FileExists(SourceDir + "\TEST-ONLY.txt")
    #error A test package cannot become a public installer.
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
