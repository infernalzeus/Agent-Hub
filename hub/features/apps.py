"""Singleton-app routes: status, start/stop, and the /app/<id>/... proxy."""
from __future__ import annotations

import asyncio
import signal
import time

from aiohttp import web

from ..config import APPS
from ..supervisor import APP_PROCS, ensure_started, stop_app
from ..proxy import _proxy_http, _proxy_ws

routes = web.RouteTableDef()


@routes.get("/api/status")
async def api_status(request: web.Request) -> web.Response:
    out = {aid: {"running": ap.running} for aid, ap in APP_PROCS.items()}
    return web.json_response(out)


@routes.post("/api/start/{app_id}")
async def api_start(request: web.Request) -> web.Response:
    app_id = request.match_info["app_id"]
    ap = APP_PROCS.get(app_id)
    if not ap:
        raise web.HTTPNotFound()
    try:
        await ensure_started(ap)
    except Exception as exc:
        raise web.HTTPBadGateway(text=str(exc))
    return web.json_response({"ok": True, "base_path": ap.cfg["base_path"]})


@routes.post("/api/shutdown")
async def api_shutdown(request: web.Request) -> web.Response:
    """Turn Agent Hub off from the UI (the header X button).

    Mirrors Ctrl+C exactly: raising SIGINT runs the same graceful shutdown
    (child apps, Taildrop watcher, and YT jobs all stopped via on_cleanup) and
    arms the force-exit watchdog. Fired just after this response flushes so the
    caller still receives a clean 200 before the server goes down.

    Scheduled as a plain loop callback, NOT a Task: the SIGINT handler raises
    KeyboardInterrupt synchronously, and from a callback it unwinds straight up
    to web.run_app's shutdown (as a real Ctrl+C does). A Task would instead
    *hold* that KeyboardInterrupt as an unretrieved result, which asyncio dumps
    to the terminal as a spurious 'Task exception was never retrieved' traceback."""
    def _raise_sigint() -> None:
        signal.raise_signal(signal.SIGINT)

    asyncio.get_running_loop().call_later(0.3, _raise_sigint)
    return web.json_response({"ok": True})


@routes.post("/api/stop/{app_id}")
async def api_stop(request: web.Request) -> web.Response:
    app_id = request.match_info["app_id"]
    ap = APP_PROCS.get(app_id)
    if not ap:
        raise web.HTTPNotFound()
    await stop_app(ap)
    return web.json_response({"ok": True})


@routes.route("*", "/app/{app_id}/{path:.*}")
async def proxy(request: web.Request) -> web.StreamResponse:
    app_id = request.match_info["app_id"]
    sub_path = request.match_info["path"]
    cfg = APPS.get(app_id)
    ap = APP_PROCS.get(app_id)
    if not cfg or not ap:
        raise web.HTTPNotFound()

    try:
        await ensure_started(ap)
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"Failed to start {cfg['name']}: {exc}")

    ap.last_activity = time.monotonic()

    target_base = f"http://127.0.0.1:{cfg['port']}"
    target_path = "/" + sub_path

    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await _proxy_ws(request, target_base, target_path)
    return await _proxy_http(request, target_base, target_path)

