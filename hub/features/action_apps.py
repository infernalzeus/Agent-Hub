"""Tiles for things that are not web apps.

An app in the registry is a web server: a command, a port, a health path, and a
proxy in front of it. That is the right shape for Movie Clipper, which you built,
and the wrong shape for Apple Music, which has a window and perhaps an MCP verb.
Both were wearing the word "app".

So this is the other kind. An action app is a name, an icon, and a set of verbs
from a connected MCP server. Opening it shows those verbs as buttons; pressing
one runs it. Nothing is spawned, nothing is proxied, and `config.APPS` is left
alone - the supervisor only ever sees things it can actually start.

Two rules that came from how you want this to feel:

* **Learning something does not create a tile.** Recording a routine, or
  ingesting a repo, leaves the thing *listed and reachable* - it does not put a
  square on your home screen. A tile is something you chose to make.
* **The verbs come from the server, the look comes from here.** The tool list is
  whatever the MCP server reports; the buttons are drawn in the Hub's own theme
  rather than whatever the server would like them to be.
"""
from __future__ import annotations

import json
import re
import uuid

from aiohttp import web

from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "action_apps.json"
ID_RX = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")


def load() -> "list[dict]":
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(rows: "list[dict]") -> None:
    write_json(FILE, rows)


def get(aid: str) -> "dict | None":
    return next((a for a in load() if a.get("id") == aid), None)


def verb(t: Any) -> dict:
    """One action on a tile: its name, and the values pressing it needs.

    Most MCP verbs take arguments, so a tile whose buttons send none can only
    drive the few that take nothing. `needs` is the same shape an automation
    step uses - describe what is missing and let the person fill it in - so one
    idea covers both, and a verb that needs nothing still just works.
    """
    if isinstance(t, str):
        return {"name": t.strip(), "needs": []}
    needs = []
    routine = str(t.get("routine") or "").strip()
    for raw in (t.get("needs") or []):
        if isinstance(raw, str) and raw.strip():
            needs.append({"key": raw.strip(), "label": raw.strip(), "why": ""})
        elif isinstance(raw, dict) and str(raw.get("key") or "").strip():
            needs.append({"key": str(raw["key"]).strip(),
                          "label": str(raw.get("label") or raw["key"]).strip(),
                          "why": str(raw.get("why") or "").strip()})
    out = {"name": str(t.get("name") or "").strip(), "needs": needs[:6]}
    if routine:
        # A button can press something the hub was taught, not only an MCP verb.
        # This is what lets a recorded routine become a button on a tile: the
        # recording is the capability, the tile is just where you press it.
        out["routine"] = routine
    return out


def names(app: dict) -> "list[str]":
    """Just the verb names - what a tile is permitted to run."""
    return [v["name"] if isinstance(v, dict) else str(v) for v in (app.get("tools") or [])]


def validate(a: dict) -> str:
    """Why this cannot be saved, or "" if it can."""
    if not str(a.get("name") or "").strip():
        return "give it a name"
    tools = a.get("tools")
    backed = isinstance(tools, list) and tools and all(
        isinstance(t, dict) and str(t.get("routine") or "").strip() for t in tools)
    if not str(a.get("server") or "").strip() and not backed:
        return "pick the MCP server its actions come from, or give every action a routine"
    if not isinstance(tools, list) or not tools:
        return "pick at least one action"
    for t in tools:
        if isinstance(t, str):
            if not t.strip():
                return "an action cannot be blank"
        elif isinstance(t, dict):
            if not str(t.get("name") or "").strip():
                return "an action cannot be blank"
            if not isinstance(t.get("needs") or [], list):
                return "an action's needs are a list"
        else:
            return "an action is a name, or a name with the values it needs"
    if len(tools) > 24:
        return "that is more actions than a panel can usefully hold"
    return ""


def save(a: dict) -> dict:
    why = validate(a)
    if why:
        raise ValueError(why)
    rows = load()
    aid = str(a.get("id") or "").strip().lower()
    if not aid or not ID_RX.match(aid):
        aid = re.sub(r"[^a-z0-9]+", "-", str(a["name"]).lower()).strip("-")[:38] or ("app" + uuid.uuid4().hex[:6])
    row = {
        "id": aid,
        "name": str(a["name"]).strip(),
        "emoji": str(a.get("emoji") or "\U0001F5A5"),
        "server": str(a["server"]).strip(),
        "tools": [verb(t) for t in a["tools"]][:24],
        "kind": "actions",
    }
    _save([r for r in rows if r.get("id") != aid] + [row])
    logger.info("action_apps: saved %s (%d action(s) from %s)", aid, len(row["tools"]), row["server"])
    return row


def delete(aid: str) -> bool:
    rows = load()
    keep = [r for r in rows if r.get("id") != aid]
    if len(keep) == len(rows):
        return False
    _save(keep)
    return True


# -- http ----------------------------------------------------------------------
# Listing a server's verbs starts it, asks, and stops it - a whole subprocess.
# The menu polls this route every few seconds, so without a cache the hub spawns
# one of those on every poll, forever. A server's tool list changes when the
# server is reinstalled, which is not something that happens every minute.
_TOOLS: "dict[str, tuple[float, list]]" = {}
_TOOLS_TTL = 600.0


async def tools_of(name: str) -> list:
    """The verbs a server offers, probed at most once every few minutes."""
    import time as _t
    from . import mcp as M
    hit = _TOOLS.get(name)
    if hit and (_t.monotonic() - hit[0]) < _TOOLS_TTL:
        return hit[1]
    try:
        got = (await M.probe(name)).get("tools") or []
    except Exception as exc:
        logger.info("action_apps: could not list %s: %s", name, exc)
        got = hit[1] if hit else []            # keep the last good answer
    _TOOLS[name] = (_t.monotonic(), got)
    return got


_REFRESHING: "set[str]" = set()


def tools_cached(name: str) -> list:
    """Answer at once from the cache; if it is missing or stale, refresh it in the background.

    The listing used to await the probe, so the first request after a start (and after every
    TTL expiry) held the whole menu - and anything waiting on it - for several seconds.
    """
    import asyncio
    import time as _t
    hit = _TOOLS.get(name)
    fresh = bool(hit) and (_t.monotonic() - hit[0]) < _TOOLS_TTL
    if not fresh and name not in _REFRESHING:
        _REFRESHING.add(name)

        async def _bg() -> None:
            try:
                await tools_of(name)
            except Exception as exc:  # tools_of already degrades; never let a background task raise
                logger.info("action_apps: background probe of %s failed: %s", name, exc)
            finally:
                _REFRESHING.discard(name)
        asyncio.get_running_loop().create_task(_bg())
    return hit[1] if hit else []


@routes.get("/api/action-apps")
async def api_list(request: web.Request) -> web.Response:
    """The tiles, and the servers and verbs one could be built from."""
    from . import mcp as M
    servers = []
    for s in M.servers():
        if not s.get("installed") or not s.get("enabled", True):
            continue
        tools = s.get("tools") or []
        if not tools:
            tools = tools_cached(s["name"])
        servers.append({
            "name": s["name"],
            "excluded": s.get("excluded_tools") or [],
            "tools": [{"name": t if isinstance(t, str) else t.get("name", ""),
                       "what": "" if isinstance(t, str) else (t.get("description") or "")[:140]}
                      for t in tools],
        })
    return web.json_response({"apps": load(), "servers": servers})


@routes.post("/api/action-apps")
async def api_save(request: web.Request) -> web.Response:
    try:
        return web.json_response(save(await request.json()))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.delete("/api/action-apps/{id}")
async def api_delete(request: web.Request) -> web.Response:
    if not delete(request.match_info["id"]):
        raise web.HTTPNotFound(text="no such tile")
    return web.json_response({"ok": True})


@routes.post("/api/action-apps/{id}/run")
async def api_run(request: web.Request) -> web.Response:
    """Press one of the buttons.

    The tool has to be one the tile was built with: a tile is a deliberate,
    named set of verbs, not a doorway to everything its server can do.
    """
    app = get(request.match_info["id"])
    if not app:
        raise web.HTTPNotFound(text="no such tile")
    try:
        b = await request.json()
    except Exception:
        b = {}
    tool = str(b.get("tool") or "").strip()
    if tool not in names(app):
        raise web.HTTPBadRequest(text=f"{tool!r} is not one of this tile's actions")
    spec = next((v for v in app["tools"] if (v.get("name") if isinstance(v, dict) else v) == tool), {})
    wanted = (spec.get("needs") or []) if isinstance(spec, dict) else []
    supplied = {str(k): v for k, v in (b.get("args") or {}).items()}
    short = [n["label"] for n in wanted if not str(supplied.get(n["key"], "")).strip()]
    if short:
        # Said rather than guessed: a verb run with a missing argument does
        # something unpredictable, which on a desktop is the wrong kind of surprise.
        raise web.HTTPBadRequest(text="needs " + ", ".join(short))
    args = {n["key"]: supplied[n["key"]] for n in wanted} if wanted else supplied
    rid = str(spec.get("routine") or "").strip() if isinstance(spec, dict) else ""
    if rid:
        from . import pc_control as PC
        try:
            out = await PC.run_routine(rid, request=f"tile {app['id']}:{tool}")
        except KeyError:
            raise web.HTTPNotFound(text="the routine behind that button is gone")
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
        logger.info("action_apps: %s ran routine %s (%s)", app["id"], rid, tool)
        return web.json_response({"ok": bool(out.get("ok")), "text": [out.get("say", "")]})
    if not app.get("server"):
        raise web.HTTPBadRequest(text=f"{tool!r} has no routine and this tile has no MCP server")
    from . import mcp as M
    try:
        out = await M.call_tool(app["server"], tool, args)
    except KeyError:
        raise web.HTTPBadRequest(text=f"{app['server']} is not configured any more")
    except PermissionError as exc:
        raise web.HTTPForbidden(text=str(exc))
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"{tool} did not answer: {str(exc)[:160]}")
    logger.info("action_apps: %s ran %s.%s", app["id"], app["server"], tool)
    return web.json_response({"ok": not out.get("error"), "text": out.get("text") or []})
