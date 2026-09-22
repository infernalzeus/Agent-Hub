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
        """)
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


@routes.get("/api/pc/routines")
async def api_routines(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT id,intent,title,status,successes,failures,created,updated FROM pc_routines ORDER BY updated DESC")]
    return web.json_response({"routines": rows})


@routes.get("/api/pc/runs")
async def api_runs(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM pc_runs ORDER BY id DESC LIMIT 30")]
    return web.json_response({"runs": rows})
