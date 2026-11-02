"""Events pushed by Claude Code (and anything else that can run a command) so the Hub knows the moment a session needs you.

`agent_sessions.py` infers state from log files, which cannot tell a permission prompt from a long command. Claude Code can run a
*hook* on its `Notification` and `Stop` events; pointing a hook at this endpoint turns the guess into a fact. The pattern is the
one ccgram uses (a hook turns a permission question into a message) and ethanplusai/jarvis uses (a session that needs a human is
announced at once). Nothing is installed by this file: `tools/claude_hook_snippet.py` prints the settings to add, and you add it.

POST /api/agent/event  {agent, session, project, event: "notification" | "stop" | "permission", message}
A notification is shown as "needs you" until the same session reports a later stop or event.
"""
from __future__ import annotations

import json
import time

from aiohttp import web

from ..runtime import STATE, write_json

routes = web.RouteTableDef()
FILE = STATE / "agent_events.json"
WAITING_FOR_S = 900
EVENTS = ("notification", "stop", "permission", "start")


def _load() -> "list[dict]":
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def record(agent: str, session: str, project: str, event: str, message: str, now: "float | None" = None) -> dict:
    if event not in EVENTS:
        raise ValueError("event must be one of " + ", ".join(EVENTS))
    row = {"agent": str(agent or "claude")[:20], "session": str(session or "")[:64], "project": str(project or "")[:80], "event": event,
           "message": " ".join(str(message or "").split())[:240], "at": now or time.time()}
    write_json(FILE, (_load() + [row])[-200:])
    return row


def waiting(now: "float | None" = None) -> "list[dict]":
    """Sessions whose latest event is a notification or permission question, not yet answered by a later event."""
    now = now or time.time()
    last: "dict[str, dict]" = {}
    for r in _load():
        last[r["agent"] + ":" + r["session"]] = r
    return [r for r in last.values() if r["event"] in ("notification", "permission") and now - r["at"] < WAITING_FOR_S]


@routes.post("/api/agent/event")
async def api_event(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    try:
        row = record(b.get("agent"), b.get("session"), b.get("project"), str(b.get("event") or ""), b.get("message"))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"ok": True, "event": row["event"]})
