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
import json
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
# its own is what lets the board say "2 waiting for you" honestly.
TERMINAL = ("done", "failed", "stopped")


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
    rows = sorted(rows, key=lambda r: r.get("started", 0), reverse=True)[:MAX_RUNS]
    write_json(RUNS, rows)


def get(aid: str) -> "dict | None":
    return next((a for a in load() if a.get("id") == aid), None)


def get_run(rid: str) -> "dict | None":
    return next((r for r in _read(RUNS, []) if r.get("id") == rid), None)


# -- validation ---------------------------------------------------------------
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
    _save([r for r in rows if r["id"] != aid] + [row])
    logger.info("automations: saved %s (%s)", aid, row["name"])
    return row


def delete(aid: str) -> bool:
    rows = load()
    keep = [r for r in rows if r.get("id") != aid]
    if len(keep) == len(rows):
        return False
    _save(keep)
    return True


# -- running ------------------------------------------------------------------
def _new_run(a: dict, why: str) -> dict:
    return {
        "id": "r" + uuid.uuid4().hex[:8],
        "automation": a["id"],
        "name": a["name"],
        "why": why,                       # what started it, in words
        "started": time.time(),
        "ended": None,
        "status": "running",
        "steps": [{"id": s["id"], "kind": s["kind"], "status": "pending",
                   "gate": bool(s.get("gate")), "note": ""} for s in a["steps"]],
    }


async def start(a: dict, why: str = "run by you") -> dict:
    """Begin a run. Returns when it finishes **or reaches a gate**."""
    run = _new_run(a, why)
    _save_run(run)                        # on disk before anything happens
    return await _advance(a, run)


async def approve(rid: str, ok: bool = True) -> dict:
    """Answer the gate a run is waiting on, and carry on - or stop."""
    run = get_run(rid)
    if not run or run["status"] != "awaiting_approval":
        raise ValueError("that run is not waiting for approval")
    a = get(run["automation"])
    if not a:
        raise ValueError("the automation behind that run is gone")
    cur = next((s for s in run["steps"] if s["status"] == "awaiting_approval"), None)
    if not ok:
        if cur:
            cur["status"], cur["note"] = "skipped", "you declined this step"
        run["status"], run["ended"] = "stopped", time.time()
        _save_run(run)
        events.publish("automation.finished", {"run": run["id"], "status": "stopped"})
        return run
    if cur:
        cur["status"], cur["note"] = "approved", "you approved this step"
    _save_run(run)
    return await _advance(a, run)


async def _advance(a: dict, run: dict) -> dict:
    """Run steps from wherever this run got to, stopping at the next gate."""
    by_id = {s["id"]: s for s in a["steps"]}
    for rs in run["steps"]:
        if rs["status"] in ("done", "skipped"):
            continue
        step = by_id.get(rs["id"])
        if not step:
            rs["status"], rs["note"] = "failed", "this step is no longer in the automation"
            run["status"], run["ended"] = "failed", time.time()
            _save_run(run)
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
            note = await _run_step(step, run)
            rs["status"], rs["note"] = "done", note
        except Exception as exc:
            rs["status"], rs["note"] = "failed", f"{exc.__class__.__name__}: {exc}"[:300]
            run["status"], run["ended"] = "failed", time.time()
            _save_run(run)
            logger.warning("automations: run %s failed at %s: %s", run["id"], rs["id"], exc)
            events.publish("automation.finished", {"run": run["id"], "status": "failed"})
            return run
        _save_run(run)
    run["status"], run["ended"] = "done", time.time()
    _save_run(run)
    events.publish("automation.finished", {"run": run["id"], "status": "done"})
    return run


# Step kinds are dispatched through a table, so adding one is a function rather
# than another branch inside the runner. Each returns a short line for the record.
async def _run_step(step: dict, run: dict) -> str:
    return await _STEPS[step["kind"]](step, run)


def _project(name: str) -> dict:
    from .. import locations
    for s in locations.sources():
        if name in (s.get("slug"), s.get("name"), s.get("path")):
            return {"slug": s.get("slug") or name, "name": s.get("name") or name,
                    "path": s.get("path")}
    raise ValueError(f"no project called {name!r}")


async def _step_mission(step: dict, run: dict) -> str:
    from . import missions as M
    m = await M.dispatch(_project(step["project"]), step["brief"],
                         agent=step.get("agent") or "orchestrator",
                         kind=step.get("agent_kind") or "orchestrator",
                         autonomy="auto")
    if not step.get("wait", True):
        return f"dispatched {m.id} (not waited for)"
    deadline = time.time() + float(step.get("timeout", 1800))
    while time.time() < deadline:
        await asyncio.sleep(2)
        cur = M.S.m.get(m.id)
        if cur and cur.status not in ("running", "queued", "blocked"):
            if cur.status in ("failed", "timed_out", "stopped"):
                raise RuntimeError(f"mission {m.id} ended {cur.status}")
            return f"mission {m.id} -> {cur.status}"
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


# -- triggers ------------------------------------------------------------------
def due(a: dict, now: float) -> float:
    """When this scheduled automation next runs. Reuses the mission scheduler's
    clock arithmetic so "daily at 09:00" means the same thing in both places."""
    from .schedule import next_after
    return next_after(dict(a["trigger"], at=a["trigger"].get("at", "09:00")), now)


async def tick(now: "float | None" = None) -> "list[str]":
    """Start every scheduled automation that is due. Returns the run ids."""
    now = now or time.time()
    started, rows, changed = [], load(), False
    for a in rows:
        if not a.get("enabled", True) or (a.get("trigger") or {}).get("kind") != "schedule":
            continue
        nxt = a.get("next") or due(a, now)
        if nxt > now:
            a["next"] = nxt
            changed = True
            continue
        try:
            run = await start(a, why="on schedule")
            started.append(run["id"])
        except Exception as exc:
            logger.warning("automations: %s could not start: %s", a["id"], exc)
        a["next"] = due(a, now)
        changed = True
    if changed:
        _save(rows)
    return started


async def on_event(ev: dict) -> None:
    """Run every automation listening for this event.

    An automation never triggers on its own completion, however it is wired: that
    is the one loop that would run forever without anybody asking it to.
    """
    for a in load():
        trig = a.get("trigger") or {}
        if not a.get("enabled", True) or trig.get("kind") != "event":
            continue
        if trig.get("event") != ev.get("kind"):
            continue
        if ev.get("kind") == "automation.finished" and \
           (ev.get("payload") or {}).get("automation") == a["id"]:
            continue
        try:
            await start(a, why=f"after {ev['kind']}")
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
        "waiting": [r for r in runs(limit=50) if r["status"] == "awaiting_approval"],
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


@routes.post("/api/automations/{id}/run")
async def api_run(request: web.Request) -> web.Response:
    """Run one now - the only safe way to try an automation before a trigger fires it."""
    a = get(request.match_info["id"])
    if not a:
        raise web.HTTPNotFound(text="no such automation")
    return web.json_response(await start(a, why="run by you"))


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
        return web.json_response(await approve(request.match_info["rid"], bool(body.get("ok", True))))
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
        _app["automation_task"] = asyncio.create_task(_loop())

    async def _stop(_app):
        t = _app.get("automation_task")
        if t:
            t.cancel()

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
