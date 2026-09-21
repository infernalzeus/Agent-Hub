param(
  [switch]$KeepBuild,
  [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".release-venv"
$out = Join-Path $root "release"
$work = Join-Path $root ".release-work"
$python = "Z:\Programs\Anaconda\python.exe"

# A venv starts empty: Anaconda's notebooks, ML stacks and GUI libraries cannot
# leak into this release. Core requirements are deliberately separate from tools.
if (-not (Test-Path "$venv\Scripts\python.exe")) { & $python -m venv $venv }
$corePython = "$venv\Scripts\python.exe"
& $corePython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $corePython -m pip install -r (Join-Path $PSScriptRoot "requirements-core.txt") pyinstaller
if ($LASTEXITCODE -ne 0) { throw "core dependency install failed" }

# Verify the core starts with its declared dependencies only.
Push-Location $root
try { & $corePython -c "import app; app.create_app(); print('Agent Hub core import: OK')"; if ($LASTEXITCODE -ne 0) { throw "core smoke test failed" } } finally { Pop-Location }

Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$work\hub" | Out-Null
Copy-Item "$root\favicon.png","$root\favicon-64.png","$root\favicon-256.png" $work
Copy-Item "$root\hub\agent_knowledge" "$work\hub\agent_knowledge" -Recurse
# The portable core begins without machine-specific fronted applications.
'[]' | Set-Content "$work\hub\apps.default.json" -Encoding utf8

Remove-Item -LiteralPath $out -Recurse -Force -ErrorAction SilentlyContinue
Push-Location $root
try {
  & $corePython -m PyInstaller --noconfirm --clean --onedir --noconsole --name AgentHub --icon "$root\favicon.ico" `
    --exclude-module hub.local_settings --exclude-module PyQt5 --exclude-module PySide6 --exclude-module tkinter `
    --add-data "$work\favicon.png;." --add-data "$work\favicon-64.png;." --add-data "$work\favicon-256.png;." `
    --add-data "$work\hub\apps.default.json;hub" --add-data "$work\hub\agent_knowledge;hub\agent_knowledge" `
    --distpath $out --workpath "$work\build" --specpath $work "$PSScriptRoot\agenthub_launcher.py"
} finally { Pop-Location }

$package = Join-Path $out "AgentHub"
Copy-Item "$PSScriptRoot\release-manifest.json" $package
$zip = Join-Path $out "AgentHub-Windows-$Version.zip"
Compress-Archive -LiteralPath $package -DestinationPath $zip -Force
$size = (Get-ChildItem $package -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Core package: $([math]::Round($size / 1MB, 1)) MB"
Write-Host "ZIP: $zip"
if (-not $KeepBuild) { Remove-Item -LiteralPath $work -Recurse -Force }


