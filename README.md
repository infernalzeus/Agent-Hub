# Agent Hub

A single always-on entry point for your personal web apps, reachable over
[Tailscale](https://tailscale.com/) at one stable address. The apps themselves are **not**
always running — the Hub spawns each one on first use, reverse-proxies it under
`/app/<id>/...`, and stops it again after a period of inactivity (unless it reports itself
busy). It also exposes a few direct actions (YouTube upload/download, a PC power menu).

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
| Movie Clipper | Movie → vertical shorts with captions | your own web app that binds `127.0.0.1` + honours a base-path env var |
| File Browser  | Small tailnet file browser (included: `file-browser/app.py`) | ships in this repo |
| YouTube Upload | Uploads an MP4 via the YouTube Data API | `youtube/yt_upload.py` (included); **you supply OAuth creds — see below** |
| YouTube Download | `yt-dlp` wrapper (`youtube/ytdl.py`, included) | needs [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) installed in the interpreter you point `YT_DL_PYTHON` at |
| OpenCode | Per-folder AI coding agent sessions | [`opencode`](https://github.com/sst/opencode) binary + a source folder |

The included `file-browser/` and `youtube/` scripts are self-contained and MIT-friendly to
reuse. Any external app just has to obey the contract in **[Adding a new app](#adding-a-new-app)**.

---

## Setup

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

> **The Hub is the only thing meant to face your tailnet.** Every app it fronts binds
> `127.0.0.1` and is reached only through the proxy. The **PC power menu** (shut
> down/restart/sleep/lock) is protected only by `HUB_POWER_PIN` — leave it empty and the
> menu is open to anyone who can reach the Hub, so set a PIN in `local_settings.py` before
> exposing it anywhere.

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
