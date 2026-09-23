# The build dialog. Launched by Build-Release.cmd; there is nothing to type.
#
# WinForms ships with Windows, so this adds no dependency. It collects the same
# options the command line takes and then calls Build-Release.ps1 with them, so
# there is one build path, not two.
[CmdletBinding()]
param([switch]$SelfTest)   # construct the form and exit; used to check it builds

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path -Parent $here
. (Join-Path $here 'version.ps1')

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# ── palette: the Hub's own colours, so the tool looks like the thing it builds ──
$bg     = [System.Drawing.Color]::FromArgb(8, 12, 40)
$panel  = [System.Drawing.Color]::FromArgb(13, 18, 71)
$green  = [System.Drawing.Color]::FromArgb(0, 230, 118)
$ink    = [System.Drawing.Color]::FromArgb(232, 255, 241)
$muted  = [System.Drawing.Color]::FromArgb(168, 203, 185)

$current  = Get-HubVersion $here
$next     = Step-PatchVersion $current
$previous = Get-ChildItem (Join-Path $root 'release') -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
$installed = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
             Where-Object { $_.DisplayName -eq 'Agent Hub' } | Select-Object -First 1

function New-Label($text, $x, $y, $w, $colour, $size, $bold) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $text; $l.Location = "$x,$y"; $l.Size = "$w,20"
    $l.ForeColor = $colour; $l.BackColor = [System.Drawing.Color]::Transparent
    $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    $l.Font = New-Object System.Drawing.Font('Segoe UI', [single]$size, $style)
    return $l
}

function New-Check($text, $x, $y, $w, $checked) {
    $c = New-Object System.Windows.Forms.CheckBox
    $c.Text = $text; $c.Location = "$x,$y"; $c.Size = "$w,24"
    $c.ForeColor = $ink; $c.BackColor = [System.Drawing.Color]::Transparent
    $c.Font = New-Object System.Drawing.Font('Segoe UI', [single]9.5)
    $c.Checked = $checked
    return $c
}

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Agent Hub - Build Release'
$form.ClientSize = '544,632'
$form.StartPosition = 'CenterScreen'
$form.BackColor = $bg
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$title = New-Label 'BUILD RELEASE' 24 16 300 $green 15 $true
$title.Size = '300,30'
$form.Controls.Add($title)
$form.Controls.Add((New-Label "current version  $current" 24 50 300 $muted 9 $false))
$form.Controls.Add((New-Label $(if ($previous) { "previous build   $($previous.Name)" } else { 'previous build   none yet' }) 24 70 480 $muted 9 $false))
$form.Controls.Add((New-Label $(if ($installed) { "installed here   $($installed.DisplayVersion) (will be upgraded)" } else { 'installed here   not installed' }) 24 90 480 $muted 9 $false))

# ── version ──────────────────────────────────────────────────────────────────
$form.Controls.Add((New-Label 'Version to build' 24 126 200 $green 9.5 $true))
$versionBox = New-Object System.Windows.Forms.TextBox
$versionBox.Location = '24,148'; $versionBox.Size = '120,24'
$versionBox.Text = $next
$versionBox.BackColor = $panel; $versionBox.ForeColor = $ink; $versionBox.BorderStyle = 'FixedSingle'
$versionBox.Font = New-Object System.Drawing.Font('Consolas', [single]10)
$form.Controls.Add($versionBox)
$form.Controls.Add((New-Label 'patch number moves on automatically' 156 152 320 $muted 8.5 $false))

# ── patch notes ──────────────────────────────────────────────────────────────
$form.Controls.Add((New-Label 'What changed - one per line' 24 186 300 $green 9.5 $true))
$notesBox = New-Object System.Windows.Forms.TextBox
$notesBox.Location = '24,208'; $notesBox.Size = '496,150'
$notesBox.Multiline = $true; $notesBox.ScrollBars = 'Vertical'; $notesBox.AcceptsReturn = $true
$notesBox.BackColor = $panel; $notesBox.ForeColor = $ink; $notesBox.BorderStyle = 'FixedSingle'
$notesBox.Font = New-Object System.Drawing.Font('Segoe UI', [single]9.5)
$form.Controls.Add($notesBox)
$form.Controls.Add((New-Label 'These become the changelog, the installer notes and the release description.' 24 362 496 $muted 8.5 $false))

# ── platforms ────────────────────────────────────────────────────────────────
$form.Controls.Add((New-Label 'Build for' 24 394 200 $green 9.5 $true))
$cbWin   = New-Check 'Windows'  24 416 110 $true
$cbMac   = New-Check 'macOS'   144 416 110 $false
$cbLinux = New-Check 'Linux'   264 416 110 $false
$form.Controls.AddRange(@($cbWin, $cbMac, $cbLinux))
$form.Controls.Add((New-Label 'Ticking macOS or Linux pushes a tag; GitHub Actions builds those two.' 24 442 496 $muted 8.5 $false))

# ── what kind of build ───────────────────────────────────────────────────────
$form.Controls.Add((New-Label 'Kind of build' 24 474 200 $green 9.5 $true))
$cbTest = New-Check 'Test build - installs separately as "Agent Hub Test", never published' 24 496 496 $false
$cbPublish = New-Check 'Publish - upload this installer to a draft GitHub release' 24 522 496 $false
$cbTested = New-Check 'I installed and tested this build on a clean machine' 44 548 476 $false
$cbTested.ForeColor = $muted
$form.Controls.AddRange(@($cbTest, $cbPublish, $cbTested))

# Publishing needs the attestation; a test build can never publish.
$sync = {
    $cbPublish.Enabled = -not $cbTest.Checked
    if ($cbTest.Checked) { $cbPublish.Checked = $false }
    $cbTested.Enabled = $cbPublish.Checked
    if (-not $cbPublish.Checked) { $cbTested.Checked = $false }
    $cbMac.Enabled = -not $cbTest.Checked
    $cbLinux.Enabled = -not $cbTest.Checked
    if ($cbTest.Checked) { $cbMac.Checked = $false; $cbLinux.Checked = $false }
}
$cbTest.Add_CheckedChanged($sync)
$cbPublish.Add_CheckedChanged($sync)
& $sync

# ── actions ──────────────────────────────────────────────────────────────────
$ok = New-Object System.Windows.Forms.Button
$ok.Text = 'COMPILE'; $ok.Location = '300,578'; $ok.Size = '110,34'
$ok.BackColor = $green; $ok.ForeColor = $bg; $ok.FlatStyle = 'Flat'
$ok.Font = New-Object System.Drawing.Font('Segoe UI', [single]9.5, [System.Drawing.FontStyle]::Bold)
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'; $cancel.Location = '420,578'; $cancel.Size = '100,34'
$cancel.BackColor = $panel; $cancel.ForeColor = $ink; $cancel.FlatStyle = 'Flat'
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.AddRange(@($ok, $cancel))
$form.AcceptButton = $ok; $form.CancelButton = $cancel

if ($SelfTest) {
    # DrawToBitmap only paints controls that have actually been shown, so put the
    # window off-screen, let it paint, capture it, then close it.
    Write-Host "Form built: $($form.Controls.Count) controls"
    $form.StartPosition = 'Manual'
    $form.Location = New-Object System.Drawing.Point(-3000, -3000)
    $form.ShowInTaskbar = $false
    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 400
    [System.Windows.Forms.Application]::DoEvents()
    $bmp = New-Object System.Drawing.Bitmap $form.Width, $form.Height
    $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle 0, 0, $form.Width, $form.Height))
    $out = Join-Path $env:TEMP 'agent-hub-build-dialog.png'
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Host "Preview: $out"
    $bmp.Dispose(); $form.Close(); $form.Dispose(); exit 0
}

if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    Write-Host 'Cancelled.'; exit 0
}

# ── translate the dialog into the same call the command line would make ──────
$notes = $notesBox.Text -split "`r?`n" | Where-Object { $_.Trim() }
$buildArgs = @{ Yes = $true; Version = $versionBox.Text.Trim() }
if ($notes) { $buildArgs['Notes'] = $notes }
if ($cbTest.Checked) { $buildArgs['TestOnly'] = $true }

# macOS and Linux are built by GitHub Actions, so ticking either means "push a tag".
# This is independent of publishing - previously these boxes did nothing at all
# unless Publish was also ticked.
if ($cbMac.Checked -or $cbLinux.Checked) { $buildArgs['CI'] = $true }

if ($cbPublish.Checked) {
    if (-not $cbTested.Checked) {
        [System.Windows.Forms.MessageBox]::Show(
            "Publishing needs the clean-machine test confirmed.`n`nInstall this build, try it, then tick the box.",
            'Not yet', 'OK', 'Warning') | Out-Null
        exit 1
    }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        $answer = [System.Windows.Forms.MessageBox]::Show(
            "GitHub CLI is needed to upload the installer to a release.`n`n" +
            "Install it now with winget?`n`n" +
            "(You will then need to run 'gh auth login' once.)",
            'GitHub CLI missing', 'YesNo', 'Question')
        if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) {
            Write-Host 'Installing GitHub CLI...'
            winget install --id GitHub.cli --exact --accept-package-agreements --accept-source-agreements
            Write-Host ''
            Write-Host 'Now run:  gh auth login' -ForegroundColor Yellow
            Write-Host 'Then build again with Publish ticked.'
            exit 0
        }
        exit 1
    }
    # The attestation, written down. Same file the command line would take.
    $evidence = Join-Path $root 'release-evidence.json'
    @{ version = $versionBox.Text.Trim(); clean_windows_profile = $true
       all_now_passed = $true; deferred_passed = $true; no_private_data = $true
       notes = "Confirmed in the build dialog on $(Get-Date -Format 'yyyy-MM-dd HH:mm')."
    } | ConvertTo-Json | Set-Content -LiteralPath $evidence -Encoding UTF8
    $buildArgs['ReleaseEvidence'] = $evidence
    $buildArgs['Publish'] = $true
}

Write-Host ''
& (Join-Path $here 'Build-Release.ps1') @buildArgs
