"""An automation: something the Hub does on its own, made of steps you can read.

A mission is one agent, one brief, run once. That is the right shape for "change
this code" and the wrong shape for "every Monday, do these four things, and stop
before the one that publishes". This is that second shape.

An automation is **steps in order**, each of one kind:

* `mission` - hand a brief to an agent in a private copy of a project. Open-ended:
  the agent decides how. Use it when the work needs judgement.
* `hub`     - call one of the Hub's own endpoints. Deterministic. The agent is not
  involved and cannot get it wrong.
* `routine` - replay a machine routine you recorded once. For programs with no
  interface but their own window.

Mixing them is the point. "Render the clip" is deterministic, "write a title that
suits it" needs an agent, "press the button in the app that has no API" needs a
routine, and one automation can be all three.

## Two rules that shape everything else

**A step with consequences stops and waits.** `gate: true` on a step means the run
pauses there and the Hub asks you, exactly as a mission's diff waits for APPLY.
Publishing, sending and spending are the cases this exists for. A gate is declared
on the step, so nothing becomes consequential by accident - and an automation that
was never given a gated step cannot discover a way to publish by rewording a brief.

**A run is a record, not a log line.** Every run persists its steps and their
outcomes before it does anything, so a crash, a restart, or a gate answered
tomorrow all resume from the same place rather than starting again. That is the
part which cannot be rebuilt from events, which is why `events.py` is deliberately
not durable.
"""
from __future__ import annotations

import asyncio
import copy
import json
import re
import time
import uuid
from typing import Any

from aiohttp import web

from .. import events
from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "automations.json"
RUNS = STATE / "automation_runs.json"
MAX_RUNS = 200                      # history is useful; unbounded history is a leak

STEP_KINDS = ("mission", "hub", "routine")
TRIGGERS = ("manual", "schedule", "event")

# A run waiting for you is neither finished nor running. Keeping that a status of
# its own is what lets the board say "2 waiting for you" honestly. There are two
# kinds of waiting and they are not the same question: `awaiting_approval` asks
# "shall I?", `awaiting_input` asks "with what?".
TERMINAL = ("done", "failed", "stopped")
WAITING = ("awaiting_approval", "awaiting_input")

# How far an event chain may go before it is cut. A listens to B listens to A is
# the loop; this is the ceiling that stops anything cleverer.
MAX_CHAIN = 3

# What a mission's status means to a run. One table, because three places each
# kept their own list and each list was different: one named a status that no
# mission ever has, another let `paused` count as finished.
#   working  keep waiting          ask    a question to answer
#   review   a result to decide    hold   waiting on a person, in the board
#   good     finished, accepted    dead   will never finish
_M_WORKING = ("running", "queued", "blocked")
_M_ASK = ("needs_input",)
_M_REVIEW = ("awaiting_review",)
_M_HOLD = ("paused", "plan_ready")
_M_GOOD = ("applied",)
_M_DEAD = ("failed", "timed_out", "stopped", "discarded", "orphaned", "archived")


def mission_outcome(status: str) -> str:
    """working / ask / review / hold / good / dead, and `unknown` for anything else.

    Unknown parks the run. Treating an unrecognised status as success is how
    `paused` ran the next step; failing closed costs one question.
    """
    for name, group in (("working", _M_WORKING), ("ask", _M_ASK), ("review", _M_REVIEW),
                        ("hold", _M_HOLD), ("good", _M_GOOD), ("dead", _M_DEAD)):
        if status in group:
            return name
    return "unknown"


# -- storage ------------------------------------------------------------------
def _read(path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def load() -> list[dict]:
    return _read(FILE, [])


def _save(rows: "list[dict]") -> None:
    write_json(FILE, rows)


def runs(automation_id: "str | None" = None, limit: int = 50) -> "list[dict]":
    rows = _read(RUNS, [])
    if automation_id:
        rows = [r for r in rows if r.get("automation") == automation_id]
    return sorted(rows, key=lambda r: r.get("started", 0), reverse=True)[:limit]


def _save_run(run: dict) -> None:
    rows = [r for r in _read(RUNS, []) if r.get("id") != run["id"]]
    rows.append(run)
    rows = sorted(rows, key=lambda r: r.get("started", 0), reverse=True)
    # History is capped; what a person still has to answer is not history. A
    # plain "newest 200" quietly deleted waiting runs once enough newer ones had
    # arrived, so a run could become unanswerable simply by being old.
    live = [r for r in rows if r.get("status") not in TERMINAL]
    done = [r for r in rows if r.get("status") in TERMINAL][:MAX_RUNS]
    write_json(RUNS, sorted(live + done, key=lambda r: r.get("started", 0), reverse=True))


def waiting_runs() -> "list[dict]":
    """Every run that is waiting, however old and however many have happened since.

    `runs(limit=50)` is a display window. Searching it for waiting runs meant a
    run with fifty newer neighbours could not be found, and so never resumed.
    """
    rows = [r for r in _read(RUNS, []) if r.get("status") in WAITING]
    return sorted(rows, key=lambda r: r.get("started", 0), reverse=True)


def get(aid: str) -> "dict | None":
    return next((a for a in load() if a.get("id") == aid), None)


def get_run(rid: str) -> "dict | None":
    return next((r for r in _read(RUNS, []) if r.get("id") == rid), None)


# -- validation ---------------------------------------------------------------
def needs_of(step: dict) -> "list[dict]":
    """Values this step cannot run without.

    Declared on the step rather than guessed from the text, so an automation can
    be built and saved before anybody knows the playlist URL - the shape is
    settled now, the value arrives later.
    """
    out = []
    for raw in (step.get("needs") or []):
        if isinstance(raw, str):
            out.append({"key": raw, "label": raw, "why": ""})
        elif isinstance(raw, dict) and str(raw.get("key") or "").strip():
            out.append({"key": str(raw["key"]).strip(),
                        "label": str(raw.get("label") or raw["key"]).strip(),
                        "why": str(raw.get("why") or "").strip()})
    return out


def missing(step: dict, have: dict) -> "list[dict]":
    """The declared values nobody has supplied yet."""
    return [n for n in needs_of(step) if not str(have.get(n["key"], "")).strip()]


def fill(value: Any, have: dict) -> Any:
    """Put the supplied values into a step, wherever {{key}} appears.

    Walks the whole step, so a value can land in a brief, a path or a body
    without each of those needing its own rule.
    """
    if isinstance(value, str):
        for k, v in have.items():
            value = value.replace("{{" + k + "}}", str(v))
        return value
    if isinstance(value, dict):
        return {k: fill(v, have) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, have) for v in value]
    return value


_SECRET = re.compile(r"pass(?:word|wd)?|secret|token|api[_-]?key|credential|card[_-]?n|\bpin\b|\bssn\b", re.I)


def _bad_step(s: Any, n: int) -> str:
    if not isinstance(s, dict):
        return f"step {n} is not an object"
    kind = s.get("kind")
    if kind not in STEP_KINDS:
        return f"step {n}: kind must be one of {', '.join(STEP_KINDS)}"
    if kind == "mission":
        if not str(s.get("brief") or "").strip():
            return f"step {n}: a mission step needs a brief"
        if not str(s.get("project") or "").strip():
            return f"step {n}: a mission step needs a project"
    if kind == "hub":
        path = str(s.get("path") or "")
        if not path.startswith("/api/"):
            return f"step {n}: a hub step needs an /api/... path"
        if str(s.get("method", "GET")).upper() not in ("GET", "POST", "PUT", "DELETE"):
            return f"step {n}: unsupported method"
    if kind == "routine" and not str(s.get("routine") or "").strip():
        return f"step {n}: a routine step needs a routine id"
    # A run asks for plain values: a playlist, a folder, a name. Never a secret.
    # The same line is drawn by MCP elicitation, which sends passwords and keys
    # to a separate channel precisely because a form is the wrong place for them.
    wanted = [str(k.get("key") if isinstance(k, dict) else k) for k in (s.get("needs") or [])]
    wanted += re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", json.dumps(s))
    for key in wanted:
        if _SECRET.search(key):
            return (f"step {n}: {key!r} looks like a secret. Runs ask for plain values only; "
                    f"keep keys and passwords in Settings, not in an automation")
    return ""


def validate(a: dict) -> str:
    """Why this automation cannot be saved, or "" if it is fine."""
    if not str(a.get("name") or "").strip():
        return "an automation needs a name"
    trig = (a.get("trigger") or {})
    kind = trig.get("kind")
    if kind not in TRIGGERS:
        return f"trigger must be one of {', '.join(TRIGGERS)}"
    if kind == "event" and trig.get("event") not in events.KINDS:
        return "pick an event the Hub actually emits"
    if kind == "schedule" and trig.get("every") not in ("daily", "weekly", "monthly"):
        return "a schedule runs daily, weekly or monthly"
    steps = a.get("steps")
    if not isinstance(steps, list) or not steps:
        return "an automation needs at least one step"
    for n, s in enumerate(steps, 1):
        why = _bad_step(s, n)
        if why:
            return why
    return ""


def save(a: dict) -> dict:
    why = validate(a)
    if why:
        raise ValueError(why)
    rows = load()
    aid = a.get("id") or ("a" + uuid.uuid4().hex[:8])
    row = {
        "id": aid,
        "name": str(a["name"]).strip(),
        "enabled": bool(a.get("enabled", True)),
        "trigger": dict(a["trigger"]),
        "steps": [dict(s, id=s.get("id") or f"s{n}") for n, s in enumerate(a["steps"], 1)],
        "created": next((r["created"] for r in rows if r["id"] == aid), time.time()),
        "updated": time.time(),
    }
    # `next` is when the clock says to run it. Dropping it on every edit made an
    # overdue automation forget it was overdue: the next tick computed a future
    # time and the missed run was silently skipped.
    prev = next((r for r in rows if r["id"] == aid), None)
    if prev and prev.get("next") and prev.get("trigger") == row["trigger"]:
        row["next"] = prev["next"]
    _save([r for r in rows if r["id"] != aid] + [row])
    logger.info("automations: saved %s (%s)", aid, row["name"])
    return row


def delete(aid: str) -> bool:
    rows = load()
    keep = [r for r in rows if r.get("id") != aid]
    if len(keep) == len(rows):
        return False
    _save(keep)
    # A run that was waiting for an answer outlives the automation it belongs
    # to, and nothing could then answer or remove it: it sat in "what is
    # waiting for you" permanently, pointing at something that no longer exists.
    # Deleting the automation closes those runs rather than orphaning them.
    stale = [r for r in _read(RUNS, []) if r.get("automation") == aid and r.get("status") in WAITING]
    for r in stale:
        r["status"] = "stopped"
        r["ended"] = time.time()
        r["why"] = (r.get("why") or "") + " (its automation was deleted)"
        _save_run(r)
    if stale:
        logger.info("automations: closed %d waiting run(s) of deleted %s", len(stale), aid)
    return True


def forget_run(rid: str) -> bool:
    """Drop one run from the history. Refuses while it is still waiting.

    Run history had no way to be cleared at all, so a few test runs were
    permanent. A waiting run is not removable, because the thing to do with it
    is answer it or stop its automation - quietly deleting something that is
    mid-flight is how state goes missing.
    """
    rows = _read(RUNS, [])
    row = next((r for r in rows if r.get("id") == rid), None)
    if row is None:
        return False
    if row.get("status") in WAITING and get(row.get("automation") or ""):
        raise ValueError("that run is still waiting - answer it, or delete its automation")
    # A waiting run whose automation is already gone cannot be answered (there
    # is nothing left to carry on) and must therefore be removable, or it is
    # stuck in "what is waiting for you" for good. Refusing it told the user to
    # do two things that were both impossible.
    write_json(RUNS, [r for r in rows if r.get("id") != rid])
    return True


# -- running ------------------------------------------------------------------
def event_summary(ev: dict) -> str:
    """One line saying what an event was actually about.

    A run triggered by an event used to record only "after download.finished",
    which tells you nothing about which download - while the YouTube panel two
    clicks away showed the title, the file and the size. The payload was there
    all along and was being thrown away.
    """
    p = ev.get("payload") or {}
    inner = p.get("result") if isinstance(p.get("result"), dict) else {}
    for src in (inner, p):
        for key in ("title", "name", "file", "filename", "path", "url", "video", "project_name"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:90]
    if "ok" in p:
        return "succeeded" if p.get("ok") else "failed"
    return ""


def event_values(ev: dict) -> dict:
    """The event's own data, as values a step can substitute with {{key}}.

    Without this an automation triggered by "a download finished" could not act
    on the thing that finished, which is most of the point of triggering on it.
    """
    out = {"event": str(ev.get("kind") or "")}
    p = ev.get("payload") or {}
    inner = p.get("result") if isinstance(p.get("result"), dict) else {}
    for src in (p, inner):                      # inner wins: it is the specific one
        for k, v in (src or {}).items():
            if isinstance(v, (str, int, float, bool)) and str(k).isidentifier():
                out[str(k)] = v
    return out


def _new_run(a: dict, why: str, values: "dict | None" = None, chain: "list | None" = None) -> dict:
    return {
        "id": "r" + uuid.uuid4().hex[:8],
        "automation": a["id"],
        "name": a["name"],
        "why": why,                       # what started it, in words
        "started": time.time(),
        "ended": None,
        "status": "running",
        # Seeded from the triggering event, so a step can use what happened
        # rather than only knowing that something did.
        "values": dict(values or {}),
        # Who triggered whom: an event loop between automations is cut here
        # rather than merely hoped against.
        "chain": list(chain or []),
        # The steps as they were when this run began. Continuing used to read
        # the automation as it is *now*, so editing one mid-run changed what an
        # already-started run would do next.
        "snapshot": copy.deepcopy(a["steps"]),
        "steps": [{"id": s["id"], "kind": s["kind"], "status": "pending",
                   "gate": bool(s.get("gate")), "note": "",
                   "needs": needs_of(s)} for s in a["steps"]],
    }


async def start(a: dict, why: str = "run by you", values: "dict | None" = None,
                chain: "list | None" = None) -> dict:
    """Begin a run. Returns when it finishes **or reaches a gate**."""
    run = _new_run(a, why, values, chain)
    _save_run(run)                        # on disk before anything happens
    return await _advance(a, run)


def _finished(run: dict, status: str) -> None:
    """Announce a run's end, saying which automation it was.

    The payload used to carry only the run and the status, so a listener's guard
    against reacting to its own completion looked for an id that was never sent.
    """
    events.publish("automation.finished", {
        "run": run["id"], "status": status, "automation": run.get("automation"),
        "chain": list(run.get("chain") or []) + [run.get("automation")]})


_TASKS: "set[asyncio.Future]" = set()


async def _carry_on(a: dict, run: dict, wait: bool) -> dict:
    """Continue a run. From a page this must not hold the request open: the
    next step may be a mission that takes twenty minutes."""
    if wait:
        return await _advance(a, run)
    run["status"] = "running"
    run.pop("waiting_on", None)
    _save_run(run)

    async def go():
        try:
            await _advance(a, run)
        except Exception as exc:
            logger.warning("automations: run %s stopped carrying on: %s", run["id"], exc)

    t = asyncio.ensure_future(go())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return run


async def approve(rid: str, ok: bool = True, wait: bool = True) -> dict:
    """Answer the gate a run is waiting on, and carry on - or stop.

    At a *mission's review* this acts on that mission: yes applies its work, no
    discards it. It never re-enters the step, which is what dispatched a second
    mission and left the first waiting.
    """
    run = get_run(rid)
    if not run or run["status"] != "awaiting_approval":
        raise ValueError("that run is waiting for a value, not for approval"
                         if run and run["status"] == "awaiting_input"
                         else "that run is not waiting for approval")
    a = get(run["automation"])
    if not a:
        raise ValueError("the automation behind that run is gone")
    cur = next((s for s in run["steps"] if s["status"] == "awaiting_approval"), None)
    if cur and cur.get("mission"):
        return await _approve_mission(a, run, cur, cur["mission"], ok, wait)
    if not ok:
        if cur:
            cur["status"], cur["note"] = "skipped", "you declined this step"
        run["status"], run["ended"] = "stopped", time.time()
        run.pop("waiting_on", None)
        _save_run(run)
        _finished(run, "stopped")
        return run
    if cur:
        cur["status"], cur["note"] = "approved", "you approved this step"
    _save_run(run)
    return await _carry_on(a, run, wait)


async def _approve_mission(a: dict, run: dict, cur: dict, mid: str, ok: bool, wait: bool) -> dict:
    from . import missions as M
    m = M.S.m.get(mid)
    if not m:
        raise ValueError("the mission this run was waiting on is gone")
    if not ok:
        try:
            await M.discard(mid)
        except Exception as exc:
            raise ValueError(f"could not discard it: {getattr(exc, 'text', exc)}")
        cur["status"], cur["note"] = "skipped", f"you declined: mission {mid}'s work was discarded"
        run["status"], run["ended"] = "stopped", time.time()
        run.pop("waiting_on", None)
        _save_run(run)
        _finished(run, "stopped")
        return run
    if m.status != "awaiting_review":
        raise ValueError(f"that mission is {m.status}, not waiting for review - "
                         f"carry on from the missions board")
    try:
        res = await M.apply(mid)
    except Exception as exc:
        raise ValueError(f"could not apply it: {getattr(exc, 'text', exc)}")
    if isinstance(res, dict) and res.get("ok") is False:
        raise ValueError("could not apply it: " + str(res.get("reason") or res.get("run_this")
                                                     or "see the missions board"))
    cur["status"], cur["note"] = "done", f"mission {mid} -> applied (you approved)"
    _save_run(run)
    return await _carry_on(a, run, wait)


def _remember_values(values: dict, keys: "list | None") -> None:
    """Keep the values a person asked to have remembered, as facts about them.

    Opt-in per value: a run asks for what it needs; whether that is *about you*
    and worth keeping is the person's call, not the automation's.
    """
    if not keys:
        return
    from . import user_facts as F
    for k in keys:
        v = (values or {}).get(str(k))
        if v and F.KEY_RX.match(str(k)):
            try:
                F.remember(str(k), str(v), how="asked")
            except ValueError:
                pass


async def provide(rid: str, values: dict, remember: "list | None" = None, wait: bool = True) -> dict:
    """Supply what a waiting run asked for, and carry on.

    Values stay on the run, not on the automation: the automation is the shape
    and is reusable, this run is the one that had this playlist in it.

    When the question came from a mission, the answer goes to *that mission*.
    """
    run = get_run(rid)
    if not run or run["status"] != "awaiting_input":
        raise ValueError("that run is not waiting for anything")
    a = get(run["automation"])
    if not a:
        raise ValueError("the automation behind that run is gone")
    clean = {str(k): str(v) for k, v in (values or {}).items() if str(v).strip()}
    if not clean:
        raise ValueError("nothing was supplied")
    run["values"] = {**(run.get("values") or {}), **clean}
    _remember_values(run["values"], remember)
    cur = next((s for s in run["steps"] if s["status"] == "awaiting_input"), None)
    if cur and cur.get("mission"):
        return await _answer_mission(a, run, cur, cur["mission"], wait)
    if cur:
        steps_def = run.get("snapshot") or a["steps"]
        still = missing(next(x for x in steps_def if x["id"] == cur["id"]), run["values"])
        if still:
            cur["needs"] = still
            cur["note"] = "still needs " + ", ".join(g["label"] for g in still)
            _save_run(run)
            return run
        cur["status"], cur["note"], cur["needs"] = "pending", "", []
    _save_run(run)
    return await _carry_on(a, run, wait)


async def _answer_mission(a: dict, run: dict, cur: dict, mid: str, wait: bool) -> dict:
    from . import missions as M
    m = M.S.m.get(mid)
    if not m:
        raise ValueError("the mission this run was waiting on is gone")
    if m.status != "needs_input":
        raise ValueError(f"that mission is {m.status}, not waiting for answers")
    vals = run.get("values") or {}
    answers = []
    for i, q in enumerate(m.questions or [], 1):
        text = q.get("q") if isinstance(q, dict) else str(q)
        answers.append({"q": str(text), "a": str(vals.get(f"answer{i}", ""))})
    try:
        await M.answer(mid, answers)
    except Exception as exc:
        raise ValueError(f"the mission would not take that: {getattr(exc, 'text', exc)}")
    # Back to waiting on the same mission. A gated step was already approved once
    # and must not be asked about again.
    cur["status"] = "approved" if cur.get("gate") else "pending"
    cur["note"], cur["needs"] = "", []
    _save_run(run)
    return await _carry_on(a, run, wait)


class NeedsYou(Exception):
    """A step stopped because the person has to answer something.

    This is not a failure and it is not success, and the lack of a third option
    is what made the hole: `_step_mission` waited for a mission to stop being
    `running`, and a mission that stops to ask a question is not running. It
    therefore counted as done, the automation carried on as though the work had
    happened, and the question was abandoned where nobody would ever see it.

    Raising this parks the whole run instead, carrying the question and a link
    to whatever is asking it, so the automations page and TALK can both put it
    in front of you and the run can be picked up again afterwards.
    """

    def __init__(self, question: str, *, mission: str = "", kind: str = "awaiting_approval",
                 needs: "list[dict] | None" = None):
        super().__init__(question)
        self.question = question
        self.mission = mission
        self.kind = kind if kind in WAITING else "awaiting_approval"
        self.needs = needs or []


def _known_facts() -> dict:
    """What the hub has been told about the person, as values a step may use.

    A step that needs `location` should not ask for it every run when the hub
    has been told. Same keys, same `{{key}}` placeholders; only the source of
    the value is new.
    """
    try:
        from . import user_facts as F
        return {k: v["value"] for k, v in F.load().items()
                if isinstance(v, dict) and str(v.get("value") or "").strip()}
    except Exception:
        return {}


async def _advance(a: dict, run: dict) -> dict:
    """Run steps from wherever this run got to, stopping at the next gate."""
    steps_def = run.get("snapshot") or a["steps"]
    by_id = {s["id"]: s for s in steps_def}
    for rs in run["steps"]:
        if rs["status"] in ("done", "skipped"):
            continue
        step = by_id.get(rs["id"])
        if not step:
            rs["status"], rs["note"] = "failed", "this step is no longer in the automation"
            run["status"], run["ended"] = "failed", time.time()
            _save_run(run)
            return run
        # What was told about the person fills in beneath what this run was given.
        have = {**_known_facts(), **(run.get("values") or {})}
        # Asking for a value comes before asking permission: there is no sense
        # confirming a step nobody can run yet.
        gaps = missing(step, have)
        if gaps:
            rs["status"] = "awaiting_input"
            rs["note"] = "needs " + ", ".join(g["label"] for g in gaps)
            rs["needs"] = gaps
            run["status"] = "awaiting_input"
            _save_run(run)
            logger.info("automations: run %s needs %s", run["id"],
                        ", ".join(g["key"] for g in gaps))
            return run
        # A gate stops *before* the step runs: the point is to ask first.
        if rs.get("gate") and rs["status"] != "approved":
            rs["status"] = "awaiting_approval"
            rs["note"] = step.get("gate_note") or "waiting for you"
            run["status"] = "awaiting_approval"
            _save_run(run)
            logger.info("automations: run %s waiting at step %s", run["id"], rs["id"])
            return run
        rs["status"] = "running"
        _save_run(run)
        try:
            note = await _run_step(fill(step, have), run)
            rs["status"], rs["note"] = "done", note
        except NeedsYou as ask:
            # Parked, not finished and not failed. `waiting_on` is what lets the
            # page offer a link straight to the thing that is asking.
            rs["status"], rs["note"] = ask.kind, ask.question[:300]
            rs["needs"] = ask.needs
            if ask.mission:
                rs["mission"] = ask.mission
                run["mission"] = ask.mission
            run["status"] = ask.kind
            run["waiting_on"] = ask.question[:300]
            _save_run(run)
            logger.info("automations: run %s is waiting on %s", run["id"], ask.mission or "you")
            events.publish("mission.needs_you", {"run": run["id"], "mission": ask.mission,
                                                 "question": ask.question[:300]})
            return run
        except Exception as exc:
            rs["status"], rs["note"] = "failed", f"{exc.__class__.__name__}: {exc}"[:300]
            run["status"], run["ended"] = "failed", time.time()
            _save_run(run)
            logger.warning("automations: run %s failed at %s: %s", run["id"], rs["id"], exc)
            _finished(run, "failed")
            return run
        _save_run(run)
    run["status"], run["ended"] = "done", time.time()
    run.pop("waiting_on", None)
    _save_run(run)
    _finished(run, "done")
    return run


# Step kinds are dispatched through a table, so adding one is a function rather
# than another branch inside the runner. Each returns a short line for the record.
async def _run_step(step: dict, run: dict) -> str:
    return await _STEPS[step["kind"]](step, run)


def _project(name: str) -> dict:
    """Find a project the way a mission does - by discovery, not by source row.

    A source is a folder you added; a project is what the hub finds inside it.
    Matching only sources meant any project living in a collection - which is
    most of them - could not be named by an automation step.
    """
    from ..agent_knowledge.projects import discover_projects
    for p in discover_projects():
        if name in (p.get("slug"), p.get("name"), p.get("path")):
            if p.get("readonly"):
                raise ValueError(f"{name!r} is read-only; missions cannot run on it")
            return {"slug": p["slug"], "name": p["name"], "path": p["path"]}
    raise ValueError(f"no project called {name!r}")


def _mission_question(m) -> str:
    """What this mission is actually asking, in the person's words where possible."""
    qs = [q for q in (getattr(m, "questions", None) or []) if q]
    if qs:
        first = qs[0]
        text = first.get("q") if isinstance(first, dict) else str(first)
        more = f" (+{len(qs) - 1} more)" if len(qs) > 1 else ""
        return f"{m.project_name}: {str(text)[:160]}{more}"
    if m.status == "awaiting_review":
        return f"{m.project_name}: the work is ready to review — apply it or discard it"
    return f"{m.project_name}: waiting for you"


def _mission_needs(m) -> "list[dict]":
    """A mission's questions as values this run can be given, so they can be
    answered from the automations page without leaving for the mission board."""
    out = []
    for i, q in enumerate(getattr(m, "questions", None) or [], 1):
        text = q.get("q") if isinstance(q, dict) else str(q)
        why = (q.get("why") or "") if isinstance(q, dict) else ""
        out.append({"key": f"answer{i}", "label": str(text)[:120], "why": str(why)[:160]})
    return out[:6]


async def _step_mission(step: dict, run: dict) -> str:
    """Run a mission as one step - or attach to the one this run already has.

    The mission id is written to the run the moment it exists, *before* anything
    waits. Everything that later continues the run (an answer, an approval, a
    restart) then acts on that id. Without it, continuing re-entered this
    function and dispatched a second mission while the first sat waiting.
    """
    from . import missions as M
    rs = next((x for x in run["steps"] if x["id"] == step.get("id")), None)
    mid = (rs or {}).get("mission")
    if mid:
        m = M.S.m.get(mid)
        if not m:
            raise RuntimeError(f"mission {mid}, which this run was waiting on, is gone")
    else:
        m = await M.dispatch(_project(step["project"]), step["brief"],
                             agent=step.get("agent") or "orchestrator",
                             kind=step.get("agent_kind") or "orchestrator",
                             model=step.get("model") or None,
                             agents=step.get("agents") or None,
                             runtime=step.get("runtime") or "opencode",
                             profile=step.get("profile") or "code",
                             reference=bool(step.get("reference")),
                             autonomy="auto")
        if rs is not None:
            rs["mission"] = m.id
        run["mission"] = m.id
        _save_run(run)
    if not step.get("wait", True):
        return f"dispatched {m.id} (not waited for)"
    deadline = time.time() + float(step.get("timeout", 1800))
    hold_since = None
    while time.time() < deadline:
        await asyncio.sleep(2)
        cur = M.S.m.get(m.id)
        if not cur:
            raise RuntimeError(f"mission {m.id} disappeared")
        kind = mission_outcome(cur.status)
        if kind == "working":
            hold_since = None
            continue
        if kind == "good":
            return f"mission {m.id} -> {cur.status}"
        if kind == "dead":
            raise RuntimeError(f"mission {m.id} ended {cur.status}")
        if kind == "ask":
            raise NeedsYou(_mission_question(cur), mission=m.id, kind="awaiting_input",
                           needs=_mission_needs(cur))
        if kind == "review":
            raise NeedsYou(_mission_question(cur), mission=m.id, kind="awaiting_approval")
        if cur.status == "plan_ready":
            # An automation's missions plan and run themselves; this is the
            # moment between. Give it a few seconds before calling it a wait.
            hold_since = hold_since or time.time()
            if time.time() - hold_since < 20:
                continue
        raise NeedsYou(f"{cur.project_name}: {cur.status} - carry on from the missions board",
                       mission=m.id, kind="awaiting_approval")
    raise TimeoutError(f"mission {m.id} did not finish in time")


async def _step_hub(step: dict, run: dict) -> str:
    """Call one of the Hub's own endpoints.

    The call goes over loopback carrying a scoped token rather than straight into
    the handler, so it passes the same security middleware as every other caller
    instead of through a private back door that would drift from it. The path is
    also checked against the allowlist the capability list is generated from, so
    an automation cannot reach an endpoint nobody meant to be automated.
    """
    from . import capabilities as C
    path, method = str(step["path"]), str(step.get("method", "GET")).upper()
    why = C.refuse(method, path)
    if why:
        raise PermissionError(why)
    return await C.call(method, path, step.get("body") or {})


async def _step_routine(step: dict, run: dict) -> str:
    """Replay something recorded once, for a program with no interface but its own.

    A disabled routine is refused rather than attempted: a routine gets disabled
    because it stopped matching the screen, and running it anyway is how an
    automation clicks the wrong thing.
    """
    from . import machine_routines as R
    from . import pc_control as PC
    with PC._db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (step["routine"],)).fetchone()
    if not row:
        raise ValueError(f"no recorded routine {step['routine']!r} - record it first")
    routine = dict(row)
    if routine.get("status") == "disabled":
        raise RuntimeError(f"routine {routine.get('title') or step['routine']!r} is disabled")
    if routine.get("tool") != "surface":
        raise ValueError("only a recorded (surface) routine can be an automation step")
    res = await R.replay_machine_routine(routine, request=f"automation {run['id']}")
    if not res.get("ok", False):
        raise RuntimeError(res.get("why") or res.get("error") or "the routine did not complete")
    return res.get("summary") or "routine replayed"


_STEPS = {"mission": _step_mission, "hub": _step_hub, "routine": _step_routine}


def from_mission(m, name: str = "", every: str = "") -> dict:
    """Keep a mission that worked, as something you can run again.

    The pattern both Goose and OpenHands have and the Hub did not: you watch
    something work, and the moment you want it repeated is right then - not
    later, in a builder, from memory. The brief becomes a step; a trigger is
    optional, because "again, when I say" is a perfectly good automation.

    The way it ran is kept with it: runtime, profile, model, team and wiki
    reference. Dropping them meant "again" ran a different thing from the one
    that had just worked.
    """
    brief = (getattr(m, "brief", "") or "").strip()
    if not brief:
        raise ValueError("that ask has no brief to keep")
    slug = getattr(m, "project_slug", "") or getattr(m, "project_name", "")
    if not slug:
        raise ValueError("that ask has no project to run against")
    trigger = ({"kind": "schedule", "every": every, "at": "09:00"} if every
               else {"kind": "manual"})
    step = {"kind": "mission", "project": slug, "brief": brief,
            "agent": getattr(m, "agent", "") or "orchestrator",
            "agent_kind": getattr(m, "kind", "") or "orchestrator"}
    for field, default in (("runtime", "opencode"), ("profile", "code"), ("model", None),
                           ("agents", None), ("reference", False)):
        v = getattr(m, field, default)
        if v and v != default:
            step[field] = list(v) if isinstance(v, (list, tuple)) else v
    return save({"name": (name or brief)[:60], "trigger": trigger, "steps": [step]})


# -- triggers ------------------------------------------------------------------
def due(a: dict, now: float) -> float:
    """When this scheduled automation next runs. Reuses the mission scheduler's
    clock arithmetic so "daily at 09:00" means the same thing in both places."""
    from .schedule import next_after
    return next_after(dict(a["trigger"], at=a["trigger"].get("at", "09:00")), now)


def _bump_next(schedule: "dict[str, float]") -> None:
    """Write back only the recomputed next-run times, onto what is on disk NOW.

    `tick` used to hold the whole automations list across its awaits and then
    save that snapshot. Starting a due automation is an await, so anything
    created, edited or deleted in the meantime was silently overwritten by the
    stale copy - an automation saved at the wrong moment simply vanished, and
    the run it had already started was left pointing at nothing.

    Writing back just the field this function owns means a concurrent save can
    no longer be lost.
    """
    rows = load()
    touched = False
    for r in rows:
        want = schedule.get(r.get("id"))
        if want is not None and r.get("next") != want:
            r["next"] = want
            touched = True
    if touched:
        _save(rows)


async def tick(now: "float | None" = None) -> "list[str]":
    """Start every scheduled automation that is due. Returns the run ids."""
    now = now or time.time()
    started, schedule = [], {}
    for a in load():
        if not a.get("enabled", True) or (a.get("trigger") or {}).get("kind") != "schedule":
            continue
        nxt = a.get("next") or due(a, now)
        if nxt > now:
            schedule[a["id"]] = nxt
            continue
        try:
            run = await start(a, why="on schedule")
            started.append(run["id"])
        except Exception as exc:
            logger.warning("automations: %s could not start: %s", a["id"], exc)
        schedule[a["id"]] = due(a, now)
    if schedule:
        _bump_next(schedule)
    return started


def _mission(mid: "str | None"):
    if not mid:
        return None
    try:
        from . import missions as M
        return M.S.m.get(mid)
    except Exception:
        return None


async def resume_after_mission(mid: str, status: str) -> None:
    """Move any run that is waiting on this mission to wherever it now is.

    Only an *accepted* result carries on. Reaching review is a decision for a
    person, not a finish: the first version treated every non-failure status as
    done, so a mission arriving at review ran the next step before APPLY.
    """
    kind = mission_outcome(status)
    if kind in ("working", "hold", "unknown"):
        return
    for r in waiting_runs():
        if r.get("mission") != mid:
            continue
        rs = next((s for s in r["steps"] if s.get("mission") == mid and s.get("status") in WAITING), None)
        if rs is None:
            continue
        a = get(r.get("automation") or "")
        if kind == "review":
            r["status"] = rs["status"] = "awaiting_approval"
            r["waiting_on"] = rs["note"] = (f"{(_mission(mid) and _mission(mid).project_name) or 'the ask'}: "
                                             f"the work is ready to review - apply it or discard it")[:300]
            rs["needs"] = []
            _save_run(r)
            continue
        if kind == "ask":
            m = _mission(mid)
            r["status"] = rs["status"] = "awaiting_input"
            if m is not None:
                r["waiting_on"] = rs["note"] = _mission_question(m)[:300]
                rs["needs"] = _mission_needs(m)
            _save_run(r)
            continue
        if kind == "dead":
            rs["status"], rs["note"] = "failed", f"mission {mid} ended {status}"
            r["status"], r["ended"] = "failed", time.time()
            r.pop("waiting_on", None)
            _save_run(r)
            _finished(r, "failed")
            continue
        # good: accepted
        if not a:
            logger.info("automations: run %s was waiting on %s but its automation is gone", r["id"], mid)
            continue
        rs["status"], rs["note"] = "done", f"mission {mid} -> {status}"
        r["status"] = "running"
        r.pop("waiting_on", None)
        _save_run(r)
        logger.info("automations: resuming run %s now %s is %s", r["id"], mid, status)
        try:
            await _advance(a, r)
        except Exception as exc:
            logger.warning("automations: run %s could not resume: %s", r["id"], exc)


async def reconcile() -> int:
    """After a restart: decide what every run that was mid-flight now is.

    A run marked `running` has no worker once the hub has restarted. Leaving it
    is a lie, and replaying it blindly may repeat something that already
    happened - an upload, a click. So: a run waiting on a mission reattaches to
    that mission; anything else is parked with a plain question, and nothing is
    re-run until a person says so.
    """
    n = 0
    for r in _read(RUNS, []):
        if r.get("status") != "running":
            continue
        n += 1
        a = get(r.get("automation") or "")
        cur = next((s for s in r["steps"] if s.get("status") == "running"), None) \
            or next((s for s in r["steps"] if s.get("status") not in ("done", "skipped")), None)
        if cur is None:
            r["status"], r["ended"] = "done", time.time()
            _save_run(r)
            continue
        mid = cur.get("mission") or r.get("mission")
        m = _mission(mid)
        if mid and m is not None and a:
            kind = mission_outcome(m.status)
            if kind == "working":
                cur["status"] = "approved" if cur.get("gate") else "pending"
                cur["mission"] = mid
                _save_run(r)
                await _carry_on(a, r, wait=False)
                continue
            cur["status"], cur["mission"] = "awaiting_approval", mid
            r["status"], r["mission"] = "awaiting_approval", mid
            _save_run(r)
            await resume_after_mission(mid, m.status)
            continue
        cur["status"] = "awaiting_approval"
        cur["note"] = ("interrupted by a restart while this step was running. Running it again "
                       "may repeat what it already did - approve to run it again, or decline")
        r["status"] = "awaiting_approval"
        r["waiting_on"] = cur["note"]
        _save_run(r)
    if n:
        logger.info("automations: reconciled %d run(s) left running by a restart", n)
    return n


async def on_event(ev: dict) -> None:
    """Run every automation listening for this event.

    An automation never triggers on its own completion, and a chain of them is
    cut at `MAX_CHAIN`. Both depend on the completion event saying which
    automation it was and what led to it - which it now does.
    """
    # Before anything is triggered: carry on whatever was waiting on this.
    if ev.get("kind") == "mission.finished":
        payload = ev.get("payload") or {}
        if payload.get("mission"):
            await resume_after_mission(str(payload["mission"]), str(payload.get("status") or ""))

    payload = ev.get("payload") or {}
    chain = list(payload.get("chain") or []) if ev.get("kind") == "automation.finished" else []
    for a in load():
        trig = a.get("trigger") or {}
        if not a.get("enabled", True) or trig.get("kind") != "event":
            continue
        if trig.get("event") != ev.get("kind"):
            continue
        if ev.get("kind") == "automation.finished":
            if a["id"] == payload.get("automation") or a["id"] in chain:
                continue
            if len(chain) >= MAX_CHAIN:
                logger.info("automations: not starting %s - chain is already %d long", a["id"], len(chain))
                continue
        try:
            what = event_summary(ev)
            await start(a, why=f"after {ev['kind']}" + (f" \u2014 {what}" if what else ""),
                        values=event_values(ev), chain=chain)
        except Exception as exc:
            logger.warning("automations: %s failed on %s: %s", a["id"], ev.get("kind"), exc)


# -- http ----------------------------------------------------------------------
def _view(a: dict) -> dict:
    last = (runs(a["id"], limit=1) or [None])[0]
    return {**a, "last_run": last, "next": a.get("next")}


@routes.get("/api/automations")
async def api_list(request: web.Request) -> web.Response:
    """Every automation, with how its last run went."""
    return web.json_response({
        "automations": [_view(a) for a in load()],
        "events": events.KINDS,
        "recent_events": events.recent()[:10],
        "waiting": waiting_runs(),
    })


@routes.post("/api/automations")
async def api_save(request: web.Request) -> web.Response:
    """Create or update an automation."""
    try:
        return web.json_response(save(await request.json()))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.delete("/api/automations/{id}")
async def api_delete(request: web.Request) -> web.Response:
    if not delete(request.match_info["id"]):
        raise web.HTTPNotFound(text="no such automation")
    return web.json_response({"ok": True})


@routes.delete("/api/automations/runs/{rid}")
async def api_forget_run(request: web.Request) -> web.Response:
    try:
        if not forget_run(request.match_info["rid"]):
            raise web.HTTPNotFound(text="no such run")
    except ValueError as exc:
        raise web.HTTPConflict(text=str(exc))
    return web.json_response({"ok": True})


@routes.post("/api/automations/{id}/run")
async def api_run(request: web.Request) -> web.Response:
    """Run one now - the only safe way to try an automation before a trigger fires it."""
    a = get(request.match_info["id"])
    if not a:
        raise web.HTTPNotFound(text="no such automation")
    return web.json_response(await start(a, why="run by you"))


@routes.post("/api/automations/from-mission/{mid}")
async def api_from_mission(request: web.Request) -> web.Response:
    """Keep a finished ask as an automation you can run again."""
    from . import missions as M
    m = M.S.m.get(request.match_info["mid"])
    if not m:
        raise web.HTTPNotFound(text="no such ask")
    try:
        b = await request.json()
    except Exception:
        b = {}
    try:
        return web.json_response(from_mission(m, str(b.get("name") or ""), str(b.get("every") or "")))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.post("/api/automations/runs/{rid}/provide")
async def api_provide(request: web.Request) -> web.Response:
    """Give a waiting run the values it asked for."""
    try:
        b = await request.json()
    except Exception:
        b = {}
    try:
        return web.json_response(await provide(request.match_info["rid"], b.get("values") or {},
                                               remember=b.get("remember") or [], wait=False))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.get("/api/automations/runs")
async def api_runs(request: web.Request) -> web.Response:
    return web.json_response(runs(request.query.get("id") or None))


@routes.post("/api/automations/runs/{rid}/approve")
async def api_approve(request: web.Request) -> web.Response:
    """Answer the gate a run is waiting on."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    try:
        return web.json_response(await approve(request.match_info["rid"], bool(body.get("ok", True)),
                                               wait=False))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


async def _loop() -> None:
    while True:
        try:
            await tick()
        except Exception as exc:
            logger.warning("automation loop: %s", exc)
        await asyncio.sleep(30)


def setup(app: web.Application) -> None:
    from . import capabilities as C
    C.remember_app(app)
    # Rewrite the "what the Hub can do" skill from the routes that exist on this
    # build, before anything publishes the skill library.
    from ..agent_knowledge import hub_skill
    hub_skill.refresh(app)
    for kind in events.KINDS:
        events.subscribe(kind, on_event)

    async def _start(_app):
        try:
            await reconcile()
        except Exception as exc:
            logger.warning("automations: could not reconcile after restart: %s", exc)
        _app["automation_task"] = asyncio.create_task(_loop())

    async def _stop(_app):
        t = _app.get("automation_task")
        if t:
            t.cancel()

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
