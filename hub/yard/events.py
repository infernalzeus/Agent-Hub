"""What is happening inside a yard session, as a short stream the FLOW tab animates.

Each event names a node of the learning canvas (see flow.py), the arrow it travels along, a plain sentence, and sometimes a number (how much a set of weights
changed, how often it succeeded). The yard writes them as it works; the panel polls `/api/yard/events?since=N` about twice a second while a session is open.
Only the newest 800 are kept, in memory; nothing is written to disk and nothing here can slow training by more than a microsecond or two.
"""
from __future__ import annotations

import collections
import threading
import time

from aiohttp import web

routes = web.RouteTableDef()
_BUF: "collections.deque[dict]" = collections.deque(maxlen=800)
_LOCK = threading.Lock()
_N = [0]


def emit(node: str, kind: str, text: str = "", value: "float | None" = None, edge: "str | None" = None, **extra) -> int:
    """node: a canvas node id. kind: what happened (episode, update, improved, fitness, saved ...). edge: "from>to" when information travels along an arrow."""
    with _LOCK:
        _N[0] += 1
        _BUF.append({"n": _N[0], "t": round(time.time(), 3), "node": node, "kind": kind, "text": text[:200], "value": None if value is None else round(float(value), 5), "edge": edge, **extra})
        return _N[0]


def since(n: int = 0, limit: int = 200) -> "list[dict]":
    with _LOCK:
        return [e for e in _BUF if e["n"] > n][-limit:]


def last() -> int:
    return _N[0]


def clear() -> None:
    with _LOCK:
        _BUF.clear()


@routes.get("/api/yard/events")
async def api_events(request: web.Request) -> web.Response:
    try:
        n = int(request.query.get("since", "0"))
    except ValueError:
        n = 0
    from . import practice as P
    return web.json_response({"events": since(n), "last": last(), "running": bool(P.CONTROL.get("running")), "phase": P.CONTROL.get("phase", ""),
                              "done": P.CONTROL.get("done", 0), "total": P.CONTROL.get("total", 0)})
