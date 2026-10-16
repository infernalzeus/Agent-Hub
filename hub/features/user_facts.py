"""What the hub knows about you, because you told it.

The hub could do a great deal and knew nothing about the person it was doing it
for. Ask it the weather and it had no location; ask it to upload something and
it had no idea which account you meant; ask it to open "my notes" and it had no
notion of which folder that is. Every one of those is the same shape: a request
the hub could serve if it knew one more thing about you, and no way to acquire
that thing except by being told again every single time.

So this is the smallest honest version of that: a store of plain facts, each one
either **asked for** or **told**, with the moment it was learned. Three rules
keep it from becoming a surveillance file:

* **Nothing is inferred.** A fact gets here because you said it, in answer to a
  question or unprompted. The hub never writes down something it guessed from
  watching, and `how` records which of the two it was.
* **Everything is visible and removable.** `GET /api/facts` lists the lot and
  `DELETE /api/facts/{key}` forgets one. A memory you cannot read back or delete
  is not a feature.
* **It stays on this machine.** The file is per-machine state, excluded from the
  release payload and from git, like tokens and keys.

The pattern it exists to serve: *cannot answer → ask for the missing thing →
remember it → answer directly next time.* The asking is the part that makes it
personalisation rather than a settings page.
"""
from __future__ import annotations

import json
import re
import time

from aiohttp import web

from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "user_facts.json"
KEY_RX = re.compile(r"^[a-z][a-z0-9_]{1,38}$")

# How a fact came to be known. There is deliberately no "inferred".
HOW = ("asked", "told")

# Facts the hub knows how to ask for, with the question it would use. A request
# that needs one of these can hand the question straight to the person rather
# than failing with "I don't know".
KNOWN = {
    "location": {
        "label": "where you are",
        "question": "Whereabouts are you? A town or postcode is enough.",
        "why": "so I can answer things like the weather without asking every time",
    },
    "timezone": {
        "label": "your timezone",
        "question": "Which timezone should I use for times you give me?",
        "why": "so a schedule means the same thing to both of us",
    },
    "name": {
        "label": "what to call you",
        "question": "What should I call you?",
        "why": "so replies read like they are meant for you",
    },
    "units": {
        "label": "units",
        "question": "Celsius or Fahrenheit, and km or miles?",
        "why": "so numbers come back in the form you actually use",
    },
}


_PLACE_LEAD = __import__("re").compile(
    r"^(?:(?:i|we)\s+(?:currently\s+|now\s+|still\s+)?(?:live|am|'?m|stay|reside)\s+(?:in|at|near|around)\s+"
    r"|(?:i'?m|i am)\s+(?:from|in|at|near|based in)\s+"
    r"|(?:it'?s|it is|that'?s|that is|the one in|somewhere in|near|around|in|at|to|as)\s+"
    r"|my\s+(?:location|town|city|place)\s+(?:is|=|:)\s+)", __import__("re").I)


def clean_place(text: str) -> str:
    """A place name out of a sentence: "I currently live in Maidstone" -> "Maidstone".

    Spoken answers arrive as sentences, and a whole sentence stored as a place is
    how the weather lookup came to be searching for "I currently live in Meadstone".
    """
    t = str(text or "").strip().strip(" .!?,")
    for _ in range(4):
        n = _PLACE_LEAD.sub("", t).strip()
        if n == t:
            break
        t = n
    t = __import__("re").sub(r"\s+(?:please|thanks|thank you|now)$", "", t, flags=__import__("re").I)
    return t.strip(" .!?,")


def load() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(rows: dict) -> None:
    write_json(FILE, rows)


def get(key: str) -> "str | None":
    row = load().get(str(key).strip().lower())
    return row.get("value") if isinstance(row, dict) else None


def remember(key: str, value: str, how: str = "told", why: str = "") -> dict:
    """Write down one fact. Raises ValueError if it is not a fact-shaped thing."""
    key = str(key or "").strip().lower()
    value = str(value or "").strip()
    if not KEY_RX.match(key):
        raise ValueError("a fact's name is lowercase letters, digits and underscores")
    if not value:
        raise ValueError("a fact needs a value")
    if len(value) > 400:
        raise ValueError("that is too long to be a fact about you")
    if how not in HOW:
        raise ValueError(f"how must be one of {', '.join(HOW)}")
    rows = load()
    row = {"value": value, "how": how, "learned": time.time(),
           "why": (why or (KNOWN.get(key) or {}).get("why") or "")[:160]}
    rows[key] = row
    _save(rows)
    logger.info("user_facts: learned %s (%s)", key, how)
    return {"key": key, **row}


def forget(key: str) -> bool:
    rows = load()
    if str(key).strip().lower() not in rows:
        return False
    rows.pop(str(key).strip().lower())
    _save(rows)
    logger.info("user_facts: forgot %s", key)
    return True


def question_for(key: str) -> str:
    """What to ask to learn this fact, in words a person can answer."""
    known = KNOWN.get(str(key).strip().lower())
    if known:
        return known["question"]
    return f"What should I use for {str(key).replace('_', ' ')}?"


def missing(keys: "list[str]") -> "list[str]":
    """Which of these the hub does not know yet, in the order given."""
    have = load()
    return [k for k in keys if not (have.get(k) or {}).get("value")]


def describe() -> str:
    """One line listing what is known, for a person asking what it remembers."""
    rows = load()
    if not rows:
        return ("I don't know anything about you yet. I'll ask when something "
                "would actually need it, and you can see or delete it afterwards.")
    bits = ", ".join(f"{k.replace('_', ' ')}: {v['value']}" for k, v in sorted(rows.items())
                     if isinstance(v, dict) and v.get("value"))
    return f"I know {bits}. Say forget my <thing> to remove any of it."


# -- http ----------------------------------------------------------------------
@routes.get("/api/facts")
async def api_list(request: web.Request) -> web.Response:
    """Everything the hub has been told, and what it knows how to ask for."""
    rows = load()
    return web.json_response({
        "facts": [{"key": k, **v} for k, v in sorted(rows.items()) if isinstance(v, dict)],
        "known": KNOWN,
    })


@routes.post("/api/facts")
async def api_remember(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:
        b = {}
    try:
        return web.json_response(remember(str(b.get("key") or ""), str(b.get("value") or ""),
                                          str(b.get("how") or "told"), str(b.get("why") or "")))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.delete("/api/facts/{key}")
async def api_forget(request: web.Request) -> web.Response:
    if not forget(request.match_info["key"]):
        raise web.HTTPNotFound(text="I don't know that about you")
    return web.json_response({"ok": True})
