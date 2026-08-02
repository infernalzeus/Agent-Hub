"""Agent Hub — configuration, constants, and the app registry."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Repo root. config.py lives in hub/, so go up one level to reach the same
# directory the original monolithic app.py sat in (favicon, youtube/, etc.).
HERE = Path(__file__).resolve().parent.parent

HOST = os.getenv("HUB_HOST", "0.0.0.0")
PORT = int(os.getenv("HUB_PORT", "8081"))

TAILDROP_DIR = Path(os.getenv("TAILDROP_DIR", r"N:\Taildrop"))
TAILSCALE_EXE = os.getenv("TAILSCALE_EXE", r"C:\Program Files\Tailscale\tailscale.exe")

# PIN that unlocks the PC power menu (shutdown/restart/sleep/lock). Prompted each
# time the power panel is opened. An empty PIN DISABLES THE GATE ENTIRELY — the
# power menu becomes available to anyone who can reach the Hub. Set a real PIN in
# hub/local_settings.py (or the HUB_POWER_PIN env var) before exposing the power
# menu on any network.
HUB_POWER_PIN = os.getenv("HUB_POWER_PIN", "")

logging.basicConfig(format="%(asctime)s — %(name)s — %(levelname)s — %(message)s", level=logging.INFO)
logger = logging.getLogger("agent-hub")


# ── App registry ────────────────────────────────────────────────────────────
# To add a new app: give it its own internal port + base_path, and whatever
# env vars it needs to know its host/port/prefix. That's the whole contract.

APPS: dict[str, dict] = {
    "movie-clipper": {
        "id": "movie-clipper",
        "name": "Movie Clipper",
        "emoji": "🎬",
        "cwd": Path(r"N:\Code\git repositories\My Repo\movie-shorts-clipper"),
        "cmd": [sys.executable, "web/app.py"],
        "port": 8091,
        "base_path": "/app/movie-clipper",
        "health_path": "/status",
        "idle_minutes": 20,
        "env": {
            "CLIPPER_WEB_HOST": "127.0.0.1",
            "CLIPPER_WEB_PORT": "8091",
            "CLIPPER_BASE_PATH": "/app/movie-clipper",
        },
    },
    "file-browser": {
        "id": "file-browser",
        "name": "File Browser",
        "emoji": "📁",
        "cwd": HERE / "file-browser",
        "cmd": [sys.executable, "app.py"],
        "port": 8092,
        "base_path": "/app/file-browser",
        "health_path": "/status",
        "idle_minutes": 20,
        "env": {
            "FB_WEB_HOST": "127.0.0.1",
            "FB_WEB_PORT": "8092",
            "FB_BASE_PATH": "/app/file-browser",
        },
    },
}

# Static shortcuts shown top-right in the header — no backend process, just a link.
# Machine-specific (e.g. an smb:// link to your own NAS/tailnet host), so this is
# empty by default and populated in hub/local_settings.py. See
# local_settings.example.py.
SHORTCUTS: list[dict] = []


# ── YouTube upload ───────────────────────────────────────────────────────────
# Self-contained: the uploader script and account credentials live inside Agent
# Hub itself (youtube/), copied from Agent CORE rather than referenced by path,
# so Agent Hub has no dependency on Agent CORE's file layout. Agent CORE keeps
# its own originals untouched and unaffected. Not a spawned/proxied app like the
# others — it's an action, not a destination, so there's no start/stop
# lifecycle: the upload script only runs as a subprocess for the duration of an
# actual upload.

YT_UPLOAD_SCRIPT = str(HERE / "youtube" / "yt_upload.py")
MC_OUTPUT_DIR = Path(r"N:\Code\git repositories\My Repo\movie-shorts-clipper\output")

YOUTUBE_ACCOUNTS: dict[str, dict] = {
    "IZ17-G": {
        "secrets_file": str(HERE / "youtube" / "credentials" / "IZ17-G" / "client_secrets.json"),
        "token_file": str(HERE / "youtube" / "credentials" / "IZ17-G" / "youtube_token.pickle"),
    },
}

# ── YouTube download ─────────────────────────────────────────────────────────
# Same self-contained shape as the uploader: script copied in, not referenced
# elsewhere. yt_dlp is only installed in this specific Python 3.11 install
# (confirmed — it's absent from the Anaconda interpreter Hub itself runs
# under), so this is the one subprocess spawn that can't use sys.executable.

YT_DL_SCRIPT = str(HERE / "youtube" / "ytdl.py")
# The one interpreter that has yt_dlp installed. Defaults to whatever "python3.11"
# resolves to on PATH; override with an absolute path in hub/local_settings.py.
YT_DL_PYTHON = os.getenv("YT_DL_PYTHON", "python3.11")
YT_DL_AUDIO_DIR = os.getenv("YT_DL_AUDIO_DIR", r"N:\Code\YT-DLP\1")
YT_DL_VIDEO_DIR = os.getenv("YT_DL_VIDEO_DIR", r"N:\Code\YT-DLP\2")

# YouTube now blocks most anonymous downloads ("Sign in to confirm you're not a
# bot"). Authenticate with an exported cookies.txt (preferred for an always-on
# service — browser-cookie extraction fails while the browser is open / with
# App-Bound Encryption). Export once with a "Get cookies.txt" extension while
# signed in to YouTube and drop the file at YT_DL_COOKIES. As a fallback,
# YT_DL_COOKIES_BROWSER (e.g. "edge") reads cookies live from a browser.
YT_DL_COOKIES = os.getenv("YT_DL_COOKIES", r"N:\Code\YT-DLP\cookies.txt")
# Default to reading Firefox's live cookies: unlike Edge/Chrome it has no
# App-Bound Encryption, so yt-dlp reads it directly (even while open) and the
# login auto-refreshes — no cookies.txt to maintain. An explicit cookies.txt at
# YT_DL_COOKIES still wins if one is ever placed there.
YT_DL_COOKIES_BROWSER = os.getenv("YT_DL_COOKIES_BROWSER", "firefox")


# ── Machine-specific overrides (secrets & local paths) ────────────────────────
# Real secrets (power PIN, tailnet SMB link) and per-machine paths live in
# hub/local_settings.py, which is GITIGNORED and never committed. It may rebind
# any name defined above — HUB_POWER_PIN, SHORTCUTS, YT_DL_PYTHON, the various
# *_DIR paths, etc. Copy local_settings.example.py to local_settings.py to set
# your own. Anything not overridden falls back to the safe defaults above.
try:
    from .local_settings import *  # noqa: F401,F403
except ImportError:
    pass
