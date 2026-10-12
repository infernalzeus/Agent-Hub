"""Which bin does a request belong in?

A spoken or typed request is one of a small number of kinds of thing, and each
kind is done in a different place. Getting that wrong is the whole class of
failure the user keeps hitting: "open Apple Music" treated as a conversation,
"what's the weather" treated as a mission, a plain command that gets stuck
because something chatty took it.

Until now this decision was implicit in the order of a long `if` ladder in
`voice.chat`. That makes it impossible to see, measure, test as a table, or
hand to a decision model. This is the same decision, written down:

    launch_app        open an installed application
    app_task          open an application AND do something inside it
    pc_direct         a fixed PC action: open Edge, a URL, a web search
    lookup_routine    a procedure the hub has that answers it (weather, time)
    lookup_agent      an outward question an agent should research
    hub_command       something about the hub itself: status, pause, open a page
    personal_fact     tell / forget / ask what it knows about you
    mission_ask       work to be done on a project
    automation_ask    work to be done on a clock or when something happens
    conversation      none of the above: talk

Deterministic evidence decides first and is recorded with its reason. A model
(local, or a hosted decision model such as Jev) is only ever asked about the
cases the rules mark as unsure, and the rules' answer stands when it cannot
answer. Every decision is logged next to what actually happened, so how often
the bin was right is a number, not an impression.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()

BINS = ("launch_app", "app_task", "pc_direct", "lookup_routine", "lookup_agent", "hub_command",
        "personal_fact", "mission_ask", "automation_ask", "conversation")

LOG = STATE / "utterance_decisions.jsonl"
SURE = 0.75            # at or above this, the rules' bin is acted on without asking anything else

# Work-on-a-project cues: an imperative that changes something, plus somewhere to do it.
_WORK_VERB = re.compile(
    r"^(?:please |can you |could you |i want you to |i need you to |go and |now )?"
    r"(?:fix|add|implement|refactor|rewrite|write|build|create|make|update|change|remove|delete|"
    r"rename|migrate|port|optimi[sz]e|clean up|document|test|debug|review|improve)\b", re.I)
_WORK_PLACE = re.compile(
    r"\b(?:in|to|for|on|inside)\s+(?:the\s+)?(?P<where>[A-Za-z0-9_.\-/]{3,}(?:\s[A-Za-z0-9_.\-]+)?)\b"
    r"|\b(?:repo|project|codebase|function|class|file|module|script|bug|feature|test|readme)\b", re.I)
_SCHEDULE = re.compile(r"\b(?:every|each|daily|nightly|weekly|monthly|hourly|every\s+(?:day|morning|night|week))\b"
                       r"|\bwhenever\b|\bwhen\s+(?:a|an|the|it|something)\b|\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.I)

# "every night, review ..." / "at 9am fix ..." - the clock comes first, the work follows.
_SCHEDULE_LEAD = re.compile(
    r"^(?:(?:every|each)\s+(?:day|morning|night|evening|week|weekday|hour|monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|every\s+night|daily|nightly|weekly|monthly|hourly|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)|whenever[^,]*)\s*,?\s*", re.I)


def _d(bin_: str, confidence: float, why: str, by: str = "rules", **extra) -> dict:
    return {"bin": bin_, "confidence": round(confidence, 2), "by": by, "why": why, **extra}


def _projects() -> "list[dict]":
    try:
        from ..agent_knowledge.projects import discover_projects
        return [p for p in discover_projects() if not p.get("readonly")]
    except Exception:
        return []


def mentioned_project(text: str) -> "dict | None":
    """A writable project named in the sentence, if exactly one is."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()) + " "
    hits = []
    for p in _projects():
        for key in {p.get("slug", ""), p.get("name", "")}:
            k = re.sub(r"[^a-z0-9]+", " ", str(key).casefold()).strip()
            if len(k) >= 4 and f" {k} " in t:
                hits.append(p)
                break
    return hits[0] if len(hits) == 1 else None


def decide(text: str, *, have_question_open: bool = False) -> dict:
    """Put one request in one bin, from evidence, and say why.

    Pure and cheap: no model, no network, nothing started. Order matters and is
    the point - it is the order in which a wrong guess is least harmful.
    """
    t = " ".join((text or "").split())
    if not t:
        return _d("conversation", 0.0, "nothing was said")
    low = t.casefold()

    # 1. About you: telling, forgetting, what it knows.
    if re.match(r"^(?:my |the )?(?:location|timezone|time zone|name|units)\s*(?:is|=|:)\s*\S", low) \
            or re.match(r"^forget (?:my |the )?[a-z ]{2,30}$", low) \
            or re.match(r"^what do you know about me\b", low):
        return _d("personal_fact", 0.97, "telling or forgetting a fact about the person")

    # 2. About the hub itself: the existing fast rules.
    try:
        from . import voice as V
        hit = V.match_rules(t)
    except Exception:
        hit = None
    if hit:
        cmd = hit[0]
        return _d("hub_command", 0.95, f"matches the hub command {cmd.get('id', '?')}", rule=cmd.get("id"))

    # 3. A PC action with a fixed shape (Edge, a URL, a web search).
    try:
        from . import voice as V
        if V._direct_pc_request(t):
            return _d("pc_direct", 0.9, "a fixed PC action")
    except Exception:
        pass

    # 4. Opening an application - alone, or with something to do inside it.
    try:
        from . import pc_control as PC
        task = PC.classify_request(t)
    except Exception:
        task = None
    if task and task.get("kind") == "launch_app":
        if task.get("then"):
            return _d("app_task", 0.9, f"opens {task['app']!r} and then {task['then']!r}",
                      app=task["app"], then=task["then"])
        return _d("launch_app", 0.95, f"opens {task['app']!r}", app=task["app"])

    # 5. Something the hub has a procedure for, or an outward question.
    try:
        from . import converse as C
        routine = C.match(t)
    except Exception:
        routine = None
    if routine:
        scheduled = bool(_SCHEDULE.search(t))
        return _d("lookup_routine", 0.92, f"the {routine['title'].lower()} routine covers it",
                  routine=routine["id"], scheduled=scheduled)

    # 6. Work on a project, or work on a clock.
    scheduled = bool(_SCHEDULE.search(t))
    core = _SCHEDULE_LEAD.sub("", low).strip(" ,")
    work = bool(_WORK_VERB.match(core))
    project = mentioned_project(t) if work else None
    if work and project:
        return _d("automation_ask" if scheduled else "mission_ask", 0.85,
                  f"an instruction to change something, naming the project {project['slug']!r}"
                  + (" on a schedule" if scheduled else ""), project=project["slug"], scheduled=scheduled)
    if work and _WORK_PLACE.search(low):
        return _d("automation_ask" if scheduled else "mission_ask", 0.6,
                  "an instruction to change something, with no project named", scheduled=scheduled)

    # 7. An outward question.
    try:
        from . import converse as C
        if C.looks_like_lookup(t):
            return _d("lookup_agent", 0.7, "a question about the world, not the hub")
    except Exception:
        pass

    return _d("conversation", 0.5 if len(t.split()) > 2 else 0.4, "nothing more specific fits")


async def refine(decision: dict, text: str) -> dict:
    """Ask a decision backend about a case the rules were unsure of.

    Backends are chosen by `HUB_BIN_BACKEND`: `rules` (default; nothing extra),
    `local` (a small local model choosing from the list, with a probability), or
    `jev` (a hosted decision model; a slot until API access is wired in, which
    answers "not configured" and so changes nothing). Whatever happens, the
    rules' answer stands unless the backend is both available and confident.
    """
    backend = os.environ.get("HUB_BIN_BACKEND", "rules").lower()
    if decision["confidence"] >= SURE or backend == "rules":
        return decision
    try:
        from .. import decide as DEC
        q = DEC.q_choice("bin", f"Which kind of request is this? {text}", list(BINS))
        got = await DEC.decide({"utterance": text}, [q], backend=backend)
    except Exception as exc:
        logger.info("binning: %s backend unavailable: %s", backend, exc)
        return decision
    r = (got or [{}])[0]
    if r.get("answer") in BINS and float(r.get("p") or 0) >= 0.8:
        return {**decision, "bin": r["answer"], "confidence": round(float(r["p"]), 2), "by": backend,
                "why": f"{backend} chose it from a case the rules were unsure of (was {decision['bin']})"}
    return decision


def record(text: str, decision: dict, outcome: dict) -> None:
    """One line per request: what was decided, and what actually happened."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {"at": round(time.time(), 1), "text": (text or "")[:300], **{k: decision.get(k) for k in
               ("bin", "confidence", "by", "why")}, **outcome}
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.info("binning: could not log: %s", exc)


def recent(limit: int = 30) -> "list[dict]":
    try:
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    return list(reversed(rows[-limit:]))


def agreement() -> dict:
    """How often the path that actually ran matched the bin. A number, not a feeling."""
    expect = {"launch_app": {"pc_app"}, "app_task": {"pc_app"}, "pc_direct": {"pc_direct"}}
    rows = recent(500)
    n = ok = 0
    for r in rows:
        b = r.get("bin")
        if b == "conversation":
            continue
        n += 1
        ran = r.get("action") or r.get("route_name") or ""
        if b in expect:
            ok += int(r.get("action") in expect[b])
        elif b == "lookup_routine":
            ok += int(str(r.get("backend")) == "router")
        elif b == "lookup_agent":
            ok += int(str(r.get("backend")) == "router")
        else:
            ok += int(bool(ran) or r.get("backend") in ("rules", "router"))
    return {"decisions": n, "matched": ok, "rate": round(ok / n, 2) if n else None}


@routes.get("/api/decisions/utterances")
async def api_recent(request: web.Request) -> web.Response:
    """Every recent request, the bin it was given, why, and what ran - for watching it work."""
    try:
        limit = max(1, min(200, int(request.query.get("limit", "30"))))
    except ValueError:
        limit = 30
    return web.json_response({"decisions": recent(limit), "agreement": agreement(), "bins": list(BINS),
                              "backend": os.environ.get("HUB_BIN_BACKEND", "rules")})


@routes.post("/api/decisions/classify")
async def api_classify(request: web.Request) -> web.Response:
    """Which bin would this go in? Decides only; nothing is run."""
    try:
        b = await request.json()
    except Exception:
        b = {}
    text = str(b.get("text") or "").strip()[:500]
    if not text:
        raise web.HTTPBadRequest(text="no text")
    return web.json_response(await refine(decide(text), text))
