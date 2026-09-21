<#
  Takes test scaffolding out of the /graph node list WITHOUT deleting anything.
  Graph nodes = project folders under git repositories\_unsorted projects (etc.) + every folder in opencode\worktrees.
  This moves the old test ones to N:\Code\_test-archive-<date>\ (same drive = instant rename, fully reversible).
    default        : dry run, prints what it would move
    -Apply         : does the move, then `git worktree prune` in the kept projects
  Kept: the latest test set (basic-*) and any mission working copy that still has a record in worktrees\_missions.
#>
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyy-MM-dd'
$archive = "N:\Code\_test-archive-$stamp"
$unsorted = 'N:\Code\git repositories\_unsorted projects'
$wtRoot = 'N:\Code\opencode\worktrees'

$projects = Get-ChildItem $unsorted -Directory | Where-Object { $_.Name -match '^(demo-|bakeoff-|calc-test-)' -or $_.Name -eq 'test cal' }
$records = @(Get-ChildItem (Join-Path $wtRoot '_missions') -Filter *.json | ForEach-Object { $_.BaseName })
$copies = Get-ChildItem $wtRoot -Directory | Where-Object { $_.Name -notin '_missions', '_scratch' -and (($_.Name -split '--')[-1]) -notin $records }

"projects to archive : $($projects.Count)"; $projects | ForEach-Object { "   $($_.Name)" }
"working copies      : $($copies.Count)  (kept: $($records.Count) with a mission record)"; $copies | ForEach-Object { "   $($_.Name)" }
if (-not $Apply) { "`nDry run only. Re-run with -Apply to move them to $archive"; return }

New-Item -ItemType Directory -Force (Join-Path $archive 'projects'), (Join-Path $archive 'worktrees') | Out-Null
foreach ($d in $projects) { Move-Item -LiteralPath $d.FullName -Destination (Join-Path $archive 'projects') }
foreach ($d in $copies)   { Move-Item -LiteralPath $d.FullName -Destination (Join-Path $archive 'worktrees') }
Get-ChildItem $unsorted -Directory -Filter 'basic-*' | ForEach-Object { git -C $_.FullName worktree prune }
"`nmoved $($projects.Count + $copies.Count) folders to $archive. Restart the hub (or refresh /graph) to see the smaller graph."
