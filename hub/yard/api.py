"""The yard's two endpoints. Reading the last report needs nothing; practising is explicit, bounded and one at a time.

numpy is imported only when a practice run starts, so a Hub without numpy still answers /api/yard/status.
"""
from __future__ import annotations

import asyncio
import json
import threading

from aiohttp import web

from ..runtime import STATE

routes = web.RouteTableDef()
REPORT = STATE / "data" / "yard" / "report.json"   # the same file practice.py writes
MAX_EPISODES = 3000
_busy = threading.Lock()


def status() -> dict:
    try:
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rep = None
    try:
        import numpy  # noqa: F401
        ready = True
    except ImportError:
        ready = False
    from . import shadow
    from . import practice as _P
    from . import store
    return {"versions": store.versions(REPORT.parent), "in_use_version": store.current_version(REPORT.with_name("policy.json")), "progress": dict(_P.CONTROL), "ready": ready, "ran": rep is not None, "report": rep, "shadow": shadow.summary(), "max_episodes": MAX_EPISODES,
            "needs": None if ready else "numpy is not installed; practising needs it, nothing else does"}


def _run(episodes: int) -> dict:
    if not _busy.acquire(blocking=False):
        raise RuntimeError("a practice run is already going")
    try:
        from . import practice
        return practice.practice(episodes=episodes)                     # unseen apps per cell and everything else come from the KNOBS tab
    finally:
        _busy.release()


@routes.get("/api/yard/status")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(status())


@routes.get("/api/yard/settings")
async def api_settings(request: web.Request) -> web.Response:
    from . import settings
    return web.json_response(settings.current())


@routes.post("/api/yard/settings")
async def api_settings_set(request: web.Request) -> web.Response:
    """{"learning": false} and/or {"shadow": true}. Switching either off stops new notes at once; nothing already recorded is deleted."""
    from . import settings
    body = await request.json()
    if not any(isinstance(body.get(k), bool) for k in (*settings.KEYS, "experimental", "fresh")):
        raise web.HTTPBadRequest(text='Send {"experimental": bool}, {"learning": bool}, {"shadow": bool} and/or {"fresh": true}')
    return web.json_response(settings.update(body))


@routes.post("/api/yard/rollback")
async def api_rollback(request: web.Request) -> web.Response:
    """{"version": 3}: make a saved version the one in use. The way back after a session you do not like; nothing is deleted."""
    from . import events as EV, store
    try:
        n = int((await request.json())["version"])
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"version": a saved version number}')
    if not store.restore(REPORT.parent, REPORT.with_name("policy.json"), n):
        raise web.HTTPNotFound(text="no such version")
    EV.emit("ver", "restored", f"version {n} is now the one in use", n)
    return web.json_response({"ok": True, "in_use_version": n})


@routes.post("/api/yard/practice/stop")
async def api_stop(request: web.Request) -> web.Response:
    """Ask a practice run to end at its next episode. Nothing is saved from a stopped run; the last finished report stays."""
    from . import practice as P
    was = bool(P.CONTROL["running"])
    if was:
        P.CONTROL["stop"] = True
    return web.json_response({"was_running": was})


@routes.post("/api/yard/practice")
async def api_practice(request: web.Request) -> web.Response:
    body = await request.json()
    if body.get("confirm") is not True:
        raise web.HTTPBadRequest(text="Confirm the practice run first; it uses the processor for about a minute")
    if not status()["ready"]:
        raise web.HTTPServiceUnavailable(text=status()["needs"])
    from . import knobs as K
    episodes = max(100, min(MAX_EPISODES, int(body.get("episodes") or K.get("episodes"))))
    try:
        rep = await asyncio.get_running_loop().run_in_executor(None, _run, episodes)
    except RuntimeError as exc:
        raise web.HTTPConflict(text=str(exc))
    if rep.get("stopped"):
        return web.json_response({"stopped": True, "done": rep["done"], "total": rep["total"]})
    return web.json_response({"means": rep["means"], "train_seconds": rep["train_seconds"], "episodes": rep["episodes"]})
