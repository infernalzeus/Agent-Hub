# Installer-only continuation — 2026-09-22

The working Hub is unchanged. `stage_release.py` copies an allowlisted source tree and applies `release-changes.json` plus `overlay/` only to the build staging directory. Each patched source has a SHA-256 precondition: later Hub edits stop the build rather than silently overwriting or ignoring them. No git operations are performed.

## Build a local test package

Run `packaging/build-core.ps1 -TestOnly`. The script creates a separate clean environment, stages the installer variant, runs the 17 behavior tests, and freezes it. It never deletes existing release folders. Conda-based Python builds explicitly include only the required ffi, SQLite and decimal runtime DLLs.

Compile the installer with Inno Setup 6:

```powershell
ISCC.exe /DTestOnly "/DSourceDir=<fresh test package directory>" packaging/AgentHub.iss
```

Test installs use a different application ID, `Agent Hub Test` installation folder, ports 18081/18092, and `%LOCALAPPDATA%\AgentHub-Test` state/working folders. They do not upgrade the existing Hub. Public builds use port 8081 with loopback binding; Tailscale Serve is an explicit onboarding action.

The old root `AgentHub.spec` is not the supported release entry point. Use the staged build above. Do not upload a test installer.

## Included behavior

- First launch offers all-now or deferred setup; optional installs run serially with visible failures and retry.
- Speech and media run in separate managed Python 3.13 environments. Speech models download only after an explicit selection.
- Windows MCP installs an actual provider, verifies its tool list and starts disabled. The excluded tool list is retained.
- File Browser runs as a fixed mode of the packaged executable. Movie Clipper is absent from the default registry and remains an optional ingested repository.
- Media creates configurable folders and installs yt-dlp, ffmpeg and Node.js. No cookies or OAuth accounts are inherited.
- SMB credentials stay in Windows; Hub saves only the tested share reference.
- Project discovery scans a chosen root; selected repositories are added only after review.
- Deferred tool requests point to the corresponding setup action.

## Verified and remaining gate

Verified: 17 isolated behavior tests; browser first-run/deferred/File Browser flow; frozen executable with a fresh application profile and Python removed from PATH; packaged File Browser child launch; no optional installation during deferred setup; clean staging privacy audit.

This is **not a clean Windows machine test**. Before public release, install on a fresh Windows profile/VM and verify all-now and every deferred action, external installer failures/retries, Tailscale sign-in/HTTPS, real microphone transcription, MCP probing/control, media download, SMB connection, ingestion/removal, upgrade and uninstall. Account sign-in and network share credentials require the owner. Upload/account connection is not preconfigured.

Public builds require a release-evidence JSON file with this version, `clean_windows_profile`, `all_now_passed`, `deferred_passed`, `no_private_data` set true, and meaningful `notes`. This is an operator checklist, not proof supplied automatically by the script. Inno also requires the evidence file and refuses a TEST-ONLY package for public output.

Dependencies are installed from official package managers at setup time; exact optional package versions still need pinning after clean-machine validation. The installed core remains dependent on the Hub's existing trust model; see the separate security findings. No Hub-wide security hardening or portfolio work was applied.
