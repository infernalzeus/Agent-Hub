"""Singleton-app routes: status, start/stop, the /app/<id>/... proxy, and the
data-driven app registry (list / reorder / hide / remove / ingest)."""
from __future__ import annotations

import asyncio
import shutil
import signal
import time

from aiohttp import web

from .. import app_registry, config
from ..config import APPS
from ..supervisor import APP_PROCS, ensure_started, rebuild_app_procs, stop_app
from ..proxy import _proxy_http, _proxy_ws

routes = web.RouteTableDef()


def _sync_registry() -> None:
    config.reload_apps()
    rebuild_app_procs()


async def _body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}

# Set by /api/restart before it triggers shutdown; app.main() reads it to decide
# whether to exit with the "relaunch me" code (42) instead of 0. The launcher
# (Agent Hub.vbs supervisor loop) restarts the hub only on 42.
_restart_requested = False


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
    resp = {"ok": True, "base_path": ap.cfg["base_path"], "serve": ap.cfg.get("serve", "proxy")}
    if ap.cfg.get("serve") == "direct":
        host = (request.host or "127.0.0.1").split(":")[0]
        resp["open_url"] = f"http://{host}:{ap.cfg['port']}/"
    return web.json_response(resp)


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


@routes.post("/api/restart")
async def api_restart(request: web.Request) -> web.Response:
    """Restart Agent Hub from the UI (the header ⟳ button).

    Same graceful shutdown as /api/shutdown, but sets _restart_requested so
    app.main() exits with code 42 — the signal the launcher's supervisor loop
    uses to relaunch a fresh hub. If the hub wasn't started via the launcher,
    this simply shuts it down (nothing catches the 42)."""
    global _restart_requested
    _restart_requested = True

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


# ── app registry: list / reorder / hide / wire-out / ingest ─────────────────
@routes.get("/api/apps")
async def api_apps(request: web.Request) -> web.Response:
    """The ordered manifest list for the menu (raw manifests + live `running`)."""
    out = []
    for m in app_registry.load_raw():
        aid = m.get("id")
        ap = APP_PROCS.get(aid)
        out.append({**m, "running": bool(ap and ap.running)})
    return web.json_response({"apps": out})


@routes.post("/api/apps/reorder")
async def api_apps_reorder(request: web.Request) -> web.Response:
    b = await _body(request)
    order = [str(x) for x in (b.get("order") or [])]
    app_registry.reorder(order)
    _sync_registry()
    return web.json_response({"ok": True})


@routes.post("/api/apps/{app_id}/hide")
async def api_apps_hide(request: web.Request) -> web.Response:
    app_registry.set_hidden(request.match_info["app_id"], True)
    _sync_registry()
    return web.json_response({"ok": True})


@routes.post("/api/apps/{app_id}/unhide")
async def api_apps_unhide(request: web.Request) -> web.Response:
    app_registry.set_hidden(request.match_info["app_id"], False)
    _sync_registry()
    return web.json_response({"ok": True})


@routes.delete("/api/apps/{app_id}")
async def api_apps_delete(request: web.Request) -> web.Response:
    """Wire an app out of the menu. Stops it, drops the registry entry. For an
    ingested app (`?purge=1`) also deletes its clone under hub/ingested_apps/.
    A built-in's underlying repo is never touched — restore it from
    apps.default.json (see /api/apps/{id}/restore)."""
    app_id = request.match_info["app_id"]
    ap = APP_PROCS.get(app_id)
    if ap and ap.running:
        await stop_app(ap)
    dropped = app_registry.remove(app_id)
    if dropped is None:
        raise web.HTTPNotFound()
    purged = False
    if request.query.get("purge") and str(dropped.get("cwd", "")).replace("\\", "/").find("/ingested_apps/") != -1:
        try:
            shutil.rmtree(dropped["cwd"], ignore_errors=True)
            purged = True
        except Exception:
            pass
    _sync_registry()
    return web.json_response({"ok": True, "was_builtin": bool(dropped.get("builtin")), "purged": purged})


@routes.post("/api/apps/{app_id}/restore")
async def api_apps_restore(request: web.Request) -> web.Response:
    """Re-add a removed built-in from apps.default.json."""
    m = app_registry.default_manifest(request.match_info["app_id"])
    if not m:
        raise web.HTTPNotFound(text="no built-in with that id")
    app_registry.add(m)
    _sync_registry()
    return web.json_response({"ok": True})


@routes.post("/api/apps/ingest")
async def api_apps_ingest(request: web.Request) -> web.Response:
    """Kick off an auto-ingest mission for a git URL. Returns the mission id;
    review + APPLY it on /missions to wire the app in."""
    b = await _body(request)
    url = (b.get("url") or "").strip()
    if not url:
        raise web.HTTPBadRequest(text="a git URL is required")
    from . import missions
    try:
        m = await missions.dispatch_ingest(url, name=b.get("name"), emoji=b.get("emoji"),
                                           branch=b.get("branch"))
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(m.summary())


@routes.route("*", "/app/{app_id}/{path:.*}")
async def proxy(request: web.Request) -> web.StreamResponse:
    app_id = request.match_info["app_id"]
    sub_path = request.match_info["path"]
    cfg = config.APPS.get(app_id)
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

