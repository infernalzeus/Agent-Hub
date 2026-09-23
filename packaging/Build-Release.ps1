# The work behind Build-Release.cmd. Run that rather than this.
#
# Takes the Hub exactly as it is on disk and produces installers. Nothing here
# knows anything about the Hub's internals: staging is a plain allowlisted copy
# and the Hub decides its own packaged behaviour at runtime (hub/runtime.py), so
# adding a feature or a skill needs no change to any of this.
[CmdletBinding()]
param(
  [switch]$All,            # also tag + push so CI builds macOS and Linux
  [switch]$TestOnly,       # throwaway build installed as a separate "Agent Hub Test"
  [string]$ReleaseEvidence # required only to PUBLISH; not to build
)
# Default is a release candidate: the real installer, for installing and testing.
# Publishing still needs evidence, so an unvalidated build cannot become a release.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path -Parent $here

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`n$text" -ForegroundColor Red; exit 1 }

$version = (Get-Content -LiteralPath (Join-Path $here 'release-manifest.json') -Raw | ConvertFrom-Json).version
Step "Agent Hub $version"

# ── 1. Freeze ────────────────────────────────────────────────────────────────
# build-core.ps1 fetches payloads, stages, runs the behaviour tests and freezes.
Step 'Building the Windows package'
# Hashtable, not an array: splatting an array passes elements POSITIONALLY, so a
# switch like -Candidate would silently bind to the first positional parameter.
$buildArgs = @{}
if ($ReleaseEvidence)  { $buildArgs['ReleaseEvidence'] = $ReleaseEvidence }
elseif ($TestOnly)     { $buildArgs['TestOnly'] = $true }
else                   { $buildArgs['Candidate'] = $true }
& (Join-Path $here 'build-core.ps1') @buildArgs
if ($LASTEXITCODE -ne 0) { Fail 'Build failed. Nothing was published.' }

$package = Get-ChildItem (Join-Path $root 'release') -Directory |
           Sort-Object LastWriteTime | Select-Object -Last 1
$package = Join-Path $package.FullName 'AgentHub'
if (-not (Test-Path (Join-Path $package 'AgentHub.exe'))) { Fail "No executable in $package." }

# ── 2. Installer ─────────────────────────────────────────────────────────────
Step 'Compiling the installer'
$iscc = Get-ChildItem "$env:LOCALAPPDATA\Programs", "${env:ProgramFiles(x86)}", "$env:ProgramFiles" `
          -Filter ISCC.exe -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
if (-not $iscc) { Fail 'Inno Setup is not installed. Get it from https://jrsoftware.org/isdl.php' }

$isccArgs = @("/DSourceDir=$package", (Join-Path $here 'AgentHub.iss'))
if ($ReleaseEvidence)  { $isccArgs = @("/DReleaseEvidence=$ReleaseEvidence") + $isccArgs }
elseif ($TestOnly)     { $isccArgs = @('/DTestOnly') + $isccArgs }
else                   { $isccArgs = @('/DCandidate') + $isccArgs }
& $iscc @isccArgs | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { Fail 'Installer compilation failed.' }

$installer = Get-ChildItem (Split-Path -Parent $package) -Filter '*Setup.exe' |
             Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "`nInstaller: $($installer.FullName)" -ForegroundColor Green
Write-Host ("Size: {0:N0} MB" -f ($installer.Length / 1MB))

# ── 3. macOS + Linux, on their own machines ──────────────────────────────────
if (-not $All) {
  Write-Host "`nWindows only. Re-run with /all to build macOS and Linux too." -ForegroundColor Yellow
  exit 0
}

if (-not $ReleaseEvidence) {
  Fail ('Publishing needs a completed clean-machine release-evidence file. ' +
        'Install and test the candidate first, then re-run with -ReleaseEvidence.')
}
Step 'Requesting the macOS and Linux builds'
if ((git -C $root status --porcelain) -ne $null) {
  Fail 'Commit your changes first — CI builds from what is pushed, not from this folder.'
}
$tag = "v$version"
if ((git -C $root tag --list $tag)) { Fail "Tag $tag already exists. Bump the version in packaging/release-manifest.json." }
git -C $root tag $tag
git -C $root push origin $tag
if ($LASTEXITCODE -ne 0) { Fail 'Could not push the tag; CI was not started.' }

Write-Host "`nPushed $tag. GitHub Actions is building macOS and Linux now:" -ForegroundColor Green
Write-Host '  https://github.com/infernalzeus/Agent-Hub/actions'
Write-Host 'It attaches all three installers to a DRAFT release. Review it, then publish.'
