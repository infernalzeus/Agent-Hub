"""What the Hub can be asked to do, read off its own routing table.

An automation step and an agent both need to know what the Hub offers. The easy
way to give them that is a hand-written list of endpoints - and a hand-written
list is wrong the first time somebody adds a route and forgets it, with nothing
to notice. So this is **generated**: it walks the application's real routes and
keeps the ones an automation is allowed to use.

Two consequences worth stating plainly:

* **New endpoints appear by themselves** if their prefix is already allowed, and
  never appear if it is not. There is no second list to maintain.
* **The allowlist is about intent, not safety.** The security boundary is still
  `request_security.py`; this decides what is *sensible* to automate, so that an
  automation cannot wander into `/api/shutdown` because an agent read it in a
  route dump.

Calls go out over loopback with a short-lived scoped token rather than straight
into the handler. That costs one local round trip and buys the real middleware -
the same CSRF and token path every other caller takes - instead of a private
back door that would drift from it.
"""
from __future__ import annotations

import json
import time
from typing import Any

import aiohttp
from aiohttp import web

from .. import integration_tokens as IT
from ..config import logger

routes = web.RouteTableDef()

# Prefix -> what this family of endpoints is for, in the words a person would use.
# Adding a prefix here is a deliberate act: it says "an automation may do this".
ALLOWED: "dict[str, str]" = {
    "/api/youtube-dl/":  "download video or audio",
    "/api/youtube/":     "list upload channels, and upload a finished video",
    "/api/missions":     "dispatch, inspect, apply or discard a mission",
    "/api/apps":         "see which fronted apps exist",
    "/api/start/":       "start a fronted app",
    "/api/status":       "what is running right now",
    "/api/graph":        "the project graph and repository status",
    "/api/locations":    "where the Hub reads and writes",
    "/api/pc/machine/":  "replay something you recorded",
    "/api/automations":  "the automations themselves",
}

# Never, whatever the prefix above would otherwise allow. These end the session
# the automation is running in, or hand out credentials.
DENIED = (
    "/api/shutdown", "/api/restart", "/api/power",
    "/api/llm/keys", "/api/integrations",
)

# Endpoints whose effects are hard to take back - they leave this machine, write
# into a real repository, destroy work, or move the mouse on your actual desktop.
# An automation may still call them, but a step that does should carry
# `gate: true`; the UI reads this when you build one, so you are told rather than
# finding out afterwards. Matched as substrings, because the real paths carry an
# `{id}` in the middle.
CONSEQUENTIAL = (
    "/api/youtube/upload",       # publishes to a real channel
    "/apply",                    # merges a mission's work into the project
    "/discard", "/forget",       # throws work away
    "/api/pc/machine/run",       # drives the real desktop
    "/api/apps/ingest",          # adds a new app and dispatches a mission for it
)

_TOKEN_NAME = "automations (internal)"
_cached: "dict[str, Any]" = {}


def refuse(method: str, path: str) -> str:
    """Why an automation may not call this, or "" if it may."""
    method = (method or "GET").upper()
    if any(path.startswith(d) for d in DENIED):
        return f"{path} is not available to automations"
    if not any(path.startswith(p) for p in ALLOWED):
        return (f"{path} is not in the automatable set - add its prefix to "
                f"capabilities.ALLOWED if it should be")
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return f"{method} is not supported"
    return ""


def consequential(path: str, method: str = "POST") -> bool:
    """Is this hard to take back?

    A GET never is: reading cannot publish, merge or delete. Saying so here keeps
    a listing endpoint from being marked just because it shares a prefix with the
    thing that acts.
    """
    if (method or "POST").upper() == "GET":
        return False
    return any(c in path for c in CONSEQUENTIAL)


def inventory(app: "web.Application | None" = None) -> "list[dict]":
    """Every automatable endpoint, generated from the routes that actually exist."""
    app = app or _cached.get("app")
    if app is None:
        return []
    seen, out = set(), []
    for res in app.router.resources():
        path = getattr(res, "canonical", "") or ""
        for route in res:
            method = route.method
            if method in ("HEAD", "OPTIONS") or refuse(method, path):
                continue
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            doc = (route.handler.__doc__ or "").strip().split("\n")[0]
            out.append({
                "method": method, "path": path,
                "what": doc or _family(path),
                "consequential": consequential(path, method),
            })
    return sorted(out, key=lambda r: (r["path"], r["method"]))


def _family(path: str) -> str:
    for prefix, what in ALLOWED.items():
        if path.startswith(prefix):
            return what
    return ""


def remember_app(app: web.Application) -> None:
    """Called once at startup so the inventory can be built without a request."""
    _cached["app"] = app


# -- calling -------------------------------------------------------------------
def _token() -> str:
    """A scoped token for the Hub's own automations, minted once and reused.

    Scoped to exactly the allowed prefixes, so if this secret ever escaped it
    would still not reach the power menu or the provider keys.
    """
    secret = _cached.get("secret")
    if secret:
        return secret
    for row in IT.listing():
        if row.get("name") == _TOKEN_NAME:
            IT.revoke(row["id"])          # the secret is unrecoverable; re-mint
    _row, secret = IT.create(_TOKEN_NAME, sorted(ALLOWED))
    _cached["secret"] = secret
    logger.info("capabilities: minted the automations token")   # never the secret
    return secret


async def call(method: str, path: str, body: "dict | None" = None) -> str:
    """Make the call and return a short line describing what came back."""
    why = refuse(method, path)
    if why:
        raise PermissionError(why)
    from ..config import HOST, PORT
    url = f"http://{HOST or '127.0.0.1'}:{PORT}{path}"
    headers = {"X-Agent-Hub-Token": _token()}
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.request(method, url, json=(body or None), headers=headers) as r:
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"{method} {path} -> {r.status}: {text[:200]}")
            return _summarise(method, path, text)


def _summarise(method: str, path: str, text: str) -> str:
    """One readable line for the run record - never the whole payload."""
    try:
        data = json.loads(text)
    except ValueError:
        return f"{method} {path} -> ok"
    if isinstance(data, list):
        return f"{method} {path} -> {len(data)} item(s)"
    if isinstance(data, dict):
        for k in ("id", "mission", "status", "ok", "path"):
            if k in data:
                return f"{method} {path} -> {k}={data[k]}"
        return f"{method} {path} -> ok"
    return f"{method} {path} -> ok"


@routes.get("/api/capabilities")
async def api_capabilities(request: web.Request) -> web.Response:
    """Everything an automation or an agent may ask the Hub to do."""
    return web.json_response({
        "generated": time.time(),
        "endpoints": inventory(request.app),
        "note": "Generated from the Hub's own routes. A step marked consequential "
                "should carry gate:true so it waits for a person.",
    })
