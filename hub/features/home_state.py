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
from pathlib import Path

from aiohttp import web

routes = web.RouteTableDef()

NEEDS_YOU = {"needs_input", "plan_ready", "awaiting_review"}
FAILED = {"failed", "timed_out"}
ACTIVE = {"running", "queued", "blocked", "proposed"}
RECENT_FAIL_S = 24 * 3600
LOW_DISK_GB = 5.0


def _short(text: str, n: int = 220) -> str:        # blocks wrap their lines and scroll inside, so a line is only cut where it is absurd
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _title(brief: str) -> str:
    """What a list should call a mission: a doctor's brief opens with its rules, so show what the owner asked instead."""
    text = str(brief or "")
    if text.startswith("You are the doctor for Agent Hub"):
        if "THE OWNER SAYS:" not in text:                  # a session list cuts the title short, before the owner's words
            return "Doctor session"
        ask = text.split("THE OWNER SAYS:", 1)[-1].split("FACTS FROM", 1)[0].split("RESTART TIMING", 1)[0].strip()
        return "Doctor: " + (ask or "a look at the Hub")
    return text


def _mission_rows(now: float) -> "list[dict]":
    try:
        from . import missions as M
        rows = list(M.S.m.values())
    except Exception:  # noqa: BLE001 - Home must draw even if missions cannot load
        return []
    out = []
    for m in sorted(rows, key=lambda x: x.created, reverse=True):
        out.append({
            "id": m.id, "project": m.project_name, "brief": _short(_title(m.brief)), "status": m.status,
            "agent": m.agent, "runtime": m.runtime, "model": m.model,
            "age_s": int(now - (m.created or now)), "error": _short(m.error, 300),
            "ended": m.ended, "changed": len(m.changed_files),
            "ask": _short((m.questions[0] or {}).get("q"), 300) if m.status == "needs_input" and m.questions else "",
        })
    return out


def _sess(a: dict) -> dict:
    """A Claude Code or Codex session in the same shape as a mission row, so every panel draws both."""
    return {"id": a["id"], "project": a["project"], "brief": _short(_title(a["title"])) or ("Claude Code session" if a["agent"] == "claude" else "Codex session"),
            "status": a["state"], "agent": "claude code" if a["agent"] == "claude" else "codex", "runtime": a["agent"], "model": None,
            "age_s": a["age_s"], "error": "", "ended": None, "changed": 0, "ask": a["ask"],
            "kind": "agent-log", "cwd": a.get("cwd", ""), "last": a.get("last", "")}


_STALE: dict = {"at": 0.0, "newest": 0.0}


def stale_code(now: float) -> "float | None":
    """When the newest Hub source file was saved, if that is later than this process started: the Hub is running older code than
    is on disk (a change was made and nobody restarted it). None for a packaged install, which cannot change under itself.
    Looked at most every 20 s: it walks about 400 files."""
    from . import diagnose as D
    from .. import runtime as RT
    if RT.PACKAGED:
        return None
    if now - _STALE["at"] > 20:
        root = Path(__file__).resolve().parents[1]
        newest = 0.0
        for p in root.rglob("*"):
            if p.suffix in (".py", ".js", ".css", ".html") and "__pycache__" not in p.parts and p.is_file():
                try:
                    newest = max(newest, p.stat().st_mtime)
                except OSError:
                    pass
        _STALE.update(at=now, newest=newest)
    return _STALE["newest"] if _STALE["newest"] > D._STARTED + 5 else None


def state() -> dict:
    from . import diagnose as D
    from . import proposals as P
    now = time.time()
    ms = _mission_rows(now)
    attention: "list[dict]" = []

    try:
        from . import support as SUP
        asked = SUP.last_asked()
    except Exception:  # noqa: BLE001
        asked = 0.0
    just_asked = now - asked < 15 * 60

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
                              "detail": f'{m["project"]}: {m["error"] or m["brief"]}',
                              "doctor": f'Mission {m["id"]} ({m["project"]}) ended {m["status"]}: {m["error"] or m["brief"]}. Find out why. '
                                        "Fix it only if the cause is in the Hub's own code; otherwise say what went wrong.",
                              "asked": just_asked})

    props = P.load()
    for p in props:
        attention.append({"level": "amber", "kind": "proposal", "id": p.get("id"), "go": "/",
                          "title": f'Proposal: {p.get("name")}',
                          "detail": _short(p.get("why") or P.KINDS.get(p.get("kind"), ""))})

    apps = D._apps()
    for aid, a in apps.items():
        if isinstance(a, dict) and a.get("last_error"):
            attention.append({"level": "red", "kind": "app", "id": aid, "go": "/",
                              "title": f"{aid} did not start", "detail": _short(a["last_error"], 300),
                          "doctor": f'The app "{aid}" did not start: {_short(a["last_error"], 300)}. Find the cause.', "asked": just_asked})

    n_err, newest_err, sample_err = D.recent_errors(now)
    if n_err and newest_err > asked:                 # errors the doctor has not been asked about since they happened
        attention.append({"level": "red", "kind": "hub-errors", "id": "hub-errors", "go": "/support",
                          "title": f"The Hub logged {n_err} error{'s' if n_err != 1 else ''} in the last hour", "detail": sample_err,
                          "doctor": f"The Hub logged {n_err} error(s) in the last hour. The newest: {sample_err}. Find the cause.", "asked": False})

    newer = stale_code(now)
    if newer:
        attention.append({"level": "amber", "kind": "restart", "id": "stale-code", "go": "/",
                          "title": "Agent Hub is running older code than is on disk",
                          "detail": "Files were saved after it started, so what you see and what was built can differ. Restart it from the power menu to use them."})

    disk = D._free_gb(__import__("hub.runtime", fromlist=["STATE"]).STATE)
    if disk is not None and disk < LOW_DISK_GB:
        attention.append({"level": "red", "kind": "disk", "id": "disk", "go": "/setup",
                          "title": "Little disk space left", "detail": f"{disk} GB free where the Hub keeps its state"})

    from . import agent_sessions as AS
    try:
        agents = AS.scan(now)
    except Exception:  # noqa: BLE001 - Home must draw even if the logs cannot be read
        agents = []
    try:                                   # a hook said so: that is a fact, not an inference from a log
        from . import agent_events as AE
        for ev in AE.waiting(now):
            attention.append({"level": "amber", "kind": "session", "id": ev["session"][:12] or ev["agent"], "go": "/",
                              "title": f'{"Claude Code" if ev["agent"] == "claude" else ev["agent"].title()} is waiting: {ev["project"] or "a session"}',
                              "detail": ev["message"]})
    except Exception:  # noqa: BLE001
        pass
    for a in agents:
        if a["state"] == "needs_you":
            attention.append({"level": "amber", "kind": "session", "id": a["id"], "go": "/",
                              "title": f'{"Claude Code" if a["agent"] == "claude" else "Codex"} is waiting: {a["project"]}',
                              "detail": a["ask"] or a["title"]})

    try:                                   # the doctor cannot reach Claude Code: that is why its fixes have not been running
        from . import support as SUP
        ch = SUP.claude_health()
        if ch.get("ok") is False:
            attention.append({"level": "amber", "kind": "doctor", "id": "claude-signin", "go": "/support", "title": "The Doctor cannot reach Claude Code", "detail": ch["why"]})
    except Exception:  # noqa: BLE001
        pass
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
            "stale_code": bool(newer), "gpu": None, "gpu_note": "not measured: the Hub does not read the graphics card",
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
# commands about the board itself: tidy it, fit everything, zoom, switch how the mouse moves it
_BOARD = (
    ("tidy", re.compile(r"\b(?:tidy|organi[sz]e|arrange|clean up|sort out)\b.*\b(?:board|dashboard|blocks|panels|windows|screen)\b|\b(?:board|dashboard|blocks|panels|windows)\b.*\b(?:tidy|organi[sz]ed?|arranged)\b", re.I)),
    ("fit", re.compile(r"\b(?:fit|show|see)\b.*\b(?:everything|all (?:of )?(?:the |my )?(?:blocks|panels|windows))\b|\bzoom to fit\b", re.I)),
    ("zoom-in", re.compile(r"^\W*zoom in\W*$", re.I)),
    ("zoom-out", re.compile(r"^\W*zoom out\W*$", re.I)),
    ("view:3d", re.compile(r"\b(?:3 ?d|three ?d)\b.*\b(?:view|mode|navigation|board|dashboard)\b|\b(?:switch|change|go|use|set|turn)\b.*\b(?:3 ?d|three ?d)\b", re.I)),
    ("view:2d", re.compile(r"\b(?:2 ?d|two ?d|flat)\b.*\b(?:view|mode|navigation|board|dashboard)\b|\b(?:switch|change|go|use|set|turn)\b.*\b(?:2 ?d|two ?d|flat)\b", re.I)),
    ("view:cad", re.compile(r"\bcad\b.*\b(?:view|mode|navigation|style)\b|\b(?:switch|change|go|use|set|turn)\b.*\bcad\b", re.I)),
    ("view:classic", re.compile(r"\bclassic\b.*\b(?:view|mode|navigation|style)\b|\b(?:switch|change|go|use|set|turn)\b.*\bclassic\b", re.I)),
)
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
    out.update({"clear": False, "doctor": False, "apply": False, "discard": False, "restart": False, "help": False, "board": None})
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
    if len(t) < 90:
        for name, rx in _BOARD:
            if rx.search(t):
                out["board"] = name
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


@routes.post("/api/sessions/open-folder")
async def api_open_folder(request: web.Request) -> web.Response:
    """Open the folder of a Claude Code or Codex session in Explorer. The folder is looked up from the session id in the log scan; a path in
    the request is never used, so this cannot open anything the agents were not already working in."""
    import os
    from . import agent_sessions as AS
    try:
        sid = str((await request.json()).get("id") or "")[:40]
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="send {\"id\": the session id}")
    folder = AS.folder_of(sid) if sid else None
    if not folder:
        raise web.HTTPNotFound(text="That session's folder is not known or no longer exists")
    if os.name != "nt":
        raise web.HTTPNotImplemented(text="Opening a folder is only built for Windows")
    os.startfile(folder)                                  # noqa: S606 - a folder the log scan reported, opened in Explorer
    return web.json_response({"ok": True, "folder": folder})


@routes.get("/api/home/state")
async def api_state(request: web.Request) -> web.Response:
    return web.json_response(state())
