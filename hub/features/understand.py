"""Understand a request: what does the person want, and which thing do they mean?

The rules (templates, the launcher's own app matcher) are the fast path and are
trusted when they are sure. When they are not - a recogniser wrote "using
adress", an app name is one the launcher cannot place, a sentence matches no
template - this asks the local decision model two closed questions in one call:

    intent   which of these things is the person asking for?
    app      which of the apps the hub knows do they mean?   (also: project)

A decision model answers by choosing among options with a probability, so the
answer is always one of the hub's own options and always carries how sure it
was. It never writes the reply. When it is off, not installed or unsure, this
returns None and the caller carries on with the rules, exactly as before.
"""
from __future__ import annotations

import time

from ..config import logger
from .. import decide as DEC

INTENTS = {
    "open_app": "Open or launch an installed application on this PC, possibly then doing something inside it.",
    "open_by_address": "Open an installed application through its URL address, link or protocol.",
    "ingest_app": "Read an installed application's own files to learn what it can do: ingest, inspect, analyse, learn it.",
    "ask_result": "Ask what was found, or whether something the hub was reading or researching has finished.",
    "tell_location": "Tell or correct where the user lives or currently is.",
    "weather": "Ask about the weather, rain, or the temperature.",
    "time": "Ask what the time or the date is.",
    "start_project_work": "Instruct changes to a software project: fix, build, write, add, refactor, test.",
    "schedule_work": "Do something repeatedly on a schedule, or when some event happens.",
    "research": "Ask a factual question about the world that needs looking up.",
    "name_recording": "Give a name to the routine that was just recorded.",
    "chat": "Greet, chat, or say something with no task in it.",
}

MIN_INTENT = 0.55
MIN_ENTITY = 0.5
NONE = "none of these"


async def _ensure_ollama() -> None:
    try:
        from . import missions as M
        await M._ensure_ollama()
        M.touch_ollama()
    except Exception as exc:
        logger.info("understand: could not start Ollama: %s", exc)


def known_apps() -> "list[str]":
    """Applications the hub can act on: installed ones and ones it has read."""
    names: list[str] = []
    try:
        from . import pc_control as PC
        names += [n for n in (PC._START_APPS.get("names") or []) if n and not PC._JUNK_NAME.search(n)]
    except Exception:
        pass
    try:
        from . import rea_inspect as REA
        names += [p.stem for p in REA.EVIDENCE.glob("*.json")]
    except Exception:
        pass
    seen, out = set(), []
    for n in names:
        k = n.casefold()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out[:120]


def known_projects() -> "list[dict]":
    try:
        from . import binning as B
        return [p for p in B._projects() if p.get("slug")]
    except Exception:
        return []


APP_INTENTS = ("open_app", "open_by_address", "ingest_app")


def shortlist(text: str, names: "list[str]", limit: int = 10) -> "list[str]":
    """The few app names that look like words in the sentence. A closed question over a handful
    of options is fast and sharp; over every installed app it is neither."""
    import difflib
    import re
    toks = [t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) > 2]
    scored = []
    for n in names:
        words = re.findall(r"[a-z0-9]+", n.casefold()) or [n.casefold()]
        s = max((difflib.SequenceMatcher(None, t, w).ratio() for t in toks for w in words), default=0.0)
        s = max(s, max((difflib.SequenceMatcher(None, " ".join(toks[i:i + len(words)]), " ".join(words)).ratio()
                        for i in range(max(1, len(toks))) if toks), default=0.0))
        if s >= 0.6:
            scored.append((s, n))
    scored.sort(key=lambda t: (-t[0], len(t[1])))
    return [n for _, n in scored[:limit]]


async def _ask(qs, model, post):
    got = await DEC._decide_systemone({"request": qs[0]["_text"]}, [{k: v for k, v in q.items() if k != "_text"} for q in qs], model, post)
    return {r["id"]: r for r in got}


async def understand(text: str, *, post=None, want_project: bool = False) -> "dict | None":
    """{intent, p_intent, app, p_app, project, p_project, ms} or None when no model could answer.

    Two cheap calls rather than one big one: the intent first, then - only if it needs one - which
    app or project, from a short list.
    """
    from . import binning as B
    if not B.settings()["local"]["enabled"] and post is None:
        return None
    t0 = time.time()
    model = B.settings()["local"]["model"]
    if post is None:
        await _ensure_ollama()
    q = DEC.q_choice("intent", "What is the person asking for?", list(INTENTS), INTENTS)
    q["_text"] = text
    try:
        by = await _ask([q], model, post)
    except Exception as exc:
        logger.info("understand: decision model failed: %s", exc)
        return None
    it = by.get("intent") or {}
    if it.get("answer") is None:
        return None
    out = {"intent": it["answer"], "p_intent": float(it.get("p") or 0), "app": None, "p_app": 0.0,
           "project": None, "p_project": 0.0, "text": text}

    async def entity(qid, question, options, descs):
        qq = DEC.q_choice(qid, question, options + [NONE], {**descs, NONE: "none of these is meant"})
        qq["_text"] = text
        r = (await _ask([qq], model, post)).get(qid) or {}
        a, p = r.get("answer"), float(r.get("p") or 0)
        return (a, p) if a and a != NONE and p >= MIN_ENTITY else (None, p)

    try:
        if out["intent"] in APP_INTENTS and out["p_intent"] >= MIN_INTENT:
            short = shortlist(text, known_apps())
            if short:
                out["app"], out["p_app"] = await entity("app", "Which application does the person mean?", short,
                                                        {a: "an application" for a in short})
        if out["intent"] == "start_project_work" and want_project:
            projs = known_projects()
            if projs:
                out["project"], out["p_project"] = await entity(
                    "project", "Which software project does the person mean?", [p["slug"] for p in projs],
                    {p["slug"]: p.get("name", p["slug"]) for p in projs})
    except Exception as exc:
        logger.info("understand: entity question failed: %s", exc)
    out["ms"] = int((time.time() - t0) * 1000)
    return out
