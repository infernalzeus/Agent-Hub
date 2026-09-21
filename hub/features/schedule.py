"""Repeat this ask: a saved ask (project + brief + work type) that the hub starts again on a schedule.

Nothing runs itself to completion: a scheduled ask is started with autonomy "auto" (it plans and runs by itself) and then WAITS AT REVIEW in the
inbox. Applying, and anything leaving the machine, is always the user's. Jobs live in <missions dir>/schedules.json.

  POST   /api/missions/{id}/repeat     {every: daily|weekly|monthly, at: "HH:MM", dow?: 0-6 (Mon=0), dom?: 1-28}
  GET    /api/schedules
  DELETE /api/schedules/{id}
  POST   /api/schedules/{id}/run       start it now (does not move the schedule)
A run that was due while the hub was off is skipped if it is more than 2 hours late; the next one is simply scheduled.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

from aiohttp import web

from ..config import logger
from . import missions as M

routes = web.RouteTableDef()
GRACE = 2 * 3600
DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _file() -> Path:
    return M.MISSIONS_DIR / "schedules.json"


def load() -> list[dict]:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(jobs: list[dict]) -> None:
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def _hm(at: str) -> tuple[int, int]:
    h, m = str(at or "09:00").split(":")[:2]
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("time must be HH:MM")
    return h, m


def next_after(job: dict, now: float) -> float:
    """The next local-time occurrence strictly after `now`."""
    h, m = _hm(job.get("at", "09:00"))
    base = dt.datetime.fromtimestamp(now)
    cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
    every = job.get("every")
    if every == "daily":
        if cand.timestamp() <= now:
            cand += dt.timedelta(days=1)
    elif every == "weekly":
        cand += dt.timedelta(days=(int(job.get("dow", 0)) - cand.weekday()) % 7)
        if cand.timestamp() <= now:
            cand += dt.timedelta(days=7)
    elif every == "monthly":
        dom = min(28, max(1, int(job.get("dom", 1))))
        cand = cand.replace(day=dom)
        if cand.timestamp() <= now:
            y, mo = (cand.year + (cand.month // 12), cand.month % 12 + 1)
            cand = cand.replace(year=y, month=mo, day=dom)
    else:
        raise ValueError("every must be daily, weekly or monthly")
    return cand.timestamp()


def describe(job: dict) -> str:
    at = job.get("at", "09:00")
    return {"daily": f"every day at {at}", "weekly": f"every {DOW[int(job.get('dow', 0)) % 7]} at {at}", "monthly": f"on day {job.get('dom', 1)} of every month at {at}"}.get(job.get("every"), "?")


def create(m: "M.Mission", every: str, at: str = "09:00", dow: int = 0, dom: int = 1) -> dict:
    if m.kind != "orchestrator":
        raise ValueError("only orchestrated asks can repeat")
    job = {"id": "s" + uuid.uuid4().hex[:8], "source_mission": m.id, "project_slug": m.project_slug, "project_name": m.project_name, "project_path": m.project_path,
           "brief": m.brief, "profile": m.profile, "reference": bool(m.reference), "every": every, "at": at, "dow": int(dow), "dom": int(dom),
           "created": time.time(), "last": None, "last_mission": None, "enabled": True}
    job["next"] = next_after(job, time.time())             # also validates every / at
    jobs = [j for j in load() if j.get("source_mission") != m.id]
    jobs.append(job)
    _save(jobs)
    return job


def for_mission(mid: str) -> "dict | None":
    j = next((x for x in load() if x.get("source_mission") == mid), None)
    return {**j, "text": describe(j)} if j else None


async def _start(job: dict) -> "M.Mission":
    project = {"slug": job["project_slug"], "name": job["project_name"], "path": job["project_path"]}
    return await M.dispatch(project, job["brief"], "orchestrator", "orchestrator", profile=job.get("profile", "code"),
                            reference=bool(job.get("reference")), autonomy="auto")


async def tick(now: "float | None" = None) -> list[str]:
    """Start every job that is due. Returns the ids of the missions it started."""
    now = now or time.time()
    started, jobs, changed = [], load(), False
    for j in jobs:
        if not j.get("enabled", True) or j.get("next", 0) > now:
            continue
        if now - j["next"] <= GRACE:
            try:
                m = await _start(j)
                j["last"], j["last_mission"] = now, m.id
                started.append(m.id)
                logger.info("schedule %s: started ask %s (%s)", j["id"], m.id, describe(j))
            except Exception as exc:
                logger.warning("schedule %s could not start: %s", j["id"], exc)
        j["next"] = next_after(j, now)
        changed = True
    if changed:
        _save(jobs)
    return started


@routes.post("/api/missions/{id}/repeat")
async def api_repeat(request: web.Request) -> web.Response:
    m = M.S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such ask")
    try:
        b = await request.json()
    except Exception:
        b = {}
    try:
        job = create(m, str(b.get("every", "")), str(b.get("at", "09:00")), int(b.get("dow", 0) or 0), int(b.get("dom", 1) or 1))
    except (ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({**job, "text": describe(job)})


@routes.get("/api/schedules")
async def api_schedules(request: web.Request) -> web.Response:
    return web.json_response({"schedules": [{**j, "text": describe(j)} for j in load()]})


@routes.delete("/api/schedules/{id}")
async def api_schedule_delete(request: web.Request) -> web.Response:
    jobs = load()
    keep = [j for j in jobs if j["id"] != request.match_info["id"]]
    if len(keep) == len(jobs):
        raise web.HTTPNotFound(text="no such schedule")
    _save(keep)
    return web.json_response({"ok": True})


@routes.post("/api/schedules/{id}/run")
async def api_schedule_run(request: web.Request) -> web.Response:
    j = next((x for x in load() if x["id"] == request.match_info["id"]), None)
    if not j:
        raise web.HTTPNotFound(text="no such schedule")
    try:
        m = await _start(j)
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({"mission": m.id})


async def _loop() -> None:
    while True:
        try:
            await tick()
        except Exception as exc:
            logger.warning("schedule loop: %s", exc)
        await asyncio.sleep(30)


def setup(app: web.Application) -> None:
    async def start(_app):
        _app["schedule_task"] = asyncio.create_task(_loop())

    async def stop(_app):
        t = _app.get("schedule_task")
        if t:
            t.cancel()
    app.on_startup.append(start)
    app.on_cleanup.append(stop)
