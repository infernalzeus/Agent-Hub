"""Finding out how something can be driven, without asking a model to do it.

The first version of this was the scout agent's whole job: call the capability
list, call the MCP listing, look along PATH, try an HTTP port, then decide and
emit a structured verdict. It never finished once on a free model, and that was
the design's fault rather than the model's. Five investigative steps and a
structured answer is exactly the shape a small model fails at.

Every one of those steps is a **lookup the Hub can do itself**. So it does. What
is left for a model is the one thing code cannot do: deciding whether the words a
person used mean the thing that was found. Often even that is unambiguous, and
then no model is involved at all.

The rule this follows: **an agent must not fail for want of a better model.**
Where a step is deterministic, it belongs in code; the model is for judgement,
and it should be handed as little of it as possible.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from aiohttp import web

from ..config import logger

routes = web.RouteTableDef()

# Folders a desktop program is likely to be in, beyond PATH. Checked only for a
# file name; nothing is executed.
_APP_DIRS = [
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    os.environ.get("LOCALAPPDATA", ""),
    "/Applications", "/usr/bin", "/usr/local/bin",
]

# Words that say what to DO, never what to do it to. They are rare enough in a
# list of program names to look identifying, which is how "take a screenshot"
# ended up keyed on "take" and matched nothing.
_STOP = {
    "the", "a", "an", "my", "me", "some", "any", "that", "this", "it",
    "on", "in", "to", "for", "of", "with", "from", "at", "by", "and", "or",
    "open", "start", "launch", "run", "use", "please", "app", "application",
    "program", "software", "thing", "something",
    "take", "make", "get", "give", "show", "tell", "find", "let", "put",
    "do", "does", "did", "is", "are", "was", "has", "have", "can", "could",
    "would", "should", "want", "need", "try", "go", "come", "then",
}


def words(text: str) -> "list[str]":
    """The meaningful words of an ask, for matching against what exists."""
    return [w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if w not in _STOP and len(w) > 1]


def key_term(terms: "list[str]", corpus: "list[str]") -> str:
    """The word that actually identifies the thing, judged against what exists.

    "VLC media player" shares `media` and `player` with half the programs on a
    Windows box; `vlc` is what names it. Picking the longest word gets this
    backwards - `player` is longer than `vlc` - so the identifying word is the
    one that appears in the FEWEST candidates here. A word in none of them is
    the most identifying of all, and the correct answer is then "no match",
    which is how VLC-not-installed should read.
    """
    if not terms:
        return ""
    low = [c.lower() for c in corpus]

    def rank(t: str):
        here = [c for c in low if t in c]
        # Ties are common on a small corpus, so the second signal is how much of
        # a name the word actually is: `vlc` is all of "VLC", while `player` is
        # a third of "Windows Media Player". The word that nearly IS the name is
        # the one that identifies it.
        cover = max((len(t) / len(c) for c in here), default=1.0)
        return (len(here), -cover, -len(t))

    return min(terms, key=rank)


def _score(terms: "list[str]", key: str, haystack: str) -> int:
    """How well this candidate matches, or 0 without the identifying word."""
    h = (haystack or "").lower()
    if key and key not in h:
        return 0
    return sum(1 for t in terms if t in h)


# -- the four lookups ----------------------------------------------------------
def _hub_candidates(app) -> "list[dict]":
    from . import capabilities as C
    return [{"kind": "hub", "text": e["path"] + " " + (e.get("what") or ""),
             "method": e["method"], "path": e["path"], "what": e.get("what", "")}
            for e in C.inventory(app)]


async def _mcp_candidates() -> "list[dict]":
    """Verbs a connected MCP server exposes. Listing a server's tools starts it
    briefly and stops it again - nothing is clicked, typed or opened."""
    from . import mcp as M
    out = []
    try:
        for srv in M.servers():
            if not srv.get("installed"):
                continue
            tools = srv.get("tools") or []
            if not tools:
                try:
                    tools = (await M.probe(srv["name"])).get("tools") or []
                except Exception as exc:
                    logger.info("probe: could not list %s tools: %s", srv.get("name"), exc)
                    continue
            for t in tools:
                name = t if isinstance(t, str) else (t.get("name") or "")
                desc = "" if isinstance(t, str) else (t.get("description") or "")
                out.append({"kind": "mcp", "text": f"{name} {desc}",
                            "server": srv["name"], "tool": name, "what": desc[:120]})
    except Exception as exc:
        logger.info("probe: MCP lookup failed: %s", exc)
    return out


def _cli_candidates(terms) -> "list[dict]":
    """A command on PATH, or a program file where programs live. Name only;
    nothing is executed."""
    out = []
    for t in terms:
        found = shutil.which(t)
        if found:
            out.append({"kind": "cli", "text": t, "command": t, "at": found})
    for base in [d for d in _APP_DIRS if d and Path(d).is_dir()]:
        try:
            for child in Path(base).iterdir():
                out.append({"kind": "cli", "text": child.name,
                            "command": child.name, "at": str(child)})
        except OSError:
            continue
    return out


def _decide(found: dict) -> "tuple[str, bool, str]":
    """(verdict, confident, why) from the evidence alone.

    Order is the rule from the other document: take the highest thing that can
    actually do it. `confident` is False when a person still has to agree that
    what was found is what they meant - that is the only part worth a model.
    """
    if found["hub"]:
        top = found["hub"][0]
        return "hub", top["score"] >= 2, f"{top['method']} {top['path']}"
    if found["mcp"]:
        top = found["mcp"][0]
        return "mcp", top["score"] >= 2, f"{top['server']}.{top['tool']}"
    if found["cli"]:
        top = found["cli"][0]
        return "cli", top["score"] >= 2, top["at"]
    return "gui", False, "nothing with an interface was found; it may still have a window"


async def look(target: str, app=None) -> dict:
    """Everything known about how `target` can be driven. No model involved."""
    terms = words(target)
    cands = _hub_candidates(app) + await _mcp_candidates() + _cli_candidates(terms)
    key = key_term(terms, [c["text"] for c in cands])

    found = {"hub": [], "mcp": [], "cli": []}
    for c in cands:
        n = _score(terms, key, c["text"])
        if n:
            found[c["kind"]].append({**{k: v for k, v in c.items() if k != "text"},
                                     "score": n})
    for k in found:
        seen, keep = set(), []
        for r in sorted(found[k], key=lambda r: -r["score"]):
            ident = r.get("at") or r.get("path") or r.get("tool")
            if ident and str(ident).lower() in seen:
                continue
            seen.add(str(ident).lower())
            keep.append(r)
        found[k] = keep[:5]

    verdict, confident, why = _decide(found)
    return {
        "target": target, "terms": terms, "key_term": key, "found": found,
        "verdict": verdict, "confident": confident, "why": why,
        "checked": ["hub", "mcp", "cli"],
        # Said plainly so a caller does not have to infer it: when this is True
        # nobody needs to ask a model anything.
        "needs_judgement": not confident,
    }


@routes.get("/api/probe")
async def api_probe(request: web.Request) -> web.Response:
    """What can drive this? Deterministic - the same answer every time."""
    target = (request.query.get("target") or "").strip()
    if not target:
        raise web.HTTPBadRequest(text="say what you are asking about")
    return web.json_response(await look(target, request.app))
