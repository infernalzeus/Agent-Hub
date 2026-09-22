# Building Agent Hub

**Double-click `Build-Release.cmd`.** That is the whole answer for a Windows
installer. Everything below is what it does and how to change it.

---

## The short version

| I want to | Do this |
|---|---|
| A Windows installer from my current code | Double-click `Build-Release.cmd` |
| ... plus macOS and Linux | `Build-Release.cmd /all` (commits must be pushed) |
| A public release | `Build-Release.cmd -ReleaseEvidence evidence.json` |
| Just check the payloads | `python packaging\fetch_payloads.py --check` |

You need [Inno Setup](https://jrsoftware.org/isdl.php) (6 or 7) and Python 3.13.
Everything else the build fetches itself.

---

## What happens

**1. Payloads** — `fetch_payloads.py` fills `packaging/payloads/` with the
Python 3.13 installer and a shared wheelhouse, ~70 MB. Skipped when already
present, so only the first build pays for it. Sizes and SHA-256s are written
back into `payloads.json`, so the manifest records what was actually
downloaded rather than what someone assumed.

**2. Staging** — `stage_release.py` copies an *allowlisted* tree into a scratch
folder. It never touches your working Hub. Then it audits what it copied and
refuses to continue if it finds a `.sqlite`, a log, `locations.json`,
`apps.json`, an absolute path to somebody's drive, or anything in
`release-deny.local.txt`.

**3. Freeze and compile** — a clean venv, the behaviour tests against the staged
tree under a throwaway profile, then PyInstaller, then Inno Setup.

Nothing patches your source. The Hub decides how to behave when installed by
reading `hub/runtime.py` (`PACKAGED`, `STATE`, `python_for`), which is why you
can add a feature, a route or a skill and rebuild with no manifest to update.

> This replaced an earlier design where the build applied 69 line-range edits to
> 19 source files, each pinned to a hash. Editing any of them failed the build
> with *"Release overlay is stale"*. If you ever see that message, you are on an
> old checkout.

---

## What the installer carries

Bundled, so these set up with **no network at all**:

- Python 3.13 installer (27.5 MB) — used only when the machine has none, and
  installed per-user
- yt-dlp, mutagen, imageio-ffmpeg (33 MB — `imageio-ffmpeg` *is* the ffmpeg
  binary), aiohttp, pytest, pillow

Fetched from PyPI or the vendor **when the user asks for that capability**:

| | Roughly | Why not bundled |
|---|---|---|
| Windows MCP (PC control) | 26 MB | numpy + pillow + pywin32, for one optional feature |
| YouTube upload | 15 MB | Google API client; most installs never upload |
| TALK speech | 80 MB+ | ctranslate2, av, onnxruntime |
| Whisper models | 75–480 MB | User picks one, or none |
| Tailscale, Node.js, Git | varies | Better taken fresh from the vendor |

To change the split, move a package between `bundled.wheels` and `on_request` in
`packaging/payloads.json`, delete `packaging/payloads/wheels/`, and rebuild.
`runtime.wheelhouse()` reads that manifest, so nothing else needs touching.

---

## macOS and Linux

PyInstaller cannot cross-compile, so those build on their own OS via
`.github/workflows/release.yml` (`packaging/build-core.sh` does the work).
`Build-Release.cmd /all` tags and pushes to start it; the three artifacts land on
one **draft** release for you to review.

Both ship the Hub core, File Browser, Missions, Media and the project graph.
Neither ships the power menu or PC control — `hub/platforms.py` declares what
each OS supports and the UI hides the rest. macOS builds are **unsigned**
(notarization needs a paid Apple Developer account), so first launch there is
right-click → Open.

---

## The release gate

A public build refuses to run without a `-ReleaseEvidence` JSON file:

```json
{
  "version": "0.1.3",
  "clean_windows_profile": true,
  "all_now_passed": true,
  "deferred_passed": true,
  "no_private_data": true,
  "notes": "Installed on a fresh Windows 11 VM; every capability set up and used."
}
```

Both `build-core.ps1` and `AgentHub.iss` check it, and Inno additionally refuses
to turn a package containing `TEST-ONLY.txt` into a public installer. This is an
operator checklist, not something the script can verify — it exists so an
unvalidated build cannot end up published under the real name. That nearly
happened once: a `release/Agent-Hub-Setup.exe` built before this gate existed
carried the public installer name despite never being installed anywhere.

---

## Gotchas

- **Never use `python -c "..."` in the build scripts.** Windows PowerShell strips
  the double quotes before the executable sees them, which silently broke both
  the startup smoke check and the DLL lookup. Use a script file —
  `smoke_check.py` and `base_library_dir.py` exist for exactly this reason.
- **Do not redirect a native command's stderr** (`2>&1`) in PowerShell 5.1. The
  Hub logs to stderr, and PS wraps each line as an error, failing the step.
- A venv built on a Conda base needs three native DLLs (ffi, sqlite3, libmpdec)
  from the base `Library/bin`. `build-core.ps1` copies only those.
- Test installs use their own AppId, `Agent Hub Test`, and ports 18081/18092, so
  they never collide with or upgrade a real install.
- `release/`, `packaging/payloads/` and `.release-work/` are gitignored. Release
  binaries belong on GitHub Releases, never in the repo.
