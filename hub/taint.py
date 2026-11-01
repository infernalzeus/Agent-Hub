"""Do not let text read from outside decide what the Hub does next.

An agent that has just read a web page or a lookup answer can be told, by that text, to press something. The Hub's own
never-press list stops the worst presses; this closes the door before it: after an *integration-token* caller has asked
the Hub something that fetches outside content (`/api/voice/chat`), the same caller may not use the acting endpoints
(`/api/pc/steps`, running a routine) for TAINT_S seconds. A person at the Hub itself is never gated: their request carries
the Hub's own origin, not a token, and doing something with their own hands clears it.

Pattern: the "taint gate" of ethanplusai/jarvis (read for ideas only; no code taken, its licence is personal use).
"""
from __future__ import annotations

import re
import time

from aiohttp import web

TAINT_S = 90
_READS = ("/api/voice/chat",)
_ACTS = re.compile(r"^/api/pc/(steps|routines/[^/]+/run|machine/[^/]+/run)$")
_until: "dict[str, float]" = {}


def _who(request: web.Request) -> str:
    tok = request.get("integration")
    return str(getattr(tok, "id", None) or (tok.get("id") if isinstance(tok, dict) else None) or tok or "")


def mark(who: str, now: "float | None" = None) -> None:
    _until[who] = (now or time.time()) + TAINT_S


def clear(who: str) -> None:
    _until.pop(who, None)


def blocked(who: str, now: "float | None" = None) -> int:
    """Seconds left on the gate for this caller, 0 if open."""
    left = _until.get(who, 0) - (now or time.time())
    return int(left) + 1 if left > 0 else 0


def guard(request: web.Request) -> None:
    """Called for token callers only. Raises 403 on an acting endpoint while the gate is closed."""
    who = _who(request)
    if not who:
        return
    if request.path in _READS:
        mark(who)
        return
    if _ACTS.match(request.path):
        left = blocked(who)
        if left:
            raise web.HTTPForbidden(text=f"Held for {left} s: this caller just read outside content, and text from outside must not decide "
                                         "what gets pressed. Ask the person at the Hub, or wait.")
