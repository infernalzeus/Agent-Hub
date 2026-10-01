"""Deciding what kind of thing an ask is, from evidence rather than from a guess.

"Open Apple Music" is one call. "Open Apple Music every morning" is the same call
with a clock on it. Neither is an automation, and the mistake this exists to
prevent is letting **repetition promote an ask** into something heavier than it
is - a saved multi-step automation, or a request to record a routine for
something that had a command all along.

Two independent axes:

* **What it takes to do once** - call, routine, or automation. Determined by
  looking: does a capability exist for it? This is the scout's question, and the
  Hub can answer part of it without an agent at all, because
  `capabilities.inventory()` is generated from its own routes.
* **When it runs** - now, on a clock, or when something happens. This is never
  inferred. It comes from the person, because nothing about an ask reveals it.

Climbing axis 1 happens only when the step below genuinely cannot do the job.
Repetition never climbs it.
"""
from __future__ import annotations

import re

from aiohttp import web

from ..config import logger

routes = web.RouteTableDef()

# A trigger is a property of an ask, not a kind of ask. Spotting one tells us
# nothing about how hard the work is - only about when it should happen.
_EVERY = re.compile(
    r"\b(every|each|daily|nightly|weekly|monthly|hourly)\b"
    r"|\bevery\s+(day|morning|night|week|month)\b"
    r"|\beach\s+(day|morning|night)\b", re.I)
_AT = re.compile(r"\b(?:at|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
_WHEN = re.compile(r"\b(when|whenever|after|once)\b\s+(?!you\b|i\b)", re.I)


def read_trigger(ask: str) -> dict:
    """What the words say about *when*, and nothing about what kind of work it is.

    Deliberately narrow: it reports what it found and how sure it is, so the
    caller can confirm rather than assume. A phrase this misreads costs one
    question; a phrase it over-reads could schedule something nobody asked to
    repeat.
    """
    text = str(ask or "")
    every = _EVERY.search(text)
    when = _WHEN.search(text)
    if every:
        at = _AT.search(text)
        hour = None
        if at:
            hour = int(at.group(1)) % 12
            if (at.group(3) or "").lower() == "pm":
                hour += 12
            hour = f"{hour:02d}:{at.group(2) or '00'}"
        word = every.group(0).lower()
        period = ("weekly" if "week" in word else
                  "monthly" if "month" in word else "daily")
        return {"kind": "schedule", "every": period, "at": hour or "09:00",
                "because": every.group(0), "sure": bool(at)}
    if when:
        return {"kind": "event", "because": when.group(0), "sure": False}
    return {"kind": "manual", "because": "", "sure": True}


def shape(steps: int, verdict: str) -> str:
    """Call, routine or automation - from the evidence, never from the wording.

    `steps` is how many distinct actions doing it ONCE takes, and `verdict` is
    what the scout found the target actually exposes.
    """
    if verdict == "gui":
        # No machine interface: one step still needs teaching once.
        return "routine" if steps <= 1 else "automation"
    if verdict == "absent":
        return "blocked"
    return "call" if steps <= 1 else "automation"


def classify(ask: str, verdict: str = "", steps: int = 1) -> dict:
    """Put the two axes together, and say what is still unknown.

    `needs_scout` is the honest part: without a verdict the kind cannot be
    decided by looking at the words, so this refuses to decide rather than
    guessing from phrasing.
    """
    trigger = read_trigger(ask)
    if not verdict:
        return {"ask": ask, "trigger": trigger, "needs_scout": True,
                "why": "what this takes depends on what the target exposes, "
                       "which has not been checked yet"}
    kind = shape(int(steps or 1), verdict)
    out = {"ask": ask, "trigger": trigger, "verdict": verdict, "steps": int(steps or 1),
           "kind": kind, "needs_scout": False}
    if kind == "call":
        out["plan"] = ("run it once" if trigger["kind"] == "manual"
                       else f"one call, {trigger['kind']}")
    elif kind == "routine":
        out["plan"] = "record it once, then it can be replayed or triggered"
    elif kind == "automation":
        out["plan"] = f"{steps} steps in order"
    else:
        out["plan"] = "nothing on this machine can do it yet"
    # The thing the rule exists to prevent, said out loud where it can be seen.
    out["note"] = ("repeating does not make this bigger than one call"
                   if kind == "call" and trigger["kind"] != "manual" else "")
    return out


@routes.post("/api/route")
async def api_route(request: web.Request) -> web.Response:
    """Say what kind of thing an ask is. Decides nothing on its own.

    With no `verdict` it reports `needs_scout` rather than guessing - the Hub
    does not know what a target exposes until something has looked.
    """
    try:
        b = await request.json()
    except Exception:
        b = {}
    ask = str(b.get("ask") or "").strip()
    if not ask:
        raise web.HTTPBadRequest(text="say what you want done")
    got = classify(ask, str(b.get("verdict") or ""), b.get("steps") or 1)
    logger.info("routing: %r -> %s", ask[:60], got.get("kind") or "needs scout")
    return web.json_response(got)
