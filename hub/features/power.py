"""PC power control: shut down / restart / sleep / lock, gated by a PIN.

Every action but the safety `abort` requires the PIN (HUB_POWER_PIN). Sleep and
lock are immediate; shutdown/restart run `shutdown /s|/r /t 30` — a normal
graceful Windows shutdown with a 30-second window that `abort` cancels.
"""
from __future__ import annotations

import subprocess

from aiohttp import web

from .. import platforms as PLAT
from .. import power_settings as PS

routes = web.RouteTableDef()

# Per-OS; empty where power control is not supported, so every action 404s
# rather than shelling out to a command that does not exist.
_POWER_CMDS = PLAT.power_commands()
_POWER_NEEDS_PIN = {"shutdown", "restart", "sleep", "lock"}


async def _json(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _pin_ok(data: dict) -> bool:
    # Read at action time, not at import: changing the PIN takes effect at once.
    return PS.verify(str(data.get("pin", "")))


@routes.post("/api/power/unlock")
async def power_unlock(request: web.Request) -> web.Response:
    """Validate the PIN when the panel opens. 200 = ok (or none configured),
    403 = wrong PIN."""
    data = await _json(request)
    if not _pin_ok(data):
        raise web.HTTPForbidden(text="wrong PIN")
    return web.json_response({"ok": True, "pin_required": PS.configured()})


# ── PIN settings ─────────────────────────────────────────────────────────────
# Registered before /api/power/{action} so "settings" is not read as an action.
@routes.get("/api/power/settings")
async def power_settings_status(request: web.Request) -> web.Response:
    """Whether a PIN is set — never the PIN itself."""
    return web.json_response(PS.status())


@routes.post("/api/power/settings/set")
async def power_settings_set(request: web.Request) -> web.Response:
    data = await _json(request)
    ok, message = PS.set_pin(data.get("new"), data.get("confirm"), data.get("current"))
    return web.json_response({"ok": ok, "message": message, **PS.status()},
                             status=200 if ok else 400)


@routes.post("/api/power/settings/remove")
async def power_settings_remove(request: web.Request) -> web.Response:
    data = await _json(request)
    ok, message = PS.remove_pin(data.get("current"))
    return web.json_response({"ok": ok, "message": message, **PS.status()},
                             status=200 if ok else 400)


@routes.post("/api/power/{action}")
async def power_action(request: web.Request) -> web.Response:
    action = request.match_info["action"]
    cmd = _POWER_CMDS.get(action)
    if not cmd:
        raise web.HTTPNotFound()

    data = await _json(request)
    if action in _POWER_NEEDS_PIN and not _pin_ok(data):
        raise web.HTTPForbidden(text="PIN required")

    # SetSuspendState blocks until the machine wakes — fire-and-forget.
    if action in ("sleep", "lock"):
        subprocess.Popen(cmd)
        return web.json_response({"ok": True, "action": action})

    r = subprocess.run(cmd, capture_output=True, text=True)
    return web.json_response({
        "ok": r.returncode == 0,
        "action": action,
        "detail": (r.stderr or r.stdout).strip()[:200],
    })
