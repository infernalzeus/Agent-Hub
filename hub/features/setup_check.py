"""Setup-prerequisite detection.

Agent Hub has no install wizard, and it fronts things it doesn't ship (an
OpenCode install, your own app repos). Rather than a card silently failing
the first time you click it, this checks what's actually missing/unwired and
reports it so the UI can say so plainly — a link to the relevant README
section, not a mystery error. Detection only: this never downloads, installs,
or writes anything on your behalf.
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from .apps import APPS
from ..config import HUB_POWER_PIN, logger
from .opencode import OPENCODE_EXE

routes = web.RouteTableDef()

HERE = Path(__file__).resolve().parent.parent.parent  # Agent Hub/


def _check() -> list[dict]:
    issues: list[dict] = []

    if not Path(OPENCODE_EXE).is_file():
        issues.append({
            "severity": "info", "title": "OpenCode isn't installed",
            "detail": "The OpenCode card won't work until you install the "
                       "opencode binary and point OPENCODE_ROOT at it.",
            "readme_anchor": "#what-it-fronts",
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

    return issues


@routes.get("/api/setup-status")
async def setup_status(request: web.Request) -> web.Response:
    try:
        issues = _check()
    except Exception as exc:
        logger.warning("setup_check: %s", exc)
        issues = []
    return web.json_response({"issues": issues})
