param(
  [switch]$TestOnly,     # separate app, clearly not the real thing
  [switch]$Candidate,    # the real installer, for installing and testing; not publishable
  [string]$Version = '',
  [string]$Python = 'python',
  [string]$ReleaseEvidence
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Version) {
  # One source of truth for the version: packaging/release-manifest.json.
  # Resolved before the evidence check below, which compares against it.
  $Version = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'release-manifest.json') -Raw | ConvertFrom-Json).version
}
if ($TestOnly -and $Candidate) { throw 'Pick one: -TestOnly or -Candidate.' }
if (-not $TestOnly -and -not $Candidate) {
  if (-not $ReleaseEvidence) { throw 'Publishing is gated. Use -Candidate to build the real installer for testing, -TestOnly for a throwaway, or supply completed clean-machine ReleaseEvidence.' }
  $evidence = Get-Content -LiteralPath $ReleaseEvidence -Raw | ConvertFrom-Json
  if ($evidence.version -ne $Version -or -not $evidence.clean_windows_profile -or -not $evidence.all_now_passed -or -not $evidence.deferred_passed -or -not $evidence.no_private_data -or -not $evidence.notes) {
    throw 'Release evidence must identify this version and record clean-Windows, all-now, deferred, privacy checks and test notes.'
  }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$work = Join-Path $root ".release-work\$stamp"
$stage = Join-Path $work 'source'
$venv = Join-Path $root '.release-venv'
$out = Join-Path $root "release\$(if ($TestOnly) {'test'} elseif ($Candidate) {'candidate'} else {'release'})-$Version-$stamp"
New-Item -ItemType Directory -Force $work | Out-Null
if (-not (Test-Path -LiteralPath "$venv\Scripts\python.exe")) {
  & $Python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw 'Build environment creation failed.' }
}
$corePython = Join-Path $venv 'Scripts\python.exe'
& $corePython -m pip install -r (Join-Path $PSScriptRoot 'requirements-core.txt') 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
# Bundled payloads must be present before freezing, or the installed Hub would
# have to reach the network to set its optional tools up.
& $corePython (Join-Path $PSScriptRoot 'fetch_payloads.py')
if ($LASTEXITCODE -ne 0) { throw 'Bundled payloads are incomplete.' }
& $corePython (Join-Path $PSScriptRoot 'stage_release.py') --root $root --destination $stage
if ($LASTEXITCODE -ne 0) { throw 'Clean staging or privacy audit failed.' }

# All verification uses a disposable profile, never the developer's live locations.
$previousState = $env:AGENTHUB_STATE_DIR
$previousRoot = $env:AGENTHUB_WORK_ROOT
$previousProfile = $env:USERPROFILE
$previousPath = $env:PYTHONPATH
$previousBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
  $env:AGENTHUB_STATE_DIR = Join-Path $work 'smoke\state'
  $env:AGENTHUB_WORK_ROOT = Join-Path $work 'smoke\data'
  $env:USERPROFILE = Join-Path $work 'smoke'
  $env:PYTHONPATH = $stage
  $env:PYTHONDONTWRITEBYTECODE = "1"
  & $corePython (Join-Path $PSScriptRoot 'smoke_check.py')
  if ($LASTEXITCODE -ne 0) { throw 'Core startup smoke check failed.' }
  & $corePython (Join-Path $PSScriptRoot 'test_release.py') --source $stage
  if ($LASTEXITCODE -ne 0) { throw 'Installer behavior tests failed.' }
  # A venv based on Conda still needs these three CPython native runtime DLLs.
  # Include only these files, never the parent environment's packages.
  $baseLibrary = & $corePython (Join-Path $PSScriptRoot 'base_library_dir.py')
  $nativeBinaries = @()
  foreach ($dll in @('ffi.dll', 'sqlite3.dll', 'libmpdec-4.dll')) {
    $dllPath = Join-Path $baseLibrary $dll
    if (Test-Path -LiteralPath $dllPath) { $nativeBinaries += @('--add-binary', "$dllPath;.") }
  }
  & $corePython -m PyInstaller @nativeBinaries --noconfirm --clean --onedir --noconsole --name AgentHub --optimize 2 `
    --paths $stage --icon "$stage\favicon.ico" --distpath $out --workpath "$work\build" --specpath $work `
    --exclude-module hub.local_settings --exclude-module PyQt5 --exclude-module PySide6 --exclude-module tkinter `
    --add-data "$stage\favicon.png;." --add-data "$stage\favicon-64.png;." --add-data "$stage\favicon-256.png;." `
    --add-data "$stage\hub\apps.default.json;hub" --add-data "$stage\hub\static;hub\static" `
    --add-data "$stage\hub\agent_knowledge;hub\agent_knowledge" --add-data "$stage\file-browser;file-browser" `
    --add-data "$stage\youtube;youtube" --add-data "$stage\packaging\speech_worker.py;packaging" `
    --add-data "$stage\requirements-youtube.txt;." `
    --add-data "$stage\payloads;payloads" "$stage\packaging\agenthub_launcher.py"
  if ($LASTEXITCODE -ne 0) { throw 'Freezing failed; no installer will be produced.' }
} finally {
  $env:AGENTHUB_STATE_DIR = $previousState
  $env:AGENTHUB_WORK_ROOT = $previousRoot
  $env:USERPROFILE = $previousProfile
  $env:PYTHONPATH = $previousPath
  $env:PYTHONDONTWRITEBYTECODE = $previousBytecode
}
$package = Join-Path $out 'AgentHub'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'release-manifest.json') -Destination $package
# Ship the notes with the build, so a folder on disk says what it is.
. (Join-Path $PSScriptRoot 'version.ps1')
$notes = Get-ChangelogEntry $PSScriptRoot $Version
if ($notes) {
  "# Agent Hub $Version`n`n$notes" | Set-Content (Join-Path $package 'RELEASE-NOTES.md') -Encoding UTF8
  Write-Host "`nPatch notes for ${Version}:"
  $notes -split "`n" | ForEach-Object { Write-Host "  $_" }
}
if ($TestOnly) {
  'LOCAL TEST BUILD ONLY. Not clean-machine verified. Not for publication.' | Set-Content (Join-Path $package 'TEST-ONLY.txt')
} elseif ($Candidate) {
  # Deliberately NOT named TEST-ONLY.txt: this IS the real installer. The marker
  # records that clean-machine validation has not happened yet, which is what the
  # release-evidence file will assert once it has.
  "RELEASE CANDIDATE $Version. Real installer, built for testing. Clean-machine validation not yet recorded, so this must not be published." |
    Set-Content (Join-Path $package 'RELEASE-CANDIDATE.txt')
} else {
  Copy-Item -LiteralPath $ReleaseEvidence -Destination (Join-Path $out 'release-evidence.json')
}
$label = if ($TestOnly) {'TEST-ONLY'} elseif ($Candidate) {"$Version-rc"} else {$Version}
Compress-Archive -LiteralPath $package -DestinationPath (Join-Path $out "AgentHub-Windows-$label.zip")
Write-Host "Package: $package"
Write-Host 'No upload, publication, commit, or changes to the working Hub were performed.'
