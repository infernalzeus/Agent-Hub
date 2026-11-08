# Changelog

Written by `Build-Release.cmd`. The newest entry at the top is what the next GitHub
Release uses as its description, so what you type at build time is what people read on the
release page.

The installer filename never changes ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â it is always `Agent-Hub-Setup.exe`, because the
portfolio links to `releases/latest/download/Agent-Hub-Setup.exe` and that resolves by
name. The version lives here, in `release-manifest.json`, and in the build folder name.

<!-- BUILD-RELEASE:INSERT-BELOW -->

## 0.2.0

_8 November 2026_

- Experimental learning layer (off by default, switch on in Settings): the yard drawn as a reinforcement-learning system, arrows that explain themselves, WHY views of what the learner would press and which weights a step would move
- Landing page: Smith's icon is the wake button and pops up when you say Smith; the page goes quiet as you enter the dashboard
- Voice: "open the dashboard" and similar phrases enter the main screen
- Saved play routines are found again whatever the wording of the request
- Installer: every data file the Hub reads (voice commands, media sources) is now bundled automatically, and the build stops if anything would be silently left out; anything the repository ignores (personal layout and settings) is never packaged

## 0.1.14

_2 October 2026_

- Automation within LLM Arch(missions), Theme and Menu UI changes. General Bug fixes

## 0.1.13

_27 September 2026_

- Location Panel updated for LLM support
- General app improvements

## 0.1.11

_26 September 2026_

- updater for patch notes added
- agentic pipeline improvement, skill editing

## 0.1.5

_23 September 2026_

- Architecture section retitled; card titles green; .claude untracked.
- Installer now shows the patch notes before installing.

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

