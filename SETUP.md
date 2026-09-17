# Agent Hub — first-run setup

A numbered checklist. Most of this is detect-only — the Hub just shows a
banner for what's missing. Two exceptions: the **OpenCode** and **YouTube
dependencies** rows below each show an **INSTALL** button right on the
banner, since those are safely local, reversible installs (a project-local
`npm install`, a `pip install` into an interpreter already on this machine —
see `hub/features/setup_actions.py`). Everything system-level (Node.js,
Tailscale) only ever offers a copyable command — the Hub never runs those
itself. Anything personal (YouTube OAuth creds, Tailscale sign-in, the power
PIN) is never automated either way.

`✅` = needed for the Hub to run at all. Everything else is opt-in — skip what
you won't use.

---

## 1. ✅ Python + dependencies

```bash
python -m pip install -r requirements.txt
```

Python 3.10+. This is all the File Browser and the power menu need.

## 2. ✅ Local secrets & paths — `hub/local_settings.py`

```bash
cp hub/local_settings.example.py hub/local_settings.py
```

`hub/local_settings.py` is **gitignored**. Set at minimum:

- **`HUB_POWER_PIN`** — a real PIN. **An empty PIN leaves the PC power menu
  (shutdown / restart / sleep / lock) open to anyone who can reach the Hub.**
  Set this before exposing the Hub beyond `localhost`.
- `YT_DL_PYTHON` — only if you use the YouTube download card (absolute path to
  the interpreter that has `yt-dlp`).
- `SHORTCUTS` — optional header links (e.g. an `smb://` link to your NAS).

Anything you leave out falls back to the safe defaults in `hub/config.py`.

## 3. ✅ Machine paths — `hub/config.py`

Edit `APPS` (the apps you want fronted), `YT_DL_*` / `MC_OUTPUT_DIR`, and
`OPENCODE_ROOT` in `hub/features/opencode.py` to point at where those live on
**your** machine. These are directories, not secrets — just change them, or
delete the `APPS` entries you don't want.

## 4. Tailscale — makes it a *remote* control

The Hub also just binds `0.0.0.0` and works on a plain LAN address, so this is
technically optional — but reaching it from your phone anywhere is the point.

1. Install Tailscale and **sign in** (`tailscale up`).
2. Expose the Hub over HTTPS on your tailnet:
   ```bash
   tailscale serve --bg 8081
   ```
   This gives you `https://<your-device>.<your-tailnet>.ts.net` — a **secure
   context**, which you need for step 6 (install-as-app) and for your phone and
   PC to share one origin.
3. Every device that will use the Hub must load that URL once while the Hub is
   up, so its service worker caches the offline/dormant page.

> Only the Hub should face your tailnet. Every app it fronts binds `127.0.0.1`
> and is reached only through the Hub's proxy.

## 5. OpenCode (AI coding sessions) — optional

If Node.js/npm is already on PATH, the setup banner's **Install OpenCode now**
button does this step for you (a local `npm install opencode-ai` under
`OPENCODE_ROOT`). No Node? The banner instead shows the install command for
that — copy it, run it, then click INSTALL.

To do it by hand instead: install [OpenCode](https://github.com/sst/opencode)
separately, then point `OPENCODE_ROOT` (`hub/features/opencode.py`) at it.
On first hub start,
`skills_sync.py` publishes the Agent Skills library into
`~/.config/opencode/skills/` so every OpenCode session picks it up — see
[README §Agent Skills](README.md#agent-skills).

### Missions

The hub's OpenCode card has four links: **MISSIONS**, **AGENTS**, **GRAPH**,
**QUICK CHAT** (a project-less raw OpenCode chat, opens in a new tab).

A **mission** = one `opencode run` against its **own git worktree** on a
throwaway branch under `N:\Code\opencode\worktrees\<project>--<id>\` — a precise
brief handed to one agent, run headless to completion. `/missions` is the board:

- **＋ NEW MISSION** → pick a project (a real folder), write the **brief** (what
  exactly the agent should do), choose **Single agent** (pick a persona) or
  **Orchestrator** (plans the goal into sub-briefs), optional model → DISPATCH.
- Each card shows status → the **ACTIVITY** feed (step / tool-call / text /
  error, live) → the **RESULT** (changed files + diff) → **APPLY** (merge the
  branch into the project's base when it's clean on base, else it hands you the
  `git merge` command) / **DISCARD** (delete the worktree). **COPY WORKTREE
  PATH** and **OPEN TRANSCRIPT** (the full OpenCode chat, on demand) are in the
  header.
- An **orchestrator** mission produces a plan of `proposed` sub-missions; review
  them, then **DISPATCH** each (or DISPATCH ALL). A sub-mission can target a
  different project; one with `depends_on` waits until its deps finish.
- Missions persist (`worktrees/_missions/*.json`) — the board survives a hub
  restart. A mission running > 15 min is timed out; `opencode run` that goes
  quiet after the agent's final `stop` is finished automatically.

### Agents

Baseline personas ship in `hub/agent_knowledge/agents/` (orchestrator + coder /
reviewer / researcher / tester / doc-writer; `agent-smith` is the persona-writer,
not a team member). They're copied into every mission's worktree. `/agents` is
management:

- Each persona shows its **effective LLM settings** (model / temperature / top_p
  / max-steps / reasoning — the value actually in effect, never blank).
  **EDIT SETTINGS** overrides them (→ `agent_overrides.json`, gitignored, applied
  on the next dispatch).
- **CREATE AGENT** / **EDIT WITH AI** → describe what you want (or what to
  change); **agent-smith** drafts/revises the persona `.md`; you review and save.
  New/edited personas land in `hub/agent_knowledge/agents_user/` (gitignored —
  yours, survive repo pulls; a user file shadows a baseline one of the same name).

### Models

`N:\Code\opencode\opencode.json` sets `model` / `small_model`. The free OpenCode
Zen tier is a shared gateway — a long turn can 504 (`Upstream idle timeout
exceeded`). Mitigations: `steps` caps + lean prompts; a mission that fails shows
the error with **RETRY** and **RETRY ON `<local/steadier model>`**; a configured
id that 404s falls back **free → other free → local** at dispatch. Only
self-hosted (`ollama` / `vllm`) or BYO-key ids never rotate. `ollama/qwen3.6:latest`
is the strongest local model installed; `nemotron-3-super:cloud` (Ollama Cloud,
`ollama signin`) is a good online-but-not-Zen-free middle option.

## 6. Run it like a desktop app (Windows) — optional

1. Start it: **double-click `Agent Hub.vbs`**. It starts the server hidden,
   opens the window, supervises (restarts on the ⟳ button), and **self-registers
   the `agenthub://` protocol** so the dormant page's START button works. No
   `.reg` file to run.
   - If your Python isn't at the default path, or you want the installed-PWA
     icon and the Tailscale Serve URL, copy `Agent Hub.local.vbs.example` to
     `Agent Hub.local.vbs` (gitignored) and fill it in.
2. Auto-start on login: put a shortcut to `Agent Hub.vbs` in `shell:startup`.
3. Own taskbar icon: open the **`https://…ts.net`** Serve URL in Edge →
   ⋯ → Apps → **Install**. Then put its app-id in `Agent Hub.local.vbs`
   (`PWA_APPID`) — the launcher will open the installed app instead of a plain
   Edge window.

## 7. YouTube upload / download — optional

Only if you use those cards. The Python side (`yt-dlp`, `mutagen`, the Google
API client libs — see `requirements-youtube.txt`) can be installed with the
setup banner's **Install YouTube dependencies now** button, or by hand:
`pip install -r requirements-youtube.txt`. Neither covers the part that's
inherently yours: see
[`youtube/credentials/README.md`](youtube/credentials/README.md) for the OAuth
*Desktop* client + `client_secrets.json` (gitignored). For downloads, stay
signed into YouTube in Firefox (the default cookie source) or point
`YT_DL_COOKIES` at an exported `cookies.txt`.

---

## Verify

```bash
python app.py
```

Open `http://localhost:8081` (or your Serve URL). The top of the page lists
anything still missing or unwired, with the doc section to read — it never
fails a card silently.
