# Agent Hub

**Your most powerful PC tools. At your fingertips, any device.**

One address on your own private network. Your phone, tablet and laptop reach the PC at
home; the PC runs the work. Nothing is exposed to the internet, and nothing leaves your
[Tailscale](https://tailscale.com/) network.

---

## Install

Download for your machine from the
[latest release](https://github.com/infernalzeus/Agent-Hub/releases/latest):

| | | |
|---|---|---|
| **Windows** | [`Agent-Hub-Setup.exe`](https://github.com/infernalzeus/Agent-Hub/releases/latest/download/Agent-Hub-Setup.exe) | Everything works |
| **macOS** | [`Agent-Hub-macOS.dmg`](https://github.com/infernalzeus/Agent-Hub/releases/latest/download/Agent-Hub-macOS.dmg) | Unsigned — first launch, right-click → **Open** |
| **Linux** | [`Agent-Hub-Linux.tar.gz`](https://github.com/infernalzeus/Agent-Hub/releases/latest/download/Agent-Hub-Linux.tar.gz) | |

Run it, and it asks one question: **set everything up now, or set each tool up the first
time you open it.** Nothing installs until you say so, and every step tells you what it
will download and how big it is. Media and file browsing work with no network at all —
they ship inside the installer.

Then, to reach it from your phone: install Tailscale on the PC and the phone, sign both
into the same private network, open the Hub address and save it to your home screen.

> **Windows gets everything.** macOS and Linux run the Hub, agents, files and media;
> desktop control is Windows-only and is hidden there rather than offered and broken.
> See [`hub/platforms.py`](hub/platforms.py).

---

## What you get

### Autonomous LLM
Describe a task. An agent picks it up and works in **its own git worktree** — a private
copy of your repo. You read the diff and decide:

```
OpenCode ─▸ Missions ─▸ Dispatch ─┬─▸ Worktree ─▸ Review ─▸ Apply  (or discard)
                                  └─▸ Orchestrator
```

Your repo is never written to until you approve. The same worktree diff is what feeds the
Git Graph, so what an agent did shows up on the map.

### MCP Control
Speak to the PC from your phone. Open an app, run a routine it has learned. Every action
is approved, and control stays **off** until you switch it on. *(Windows only.)*

### Media Vault
Download, convert and file video and audio. Browse the machine's drives from anywhere, and
send files straight from your phone. Runs on yt-dlp and ffmpeg, both bundled.

### Git Graph
Every repo's real state, read live from its git history, drawn as one map — including the
worktrees your agents are working in.

### Your own apps
Point the Hub at any web app that binds `127.0.0.1` and honours a base-path env var. It
spawns it on first use, proxies it under `/app/<id>/`, and stops it when idle. See
[Adding a new app](#adding-a-new-app).

---

## Building your own installer

**Double-click `Build-Release.cmd`.** A window opens: type what changed, tick Windows /
macOS / Linux, press COMPILE. It bumps the patch version, writes the changelog, stamps the
notes into the installer, and — if you tick Publish — creates a draft GitHub release with
the installer attached.

macOS and Linux build on GitHub Actions, because PyInstaller cannot cross-compile.

Full detail, and how to change what ships inside the installer:
[`packaging/BUILDING.md`](packaging/BUILDING.md).

---

## Running from source

Everything below is for working on the Hub itself. To just use it, the installer above is
the supported path.

## Setup

> **First time here? Follow [`SETUP.md`](SETUP.md)** — a numbered do-this-in-order
> checklist. The rest of this section is the same ground in prose.

**An installed Hub has a first-run wizard**; running from source does not. From source,
the Hub checks its own prerequisites and shows a banner for anything missing — which
README section to read, not a silent broken card — but it never downloads or installs
anything on your behalf. That part is on you, once, per prerequisite below.

**Prerequisites checklist** (✅ = works with zero setup beyond `pip install`; the rest are
opt-in — skip anything you won't use):
- ✅ Python 3.10+ and `pip install -r requirements.txt` — this is all the File Browser and
  the power menu need.
- **Tailscale**, installed and signed in — technically optional (the Hub also just binds
  `0.0.0.0` and works over a plain LAN address), but it's what makes this a *remote
  control*, not just a local web page — install it if that's the point for you.
- **Any app you want fronted** (Movie Clipper, etc.) — your own repo, already runnable on
  its own. Hub only spawns/proxies it; see [Adding a new app](#adding-a-new-app).
- **[OpenCode](https://github.com/sst/opencode)**, installed separately, if you want the
  AI-coding-session feature. Point `OPENCODE_ROOT` (`hub/features/opencode.py`) at it.
- **YouTube upload/download** — only if you use those cards; see steps 3–4 below.

```bash
pip install -r requirements.txt        # just aiohttp
```

1. **Local secrets & paths.** Copy the override template and fill in your values:
   ```bash
   cp hub/local_settings.example.py hub/local_settings.py
   ```
   `hub/local_settings.py` is **gitignored** — it holds your power-menu PIN, any header
   shortcut (e.g. an `smb://` link to your NAS), and the absolute path to the interpreter
   that has `yt-dlp`. Anything you leave out falls back to the safe defaults in
   `hub/config.py`.

2. **Machine-specific app paths.** Edit `hub/config.py` (`APPS`, the `YT_DL_*`/`MC_OUTPUT_DIR`
   paths) and `hub/features/opencode.py` (`OPENCODE_ROOT`) to point at where those apps and
   folders live on your machine. These are your directories, not secrets — just change them.

3. **YouTube credentials** (only if you use upload). See
   [`youtube/credentials/README.md`](youtube/credentials/README.md): create a Google OAuth
   *Desktop* client, drop `client_secrets.json` under
   `youtube/credentials/<TAG>/`, and register `<TAG>` in `YOUTUBE_ACCOUNTS`. The token is
   created on first authorization. **Both files are gitignored — never commit them.**

4. **YouTube download auth.** YouTube bot-checks anonymous downloads. `ytdl.py` reads cookies
   from Firefox by default (`YT_DL_COOKIES_BROWSER=firefox`) — just stay signed into YouTube
   in Firefox — or point `YT_DL_COOKIES` at an exported `cookies.txt`.

### Run

```bash
python app.py
```

Opens on `http://0.0.0.0:8081` (override with `HUB_HOST` / `HUB_PORT`). From another
Tailscale device: `http://<this-machine>.<tailnet>.ts.net:8081`.

Open it in a browser and check the top of the page — if anything above is missing or
unwired, the Hub says so there directly instead of a card just failing.

> **The Hub is the only thing meant to face your tailnet.** Every app it fronts binds
> `127.0.0.1` and is reached only through the proxy. The **PC power menu** (shut
> down/restart/sleep/lock) is protected only by `HUB_POWER_PIN` — leave it empty and the
> menu is open to anyone who can reach the Hub, so set a PIN in `local_settings.py` before
> exposing it anywhere.

---

## Running it like a desktop app (Windows)

`python app.py` works, but for daily use there's a launcher that makes it feel native.

**`Agent Hub.vbs`** (in the repo root) — double-click it (or a shortcut to it) to:
- start the server **hidden** (no console window), and
- open the Hub in its **own window** — the installed PWA if present (own icon), else a
  chromeless Edge `--app` window.

It also doubles as a **supervisor**: the header **⟳ restart** button makes the Hub exit with
code `42`, and the `.vbs` loop relaunches it; the header **✕** exits `0`, so it stays down.
Launching again while it's already running just opens a window (it won't start a second server).
A dedicated helper process waits for the server to come up, then opens the window.

- **Desktop shortcut:** right-click `Agent Hub.vbs` → *Send to → Desktop*. Point its icon at
  `favicon.ico` (round icon shipped in the repo).
- **Auto-start at login:** drop that shortcut into `shell:startup`. The "already running" guard
  makes a double-launch harmless.

**Own taskbar icon (install as a PWA).** An `--app` window borrows Edge's icon. To give the Hub
its **own** icon + taskbar identity, install it as a PWA — but note two requirements the launcher
now handles for you:
- **Install needs a secure context.** `http://localhost` works, but the plain-HTTP tailnet
  address (`http://<host>:8081`) does **not** offer install. If you front the Hub with
  **Tailscale Serve** (HTTPS), open that `https://…ts.net` URL in a normal Edge tab → **⋯ → Apps
  → Install Agent Hub**. Bonus: it's the *same origin* your phone uses, so it's one unified app.
- Once installed, the `.vbs` launches the PWA **by its app-id**. Copy `Agent Hub.local.vbs.example`
  to `Agent Hub.local.vbs` (gitignored — never commit it) and set `PWA_APPID` there (find it in
  the shortcut Edge creates, `…msedge_proxy.exe --app-id=<id>`) and `APP_URL` (your Tailscale
  Serve HTTPS URL). Both are specific to your machine/tailnet, so they're kept out of the tracked
  script; without the local file, the launcher just opens plain `http://localhost` instead — it
  still works, you only lose the own-icon/same-origin bonuses above.

**Logs.** Every launch writes one decision log `logs/hub_<timestamp>.log` (plus the server's
own output as `.server.txt`); the last **5** launches are kept. If a window won't open, that log
records every step (already-running check, window-opener, what it launched).

**Dormant page.** When the Hub is down, the service worker serves the "DORMANT" page. It's
**device-aware**:
- On the **PC (Windows)** it shows a green **START** button. A web page can't run a local
  program, so START fires a custom URL protocol — run **`register-agenthub-protocol.reg`** once
  (per-user, no admin) to register `agenthub://` → the `.vbs`. START then relaunches the Hub in
  place.
- On a **phone/tablet** the button is greyed out with the note *"Agent Hub is dormant. Initiate
  from PC"* — the protocol is PC-only, and Tailscale carries traffic to *running* services but
  can't start a stopped one. Either page **auto-reconnects** once the Hub is back up.

> Editing the dormant page (`offline.html`) means bumping `CACHE_NAME` in the service worker,
> or the old page stays cached. Each device also needs to load the Hub once (while up) to pick
> up the new cache.

---

## Adding a new app

Add an entry to `APPS` in **`hub/config.py`**:

```python
"my-app": {
    "id": "my-app",
    "name": "My App",
    "emoji": "🛠️",
    "cwd": Path(r"C:\path\to\my-app"),
    "cmd": [sys.executable, "web/app.py"],
    "port": 8093,                       # pick an unused internal port
    "base_path": "/app/my-app",
    "health_path": "/status",           # 200 once ready; {"busy": bool} drives the idle reaper
    "idle_minutes": 20,
    "env": {
        "MYAPP_WEB_HOST": "127.0.0.1",
        "MYAPP_WEB_PORT": "8093",
        "MYAPP_BASE_PATH": "/app/my-app",
    },
},
```

The app itself needs to:

- Bind to `127.0.0.1` only (never exposed to the tailnet directly — only the Hub is).
- Serve `GET <health_path>` returning `200` once ready, ideally `{"busy": true/false}`.
- Use its `*_BASE_PATH` env var (empty by default, for standalone use) to prefix any
  absolute paths in its own HTML/JS and any URLs it hands back to the client.

---

## Agent Skills

The Hub carries a library of [Agent Skills](https://agentskills.io) (standard
`<name>/SKILL.md` directories) and **publishes it into the dirs OpenCode and Claude Code
already scan** — so every AI session on the machine gets them through the native `skill`
tool with progressive disclosure. The Hub owns the *source*; it does not invent a skill
mechanism.

Three sources feed one library (`hub/agent_knowledge/`):

| Source dir | What | In git? |
|---|---|---|
| `skills/` | hand-written skills | yes |
| `skills_vendor/` | verbatim Apache-2.0 skills from [`anthropics/skills`](https://github.com/anthropics/skills) — see `skills_vendor/PROVENANCE.md` | yes |
| `skills_generated/` | compiled on each hub start from LLM-wiki pages tagged `skill: true` | no (build artifact) |

`skills_sync.py` runs on every `python app.py` start and mirrors them to
`~/.config/opencode/skills/` (all) and `~/.claude/skills/` (hand-written + wiki only —
Claude Code ships the vendored ones as plugins). It's idempotent and only ever touches
dirs it created. The `/graph` page's project panel shows which skills match each project.

---

## Architecture

`app.py` is a thin composition root: every module in `FEATURES` exposes `routes` and an
optional `setup(app)`, and `app.py` wires them into one aiohttp app. Adding a feature
means adding it to that list. `request_security.install(app)` runs last, so it is the
first thing a state-changing request meets. Supporting modules in `hub/`:

- `config.py` — constants, the `APPS` registry, paths (+ `local_settings.py` overrides).
- `platform_win.py` — Windows Job Object so every spawned child dies with the Hub.
- `proxy.py` — WebSocket-aware streaming reverse proxy.
- `supervisor.py` — start/stop + idle reaper for the proxied apps.
- `lifecycle.py` — startup hooks, graceful cleanup, force-exit watchdog.
- `runtime.py` — the only place that knows source-from-clone versus installed:
  `PACKAGED`, `STATE` (where writable state lives) and `python_for(capability)`.
  It exists so the build never has to patch source.
- `platforms.py` — what this OS can actually do; the UI hides the rest.
- `request_security.py` / `integration_tokens.py` — same-origin enforcement, plus
  named revocable tokens so scripts and phone shortcuts still work.
- `ui.py` — the menu page, offline page, service worker, favicons.
