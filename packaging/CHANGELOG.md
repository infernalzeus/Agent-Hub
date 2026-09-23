# Changelog

Written by `Build-Release.cmd`. The newest entry at the top is what the next GitHub
Release uses as its description, so what you type at build time is what people read on the
release page.

The installer filename never changes â€” it is always `Agent-Hub-Setup.exe`, because the
portfolio links to `releases/latest/download/Agent-Hub-Setup.exe` and that resolves by
name. The version lives here, in `release-manifest.json`, and in the build folder name.

<!-- BUILD-RELEASE:INSERT-BELOW -->

## 0.1.4

_23 September 2026_

- Portfolio page reworked: Configuration section, architecture diagram, keyword cards.
- Card reveal rebuilt on grid rows, so the text can never be clipped.
- Build now records patch notes and bumps the patch version automatically.
- Release-candidate mode: build the real installer for testing without faking release evidence.

## 0.1.3

- First packaged build: bundled payloads, offline setup for media and file tools.
- Loopback binding by default; Tailscale Serve provides remote access.
- Missions, PC control, media and the project graph all reachable from one address.

