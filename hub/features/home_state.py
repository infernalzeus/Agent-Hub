"""What Home shows, in one read-only call: what needs you, what is running, how the machine is.

Home used to be a grid of tiles and nothing else: a mission waiting for review, an app that
failed to start and a pending proposal each lived on a different page, and you found out by
opening them. This gathers the three lists the Home panels draw. It reads state the Hub
already keeps and changes nothing, so it can be asked as often as the page likes.

Nothing here is measured that is not measured elsewhere: the GPU is reported as unknown
because nothing in the Hub reads it, and the panel says so rather than showing a number.
"""
from __future__ import annotations

import time

from aiohttp import web

routes = web.RouteTableDef()

NEEDS_YOU = {"needs_input", "plan_ready", "awaiting_review"}
FAILED = {"failed", "timed_out"}
ACTIVE = {"running", "queued", "blocked", "proposed"}
RECENT_FAIL_S = 24 * 3600
LOW_DISK_GB = 5.0


def _short(text: str, n: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _mission_rows(now: float) -> "list[dict]":
    try:
        from . import missions as M
        rows = list(M.S.m.values())
    except Exception:  # noqa: BLE001 - Home must draw even if missions cannot load
        return []
    out = []
    for m in sorted(rows, key=lambda x: x.created, reverse=True):
        out.append({
            "id": m.id, "project": m.project_name, "brief": _short(m.brief), "status": m.status,
            "agent": m.agent, "runtime": m.runtime, "model": m.model,
            "age_s": int(now - (m.created or now)), "error": _short(m.error, 120),
            "ended": m.ended, "changed": len(m.changed_files),
            "ask": _short((m.questions[0] or {}).get("q"), 120) if m.status == "needs_input" and m.questions else "",
        })
    return out


def state() -> dict:
    from . import diagnose as D
    from . import proposals as P
    now = time.time()
    ms = _mission_rows(now)
    attention: "list[dict]" = []

    for m in ms:
        if m["status"] in NEEDS_YOU:
            attention.append({"level": "amber", "kind": "mission", "id": m["id"], "go": "/missions",
                              "title": {"needs_input": "A mission is asking you something",
                                        "plan_ready": "A plan is ready for your yes",
                                        "awaiting_review": "A mission is waiting for review"}[m["status"]],
                              "detail": m["ask"] or f'{m["project"]}: {m["brief"]}'})
        elif m["status"] in FAILED and m["ended"] and now - m["ended"] < RECENT_FAIL_S:
            attention.append({"level": "red", "kind": "mission", "id": m["id"], "go": "/missions",
                              "title": "A mission failed in the last day",
                              "detail": f'{m["project"]}: {m["error"] or m["brief"]}'})

    props = P.load()
    for p in props:
        attention.append({"level": "amber", "kind": "proposal", "id": p.get("id"), "go": "/",
                          "title": f'Proposal: {p.get("name")}',
                          "detail": _short(p.get("why") or P.KINDS.get(p.get("kind"), ""))})

    apps = D._apps()
    for aid, a in apps.items():
        if isinstance(a, dict) and a.get("last_error"):
            attention.append({"level": "red", "kind": "app", "id": aid, "go": "/",
                              "title": f"{aid} did not start", "detail": _short(a["last_error"], 140)})

    disk = D._free_gb(__import__("hub.runtime", fromlist=["STATE"]).STATE)
    if disk is not None and disk < LOW_DISK_GB:
        attention.append({"level": "red", "kind": "disk", "id": "disk", "go": "/setup",
                          "title": "Little disk space left", "detail": f"{disk} GB free where the Hub keeps its state"})

    runs = [m for m in ms if m["status"] in ACTIVE]
    working = [m for m in ms if m["status"] in ACTIVE]
    waiting = [m for m in ms if m["status"] in NEEDS_YOU]
    idle = [m for m in ms if m["status"] not in ACTIVE and m["status"] not in NEEDS_YOU
            and m["ended"] and now - m["ended"] < 24 * 3600][:6]
    model = D._local_model_server()
    b = D.bundle(lines=10)
    return {
        "generated": now,
        "attention": attention,
        "runs": runs[:8],
        "sessions": {"needs_you": waiting[:8], "working": working[:8], "idle": idle},
        "health": {
            "version": b["hub"]["version"], "uptime_s": b["hub"]["uptime_s"],
            "apps": {"running": [a for a, v in apps.items() if isinstance(v, dict) and v.get("running")],
                     "failed": [a for a, v in apps.items() if isinstance(v, dict) and v.get("last_error")]},
            "local_model": model, "stay_local": b["missions"].get("stay_local"),
            "disk_free_gb": b["disk_free_gb"], "recent_problems": len(b["problems"]),
            "gpu": None, "gpu_note": "not measured: the Hub does not read the graphics card",
        },
    }


@routes.get("/api/home/state")
async def api_state(request: web.Request) -> web.Response:
    return web.json_response(state())
