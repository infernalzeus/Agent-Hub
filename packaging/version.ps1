# Version and changelog handling for Build-Release.
#
# The installer filename is fixed (Agent-Hub-Setup.exe) because the portfolio links to
# releases/latest/download/Agent-Hub-Setup.exe, which resolves by name. So the version
# lives in three places instead, all written from here:
#   packaging/release-manifest.json   what the build stamps into the package
#   packaging/CHANGELOG.md            what the GitHub Release shows as its notes
#   release/<mode>-<version>-<stamp>/ the folder the build lands in

function Write-Utf8NoBom {
    <#  Windows PowerShell 5.1's "-Encoding UTF8" writes a BYTE ORDER MARK, and
        Python's json.load rejects a leading BOM outright. That is what broke the
        macOS and Linux CI builds: they read release-manifest.json and got
        "Unexpected UTF-8 BOM". Always write these files without one.  #>
    param([string]$Path, [string]$Text)
    # .NET resolves relative paths against the PROCESS working directory, which is
    # not PowerShell's location. Resolve first so a relative path cannot land
    # somewhere unexpected.
    $full = if ([System.IO.Path]::IsPathRooted($Path)) { $Path }
            else { Join-Path (Get-Location).ProviderPath $Path }
    [System.IO.File]::WriteAllText($full, $Text, (New-Object System.Text.UTF8Encoding $false))
}

function Get-HubVersion {
    param([string]$PackagingDir)
    (Get-Content -LiteralPath (Join-Path $PackagingDir 'release-manifest.json') -Raw |
        ConvertFrom-Json).version
}

function Step-PatchVersion {
    <#  0.1.3 -> 0.1.4. Only the patch part moves automatically; a minor or major
        bump is a deliberate decision, made with -Version.  #>
    param([string]$Version)
    $parts = $Version.Split('.')
    if ($parts.Count -lt 3) { throw "Version '$Version' is not major.minor.patch." }
    $parts[-1] = [int]$parts[-1] + 1
    return ($parts -join '.')
}

function Set-HubVersion {
    param([string]$PackagingDir, [string]$Version)
    $path = Join-Path $PackagingDir 'release-manifest.json'
    $manifest = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $manifest.version = $Version
    # 10 levels so nested objects in the manifest survive the round trip.
    Write-Utf8NoBom $path (($manifest | ConvertTo-Json -Depth 10) + "`n")
}

function Add-ChangelogEntry {
    <#  Writes a new version section directly under the marker, so the newest entry is
        always first and the file stays readable by hand.  #>
    param([string]$PackagingDir, [string]$Version, [string[]]$Notes)
    $path = Join-Path $PackagingDir 'CHANGELOG.md'
    $marker = '<!-- BUILD-RELEASE:INSERT-BELOW -->'
    $body = ($Notes | Where-Object { $_.Trim() } | ForEach-Object { "- $($_.Trim())" }) -join "`n"
    if (-not $body) { $body = '- No notes recorded for this build.' }
    $entry = "$marker`n`n## $Version`n`n_$(Get-Date -Format 'd MMMM yyyy')_`n`n$body"
    $text = Get-Content -LiteralPath $path -Raw
    if ($text -notmatch [regex]::Escape($marker)) { throw "CHANGELOG.md is missing its insert marker." }
    Write-Utf8NoBom $path ($text -replace [regex]::Escape($marker), $entry)
}

function Get-ChangelogEntry {
    <#  The newest section, used as the GitHub Release description.  #>
    param([string]$PackagingDir, [string]$Version)
    $text = Get-Content -LiteralPath (Join-Path $PackagingDir 'CHANGELOG.md') -Raw
    $escaped = [regex]::Escape($Version)
    $pattern = '(?ms)^## ' + $escaped + '\s*$(.*?)(?=^## |\z)'
    $found = [regex]::Match($text, $pattern)
    if ($found.Success) { return $found.Groups[1].Value.Trim() }
    return ''
}
