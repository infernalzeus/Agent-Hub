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
    return {"ready": ready, "ran": rep is not None, "report": rep, "max_episodes": MAX_EPISODES,
            "needs": None if ready else "numpy is not installed; practising needs it, nothing else does"}


def _run(episodes: int) -> dict:
    if not _busy.acquire(blocking=False):
        raise RuntimeError("a practice run is already going")
    try:
        from . import practice
        return practice.practice(episodes=episodes, n_eval=20)
    finally:
        _busy.release()


@routes.get("/api/yard/status")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(status())


@routes.post("/api/yard/practice")
async def api_practice(request: web.Request) -> web.Response:
    body = await request.json()
    if body.get("confirm") is not True:
        raise web.HTTPBadRequest(text="Confirm the practice run first; it uses the processor for about a minute")
    if not status()["ready"]:
        raise web.HTTPServiceUnavailable(text=status()["needs"])
    episodes = max(100, min(MAX_EPISODES, int(body.get("episodes") or 1500)))
    try:
        rep = await asyncio.get_running_loop().run_in_executor(None, _run, episodes)
    except RuntimeError as exc:
        raise web.HTTPConflict(text=str(exc))
    return web.json_response({"means": rep["means"], "train_seconds": rep["train_seconds"], "episodes": rep["episodes"]})
