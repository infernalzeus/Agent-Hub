<#
    Checks an Agent Hub install from outside the app, and writes a report.

    Why this exists: an installer test is mostly not a visual question. Where the
    files landed, what the registry says, where the shortcuts point and whether
    the right things were left alone are all text, and text can be asserted,
    re-run and diffed. Driving a wizard with screenshots proves far less and
    costs far more, so the only thing left for a human (or a vision pass) is
    "does the wizard render correctly", once.

    Run it three times: before installing, after installing, and after a folder
    move. Each run appends to the same JSON file, so the three can be compared.

        pwsh -File verify_install.ps1 -Phase before
        pwsh -File verify_install.ps1 -Phase after  -AppDir "C:\Users\me\AppData\Local\Agent Hub"
        pwsh -File verify_install.ps1 -Phase moved  -AppDir "D:\Hub" -OldAppDir "C:\Users\me\AppData\Local\Agent Hub"

    Every check prints PASS / FAIL / SKIP with the value it actually saw, so a
    failure says what is wrong rather than only that something is.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('before', 'after', 'moved')][string]$Phase,
    [string]$AppDir = "",
    [string]$OldAppDir = "",
    [string]$Report = "$env:USERPROFILE\agent-hub-verify.json"
)

$ErrorActionPreference = 'Continue'
$results = @()

function Check {
    param([string]$Id, [string]$What, [scriptblock]$Test)
    $value = $null; $ok = $false; $err = $null
    try { $r = & $Test; $ok = [bool]$r.ok; $value = $r.value }
    catch { $err = $_.Exception.Message }
    $state = if ($err) { 'ERROR' } elseif ($ok) { 'PASS' } else { 'FAIL' }
    $colour = @{ PASS = 'Green'; FAIL = 'Red'; ERROR = 'Yellow'; SKIP = 'DarkGray' }[$state]
    Write-Host ("{0,-6} {1,-34} {2}" -f $state, $Id, $value) -ForegroundColor $colour
    $script:results += [pscustomobject]@{ id = $Id; what = $What; state = $state; value = "$value"; error = $err }
}

function Skip { param([string]$Id, [string]$Why)
    Write-Host ("{0,-6} {1,-34} {2}" -f 'SKIP', $Id, $Why) -ForegroundColor DarkGray
    $script:results += [pscustomobject]@{ id = $Id; what = $Why; state = 'SKIP'; value = $Why; error = $null }
}

Write-Host "`n=== Agent Hub install check - phase: $Phase ===" -ForegroundColor Cyan

# -- the program itself --------------------------------------------------------
if ($Phase -eq 'before') {
    Check 'app.absent' 'the install folder does not exist yet' {
        $p = if ($AppDir) { $AppDir } else { "$env:LOCALAPPDATA\Agent Hub" }
        @{ ok = -not (Test-Path $p); value = $p }
    }
} else {
    Check 'app.exists' 'the install folder exists' { @{ ok = (Test-Path $AppDir); value = $AppDir } }
    Check 'app.exe' 'AgentHub.exe is present' {
        $f = Join-Path $AppDir 'AgentHub.exe'; @{ ok = (Test-Path $f); value = $f }
    }
    Check 'app.size' 'the install is a plausible size (>40 MB)' {
        $mb = [math]::Round(((Get-ChildItem $AppDir -Recurse -File -ErrorAction SilentlyContinue |
               Measure-Object Length -Sum).Sum / 1MB), 1)
        @{ ok = ($mb -gt 40); value = "$mb MB" }
    }
}

# -- registry: per-user only, and both values present --------------------------
Check 'reg.workroot' 'AGENTHUB_WORK_ROOT is set for this user' {
    $v = (Get-ItemProperty 'HKCU:\Environment' -Name AGENTHUB_WORK_ROOT -ErrorAction SilentlyContinue).AGENTHUB_WORK_ROOT
    @{ ok = ($Phase -eq 'before') -or [bool]$v; value = $v }
}
Check 'reg.protocol' 'agenthub:// is registered for this user' {
    $v = (Get-ItemProperty 'HKCU:\Software\Classes\agenthub\shell\open\command' -Name '(default)' -ErrorAction SilentlyContinue).'(default)'
    @{ ok = ($Phase -eq 'before') -or [bool]$v; value = $v }
}
Check 'reg.no-machine-wide' 'nothing was written under HKLM' {
    $v = Test-Path 'HKLM:\Software\Classes\agenthub'
    @{ ok = (-not $v); value = if ($v) { 'FOUND under HKLM - should be per-user' } else { 'none' } }
}

# -- shortcuts -----------------------------------------------------------------
$shell = New-Object -ComObject WScript.Shell
$links = @{
    'link.startmenu' = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Agent Hub.lnk"
    'link.desktop'   = "$env:USERPROFILE\Desktop\Agent Hub.lnk"
    'link.startup'   = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Agent Hub.lnk"
}
foreach ($k in $links.Keys) {
    $path = $links[$k]
    if ($Phase -eq 'before') { Skip $k 'not installed yet'; continue }
    Check $k "the shortcut points into the install folder" {
        if (-not (Test-Path $path)) { return @{ ok = $false; value = 'missing (may not have been chosen at install)' } }
        $target = $shell.CreateShortcut($path).TargetPath
        @{ ok = ($target -like "$AppDir*"); value = $target }
    }
}

# -- the move ------------------------------------------------------------------
if ($Phase -eq 'moved') {
    Check 'move.old-gone' 'the old folder was removed' {
        @{ ok = (-not (Test-Path $OldAppDir)); value = $OldAppDir }
    }
    Check 'move.state-kept' 'settings did not move and are still there' {
        $s = "$env:LOCALAPPDATA\AgentHub\state"
        @{ ok = (Test-Path $s); value = $s }
    }
    Check 'move.no-pending' 'the queued move was cleared' {
        $f = "$env:LOCALAPPDATA\AgentHub\state\pending_move.json"
        if (-not (Test-Path $f)) { return @{ ok = $true; value = 'no pending record' } }
        $j = Get-Content $f -Raw | ConvertFrom-Json
        @{ ok = ($j.state -ne 'queued'); value = $j.state }
    }
    Check 'move.protocol-healed' 'agenthub:// now points at the new folder' {
        $v = (Get-ItemProperty 'HKCU:\Software\Classes\agenthub\shell\open\command' -Name '(default)' -ErrorAction SilentlyContinue).'(default)'
        @{ ok = ($v -like "*$AppDir*"); value = $v }
    }
}

# -- is it actually running ----------------------------------------------------
if ($Phase -ne 'before') {
    Check 'run.listening' 'something answers on 8081' {
        $c = Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue
        @{ ok = [bool]$c; value = if ($c) { "pid $($c.OwningProcess -join ',')" } else { 'nothing listening' } }
    }
    Check 'run.http' 'the hub serves its own page' {
        try { $r = Invoke-WebRequest 'http://127.0.0.1:8081/' -UseBasicParsing -TimeoutSec 8
              @{ ok = ($r.StatusCode -eq 200); value = "HTTP $($r.StatusCode)" } }
        catch { @{ ok = $false; value = $_.Exception.Message } }
    }
    Check 'run.version' 'the version it reports' {
        try { $j = Invoke-RestMethod 'http://127.0.0.1:8081/api/update' -TimeoutSec 8
              @{ ok = [bool]$j.current; value = $j.current } }
        catch { @{ ok = $false; value = $_.Exception.Message } }
    }
}

# -- report --------------------------------------------------------------------
$pass = ($results | Where-Object state -eq 'PASS').Count
$fail = ($results | Where-Object { $_.state -in 'FAIL', 'ERROR' }).Count
Write-Host "`n$pass passed, $fail failed" -ForegroundColor $(if ($fail) { 'Red' } else { 'Green' })

$all = @()
if (Test-Path $Report) { $all = @(Get-Content $Report -Raw | ConvertFrom-Json) }
$all += [pscustomobject]@{
    phase = $Phase; at = (Get-Date).ToString('s'); appDir = $AppDir; oldAppDir = $OldAppDir
    os = (Get-CimInstance Win32_OperatingSystem).Caption
    passed = $pass; failed = $fail; checks = $results
}
$all | ConvertTo-Json -Depth 6 | Set-Content $Report -Encoding utf8
Write-Host "report -> $Report`n" -ForegroundColor Cyan
if ($fail) { exit 1 } else { exit 0 }
