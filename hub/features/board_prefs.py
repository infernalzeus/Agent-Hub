"""The dashboard's saved choices (layer order, block order, which controls are hidden...), kept on the Hub so the PC and the iPad see the same.

The page keeps a fast copy in localStorage and treats this as the shared one. The Hub does not read or interpret the contents: one JSON
object, at most 64 KB, replaced whole on PUT. Never holds anything secret; the board decides what goes in.
"""
from __future__ import annotations

import json

from aiohttp import web

from ..runtime import STATE, write_json

routes = web.RouteTableDef()
FILE = STATE / "board_prefs.json"
MAX_BYTES = 64 * 1024


def read() -> dict:
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


@routes.get("/api/board/prefs")
async def api_get(request: web.Request) -> web.Response:
    return web.json_response(read())


@routes.put("/api/board/prefs")
async def api_put(request: web.Request) -> web.Response:
    raw = await request.read()
    if len(raw) > MAX_BYTES:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_BYTES, actual_size=len(raw))
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="send a JSON object")
    if not isinstance(d, dict):
        raise web.HTTPBadRequest(text="send a JSON object")
    write_json(FILE, d)
    return web.json_response({"ok": True, "bytes": len(raw)})
