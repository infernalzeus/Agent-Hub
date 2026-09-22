param(
  [switch]$TestOnly,
  [string]$Version = '0.1.3',
  [string]$Python = 'python',
  [string]$ReleaseEvidence
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $TestOnly) {
  if (-not $ReleaseEvidence) { throw 'Public release is gated. Use -TestOnly for a local test build, or supply completed clean-Windows ReleaseEvidence.' }
  $evidence = Get-Content -LiteralPath $ReleaseEvidence -Raw | ConvertFrom-Json
  if ($evidence.version -ne $Version -or -not $evidence.clean_windows_profile -or -not $evidence.all_now_passed -or -not $evidence.deferred_passed -or -not $evidence.no_private_data -or -not $evidence.notes) {
    throw 'Release evidence must identify this version and record clean-Windows, all-now, deferred, privacy checks and test notes.'
  }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$work = Join-Path $root ".release-work\$stamp"
$stage = Join-Path $work 'source'
$venv = Join-Path $root '.release-venv'
$out = Join-Path $root "release\$(if ($TestOnly) {'test'} else {'candidate'})-$Version-$stamp"
New-Item -ItemType Directory -Force $work | Out-Null
if (-not (Test-Path -LiteralPath "$venv\Scripts\python.exe")) {
  & $Python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw 'Build environment creation failed.' }
}
$corePython = Join-Path $venv 'Scripts\python.exe'
& $corePython -m pip install -r (Join-Path $PSScriptRoot 'requirements-core.txt') 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
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
  & $corePython -c 'import app; app.create_app(); app._selfcheck(); print("Core import and optional-app startup: OK")'
  if ($LASTEXITCODE -ne 0) { throw 'Core startup smoke check failed.' }
  & $corePython (Join-Path $PSScriptRoot 'test_release.py') --source $stage
  if ($LASTEXITCODE -ne 0) { throw 'Installer behavior tests failed.' }
  # A venv based on Conda still needs these three CPython native runtime DLLs.
  # Include only these files, never the parent environment's packages.
  $baseLibrary = & $corePython -c 'import sys; from pathlib import Path; print(Path(sys.base_prefix) / "Library" / "bin")'
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
    --add-data "$stage\requirements-youtube.txt;." "$stage\packaging\agenthub_launcher.py"
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
if ($TestOnly) {
  'LOCAL TEST BUILD ONLY. Not clean-Windows verified. Not for publication.' | Set-Content (Join-Path $package 'TEST-ONLY.txt')
} else {
  Copy-Item -LiteralPath $ReleaseEvidence -Destination (Join-Path $out 'release-evidence.json')
}
$label = if ($TestOnly) {'TEST-ONLY'} else {$Version}
Compress-Archive -LiteralPath $package -DestinationPath (Join-Path $out "AgentHub-Windows-$label.zip")
Write-Host "Package: $package"
Write-Host 'No upload, publication, commit, or changes to the working Hub were performed.'
