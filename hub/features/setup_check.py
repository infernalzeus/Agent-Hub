"""Setup-prerequisite detection.

Agent Hub has no install wizard, and it fronts things it doesn't ship (an
OpenCode install, your own app repos). Rather than a card silently failing
the first time you click it, this checks what's actually missing/unwired and
reports it so the UI can say so plainly — a link to the relevant README
section, not a mystery error.

Detection is the default for everything here. Two issues (OpenCode, YouTube
deps) additionally carry a same-machine, reversible `action` the UI can offer
as a one-click fix — see setup_actions.py for exactly what those run and why
they're the only ones. Everything else, and anything system-level (Node.js,
Tailscale), stays detect-and-point-at-the-README, or at most a copyable
command — never auto-installed.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import time
import sys
from pathlib import Path

from aiohttp import web

from .apps import APPS
from ..config import HUB_POWER_PIN, TAILSCALE_EXE, logger
from .opencode import OPENCODE_EXE
from . import setup_actions

routes = web.RouteTableDef()

HERE = Path(__file__).resolve().parent.parent.parent  # Agent Hub/


def _module_missing_in(python_exe: str, modules: list[str]) -> list[str]:
    missing = []
    for mod in modules:
        try:
            r = subprocess.run([python_exe, "-c", f"import {mod}"],
                                capture_output=True, timeout=8)
            if r.returncode != 0:
                missing.append(mod)
        except Exception:
            missing.append(mod)
    return missing


OPENCODE_MIN_VERSION = (1, 18, 0)     # OpenCode Zen free tier rejects older clients with HTTP 426


def _opencode_version() -> tuple[int, ...] | None:
    try:
        r = subprocess.run([OPENCODE_EXE, "--version"], capture_output=True, text=True, timeout=8)
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout + r.stderr)
        return tuple(int(x) for x in m.groups()) if m else None
    except Exception:
        return None


def _check() -> list[dict]:
    issues: list[dict] = []

    from .. import locations as LOC
    if LOC.configured():
        for r in LOC.REGISTRY:
            st = LOC.validate(r["key"], LOC.get(r["key"]))
            if st["level"] == "error":
                issues.append({"severity": "warn", "title": f"{r['label']}: {st['msg']}", "detail": r["purpose"],
                               "action": {"kind": "link", "label": "Fix in LOCATIONS", "href": "/setup"}})

    if Path(OPENCODE_EXE).is_file():
        ver = _opencode_version()
        if ver and ver < OPENCODE_MIN_VERSION and shutil.which("npm"):
            issues.append({
                "severity": "warn", "title": f"OpenCode {'.'.join(map(str, ver))} is too old for the free models",
                "detail": "OpenCode Zen now rejects clients older than "
                          f"{'.'.join(map(str, OPENCODE_MIN_VERSION))} (HTTP 426) — every free-model mission fails until it's updated.",
                "readme_anchor": "#what-it-fronts",
                "action": {"kind": "install", "id": "update-opencode", "label": "Update OpenCode now"},
            })

    if not Path(OPENCODE_EXE).is_file():
        if shutil.which("npm"):
            action = {"kind": "install", "id": "install-opencode",
                      "label": "Install OpenCode now"}
        else:
            action = {"kind": "command", "label": "Copy install command",
                       "command": "winget install OpenJS.NodeJS.LTS"}
        issues.append({
            "severity": "info", "title": "OpenCode isn't installed",
            "detail": "The OpenCode card won't work until you install the "
                       "opencode binary and point OPENCODE_ROOT at it."
                       + ("" if shutil.which("npm") else
                          " Needs Node.js/npm on PATH first — install that, then retry."),
            "readme_anchor": "#what-it-fronts",
            "action": action,
        })

    yt_missing = (_module_missing_in(setup_actions.yt_python_target(), ["yt_dlp", "mutagen"])
                  + _module_missing_in(sys.executable,
                                       ["googleapiclient", "google_auth_oauthlib"]))
    if yt_missing:
        issues.append({
            "severity": "info",
            "title": f"YouTube dependencies missing ({', '.join(sorted(set(yt_missing)))})",
            "detail": "YT Download and YT Upload won't work until these Python "
                       "packages are installed.",
            "readme_anchor": "#what-it-fronts",
            "action": {"kind": "install", "id": "install-yt-deps",
                       "label": "Install YouTube dependencies now"},
        })

    missing_apps = [cfg["name"] for cfg in APPS.values()
                     if not Path(cfg["cwd"]).is_dir()]
    if missing_apps:
        issues.append({
            "severity": "info",
            "title": f"{len(missing_apps)} app folder(s) not found: {', '.join(missing_apps)}",
            "detail": "These are configured in hub/config.py (APPS) but their "
                       "cwd doesn't exist on this machine yet — point them at "
                       "your own copies, or remove the entries you don't want.",
            "readme_anchor": "#adding-a-new-app",
        })

    if not (HERE / "hub" / "local_settings.py").is_file():
        issues.append({
            "severity": "info", "title": "hub/local_settings.py not set up",
            "detail": "Running on defaults — fine to start, but the power-menu "
                       "PIN, any header shortcut, and machine-specific paths "
                       "live here. Copy local_settings.example.py to set them.",
            "readme_anchor": "#setup",
        })
    elif not HUB_POWER_PIN:
        issues.append({
            "severity": "warn", "title": "Power-menu PIN is empty",
            "detail": "Shutdown/restart/sleep/lock are open to anyone who can "
                       "reach the Hub. Set HUB_POWER_PIN in hub/local_settings.py "
                       "before exposing this beyond localhost.",
            "readme_anchor": "#setup",
        })

    if not (HERE / "Agent Hub.local.vbs").is_file():
        issues.append({
            "severity": "info", "title": "Agent Hub.local.vbs not set up",
            "detail": "Only needed for the desktop-app launcher's own-icon/"
                       "same-origin-as-phone bonus (Tailscale Serve URL). The "
                       "launcher works without it — falls back to localhost.",
            "readme_anchor": "#running-it-like-a-desktop-app-windows",
        })

    # Tailscale: technically optional, but it's what makes this a *remote*
    # control rather than a local page. Only flag if it's not even installed.
    tailscale = TAILSCALE_EXE if Path(TAILSCALE_EXE).is_file() else shutil.which("tailscale")
    if not tailscale:
        issues.append({
            "severity": "info", "title": "Tailscale not found",
            "detail": "The Hub runs fine on a plain LAN address, but Tailscale "
                       "is what lets you reach it from your phone anywhere. "
                       "Install it and sign in, then set up `tailscale serve` "
                       "for the HTTPS origin (see SETUP.md).",
            "readme_anchor": "#setup",
            "action": {"kind": "command", "label": "Copy install command",
                       "command": "winget install Tailscale.Tailscale"},
        })
    else:
        try:
            r = subprocess.run([tailscale, "status"], capture_output=True,
                               text=True, timeout=4)
            if r.returncode != 0 or "Logged out" in (r.stdout + r.stderr):
                issues.append({
                    "severity": "info", "title": "Tailscale installed but not connected",
                    "detail": "Run `tailscale up` and sign in so other devices "
                               "can reach the Hub.",
                    "readme_anchor": "#setup",
                })
        except Exception:
            pass

    # Skills library: skills_sync publishes into OpenCode's global dir on every
    # hub start. If it's empty, the sync hasn't run (or failed).
    oc_skills = Path.home() / ".config" / "opencode" / "skills"
    if not (oc_skills.is_dir() and any(oc_skills.iterdir())):
        issues.append({
            "severity": "info", "title": "Agent Skills not published yet",
            "detail": f"{oc_skills} is empty — the skill library hasn't synced. "
                       "It publishes automatically on hub start; check the log "
                       "for a `skills_sync` line.",
            "readme_anchor": "#agent-skills",
        })

    return issues


_CACHE: dict = {"at": 0.0, "issues": [], "busy": False}
_TTL = 60.0


def _safe_check() -> list[dict]:
    try:
        return _check()
    except Exception as exc:
        logger.warning("setup_check: %s", exc)
        return []


async def _refresh_cache() -> None:
    """`_check()` shells out (opencode --version, import probes, tailscale status) ~2s — it must run in a
    worker thread: run inline it froze EVERY request (menu tiles, status, clicks) while it ran."""
    if _CACHE["busy"]:
        return
    _CACHE["busy"] = True
    try:
        _CACHE["issues"] = await asyncio.get_running_loop().run_in_executor(None, _safe_check)
        _CACHE["at"] = time.time()
    finally:
        _CACHE["busy"] = False


@routes.get("/api/setup-status")
async def setup_status(request: web.Request) -> web.Response:
    if not _CACHE["at"]:
        await _refresh_cache()                       # first ever call: wait, but off the event loop
    elif time.time() - _CACHE["at"] > _TTL:
        asyncio.create_task(_refresh_cache())        # stale-while-revalidate: answer instantly, refresh behind
    return web.json_response({"issues": _CACHE["issues"]})


def setup(app: web.Application) -> None:
    async def _warm(_app: web.Application) -> None:
        asyncio.create_task(_refresh_cache())        # compute once in the background after the hub is listening
    app.on_startup.append(_warm)


@routes.post("/api/setup/install/{action_id}")
async def setup_install(request: web.Request) -> web.Response:
    """Run one of the safely-local install actions (setup_actions.ACTIONS) and
    report what happened. Never used for Node.js/Tailscale/anything
    system-level — those stay show-command-only issues, with no route here."""
    action = setup_actions.ACTIONS.get(request.match_info["action_id"])
    if action is None:
        return web.json_response({"error": "unknown action"}, status=404)
    ok, log = await asyncio.get_event_loop().run_in_executor(None, action.run)
    _CACHE["at"] = 0.0                                  # something was just installed — re-probe on the next status call
    return web.json_response({"ok": ok, "log": log})

