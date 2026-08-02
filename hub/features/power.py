"""PC power control: shut down / restart / sleep / lock, gated by a PIN.

Every action but the safety `abort` requires the PIN (HUB_POWER_PIN). Sleep and
lock are immediate; shutdown/restart run `shutdown /s|/r /t 30` — a normal
graceful Windows shutdown with a 30-second window that `abort` cancels.
"""
from __future__ import annotations

import subprocess

from aiohttp import web

from ..config import HUB_POWER_PIN

routes = web.RouteTableDef()

_POWER_CMDS = {
    "shutdown": ["shutdown", "/s", "/t", "30"],
    "restart":  ["shutdown", "/r", "/t", "30"],
    "abort":    ["shutdown", "/a"],
    "sleep":    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "lock":     ["rundll32.exe", "user32.dll,LockWorkStation"],
}
_POWER_NEEDS_PIN = {"shutdown", "restart", "sleep", "lock"}


async def _json(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _pin_ok(data: dict) -> bool:
    return (not HUB_POWER_PIN) or (str(data.get("pin", "")) == HUB_POWER_PIN)


@routes.post("/api/power/unlock")
async def power_unlock(request: web.Request) -> web.Response:
    """Validate the PIN when the panel opens. 200 = ok (or none configured),
    403 = wrong PIN."""
    data = await _json(request)
    if not _pin_ok(data):
        raise web.HTTPForbidden(text="wrong PIN")
    return web.json_response({"ok": True, "pin_required": bool(HUB_POWER_PIN)})


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
