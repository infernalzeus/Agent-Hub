# Agent Hub

A remote control for your PC: one always-on entry point, reachable from any device over
[Tailscale](https://tailscale.com/) at a single stable address, that wires into your own
web-UI and CLI apps. The apps themselves are **not** always running — the Hub spawns each
one on first use, reverse-proxies it under `/app/<id>/...`, and stops it again after a
period of inactivity (unless it reports itself busy). It also exposes a few direct actions
(YouTube upload/download, per-folder AI coding sessions via OpenCode, a PC power menu).

It's just a launcher/proxy: it doesn't modify the apps it fronts, it only starts them as
subprocesses and talks to them over `127.0.0.1`.

> **Windows-only.** It shells out to `shutdown`, `rundll32`, `tailscale.exe`, and uses a
> Windows Job Object to make child processes die with the Hub.

---

## What it fronts

None of these ship in this repo — they're separate, mostly open-source projects that the
Hub launches by path. Point the paths in `hub/config.py` (and `hub/features/opencode.py`)
at your own copies, or remove the entries you don't want:

| Feature | What it is | Where to get it |
|---------|-----------|-----------------|
| Movie Clipper | Not shipped — a slot for any CLI/web-UI app of your choice. Example: my own [movie-shorts-clipper](https://github.com/infernalzeus/movie-shorts-clipper) (movie → vertical shorts with captions) | your own web app that binds `127.0.0.1` + honours a base-path env var |
| File Browser  | Small tailnet file browser (included: `file-browser/app.py`) | ships in this repo |
| YouTube Upload | Uploads an MP4 via the YouTube Data API | `youtube/yt_upload.py` (included); **you supply OAuth creds — see below** |
| YouTube Download | `yt-dlp` wrapper (`youtube/ytdl.py`, included) | needs [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) installed in the interpreter you point `YT_DL_PYTHON` at |
| OpenCode | Per-folder AI coding agent sessions | [`opencode`](https://github.com/sst/opencode) binary + a source folder |

The included `file-browser/` and `youtube/` scripts are self-contained and MIT-friendly to
reuse. Any external app just has to obey the contract in **[Adding a new app](#adding-a-new-app)**.

---

## Setup

**Nothing here auto-installs.** There's no setup wizard — once running, the Hub checks its
own prerequisites and shows a banner for anything missing (which README section to read,
not a silent broken card), but it will never download or install something on your behalf.
That part's on you, once, per prerequisite below.

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

## Architecture

`app.py` is a thin composition root: `FEATURES = [apps, youtube, opencode, power, ui]`; each
feature module in `hub/features/` exposes `routes` + an optional `setup(app)`. Supporting
modules in `hub/`:

- `config.py` — constants, the `APPS` registry, paths (+ `local_settings.py` overrides).
- `platform_win.py` — Windows Job Object so every spawned child dies with the Hub.
- `proxy.py` — WebSocket-aware streaming reverse proxy.
- `supervisor.py` — start/stop + idle reaper for the proxied apps.
- `lifecycle.py` — startup hooks, graceful cleanup, force-exit watchdog.
- `ui.py` — the menu page, offline page, service worker, favicons.
