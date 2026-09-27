"""Learn how to start an app once, then recognise the shape next time.

Working out how to run a project is a small, bounded question — framework,
command, port, health path — and the answer is almost always the same for two
projects of the same shape. Asking a model every time costs minutes and can
time out; asking it once and keeping the answer costs nothing on the second
Flask app you point at.

So ingestion becomes:

    signature(folder)            cheap, no model: what files are here
      -> a trusted recipe?       apply it, seconds, no model call
      -> otherwise               ask the agent, then save what worked

The rules are `pc_control`'s, because they are the same rules: a recipe is a
**candidate** until it has worked twice, a failure disables it, and the
signature is re-checked before reuse so a recipe that no longer fits falls
through to the model instead of producing a wrong command.

What a recipe stores is a *template*, not a manifest: the command and health
path, with the port left to be assigned, because two apps of the same shape
must not both claim 8110.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from . import pc_control as PC

routes = web.RouteTableDef()

# What makes two projects "the same shape". Ordered: the first match wins, so
# put the specific markers above the generic ones.
MARKERS = [
    ("django", ["manage.py"]),
    ("next", ["next.config.js", "next.config.mjs", "next.config.ts"]),
    ("vite", ["vite.config.js", "vite.config.ts"]),
    ("fastapi-uvicorn", ["pyproject.toml", "main.py"]),
    ("node", ["package.json"]),
    ("python-web", ["requirements.txt"]),
    ("go", ["go.mod"]),
    ("rust", ["Cargo.toml"]),
]


def signature(folder: Path) -> dict:
    """What kind of thing this folder is, from its files alone.

    Deliberately shallow: filenames at the root plus the entrypoint we can see.
    A signature that reads code would be more accurate and would also stop
    matching the moment anyone edited anything.
    """
    folder = Path(folder)
    try:
        names = {p.name for p in folder.iterdir()}
    except OSError:
        return {}
    kind = next((k for k, marks in MARKERS if any(m in names for m in marks)), "unknown")

    entry = ""
    for candidate in ("app.py", "main.py", "server.py", "manage.py", "wsgi.py",
                      "web/app.py", "src/index.js", "index.js"):
        if (folder / candidate).is_file():
            entry = candidate
            break

    # A Procfile tells you what the AUTHOR runs, which is the single most useful
    # hint there is — but it targets their deployment host, not this machine.
    procfiles = sorted(n for n in names if n.lower().startswith("procfile"))

    facts = {"kind": kind, "entry": entry, "procfiles": procfiles,
             "markers": sorted(n for n in names if n in
                               {m for _, ms in MARKERS for m in ms})}
    facts["fingerprint"] = hashlib.sha256(
        json.dumps(facts, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return facts


def _intent(sig: dict) -> str:
    return "ingest:" + str(sig.get("kind") or "unknown") + ":" + str(sig.get("entry") or "-")


def find(sig: dict) -> dict | None:
    """A recipe for this shape that is still trusted, or None.

    Matching is on the whole fingerprint, not the kind, so "a Django app with
    manage.py" and "a Django app with manage.py AND a Procfile.windows" are
    different shapes — which they are, because the second one tells you more.
    """
    if not sig:
        return None
    with PC._db() as db:
        rows = db.execute(
            "SELECT * FROM pc_routines WHERE kind='ingest' AND status='trusted'").fetchall()
    for r in rows:
        try:
            stored = json.loads(r["signature_json"] or "{}")
        except ValueError:
            continue
        if stored.get("fingerprint") == sig.get("fingerprint"):
            return dict(r)
    return None


def remember(sig: dict, manifest: dict, *, success: bool = True) -> dict | None:
    """Keep what worked, as a template. Two clean uses promote it to trusted."""
    if not sig or not manifest.get("cmd"):
        return None
    intent, now = _intent(sig), time.time()
    rid = hashlib.sha256(("ingest:" + sig["fingerprint"]).encode()).hexdigest()[:16]
    # The port is per-app, never per-shape: two Flask apps cannot share 8110. It
    # hides in two places — the `port` field AND a PORT in env — so both go.
    template = {k: manifest.get(k) for k in ("cmd", "install", "health_path", "serve")}
    template["env"] = {k: v for k, v in (manifest.get("env") or {}).items()
                       if k.upper() != "PORT"}
    title = f"Start a {sig.get('kind', 'unknown')} app" + (f" ({sig['entry']})" if sig.get("entry") else "")
    with PC._db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, "
                       "args_json=?, updated=? WHERE id=?",
                       (int(success), int(not success), json.dumps(template), now, row["id"]))
            if not success:
                db.execute("UPDATE pc_routines SET status='disabled', updated=? WHERE id=? "
                           "AND status='candidate'", (now, row["id"]))
            else:
                db.execute("UPDATE pc_routines SET status='trusted', updated=? WHERE id=? "
                           "AND status='candidate' AND successes>=2", (now, row["id"]))
            return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())
        if not success:
            return None
        db.execute("INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,"
                   "successes,failures,created,updated,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (rid, intent, title, "recipe", json.dumps(template), json.dumps(sig),
                    "candidate", 1, 0, now, now, "ingest"))
        logger.info("ingest: learned a recipe for %s (%s)", sig.get("kind"), sig["fingerprint"])
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


def free_port(taken: set[int], lo: int = 8110, hi: int = 8199) -> int | None:
    return next((p for p in range(lo, hi + 1) if p not in taken), None)


def manifest_from(recipe: dict, folder: Path, app_id: str, name: str, taken: set[int]) -> dict | None:
    """Fill a recipe's template in for THIS app. None if there is no port left."""
    try:
        template = json.loads(recipe["args_json"] or "{}")
    except ValueError:
        return None
    port = free_port(taken)
    if not port or not template.get("cmd"):
        return None
    env = {k: v for k, v in (template.get("env") or {}).items() if k.upper() != "PORT"}
    env["PORT"] = str(port)          # always this app's port, never the one we learned on
    return {"id": app_id, "name": name, "cmd": template["cmd"], "port": port,
            "serve": template.get("serve") or "proxy",
            "health_path": template.get("health_path") or "/",
            "install": template.get("install"), "env": env, "idle_minutes": 20}


@routes.get("/api/ingest/recipes")
async def api_recipes(request: web.Request) -> web.Response:
    """Every learned recipe, and — if `folder` is given — whether one matches it."""
    with PC._db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT id,intent,title,status,successes,failures,signature_json,args_json,updated "
            "FROM pc_routines WHERE kind='ingest' ORDER BY updated DESC")]
    for r in rows:
        for key in ("signature_json", "args_json"):
            try:
                r[key[:-5]] = json.loads(r.pop(key) or "{}")
            except ValueError:
                r[key[:-5]] = {}
    out = {"recipes": rows}
    folder = request.query.get("folder")
    if folder:
        sig = signature(Path(folder))
        hit = find(sig)
        out["signature"] = sig
        out["match"] = {"id": hit["id"], "title": hit["title"]} if hit else None
    return web.json_response(out)
