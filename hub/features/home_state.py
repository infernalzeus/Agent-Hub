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


def _sess(a: dict) -> dict:
    """A Claude Code or Codex session in the same shape as a mission row, so every panel draws both."""
    return {"id": a["id"], "project": a["project"], "brief": a["title"] or ("Claude Code session" if a["agent"] == "claude" else "Codex session"),
            "status": a["state"], "agent": "claude code" if a["agent"] == "claude" else "codex", "runtime": a["agent"], "model": None,
            "age_s": a["age_s"], "error": "", "ended": None, "changed": 0, "ask": a["ask"]}


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

    from . import agent_sessions as AS
    try:
        agents = AS.scan(now)
    except Exception:  # noqa: BLE001 - Home must draw even if the logs cannot be read
        agents = []
    for a in agents:
        if a["state"] == "needs_you":
            attention.append({"level": "amber", "kind": "session", "id": a["id"], "go": "/",
                              "title": f'{"Claude Code" if a["agent"] == "claude" else "Codex"} is waiting: {a["project"]}',
                              "detail": a["ask"] or a["title"]})

    try:
        from . import acp_client as ACP
        for q in ACP.pending():
            attention.append({"level": "amber", "kind": "agent-asks", "id": q["id"], "go": "/",
                              "title": f'{q["agent"]} asks: {q["title"]}', "detail": " / ".join(str(o["name"]) for o in q["options"])[:140],
                              "options": q["options"]})
    except Exception:  # noqa: BLE001
        pass

    runs = [m for m in ms if m["status"] in ACTIVE]
    working = [m for m in ms if m["status"] in ACTIVE]
    waiting = [m for m in ms if m["status"] in NEEDS_YOU]
    idle = [m for m in ms if m["status"] not in ACTIVE and m["status"] not in NEEDS_YOU
            and m["ended"] and now - m["ended"] < 24 * 3600][:6]
    model = D._local_model_server()
    b = D.bundle(lines=10)
    try:
        usage = AS.usage(now)
    except Exception:  # noqa: BLE001
        usage = None
    return {
        "generated": now,
        "usage": usage,
        "attention": attention,
        "runs": runs[:8],
        "sessions": {
            "needs_you": waiting[:8] + [_sess(a) for a in agents if a["state"] == "needs_you"],
            "working": working[:8] + [_sess(a) for a in agents if a["state"] == "working"],
            "idle": idle + [_sess(a) for a in agents if a["state"] == "idle"][:6]},
        "health": {
            "version": b["hub"]["version"], "uptime_s": b["hub"]["uptime_s"],
            "apps": {"running": [a for a, v in apps.items() if isinstance(v, dict) and v.get("running")],
                     "failed": [a for a, v in apps.items() if isinstance(v, dict) and v.get("last_error")]},
            "local_model": model, "stay_local": b["missions"].get("stay_local"),
            "disk_free_gb": b["disk_free_gb"], "recent_problems": len(b["problems"]),
            "gpu": None, "gpu_note": "not measured: the Hub does not read the graphics card",
        },
    }


# --- the answer contract: what a spoken answer also carries, so the screen can show it ----------------------------------
import re

_TOPICS = (
    ("overview", re.compile(r"\b(?:show|bring up|give me|display|open|pull up)\b.*\b(?:dashboard|overview|everything|summary)\b", re.I)),
    ("work", re.compile(r"\b(running|missions?|attention|need me|needs me|proposals?|waiting|sessions?|busy|doing|going on|status|agents?)\b", re.I)),
    ("health", re.compile(r"\b(health|disk|model|computer|machine|pc|space|warnings?|errors?|healthy)\b", re.I)),
    ("usage", re.compile(r"\b(usage|tokens?|how much (?:have i|did i|am i)|limit|quota)\b", re.I)),
    ("memory", re.compile(r"\b(memory|remember|know about me|facts|rules)\b", re.I)),
)
# Topic answers are for questions and "show" requests. "Open Apple Music on the PC" mentions the PC but is not a question about it.
_QUESTIONY = re.compile(r"^\W*(?:(?:and|so|ok|okay|hey|please|now|can you|could you|would you|will you)\W+)*(?:show|what|how|any|is|are|tell|give|do|does|display|list|check|where|which|bring)\b", re.I)
_FOCUS = re.compile(r"\b(?:maximi[sz]e|focus(?: on)?|zoom (?:in )?(?:on|to)|enlarge|expand|show me only)\s+(?:the\s+)?([a-z ]{3,30})", re.I)
_SLEEP = re.compile(r"\b(go to sleep|goodnight|good night|that'?s all|that is all|goodbye|stop listening|dismiss yourself)\b", re.I)
_CLEAR = re.compile(r"\b(?:clear|hide|dismiss|close|remove|wipe|get rid of|take away)\b.*\b(?:dashboard|screen|everything|blocks?|panels?|cards?|these|that|them|display)\b|\bclear (?:it|that|all)\b", re.I)
_HOME = re.compile(r"\b(?:enter|open|go|take me|show me|bring up|launch|switch)\b.*\b(?:home|hub|apps|main page|main screen|my apps)\b(?: ?page| ?screen)?|\bgo (?:in|inside)\b|^\W*(?:enter|come in)\W*$", re.I)
_DOCTOR = re.compile(r"\b(diagnos\w*|the doctor|doctor,|ask the doctor|something(?:'s| is) (?:wrong|broken|off)|(?:fix|repair|check|debug) (?:the |agent )?hub|hub (?:is )?(?:broken|not working|acting up|slow|stuck))\b", re.I)
_APPLY = re.compile(r"\b(apply|install|accept|use|go with)\b.*\b(fix|change|patch|that|it)\b", re.I)
_DISCARD = re.compile(r"\b(discard|throw away|drop|reject|forget)\b.*\b(fix|change|patch|that|it)\b", re.I)
_RESTART = re.compile(r"\brestart (?:the |agent )?hub\b", re.I)
_HELP = re.compile(r"\b(what can (?:you|i) (?:do|say)|help|commands|what do i say)\b", re.I)


def _blocks(topic: str, st: dict) -> "list[dict]":
    if topic == "overview":
        return _blocks("work", st) + _blocks("health", st) + _blocks("usage", st)
    if topic == "work":
        att = st["attention"]
        ss = st["sessions"]
        return [
            {"id": "attention", "t": "NEEDS YOU", "n": str(len(att)), "type": "list", "cls": "amber" if att else "",
             "rows": [["r" if a["level"] == "red" else "a", a["title"], ""] for a in att[:3]] or [["o", "Nothing needs you right now", ""]]},
            {"id": "runs", "t": "RUNS", "type": "num", "big": str(len(st["runs"])), "cap": "missions running"},
            {"id": "sessions", "t": "SESSIONS", "type": "num", "big": str(len(ss["working"]) + len(ss["needs_you"])),
             "cap": f'{len(ss["needs_you"])} need you · {len(ss["working"])} working'},
        ]
    if topic == "health":
        h = st["health"]
        return [
            {"id": "health", "t": "HEALTH", "type": "list", "rows": [
                ["", f'Hub v{h["version"]}', f'up {round(h["uptime_s"] / 60)} min'],
                ["" if (h["local_model"] or {}).get("listening") else "o", "Local model", "listening" if (h["local_model"] or {}).get("listening") else "off"],
                ["a" if h["recent_problems"] else "", "Warnings", str(h["recent_problems"])]]},
            {"id": "disk", "t": "DISK", "type": "num", "big": f'{round(h["disk_free_gb"].get("work") or 0)} GB', "cap": "free where missions work"},
        ]
    if topic == "usage":
        u = (st.get("usage") or {}).get("claude")
        if not u:
            return [{"id": "usage", "t": "USAGE", "type": "note", "text": "Still counting Claude Code's logs; ask again in a few seconds."}]
        return [{"id": "usage", "t": "USAGE · 24 H", "type": "bars", "values": u["by_hour"], "cap": f'{u["tokens_5h"]:,} tokens in 5 h · {u["tokens_7d"]:,} in 7 days'}]
    if topic == "memory":
        from . import memory_tiers as MT
        t = MT.status()["tiers"]
        return [{"id": "memory", "t": "MEMORY", "type": "list", "rows": [["", name, f'{v["count"]}: {v["rule"].split(":")[0]}'] for name, v in t.items()]}]
    return []


def summary(topic: str, blocks: "list[dict]") -> str:
    """One spoken line for blocks the screen is about to show, so the voice and the picture say the same thing."""
    by = {b["id"]: b for b in blocks}
    bits = []
    if "attention" in by:
        n = int(by["attention"].get("n") or 0)
        bits.append(f"{n} need you" if n else "Nothing needs you")
    if "runs" in by:
        r = by["runs"]["big"]
        bits.append("nothing is running" if r == "0" else f"{r} running")
    if "health" in by:
        bits.append("the Hub is healthy")
    if "usage" in by:
        bits.append(by["usage"].get("cap", "").split(" · ")[0])
    if "memory" in by:
        bits.append("three kinds of memory are kept")
    return (", ".join(b for b in bits if b).capitalize() + ".") if bits else ""


def _support_waiting() -> bool:
    try:
        from . import support as SUP
        r = SUP.latest()
        return bool(r and r["status"] == "awaiting_review" and r["changed"])
    except Exception:  # noqa: BLE001
        return False


def ui_for(text: str, say: str, scene: "list | None" = None) -> dict:
    """What the screen should do with this answer: raise blocks for a topic, focus one on screen, open Home, or sleep."""
    out: dict = {"topic": None, "blocks": [], "focus": None, "open": None, "sleep": False}
    t = str(text or "")
    out.update({"clear": False, "doctor": False, "apply": False, "discard": False, "restart": False, "help": False})
    if _SLEEP.search(t):
        out["sleep"] = True
        return out
    if _RESTART.search(t):
        out["restart"] = True
        return out
    if _DISCARD.search(t) and _support_waiting():
        out["discard"] = True
        return out
    if _APPLY.search(t) and _support_waiting():
        out["apply"] = True
        return out
    if _CLEAR.search(t):
        out["clear"] = True
        return out
    if _DOCTOR.search(t):
        out["doctor"] = True
        return out
    if _HELP.search(t) and len(t) < 60:
        out["help"] = True
        return out
    if _HOME.search(t) and len(t) < 90:
        out["open"] = "home"
        return out
    m = _FOCUS.search(t)
    if m and scene:
        want = m.group(1).lower().strip()
        for item in scene:
            title = str(item.get("t") or item.get("id") or "").lower()
            if title and (title in want or want in title or any(w and w in title for w in want.split() if len(w) > 3)):
                out["focus"] = item.get("id")
                return out
    for name, rx in _TOPICS:
        if rx.search(t) and _QUESTIONY.search(t) and len(t) < 110:
            out["topic"] = name
            try:
                out["blocks"] = _blocks(name, state())
            except Exception:  # noqa: BLE001 - an answer must never fail because a panel could not be built
                out["blocks"] = []
            return out
    return out


@routes.get("/api/home/state")
async def api_state(request: web.Request) -> web.Response:
    return web.json_response(state())
