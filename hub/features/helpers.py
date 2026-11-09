"""The Hub's own helpers, as one honest list for the Agents page: who they are, what each one does, and where it stands right now.

The Agents page lists the personas that take missions (coder, tester...). The Hub also has helpers of its own that are not missions: the voice (Smith),
the Doctor, the desktop agent, the router, and the small learners. They used to appear nowhere. This list is built from live facts, so a learner that
is added or changes state shows up here without anyone editing a page.
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()


def _learning() -> dict:
    try:
        from . import learning as LRN
        return LRN.status()
    except Exception:  # noqa: BLE001
        return {}


def _yard() -> dict:
    try:
        from ..yard import api as YA
        return YA.status()
    except Exception:  # noqa: BLE001
        return {}


def build() -> "list[dict]":
    st, yd = _learning(), _yard()
    per = st.get("per_kind", {})
    bands = st.get("bandits", {})
    v = yd.get("in_use_version")
    shadow = (yd.get("shadow") or {})
    rows = [
        {"id": "smith", "name": "Agent Smith", "kind": "voice agent", "icon": "smith", "state": "live",
         "does": "The voice you talk to: wake word, Talk, speaks the answers, and calls the Hub's own commands (open a page, run a PC task). Smith does not design agents; Neo does.", "where": "TALK (top left)",
         "calls": ["router", "desktop", "doctor", "neo"]},
        {"id": "neo", "name": "Neo", "kind": "agent", "icon": "neo", "state": "live",
         "does": "Designs and edits other agents from a plain description and hands back one ready-to-save agent file. Called from the Agents page, by Smith when you ask for a new agent, and by the Doctor when a fix needs an agent changed.", "where": "Agents page", "calls": []},
        {"id": "doctor", "name": "The Doctor", "kind": "agent", "icon": "doctor", "state": "live",
         "does": "Diagnoses the Hub when something is wrong and proposes a fix as a diff in Missions. Never restarts anything and never applies a fix without you.", "where": "Support block", "calls": ["neo"]},
        {"id": "desktop", "name": "Desktop agent", "kind": "agent", "icon": "desktop", "state": "live",
         "does": "Presses and types in apps on this PC for a goal, one step at a time, checking the screen after each. Replays a saved routine first when there is one.", "where": "PC CONTROL"},
        {"id": "router", "name": "Router", "kind": "rules", "icon": "router", "state": "live",
         "does": "Decides what you meant (open an app, a Hub command, a task inside an app, just talk). Fixed rules today.",
         "learning": f"{per.get('route', {}).get('labelled', 0)} of {per.get('route', {}).get('events', 0)} decisions have an exact label", "where": "REINFORCEMENT LEARNING > TEACH"},
        {"id": "yard", "name": "Yard learner", "kind": "learner (actor-critic)", "icon": "learner", "state": "shadow" if shadow.get("policy") else "practising only",
         "does": "A small neural network that practises pressing through pretend apps. In shadow mode it watches the live desktop agent and notes what it would have pressed. It never acts.",
         "learning": (f"version {v} in use" if v else "no session finished yet"), "where": "REINFORCEMENT LEARNING > YARD"},
        {"id": "bandit-model", "name": "Model bandit (R3)", "kind": "learner (bandit)", "icon": "bandit", "state": "recording",
         "does": "A tally of how often each model's mission worked. Says nothing until two models have three exact results each.",
         "learning": "%s decisions, opinion on %s" % (bands.get("R3 model choice", {}).get("decided", 0), bands.get("R3 model choice", {}).get("had_an_opinion", 0)), "where": "REINFORCEMENT LEARNING > STATUS"},
        {"id": "bandit-rung", "name": "PC-task bandit (R4)", "kind": "learner (bandit)", "icon": "bandit", "state": "recording",
         "does": "A tally of whether replaying a saved routine or letting the agent try works better for each app.",
         "learning": "%s decisions, opinion on %s" % (bands.get("R4 PC-task way", {}).get("decided", 0), bands.get("R4 PC-task way", {}).get("had_an_opinion", 0)), "where": "REINFORCEMENT LEARNING > STATUS"},
        {"id": "recorder", "name": "Learning log", "kind": "recorder", "icon": "log", "state": "live" if st.get("logging") else "off",
         "does": "Writes down every choice the Hub makes and how it turned out. This is what the learners learn from.",
         "learning": "%s choices recorded" % sum(k.get("events", 0) for k in per.values()), "where": "REINFORCEMENT LEARNING > STATUS"},
    ]
    for r in rows:
        m = _model_block(r["id"])
        if m:
            r["model"] = m
    return rows


def _model_block(hid: str) -> "dict | None":
    """Only helpers that really have a model setting get one: the desktop agent (which model it tries first) and the router (the small local model it may ask)."""
    from . import desktop_agent as DA, binning as BIN
    try:
        options = DA.ladder()
    except Exception:  # noqa: BLE001
        options = []
    if hid == "desktop":
        cur = DA.chosen_model()
        first = options[0] if options else ""
        return {"current": cur, "effective": cur or first, "options": [m for m in dict.fromkeys(([cur] if cur else []) + options)], "note": "tried first; the rest stay as the fall-back order"}
    if hid == "router":
        loc = BIN.settings()["local"]
        return {"current": loc["model"], "effective": loc["model"], "options": list(dict.fromkeys([loc["model"]] + options)),
                "note": "asked only when local decisions are switched on" + ("" if loc["enabled"] else " (they are off now)")}
    return None


@routes.post("/api/hub/helpers/{id}/model")
async def api_helper_model(request: web.Request) -> web.Response:
    from . import desktop_agent as DA, binning as BIN
    hid = request.match_info["id"]
    try:
        model = str((await request.json()).get("model") or "").strip()[:80]
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"model": "name"}')
    if hid == "desktop":
        DA.set_chosen_model(model)
    elif hid == "router" and model:
        BIN.save_settings({"local": {"model": model}})
    else:
        raise web.HTTPNotFound(text="this helper has no model of its own")
    return web.json_response({"ok": True, "model": _model_block(hid)})


@routes.get("/api/hub/helpers")
async def api_helpers(request: web.Request) -> web.Response:
    return web.json_response({"helpers": build()})


ICON_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "static" / "agent-icons"
ART_DIR = ICON_DIR.parent / "agent-art"
CREW = ("orchestrator", "neo", "smith", "doctor")


@routes.get("/static/agent-icons/{name}")
async def agent_icon(request: web.Request) -> web.StreamResponse:
    """One picture per agent or helper, by id (`doctor.png`, `coder.png`...). A missing file is a plain 404; the page falls back to a drawn glyph."""
    import re
    name = request.match_info["name"]
    crew = ART_DIR / (name[:-4] + ".svg")
    on_agency = "/agents" in (__import__("urllib.parse", fromlist=["urlparse"]).urlparse(request.headers.get("Referer", "")).path or "")
    if on_agency and name[:-4] in CREW and name.endswith(".png") and crew.is_file():   # the four crew have a vector picture; only the Agency page shows it, large
        return web.FileResponse(crew, headers={"Cache-Control": "public, max-age=300", "Content-Type": "image/svg+xml"})
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}\.png", name) or not (ICON_DIR / name).is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(ICON_DIR / name, headers={"Cache-Control": "public, max-age=300"})
