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
VOICEBOX_URL = os.getenv("VOICEBOX_URL", "http://127.0.0.1:17493").rstrip("/")

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
# The fronted-app list is now data-driven: hub/apps.json (gitignored, seeded on
# first run from hub/apps.default.json). The auto-ingest flow and the menu's
# edit mode write that file; call reload_apps() + supervisor.rebuild_app_procs()
# to pick up a change without a restart. See hub/app_registry.py.

from . import app_registry  # noqa: E402

APPS: dict[str, dict] = app_registry.load()


def reload_apps() -> None:
    """Re-read hub/apps.json into APPS (after the registry is edited)."""
    global APPS
    APPS = app_registry.load()

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
# YouTube downloads run through Agent Hub's own Python interpreter.
# The setup action maintains yt-dlp in that interpreter.
YT_DL_SCRIPT = str(HERE / "youtube" / "ytdl.py")
# Override with an absolute path in hub/local_settings.py only when required.
YT_DL_PYTHON = os.getenv("YT_DL_PYTHON", sys.executable)
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

# Locations the user saved from /setup win over everything above (see hub/locations.py).
from . import locations as _locations  # noqa: E402
_locations.apply_to_config(globals())




