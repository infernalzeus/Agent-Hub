"""Things that happened, so one part of the Hub can react to another.

Automations need to start when something finishes — a render completes, a
mission reaches review, a file lands in the inbox — and the alternative to this
is every feature polling every other one.

Deliberately small:

* **In-process only.** Subscribers are Python callables in this one process.
  Nothing is queued to disk and nothing survives a restart, because an event is
  a notification that something *just* happened; a missed one must never leave
  an automation half-run. Durable state belongs to the automation's own run
  record, not here.

* **A subscriber cannot break the publisher.** Callbacks run inside a task and
  their exceptions are logged, never raised into whatever was saving a mission.
  Publishing is fire-and-forget by design.

* **A short tail is kept** so a person opening the automations page can see what
  the Hub has been emitting and build a trigger against a real event name,
  rather than guessing at one from documentation.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable

from .config import logger

# What the Hub emits. Listed here so a trigger can be chosen from a known set
# rather than a typed string that silently never fires.
KINDS = {
    "mission.finished":   "a mission reached a terminal status",
    "mission.needs_you":  "a mission is waiting for a reply, a plan or a review",
    "download.finished":  "a YouTube download completed",
    "upload.finished":    "a YouTube upload completed",
    "inbox.file":         "a file arrived in the phone inbox",
    "automation.finished": "an automation run ended",
}

_subs: "dict[str, list[Callable]]" = {}
_recent: "deque[dict]" = deque(maxlen=50)


def subscribe(kind: str, cb: Callable[[dict], Any]) -> Callable[[], None]:
    """Call `cb(event)` whenever `kind` is published. Returns an unsubscribe."""
    _subs.setdefault(kind, []).append(cb)

    def off() -> None:
        try:
            _subs.get(kind, []).remove(cb)
        except ValueError:
            pass
    return off


def recent() -> list[dict]:
    """The last few events, newest first — what the UI shows."""
    return list(reversed(_recent))


def publish(kind: str, payload: "dict | None" = None) -> None:
    """Announce that `kind` happened. Never raises, never blocks the caller."""
    ev = {"kind": kind, "at": time.time(), "payload": dict(payload or {})}
    _recent.append(ev)
    subs = list(_subs.get(kind, []))
    if not subs:
        return
    for cb in subs:
        try:
            r = cb(ev)
            if asyncio.iscoroutine(r):
                # Fire-and-forget: a slow automation must not hold up the save
                # that triggered it. Needs a running loop; without one (a sync
                # test, a startup path) the coroutine is closed rather than left
                # pending, which would warn at exit.
                try:
                    asyncio.get_running_loop().create_task(_guard(kind, r))
                except RuntimeError:
                    r.close()
        except Exception:
            logger.exception("events: subscriber for %s failed", kind)


async def _guard(kind: str, coro) -> None:
    try:
        await coro
    except Exception:
        logger.exception("events: async subscriber for %s failed", kind)
