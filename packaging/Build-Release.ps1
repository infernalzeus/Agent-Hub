# The work behind Build-Release.cmd. Run that rather than this.
#
# Takes the Hub exactly as it is on disk and produces installers. Nothing here
# knows anything about the Hub's internals: staging is a plain allowlisted copy
# and the Hub decides its own packaged behaviour at runtime (hub/runtime.py), so
# adding a feature or a skill needs no change to any of this.
[CmdletBinding()]
param(
  [switch]$Publish,         # create the GitHub release and upload this installer
  [switch]$CI,              # push a tag so GitHub Actions builds macOS and Linux
  [switch]$TestOnly,        # throwaway build installed as a separate "Agent Hub Test"
  [string[]]$Notes,         # patch notes; prompted for when omitted and running interactively
  [switch]$NoBump,          # rebuild the current version instead of moving the patch number on
  [switch]$Yes,             # skip the confirm prompt (scripted runs)
  [string]$Version,         # force a version (a minor/major bump is always deliberate)
  [string]$ReleaseEvidence  # required only to PUBLISH; not to build
)
# Default is a release candidate: the real installer, for installing and testing.
# Publishing still needs evidence, so an unvalidated build cannot become a release.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path -Parent $here

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "`n$text" -ForegroundColor Red; exit 1 }

. (Join-Path $here 'version.ps1')

# ── Version + patch notes ────────────────────────────────────────────────────
$current = Get-HubVersion $here
if ($Version) {
  $version = $Version
} elseif ($NoBump -or $TestOnly) {
  $version = $current            # a throwaway build should not consume a version number
} else {
  $version = Step-PatchVersion $current
}

if (-not $Notes -and -not $TestOnly) {
  # Interactive only: CI and scripted builds pass -Notes (or nothing) and carry on.
  if (-not $env:CI) {
    try {
      Write-Host "`nWhat changed in ${version}? One line each, blank line to finish." -ForegroundColor Cyan
      Write-Host "(press Enter straight away to skip)" -ForegroundColor DarkGray
      $collected = @()
      while ($true) {
        $line = Read-Host '  -'
        if (-not $line.Trim()) { break }
        $collected += $line
      }
      $Notes = $collected
    } catch {
      # No console to prompt on (CI, a scripted run, a redirected host). Build without notes.
      Write-Host '  (no console to prompt on - building without notes)' -ForegroundColor DarkGray
    }
  }
}

Step "Agent Hub $version"
if ($version -ne $current) { Write-Host "  version $current -> $version" }
if ($Notes) {
  Write-Host '  patch notes:'
  $Notes | ForEach-Object { Write-Host "    - $_" }
} elseif (-not $TestOnly) {
  Write-Host '  no patch notes recorded for this build' -ForegroundColor DarkGray
}

# ──── What exists already ────
$previous = Get-ChildItem (Join-Path $root 'release') -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
if ($previous) { Write-Host "  previous build: $($previous.Name)" }
else { Write-Host '  previous build: none - this is the first' }
$installed = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
             Where-Object { $_.DisplayName -eq 'Agent Hub' } | Select-Object -First 1
if ($installed) {
  Write-Host "  installed on this PC: $($installed.DisplayVersion) - the new installer upgrades it in place"
}

if (-not $Yes) {
  try {
    $go = Read-Host "`nCompile $version? [Y/n]"
    if ($go -and $go.Trim().ToLower().StartsWith('n')) { Write-Host 'Cancelled.'; exit 0 }
  } catch { }   # no console to confirm on; carry on
}

# Record BEFORE building, so the package is stamped with the version it ships as.
if (-not $TestOnly) {
  if ($version -ne $current) { Set-HubVersion $here $version }
  if ($Notes) { Add-ChangelogEntry $here $version $Notes }
}

# ── 1. Freeze ────────────────────────────────────────────────────────────────
# build-core.ps1 fetches payloads, stages, runs the behaviour tests and freezes.
Step 'Building the Windows package'
# Hashtable, not an array: splatting an array passes elements POSITIONALLY, so a
# switch like -Candidate would silently bind to the first positional parameter.
$buildArgs = @{ Version = $version }
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

$isccArgs = @("/DSourceDir=$package", "/DAppVersion=$version", (Join-Path $here 'AgentHub.iss'))
if ($ReleaseEvidence)  { $isccArgs = @("/DReleaseEvidence=$ReleaseEvidence") + $isccArgs }
elseif ($TestOnly)     { $isccArgs = @('/DTestOnly') + $isccArgs }
else                   { $isccArgs = @('/DCandidate') + $isccArgs }
& $iscc @isccArgs | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) { Fail 'Installer compilation failed.' }

$installer = Get-ChildItem (Split-Path -Parent $package) -Filter '*Setup.exe' |
             Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "`nInstaller: $($installer.FullName)" -ForegroundColor Green
Write-Host ("Size: {0:N0} MB" -f ($installer.Length / 1MB))

# ── 3. Publish ───────────────────────────────────────────────────────────────
if (-not $Publish -and -not $CI) {
  Write-Host "`nBuilt, not published. Tick Publish in the dialog when you have tested it." -ForegroundColor Yellow
  exit 0
}

if ($TestOnly) { Fail 'A test build is never published.' }

$repo = 'infernalzeus/Agent-Hub'
$tag  = "v$version"

# The build writes the version bump and the changelog, so the tree is ALWAYS dirty
# at this point. Commit exactly those two files - nothing else - so the tag points
# at the version it claims to be.
$versionFiles = @('packaging/CHANGELOG.md', 'packaging/release-manifest.json')
$dirty = git -C $root status --porcelain
$staged = @()
foreach ($f in $versionFiles) {
  if ($dirty -match [regex]::Escape($f)) { git -C $root add -- $f; $staged += $f }
}
if ($staged) {
  git -C $root commit -q -m "Agent Hub $version" -m "Version bump and changelog for $tag."
  Write-Host "  committed: $($staged -join ', ')"
}
$others = (git -C $root status --porcelain) -split "`n" | Where-Object { $_.Trim() }
if ($others) {
  Write-Host "  note: $($others.Count) other file(s) left uncommitted - commit them yourself if they belong in this release" -ForegroundColor DarkGray
}

if (git -C $root tag --list $tag) {
  Fail "Tag $tag already exists. Build a new version, or delete the tag first."
}
$entry = Get-ChangelogEntry $here $version
if ($entry) { git -C $root tag -a $tag -m "Agent Hub $version" -m $entry } else { git -C $root tag -a $tag -m "Agent Hub $version" }

Step 'Pushing to GitHub'
git -C $root push origin HEAD
if ($LASTEXITCODE -ne 0) { Fail 'Push failed. Nothing was released; the tag is still local.' }
git -C $root push origin $tag
if ($LASTEXITCODE -ne 0) { Fail 'Tag push failed. Nothing was released.' }
Write-Host "  pushed $tag"

# ── the release itself ───────────────────────────────────────────────────────
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
  Write-Host ''
  Write-Host 'GitHub CLI is not installed, so the installer cannot be uploaded automatically.' -ForegroundColor Yellow
  Write-Host '  Install it once:  winget install GitHub.cli'
  Write-Host '  Then sign in:     gh auth login'
  Write-Host ''
  Write-Host "The tag is pushed, so you can also do it by hand:"
  Write-Host "  https://github.com/$repo/releases/new?tag=$tag"
  Write-Host "  Attach: $($installer.FullName)"
  exit 1
}

Step 'Creating the release'
$notesFile = Join-Path $env:TEMP "agent-hub-$tag-notes.md"
if ($entry) { $entry | Set-Content -LiteralPath $notesFile -Encoding UTF8 }
else { "Agent Hub $version" | Set-Content -LiteralPath $notesFile -Encoding UTF8 }

# Draft, so nothing goes public until you have looked at it.
& $gh release create $tag $installer.FullName --repo $repo --title "Agent Hub $version" --notes-file $notesFile --draft
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Could not create the release. If it already exists, upload to it with:' -ForegroundColor Yellow
  Write-Host "  gh release upload $tag `"$($installer.FullName)`" --repo $repo --clobber"
  Fail 'Release creation failed.'
}

$url = & $gh release view $tag --repo $repo --json url --jq .url 2>$null
Write-Host ''
Write-Host "Draft release created with Agent-Hub-Setup.exe attached." -ForegroundColor Green
if ($url) { Write-Host "  $url" }
Write-Host '  It is a DRAFT - open it and press Publish release to make the download live.'

if ($CI) {
  Write-Host ''
  Write-Host "GitHub Actions is building macOS and Linux for $tag and will attach them to the same release:"
  Write-Host "  https://github.com/$repo/actions"
  Write-Host '  That workflow has never run before, so watch the first one.' -ForegroundColor DarkGray
}
