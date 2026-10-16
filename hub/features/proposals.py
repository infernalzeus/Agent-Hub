"""Things an automation worked out, waiting for you to say yes.

An automation can already dispatch missions and call endpoints. The question was
whether it should also be able to *create* things - save a routine it learned,
add a tile, wire a new button into the Hub. Letting it do that directly makes a
system nobody can reason about at three in the morning: you would find buttons
you did not add, doing things you did not ask for.

So it does the work and stops one step short. A proposal holds the **entire
wiring, ready to go**, and sits in a list. Nothing is wired in until you press
the button next to it; the edit beside it removes it. The automation is allowed
to be clever; only you are allowed to install.

Confidence rides along because it is what makes a list like this readable at a
glance: a routine that matched its anchors nine times out of ten is a different
proposition from one that scraped through once, and you should not have to open
each to find out.
"""
from __future__ import annotations

import json
import time
import uuid

from aiohttp import web

from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "proposals.json"

# What a proposal can turn into once you accept it.
KINDS = {
    "app_ingest": "a web app, brought in and waiting to be wired",
    "action_app": "a tile with actions on it",
    "automation": "an automation you can run or schedule",
    "routine": "a recorded routine, kept for reuse",
    "app_evidence": "what an installed app exposes, read from its own files",
}


def load() -> "list[dict]":
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(rows: "list[dict]") -> None:
    write_json(FILE, rows)


def get(pid: str) -> "dict | None":
    return next((p for p in load() if p.get("id") == pid), None)


def validate(p: dict) -> str:
    if p.get("kind") not in KINDS:
        return f"kind must be one of {', '.join(KINDS)}"
    if not str(p.get("name") or "").strip():
        return "a proposal needs a name"
    if not isinstance(p.get("wiring"), dict) or not p["wiring"]:
        return "a proposal carries the whole wiring, ready to install"
    c = p.get("confidence")
    if c is not None and not (isinstance(c, (int, float)) and 0 <= float(c) <= 1):
        return "confidence is a number between 0 and 1"
    return ""


def propose(p: dict) -> dict:
    """Record something worked out, without installing any of it."""
    why = validate(p)
    if why:
        raise ValueError(why)
    row = {
        "id": "p" + uuid.uuid4().hex[:8],
        "kind": p["kind"],
        "name": str(p["name"]).strip()[:80],
        "why": str(p.get("why") or "").strip()[:240],
        "from": str(p.get("from") or "").strip()[:60],     # the run or mission behind it
        "confidence": round(float(p["confidence"]), 2) if p.get("confidence") is not None else None,
        "wiring": p["wiring"],
        "created": time.time(),
    }
    _save(load() + [row])
    logger.info("proposals: %s proposed a %s (%s)", row["from"] or "something", row["kind"], row["name"])
    return row


def dismiss(pid: str) -> bool:
    rows = load()
    keep = [p for p in rows if p.get("id") != pid]
    if len(keep) == len(rows):
        return False
    _save(keep)
    return True


async def accept(pid: str) -> dict:
    """Install it, for real, because you asked.

    This is the only place a proposal becomes a thing. It is removed from the
    list afterwards: a proposal that has been taken up is not still pending, and
    leaving it there would invite installing it twice.
    """
    p = get(pid)
    if not p:
        raise ValueError("no such proposal")
    kind, wiring = p["kind"], p["wiring"]
    if kind == "action_app":
        from . import action_apps as AA
        made = AA.save(wiring)
    elif kind == "automation":
        from . import automations as A
        made = A.save(wiring)
    elif kind == "routine":
        # A routine is already on disk once recorded; accepting it is agreeing it
        # may be used, which is what leaving the proposal list means.
        made = dict(wiring)
    elif kind == "app_evidence":
        # Nothing is installed: accepting says the evidence may be used when routines for
        # this app are built, which is what leaving the list means.
        made = {"app": wiring.get("app"), "accepted": True}
    elif kind == "app_ingest":
        # The work of bringing the app in is done and reviewed on the board;
        # accepting here is the same APPLY, from where you were already looking.
        from . import missions as M
        mid = str(wiring.get("mission") or "")
        if mid not in M.S.m:
            dismiss(pid)
            raise ValueError("that ingest is gone - nothing to wire in")
        try:
            res = await M.apply(mid)
        except Exception as exc:
            raise ValueError(f"could not wire it in: {getattr(exc, 'text', exc)}")
        if isinstance(res, dict) and res.get("ok") is False:
            raise ValueError("could not wire it in: " + str(res.get("reason") or res.get("run_this")
                                                           or "see the missions board"))
        made = {"mission": mid, "applied": True}
    else:
        raise ValueError(f"cannot install a {kind}")
    dismiss(pid)
    logger.info("proposals: installed %s (%s)", p["name"], kind)
    return {"installed": kind, "what": made}


# -- http ----------------------------------------------------------------------
@routes.get("/api/proposals")
async def api_list(request: web.Request) -> web.Response:
    """Everything worked out and waiting for a yes."""
    return web.json_response({"proposals": sorted(load(), key=lambda p: -p.get("created", 0)),
                              "kinds": KINDS})


@routes.post("/api/proposals")
async def api_propose(request: web.Request) -> web.Response:
    try:
        return web.json_response(propose(await request.json()))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.post("/api/proposals/{id}/accept")
async def api_accept(request: web.Request) -> web.Response:
    try:
        return web.json_response(await accept(request.match_info["id"]))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.delete("/api/proposals/{id}")
async def api_dismiss(request: web.Request) -> web.Response:
    if not dismiss(request.match_info["id"]):
        raise web.HTTPNotFound(text="no such proposal")
    return web.json_response({"ok": True})


# -- an ingest that finishes offers itself ---------------------------------------
# Only a recording ever produced a proposal, so the "ready to be wired in" list
# was empty for every other way of bringing something in - and it said so,
# truthfully. Reaching review is the moment an ingested app is ready to wire in.
_DONE = ("applied", "discarded", "failed", "timed_out", "stopped", "archived", "orphaned")


def on_mission(ev: dict) -> None:
    pay = ev.get("payload") or {}
    if pay.get("kind") != "ingest-app" or not pay.get("mission"):
        return
    mid, status = str(pay["mission"]), str(pay.get("status") or "")
    mine = [p for p in load() if p.get("kind") == "app_ingest" and p.get("from") == mid]
    if status == "awaiting_review" and not mine:
        propose({"kind": "app_ingest", "name": pay.get("project_name") or pay.get("project") or "an app",
                 "why": "brought in and checked - ADD wires it into the hub", "from": mid,
                 "wiring": {"mission": mid}})
    elif status in _DONE:
        for p in mine:
            dismiss(p["id"])


def setup(app) -> None:
    from .. import events
    events.subscribe("mission.finished", on_mission)
