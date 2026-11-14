"""The trusted folder: trusted routines are filed away so the routines list stays short.

A routine you trusted stays in the main list for 30 days, then goes into the folder by itself. You can also drag one into the folder (or press FILE AWAY) and drag it back out. Only a
trusted routine can be filed; filing changes nothing about the routine, how it runs, or what the learners take from it. The folder is kept in one small file beside the learning data.
"""
from __future__ import annotations

import json
import time

from aiohttp import web

routes = web.RouteTableDef()
AUTO_DAYS = 30


def _file():
    from ..runtime import STATE
    return STATE / "data" / "yard" / "routine_folder.json"


def _load() -> dict:
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    from ..runtime import write_json
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    write_json(f, d)


def _routines() -> "list[dict]":
    from ..features import pc_control as PC
    with PC._db() as db:
        return [dict(r) for r in db.execute("SELECT id,status,updated FROM pc_routines")]


def state(now: "float | None" = None) -> dict:
    """{"filed": [ids in the folder], "days": 30}. A routine is in the folder when you filed it, or when it has been trusted for 30 days and you did not take it out."""
    now = now or time.time()
    d = _load()
    trusted_at = {k: float(v) for k, v in (d.get("trusted_at") or {}).items()}
    filed, out, taken = set(d.get("filed") or []), set(), set(d.get("taken_out") or [])
    live = {}
    changed = False
    for r in _routines():
        live[r["id"]] = r["status"]
        if r["status"] == "trusted":
            if r["id"] not in trusted_at:                                       # first time seen as trusted: the clock starts at its last change
                trusted_at[r["id"]] = float(r.get("updated") or now)
                changed = True
            if r["id"] in filed or (r["id"] not in taken and now - trusted_at[r["id"]] > AUTO_DAYS * 86400):
                out.add(r["id"])
    for k in list(trusted_at):                                                  # a routine that is no longer trusted has no clock and is not in the folder
        if live.get(k) != "trusted":
            trusted_at.pop(k)
            filed.discard(k)
            taken.discard(k)
            changed = True
    if changed:
        _save({"filed": sorted(filed), "taken_out": sorted(taken), "trusted_at": trusted_at})
    return {"filed": sorted(out), "days": AUTO_DAYS}


def set_filed(rid: str, filed: bool) -> bool:
    row = next((r for r in _routines() if r["id"] == rid), None)
    if not row or row["status"] != "trusted":
        return False
    state()
    d = _load()
    f, t = set(d.get("filed") or []), set(d.get("taken_out") or [])
    if filed:
        f.add(rid)
        t.discard(rid)
    else:
        f.discard(rid)
        t.add(rid)                                                              # taken out by you: the 30-day rule does not put it back
    _save({**d, "filed": sorted(f), "taken_out": sorted(t)})
    return True


@routes.get("/api/yard/routine-folder")
async def api_get(request: web.Request) -> web.Response:
    return web.json_response(state())


@routes.post("/api/yard/routine-folder")
async def api_set(request: web.Request) -> web.Response:
    try:
        b = await request.json()
        rid, filed = str(b["id"]), bool(b["filed"])
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"id": routine id, "filed": true or false}')
    if not set_filed(rid, filed):
        raise web.HTTPBadRequest(text="only a trusted routine can be filed")
    return web.json_response(state())
