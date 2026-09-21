"""Locations API — read/edit the pointers in hub/locations.py from the UI (/setup).

  GET  /api/locations            every location with its value, where it came from, and a status
  PUT  /api/locations            {values: {key: value}}  validate + save (nothing is written if any value is rejected)
  POST /api/locations/validate   {key, value}
  POST /api/locations/suggest    folders that already hold several git repos
  GET  /api/fs/list?path=        folders only (the picker); no path = drives and common places
  POST /api/fs/mkdir             {path}  create one folder
Folder names are listed to any device that can reach the hub, the same trust level as the file-browser app.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from aiohttp import web

from .. import locations as LOC

routes = web.RouteTableDef()


def _view() -> dict:
    items = []
    for r in LOC.REGISTRY:
        v = LOC.get(r["key"])
        items.append({**r, "value": v, "source": LOC.source(r["key"]),
                      "status": LOC.validate(r["key"], v),
                      "sources_status": [LOC.validate_source(x) for x in v] if r["kind"] == "sources" else None})
    return {"configured": LOC.configured(), "items": items, "base": str(LOC.BASE)}


async def _body(request: web.Request) -> dict:
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _tailscale_https() -> dict:
    import json as _json
    import subprocess
    from ..config import TAILSCALE_EXE, PORT
    out = {"available": False, "url": None, "serving": False, "command": f"tailscale serve --bg {PORT}"}
    try:
        st = _json.loads(subprocess.run([TAILSCALE_EXE, "status", "--json"], capture_output=True, text=True, timeout=8).stdout or "{}")
        dns = (st.get("Self") or {}).get("DNSName", "").rstrip(".")
        if dns:
            out.update(available=True, url=f"https://{dns}", certs=bool(st.get("CertDomains")))
        sv = _json.loads(subprocess.run([TAILSCALE_EXE, "serve", "status", "--json"], capture_output=True, text=True, timeout=8).stdout or "{}")
        out["serving"] = bool(sv.get("Web") or sv.get("TCP"))
    except Exception:
        pass
    return out


@routes.get("/api/phone-https")
async def phone_https(request: web.Request) -> web.Response:
    """Browsers only allow a microphone (and reliable sound) on https or localhost; on the tailnet that means the Tailscale serve address."""
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, _tailscale_https))


@routes.get("/api/locations/state")
async def locations_state(request: web.Request) -> web.Response:
    return web.json_response({"configured": LOC.configured()})


@routes.get("/api/locations")
async def get_locations(request: web.Request) -> web.Response:
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, _view))


@routes.put("/api/locations")
async def put_locations(request: web.Request) -> web.Response:
    b = await _body(request)
    values = b.get("values")
    if not isinstance(values, dict) or not values:
        raise web.HTTPBadRequest(text="send {values: {...}}")
    errors = await asyncio.get_running_loop().run_in_executor(None, LOC.save, values)
    if errors:
        return web.json_response({"errors": errors}, status=400)
    view = await asyncio.get_running_loop().run_in_executor(None, _view)
    view["restart"] = [k for k in values if LOC._BY_KEY.get(k, {}).get("restart")]
    return web.json_response(view)


@routes.post("/api/locations/validate")
async def validate_location(request: web.Request) -> web.Response:
    b = await _body(request)
    return web.json_response(LOC.validate(str(b.get("key", "")), b.get("value")))


@routes.post("/api/locations/suggest")
async def suggest(request: web.Request) -> web.Response:
    return web.json_response({"folders": await asyncio.get_running_loop().run_in_executor(None, LOC.suggest_sources)})


def _drives() -> list[str]:
    out = []
    for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{c}:\\"
        try:
            if os.path.exists(p):
                out.append(p)
        except OSError:
            pass
    return out


def _list(path: str) -> dict:
    if not path:
        places = [str(LOC.HOME)] + [str(LOC.HOME / n) for n in ("Documents", "Desktop", "Downloads") if (LOC.HOME / n).is_dir()]
        return {"path": "", "parent": None, "dirs": [], "places": places, "drives": _drives()}
    p = Path(path)
    if not p.is_dir():
        raise web.HTTPNotFound(text="not a folder")
    dirs = []
    try:
        for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if len(dirs) >= 500:
                break
            if c.name.startswith(("$", ".")) or c.name in ("System Volume Information",):
                continue
            try:
                if c.is_dir():
                    dirs.append({"name": c.name, "git": (c / ".git").exists()})
            except OSError:
                continue
    except PermissionError:
        raise web.HTTPForbidden(text="no permission to list this folder")
    parent = str(p.parent) if p.parent != p else ""
    return {"path": str(p), "parent": parent, "dirs": dirs, "git": (p / ".git").exists()}


@routes.get("/api/fs/list")
async def fs_list(request: web.Request) -> web.Response:
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, _list, request.query.get("path", "")))


@routes.post("/api/fs/mkdir")
async def fs_mkdir(request: web.Request) -> web.Response:
    b = await _body(request)
    p = Path(str(b.get("path", "")).strip())
    if not p.is_absolute() or LOC._forbidden(p):
        raise web.HTTPBadRequest(text="pick a folder inside an existing folder")
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"path": str(p)})
