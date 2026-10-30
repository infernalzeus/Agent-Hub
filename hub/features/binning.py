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
SETTINGS = STATE / "decision_settings.json"
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


# What a person can switch Jev on for. Each is a kind of request the rules were unsure about.
TYPES = {
    "unclear": ("Requests nothing else recognised", ("conversation",),
                "Otherwise these go to the local chat model."),
    "project_work": ("Looks like work on a project", ("mission_ask",), "A mission."),
    "scheduled": ("Looks like something on a schedule", ("automation_ask",), "An automation."),
    "research": ("Looks like a question to research", ("lookup_agent",), "A research agent."),
    "apps": ("Looks like opening or using an app", ("launch_app", "app_task"), "PC control."),
}


def settings() -> dict:
    """{"jev": {"enabled": bool, "types": {type: bool}}}. Everything off until you turn it on."""
    base = {"jev": {"enabled": False, "types": {k: False for k in TYPES}},
            "local": {"enabled": False, "model": "tev1:4b"}}
    try:
        got = json.loads(SETTINGS.read_text(encoding="utf-8"))
        j = got.get("jev") or {}
        loc = got.get("local") or {}
        base["local"]["enabled"] = bool(loc.get("enabled"))
        base["local"]["model"] = str(loc.get("model") or "tev1:4b")[:60]
        base["jev"]["enabled"] = bool(j.get("enabled"))
        for k in TYPES:
            base["jev"]["types"][k] = bool((j.get("types") or {}).get(k))
    except (OSError, ValueError, AttributeError):
        pass
    return base


def save_settings(new: dict) -> dict:
    cur = settings()
    j = (new or {}).get("jev") or {}
    loc = (new or {}).get("local") or {}
    if "enabled" in loc:
        cur["local"]["enabled"] = bool(loc["enabled"])
    if loc.get("model"):
        cur["local"]["model"] = str(loc["model"])[:60]
    if "enabled" in j:
        cur["jev"]["enabled"] = bool(j["enabled"])
    for k, v in (j.get("types") or {}).items():
        if k in TYPES:
            cur["jev"]["types"][k] = bool(v)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return cur


def type_of(bin_: str) -> str:
    for k, (_, bins, _) in TYPES.items():
        if bin_ in bins:
            return k
    return ""


def _type_on(decision: dict) -> bool:
    return bool(settings()["jev"]["types"].get(type_of(decision.get("bin", "")), False))


def jev_allowed(decision: dict) -> bool:
    return bool(settings()["jev"]["enabled"] and _type_on(decision))


def local_allowed(decision: dict) -> bool:
    """The same decision, answered by a model on this PC. Shares the per-type switches with Jev."""
    return bool(settings()["local"]["enabled"])


_BIN_DESC = {
    "launch_app": "Open an installed application on this PC.",
    "app_task": "Open an application and then do something inside it.",
    "pc_direct": "A fixed PC action: open the browser, a web address, or a web search.",
    "lookup_routine": "A question the hub already has a procedure for, such as weather or the time.",
    "lookup_agent": "A factual question about the world that needs researching.",
    "hub_command": "Something about this hub itself: its status, pausing, opening one of its pages.",
    "personal_fact": "Telling the hub, or asking it, a fact about the person.",
    "mission_ask": "An instruction to change or build something in a software project.",
    "automation_ask": "An instruction to do something repeatedly or when an event happens.",
    "conversation": "Ordinary talk with no task in it.",
}


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


async def _ensure_local_model() -> None:
    """Start Ollama if it is not up (it is stopped again when idle), as the chat model path does."""
    try:
        from . import missions as M
        await M._ensure_ollama()
        M.touch_ollama()
    except Exception as exc:
        logger.info("binning: could not start Ollama: %s", exc)


async def refine(decision: dict, text: str, post=None) -> dict:
    """Ask a decision model about a case the rules were unsure of.

    Level order: rules (already done) -> Jev, only if you switched it on for this
    kind of request -> the local model, only if HUB_BIN_BACKEND=local. A backend
    that is off, missing a key, offline or unsure changes nothing: the rules'
    answer stands.
    """
    if decision["confidence"] >= SURE:
        return decision
    backends = []
    if local_allowed(decision):
        backends.append("systemone")                # on this PC first: nothing leaves the machine
    if jev_allowed(decision):
        backends.append("jev")
    if os.environ.get("HUB_BIN_BACKEND", "rules").lower() == "local":
        backends.append("local")
    asked = []
    for backend in backends:
        t0 = time.time()
        try:
            from .. import decide as DEC
            q = DEC.q_choice("bin", "Which kind of request is this?", list(BINS), _BIN_DESC)
            if backend == "jev":
                got = await DEC._decide_jev({"utterance": text}, [q], post)
            elif backend == "systemone":
                if post is None:
                    await _ensure_local_model()
                got = await DEC._decide_systemone({"utterance": text}, [q], settings()["local"]["model"], post)
            else:
                got = await DEC.decide({"utterance": text}, [q], backend=backend)
        except Exception as exc:
            logger.info("binning: %s backend unavailable: %s", backend, exc)
            continue
        r = (got or [{}])[0]
        asked.append({"backend": backend, "answer": r.get("answer"), "p": round(float(r.get("p") or 0), 2),
                      "ms": int((time.time() - t0) * 1000), "note": str(r.get("note") or "")[:80]})
        if r.get("answer") in BINS and float(r.get("p") or 0) >= 0.8:
            return {**decision, "bin": r["answer"], "confidence": round(float(r["p"]), 2), "by": backend, "asked": asked,
                    "why": f"{backend} chose it from a case the rules were unsure of (was {decision['bin']})"}
    return {**decision, "asked": asked} if asked else decision


def _append(row: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.info("binning: could not log: %s", exc)


def record(text: str, decision: dict, outcome: dict) -> None:
    """One line per request: what was decided, and what actually happened.

    `escalated` is whether a model was asked at all, so how often the rules were not
    enough is a count. `ms` and `timed_out` come from the caller when it knows them.
    """
    asked = decision.get("asked")
    _append({"at": round(time.time(), 1), "text": (text or "")[:300], **{k: decision.get(k) for k in
             ("bin", "confidence", "by", "why", "asked")}, "escalated": bool(asked), **outcome})


def record_outcome(action_id: str, ok: "bool | None", said: str = "") -> None:
    """What happened when an action the router chose was actually run (after any yes).

    A separate line of kind "outcome", never counted as a decision. `ok` is None when the
    action does not report success, so a missing answer is not read as a good one.
    """
    if not action_id:
        return
    _append({"kind": "outcome", "at": round(time.time(), 1), "action": action_id,
             "ok": ok if isinstance(ok, bool) else None, "said": (said or "")[:120]})


def _rows() -> "list[dict]":
    try:
        return [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def recent(limit: int = 30) -> "list[dict]":
    """Decisions only, newest first. Outcome lines are read by `summary`."""
    rows = [r for r in _rows() if r.get("kind") != "outcome"]
    return list(reversed(rows[-limit:]))


def summary() -> dict:
    """The evidence base for the router: how many decisions, who made them, how many needed a
    model, how many ran, and how often a run that was confirmed actually worked."""
    rows = _rows()
    decisions = [r for r in rows if r.get("kind") != "outcome"]
    outcomes = [r for r in rows if r.get("kind") == "outcome"]
    by: "dict[str, int]" = {}
    per_bin: "dict[str, int]" = {}
    for r in decisions:
        by[str(r.get("by") or "rules")] = by.get(str(r.get("by") or "rules"), 0) + 1
        per_bin[str(r.get("bin"))] = per_bin.get(str(r.get("bin")), 0) + 1
    return {"decisions": len(decisions), "by": by, "per_bin": per_bin,
            "escalated": sum(1 for r in decisions if r.get("asked")),
            "timed_out": sum(1 for r in decisions if r.get("timed_out")),
            "outcomes": len(outcomes),
            "outcomes_ok": sum(1 for r in outcomes if r.get("ok") is True),
            "outcomes_failed": sum(1 for r in outcomes if r.get("ok") is False),
            "outcomes_unknown": sum(1 for r in outcomes if r.get("ok") is None),
            "enough_to_calibrate": len(decisions) >= 100}


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
    return web.json_response({"decisions": recent(limit), "agreement": agreement(), "summary": summary(), "bins": list(BINS),
                              "backend": os.environ.get("HUB_BIN_BACKEND", "rules")})


@routes.get("/api/decisions/settings")
async def api_settings(request: web.Request) -> web.Response:
    from .. import decide as DEC
    return web.json_response({**settings(), "types": {k: {"label": v[0], "goes_to": v[2]} for k, v in TYPES.items()},
                              "key_present": bool(DEC._openrouter_key()),
                              "local_status": await DEC.systemone_status(model=settings()["local"]["model"]),
                              "note": "Jev is reached through OpenRouter. The sentence is sent to it only for the request "
                                      "types switched on here."})


@routes.post("/api/decisions/settings")
async def api_save_settings(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:
        b = {}
    return web.json_response(save_settings(b if isinstance(b, dict) else {}))


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
    return web.json_response(await refine(decide(text), text, None))

