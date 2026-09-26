"""TALK PC-control router: a small, auditable routine store over Windows MCP."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import sqlite3
import time
from pathlib import Path

from aiohttp import web

from ..runtime import STATE
from . import mcp as MCP

routes = web.RouteTableDef()
# Learned routines are per-machine state, not part of the program.
DB_PATH = STATE / "data" / "pc_control.sqlite"


def canonical_app_name(value: str) -> str:
    """Normalise spoken app names before they become routine parameters or keys."""
    app = " ".join((value or "").casefold().split())
    app = __import__("re").sub(r"^(?:the )|(?: for me| please| app| application)$", "", app).strip()
    return app[:80]


def display_app_name(app: str) -> str:
    return " ".join(part.capitalize() for part in canonical_app_name(app).split())


def classify_request(text: str) -> dict | None:
    """Classify transcribed speech into a task before any routine is looked up."""
    import re
    t = " ".join((text or "").casefold().split())
    m = re.fullmatch(r"(?:please )?(?:open|launch|start)(?: up)? (?:the )?([a-z][a-z0-9 '&.-]{1,78})(?: please)?", t)
    if not m:
        return None
    app = canonical_app_name(m.group(1))
    return {"kind": "launch_app", "app": app, "intent": _intent(app)} if len(app) >= 2 else None


def _consolidate_launch_routines(db: sqlite3.Connection) -> None:
    """Merge pre-classifier routine keys such as 'open:outlook for me' into 'open:outlook'."""
    rows = list(db.execute("SELECT * FROM pc_routines WHERE tool='App'"))
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        try:
            app = canonical_app_name(json.loads(row["args_json"]).get("name", ""))
        except Exception:
            continue
        if app:
            groups.setdefault(_intent(app), []).append(row)
    for intent, same in groups.items():
        if len(same) == 1 and same[0]["intent"] == intent:
            continue
        same.sort(key=lambda r: (r["intent"] != intent, r["created"]))
        keep, rest = same[0], same[1:]
        app = intent.split(":", 1)[1]
        successes = sum(int(r["successes"]) for r in same)
        failures = sum(int(r["failures"]) for r in same)
        status = "trusted" if successes >= 2 else "candidate"
        args = json.dumps({"mode": "launch", "name": display_app_name(app)})
        signature = json.dumps({"kind": "start_menu_app", "name": display_app_name(app)})
        for row in rest:
            db.execute("DELETE FROM pc_routines WHERE id=?", (row["id"],))
        db.execute("UPDATE pc_routines SET intent=?,title=?,args_json=?,signature_json=?,status=?,successes=?,failures=?,updated=? WHERE id=?", (intent, f"Open {display_app_name(app)}", args, signature, status, successes, failures, time.time(), keep["id"]))


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS pc_runs (
              id INTEGER PRIMARY KEY, created REAL NOT NULL, request TEXT NOT NULL,
              route TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pc_routines (
              id TEXT PRIMARY KEY, intent TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
              tool TEXT NOT NULL, args_json TEXT NOT NULL, signature_json TEXT NOT NULL,
              status TEXT NOT NULL, successes INTEGER NOT NULL DEFAULT 0,
              failures INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pc_steps (
              id INTEGER PRIMARY KEY, routine_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
              tool TEXT NOT NULL, args_json TEXT NOT NULL, target_json TEXT NOT NULL,
              created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pc_steps_routine ON pc_steps(routine_id, ordinal);
        """)
        # 'mcp' = driven through Windows MCP and resolved semantically.
        # 'machine' = recorded from the screen surface (Phase 3); not written yet.
        if "kind" not in {c[1] for c in db.execute("PRAGMA table_info(pc_routines)")}:
            db.execute("ALTER TABLE pc_routines ADD COLUMN kind TEXT NOT NULL DEFAULT 'mcp'")
        _consolidate_launch_routines(db)
        db.execute("UPDATE pc_routines SET status='trusted', updated=? WHERE status='candidate' AND successes>=2", (time.time(),))
        yield db
        db.commit()
    finally:
        db.close()


def _intent(app: str) -> str:
    return "open:" + canonical_app_name(app)


def _record_run(request: str, route: str, status: str, detail: str) -> None:
    with _db() as db:
        db.execute("INSERT INTO pc_runs(created,request,route,status,detail) VALUES(?,?,?,?,?)", (time.time(), request, route, status, detail[:1000]))


def _remember_launch(app: str, success: bool) -> dict:
    intent = _intent(app); now = time.time()
    rid = hashlib.sha256(intent.encode()).hexdigest()[:16]
    args = {"mode": "launch", "name": display_app_name(app)}
    signature = {"kind": "start_menu_app", "name": display_app_name(app)}
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, updated=? WHERE id=?", (int(success), int(not success), now, row["id"]))
            return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())
        if not success:
            return None
        db.execute("INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,successes,failures,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (rid, intent, f"Open {display_app_name(app)}", "App", json.dumps(args), json.dumps(signature), "candidate", 1, 0, now, now))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


def _routine(intent: str) -> dict | None:
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE intent=? AND status!='disabled'", (intent,)).fetchone()
    return dict(row) if row else None


async def launch_app(app: str, request: str) -> dict:
    """Run a learned or first-seen Start Menu application launch through MCP App."""
    app = canonical_app_name(app)
    if len(app) < 2:
        return {"ok": False, "say": "Tell me which application to open."}
    known = _routine(_intent(app))
    args = json.loads(known["args_json"]) if known else {"mode": "launch", "name": app}
    route = "routine" if known else "discovery"
    try:
        result = await MCP.call_tool("windows", "App", args)
    except Exception as exc:
        _record_run(request, route, "failed", str(exc))
        _remember_launch(app, False)
        return {"ok": False, "say": f"I could not open {app}: {str(exc)[:150]}."}
    routine = _remember_launch(app, True)
    _record_run(request, route, "done", " ".join(result.get("text") or []))
    state = "using the learned routine" if known else "and saved this as a candidate routine"
    return {"ok": True, "say": f"Opened {display_app_name(app)}.", "routine": {"id": routine["id"], "status": routine["status"], "successes": routine["successes"], "tag": "ROUTINE"}}


# ── reading the screen ───────────────────────────────────────────────────────────────────────────────────────────────
# Windows MCP renders its accessibility tree as text, one element per line:
#     window "Untitled - Notepad"
#     +-- (123,456) button "Save"  [action: click]
# There is no stable id in that output, so an element is identified by what it is.
_WINDOW_RX = __import__("re").compile(r'^\s*window "(.*)"\s*$')
_ELEMENT_RX = __import__("re").compile(
    r'^[^()]*?\((\d+)\s*,\s*(\d+)\)\s+(\S+)\s+"(.*?)"\s+\[action:\s*([a-z]+)\]')


def parse_snapshot(text: str) -> list[dict]:
    """Every interactive element the snapshot listed, with its window and centre."""
    out, window = [], ""
    for line in (text or "").splitlines():
        w = _WINDOW_RX.match(line)
        if w:
            window = w.group(1)
            continue
        m = _ELEMENT_RX.match(line)
        if m:
            x, y, control, name, action = m.groups()
            out.append({"window": window, "control": control.lower(), "name": name,
                        "x": int(x), "y": int(y), "action": action})
    return out


def ui_signature(elements: list[dict], window: str) -> dict:
    """What this screen looked like, in a form that survives it being moved or resized.

    Names and control types only - never coordinates, so dragging the window does
    not invalidate the routine, while the dialog changing underneath it does.
    """
    same = sorted(f"{e['control']}|{e['name']}" for e in elements if e["window"] == window)
    digest = hashlib.sha256("\n".join(same).encode("utf-8")).hexdigest()[:16]
    return {"kind": "ui", "window": window, "controls": len(same), "fingerprint": digest}


async def _snapshot() -> list[dict]:
    result = await MCP.call_tool("windows", "Snapshot", {"use_vision": False})
    return parse_snapshot(" ".join(result.get("text") or []))


def _match(elements: list[dict], target: dict) -> dict | None:
    """Find the element a step was recorded against, in a fresh snapshot.

    Exact window+control+name first; then the same control+name in any window,
    because a document title changes far more often than a button's label.
    """
    name, control = target.get("name", ""), (target.get("control") or "").lower()
    window = target.get("window", "")
    for e in elements:
        if e["name"] == name and e["control"] == control and e["window"] == window:
            return e
    for e in elements:
        if e["name"] == name and e["control"] == control:
            return e
    return None


# ── multi-step routines ──────────────────────────────────────────────────────────────────────────────────────────────
def _steps(routine_id: str) -> list[dict]:
    with _db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM pc_steps WHERE routine_id=? ORDER BY ordinal", (routine_id,))]


def save_ui_routine(intent: str, title: str, window: str, steps: list[dict],
                    signature: dict) -> dict:
    """Store a step sequence as a candidate routine. Replaces any steps it had."""
    now = time.time()
    rid = hashlib.sha256(intent.encode()).hexdigest()[:16]
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            rid = row["id"]
            db.execute("UPDATE pc_routines SET title=?,tool=?,signature_json=?,updated=? WHERE id=?",
                       (title, "ui", json.dumps(signature), now, rid))
            db.execute("DELETE FROM pc_steps WHERE routine_id=?", (rid,))
        else:
            db.execute(
                "INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,"
                "successes,failures,created,updated,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, intent, title, "ui", json.dumps({"window": window}),
                 json.dumps(signature), "candidate", 0, 0, now, now, "mcp"))
        for i, st in enumerate(steps):
            db.execute("INSERT INTO pc_steps(routine_id,ordinal,tool,args_json,target_json,created) "
                       "VALUES(?,?,?,?,?,?)",
                       (rid, i, st["tool"], json.dumps(st.get("args") or {}),
                        json.dumps(st.get("target") or {}), now))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


async def replay_ui_routine(routine: dict, request: str = "") -> dict:
    """Run a stored step sequence, but only onto the screen it was recorded against.

    Every refusal here is deliberate: a routine that cannot see what it expects
    must stop, never fall back to clicking where the control used to be.
    """
    stored = json.loads(routine["signature_json"] or "{}")
    steps = _steps(routine["id"])
    if not steps:
        return {"ok": False, "route": "fall-through", "say": "That routine has no steps saved."}

    elements = await _snapshot()
    live = ui_signature(elements, stored.get("window", ""))
    if live["fingerprint"] != stored.get("fingerprint"):
        _record_run(request, "fall-through", "skipped",
                    f"signature mismatch: expected {stored.get('fingerprint')}, saw {live['fingerprint']}")
        _remember_outcome(routine["id"], False)
        return {"ok": False, "route": "fall-through",
                "say": f"{routine['title']} was recorded on a different screen, so I did not touch it."}

    for step in steps:
        target = json.loads(step["target_json"] or "{}")
        args = dict(json.loads(step["args_json"] or "{}"))
        if target:
            found = _match(elements, target)
            if not found:
                _record_run(request, "fall-through", "skipped",
                            f"step {step['ordinal']}: no element {target.get('control')} \"{target.get('name')}\"")
                _remember_outcome(routine["id"], False)
                return {"ok": False, "route": "fall-through",
                        "say": f"I could not find \"{target.get('name')}\" on screen, so I stopped."}
            args["loc"] = [found["x"], found["y"]]
        try:
            await MCP.call_tool("windows", step["tool"], args)
        except Exception as exc:
            _record_run(request, "routine", "failed", f"step {step['ordinal']}: {exc}")
            _remember_outcome(routine["id"], False)
            return {"ok": False, "route": "routine", "say": f"{routine['title']} failed: {str(exc)[:150]}"}
        # The screen moved; anything resolved from the old snapshot is now a guess.
        elements = await _snapshot()

    updated = _remember_outcome(routine["id"], True)
    _record_run(request, "routine", "done", f"{len(steps)} step(s)")
    return {"ok": True, "route": "routine", "say": f"Ran {routine['title']}.",
            "routine": {"id": routine["id"], "status": updated["status"],
                        "successes": updated["successes"], "tag": "ROUTINE"}}


def _remember_outcome(routine_id: str, success: bool) -> dict:
    """Same promotion rule as launches: two clean runs earn trust, a failure disables."""
    with _db() as db:
        db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, updated=? WHERE id=?",
                   (int(success), int(not success), time.time(), routine_id))
        if not success:
            db.execute("UPDATE pc_routines SET status='disabled', updated=? WHERE id=? AND status='candidate'",
                       (time.time(), routine_id))
        else:
            # Promote in the same transaction. _db() also does this on open, but that
            # would not run until the next call, so the status handed back to the
            # caller would describe the run before this one.
            db.execute("UPDATE pc_routines SET status='trusted', updated=? "
                       "WHERE id=? AND status='candidate' AND successes>=2", (time.time(), routine_id))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (routine_id,)).fetchone())


@routes.get("/api/pc/routines")
async def api_routines(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT id,intent,title,tool,kind,args_json,status,successes,failures,created,updated FROM pc_routines ORDER BY updated DESC")]
        counts = {r["routine_id"]: r["n"] for r in db.execute(
            "SELECT routine_id, COUNT(*) AS n FROM pc_steps GROUP BY routine_id")}
        scores = {}
        for s in db.execute("SELECT routine_id, target_json FROM pc_steps"):
            try:
                v = json.loads(s["target_json"] or "{}").get("last_score")
            except ValueError:
                v = None
            if v is not None:
                scores.setdefault(s["routine_id"], []).append(float(v))
        for r in rows:
            r["steps"] = counts.get(r["id"], 0)
            try:
                r["profile"] = json.loads(r.pop("args_json", "") or "{}").get("profile")
            except ValueError:
                r["profile"] = None
            seen = scores.get(r["id"]) or []
            r["lowest_match"] = min(seen) if seen else None
            r["matched"] = len(seen)
    return web.json_response({"routines": rows})


@routes.get("/api/pc/runs")
async def api_runs(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM pc_runs ORDER BY id DESC LIMIT 30")]
    return web.json_response({"runs": rows})


@routes.get("/api/pc/snapshot")
async def api_snapshot(request: web.Request) -> web.Response:
    """What is on screen right now, parsed. Reads; clicks nothing."""
    try:
        elements = await _snapshot()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"Snapshot failed: {str(exc)[:200]}")
    windows = sorted({e["window"] for e in elements if e["window"]})
    return web.json_response({"elements": elements, "windows": windows,
                              "signatures": {w: ui_signature(elements, w) for w in windows}})


@routes.post("/api/pc/routines")
async def api_save_routine(request: web.Request) -> web.Response:
    """Record a UI routine: {intent, title, window, steps:[{tool,args,target}]}.

    The signature is taken from the screen as it is NOW, which is the screen the
    caller just drove - that is what makes the replay check meaningful.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    intent = " ".join(str(body.get("intent", "")).split())[:120]
    title = " ".join(str(body.get("title", "")).split())[:120] or intent
    window = str(body.get("window", ""))
    steps = body.get("steps") or []
    if not intent or not steps:
        raise web.HTTPBadRequest(text="intent and at least one step are required")
    allowed = {"Click", "Type", "Shortcut", "Scroll", "Wait", "App"}
    for st in steps:
        if not isinstance(st, dict) or st.get("tool") not in allowed:
            raise web.HTTPBadRequest(text=f"each step needs a tool from {sorted(allowed)}")
    try:
        elements = await _snapshot()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"Snapshot failed: {str(exc)[:200]}")
    if window and window not in {e["window"] for e in elements}:
        raise web.HTTPBadRequest(text=f"no window named {window!r} is on screen to record against")
    saved = save_ui_routine(intent, title, window, steps, ui_signature(elements, window))
    return web.json_response({"ok": True, "routine": saved, "steps": len(steps)})


@routes.post("/api/pc/routines/{id}/run")
async def api_run_routine(request: web.Request) -> web.Response:
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
    if not row:
        raise web.HTTPNotFound(text="no such routine")
    routine = dict(row)
    if routine["status"] == "disabled":
        raise web.HTTPBadRequest(text="that routine is disabled")
    if routine["tool"] == "surface":
        from . import machine_routines as MR
        return web.json_response(await MR.replay_machine_routine(routine, request="manual run"))
    if routine["tool"] != "ui":
        raise web.HTTPBadRequest(text="only recorded routines can be replayed from here; launches go through TALK")
    return web.json_response(await replay_ui_routine(routine, request="manual run"))


@routes.post("/api/pc/routines/{id}/status")
async def api_set_status(request: web.Request) -> web.Response:
    """Disable a routine, or put it back to candidate. Never promotes to trusted -
    that is earned by clean runs, not by a button."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = str(body.get("status", ""))
    if status not in ("disabled", "candidate"):
        raise web.HTTPBadRequest(text="status must be 'disabled' or 'candidate'")
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
        if not row:
            raise web.HTTPNotFound(text="no such routine")
        db.execute("UPDATE pc_routines SET status=?, updated=? WHERE id=?",
                   (status, time.time(), row["id"]))
        return web.json_response({"ok": True, "routine": dict(
            db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())})


@routes.get("/api/pc/routines/{id}/steps")
async def api_routine_steps(request: web.Request) -> web.Response:
    steps = _steps(request.match_info["id"])
    return web.json_response({"steps": [
        {"ordinal": s["ordinal"], "tool": s["tool"],
         "args": json.loads(s["args_json"] or "{}"),
         "target": json.loads(s["target_json"] or "{}")} for s in steps]})
