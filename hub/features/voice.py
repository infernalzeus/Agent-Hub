"""The hub's voice / chat assistant: what the TALK button (and the Missions input bar) talk to.

  speech -> text        local faster-whisper on this PC (or the browser's speech API as a fallback)
  text -> reply+action  1. rules for the obvious commands (instant)  2. small talk (instant)  3. the local/cloud Ollama model, given a
                        snapshot of the hub, the list of things it CAN do and the list of things it CANNOT (it must say so plainly)
  reply -> speech       Microsoft's neural voices through edge-tts (only the reply text leaves this PC), browser voice as the fallback

The microphone is always the one on the device whose browser is open (phone or PC); the audio is uploaded here to be transcribed.

Everything the assistant can do is an entry in ACTIONS below: id, arguments, whether it needs a yes first, and what it does. The model may
only pick from that list; the server re-validates every action, so a made-up mission id or an action that does not fit the mission's
state is refused with an explanation instead of being run.

  GET  /api/voice/status         {whisper, model, note}
  GET  /api/voice/voices         the selectable speaking voices
  POST /api/voice/transcribe     raw audio -> {text}
  POST /api/voice/chat           {text, history?, mission?} -> {say, action?, confirm, url?, backend, heard}
  POST /api/voice/act            {id, args} -> {say, url?}         runs an action (after the user said yes when it needs one)
  POST /api/voice/speak          {text, voice?} -> audio/mpeg
  GET  /smith-icon.png
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, quote_plus

import aiohttp
from aiohttp import web

from .. import agent_knowledge, decide as DEC
from ..config import VOICEBOX_URL, logger
from .. import runtime as RT

routes = web.RouteTableDef()


async def _voicebox_state() -> dict:
    """Read the optional, local Voicebox service without making TALK depend on it."""
    timeout = aiohttp.ClientTimeout(total=3)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{VOICEBOX_URL}/health") as response:
                if response.status != 200:
                    return {"online": False, "profiles": [], "reason": f"Voicebox returned {response.status}"}
                health = await response.json()
            async with session.get(f"{VOICEBOX_URL}/profiles") as response:
                profiles = await response.json() if response.status == 200 else []
                profiles.sort(key=lambda item: 0 if str(item.get("name", "")) == "Hub · Personal Voice" else 1)
            async with session.get(f"{VOICEBOX_URL}/models/status") as response:
                models = (await response.json()).get("models", []) if response.status == 200 else []
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return {"online": False, "profiles": [], "reason": str(exc)[:100]}
    return {
        "online": True,
        "profiles": [
            {"id": str(item.get("id", "")), "name": str(item.get("name", "Profile")),
             "type": str(item.get("voice_type", "")), "engine": item.get("default_engine"),
             "ready": str(item.get("voice_type", "")) == "preset" or bool(item.get("sample_count"))}
            for item in profiles if item.get("id") and str(item.get("id")) != "6332e75b-b73e-4950-8b46-2606d832ab0a"
        ],
        "model_ready": bool(health.get("model_loaded")),
        "downloaded_models": [item.get("display_name") for item in models if item.get("downloaded")],
    }


@routes.get("/api/voice/voicebox")
async def api_voicebox(request: web.Request) -> web.Response:
    return web.json_response(await _voicebox_state())


@routes.post("/api/voice/voicebox/speak")
async def api_voicebox_speak(request: web.Request) -> web.Response:
    """Generate locally with an existing Voicebox profile and relay WAV audio to TALK."""
    body = await _body(request)
    text = _speakable(str(body.get("text") or ""))
    profile = str(body.get("profile") or "")
    if not text or not profile:
        raise web.HTTPBadRequest(text="choose a Voicebox profile first")
    state = await _voicebox_state()
    if not state["online"]:
        raise web.HTTPServiceUnavailable(text="Voicebox is not running on this PC")
    if profile not in {item["id"] for item in state["profiles"]}:
        raise web.HTTPBadRequest(text="that Voicebox profile is no longer available")
    timeout = aiohttp.ClientTimeout(total=90)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{VOICEBOX_URL}/speak", json={"text": text, "profile": profile, "language": "en"}) as response:
                if response.status != 200:
                    raise web.HTTPServiceUnavailable(text=(await response.text())[:160])
                generation = await response.json()
            generation_id = str(generation.get("id") or "")
            if not generation_id:
                raise web.HTTPServiceUnavailable(text="Voicebox did not start speech generation")
            for _ in range(80):
                await asyncio.sleep(0.5)
                async with session.get(f"{VOICEBOX_URL}/audio/{quote(generation_id, safe='')}") as audio_response:
                    if audio_response.status == 200:
                        audio = await audio_response.read()
                        content_type = audio_response.headers.get("Content-Type", "audio/wav").split(";", 1)[0]
                        if audio:
                            return web.Response(body=audio, content_type=content_type)
                    elif audio_response.status >= 500:
                        raise web.HTTPServiceUnavailable(text=(await audio_response.text())[:160])
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise web.HTTPServiceUnavailable(text=f"Voicebox did not finish: {str(exc)[:120]}")
    raise web.HTTPGatewayTimeout(text="Voicebox did not finish in time")

# ── what the assistant can do ────────────────────────────────────────────────────────────────────────────────────────
PAGES = {"missions": "/missions", "agents": "/agents", "graph": "/graph", "locations": "/setup", "hub": "/"}
ACTIONS = {
    "open_page": {"desc": "Open a page: missions, agents, graph, locations, hub.", "args": "page", "confirm": False},
    "status": {"desc": "Say what is waiting for the user and what is running, hub-wide.", "args": "", "confirm": False},
    "mission_info": {"desc": "Explain one ask: its state, progress, open questions, checks, and what the user should do next.", "args": "mission", "confirm": False},
    "open_mission": {"desc": "Open the Missions page on one specific ask AND read its summary aloud (use when the user says open it, show me, read it).", "args": "mission", "confirm": False},
    "new_ask": {"desc": "Open the new-ask form filled with the user's words (optionally for a named project).", "args": "text, project", "confirm": False},
    "answer_defaults": {"desc": "Answer an ask's clarifying questions with the recommended defaults so it carries on planning.", "args": "mission", "confirm": True},
    "run_plan": {"desc": "Start an ask's plan (the same as RUN PIPELINE).", "args": "mission", "confirm": True},
    "apply": {"desc": "APPLY a finished ask: merge its work into the project.", "args": "mission", "confirm": True},
    "discard": {"desc": "DISCARD an ask and delete its working copy.", "args": "mission", "confirm": True},
    "pause": {"desc": "Pause one running ask, or every running ask when no mission is given.", "args": "mission (optional)", "confirm": True},
    "resume": {"desc": "Resume a paused or stopped ask.", "args": "mission", "confirm": True},
    "ingest_app": {"desc": "Ingest a web app from a git URL so the hub can run it (starts an ingest ask that waits for review).", "args": "url", "confirm": True},
    "pc_control": {"desc": "Switch PC control (Windows MCP: click, type, screenshots, apps, clipboard for OpenCode agents) on or off.", "args": "state: on|off", "confirm": False},
    "pc_direct": {"desc": "Carry out a bounded PC command directly: open Edge, YouTube, Google, or a web search. PC control must be on.", "args": "kind, value (optional)", "confirm": False},
    "pc_app": {"desc": "Open a named Windows application through the Windows MCP App tool and learn its launch routine.", "args": "app, request", "confirm": False},
    "pc_task": {"desc": "Use a fresh OpenCode Quick Chat with Windows MCP to carry out an explicit desktop request.", "args": "text, state (optional: on)", "confirm": False},
    "mcp_status": {"desc": "Report which MCP servers OpenCode has configured, and what that means the assistant can and cannot do.", "args": "", "confirm": False},
    "list_projects": {"desc": "List the project folders the hub knows.", "args": "", "confirm": False},
    "list_agents": {"desc": "List the agents (personas) and what each does.", "args": "", "confirm": False},
}
def limits() -> list:
    from . import mcp as MCP
    win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
    if not win:
        pc = "Control the rest of the PC: NOT possible; no MCP server is configured. It would need a Windows MCP server installed for OpenCode and the user's approval."
    elif not win["installed"]:
        pc = "Control the rest of the PC: NOT possible; a Windows MCP entry exists but its program is missing."
    elif not win["enabled"]:
        pc = ("Control the rest of the PC: currently OFF. Windows MCP is installed and can be switched on with pc_control (needs a yes). Even when on, only OpenCode "
              "agents inside an ask use it, and only to click, type, take screenshots, open apps, use the clipboard and scrape pages (PowerShell, registry, files and "
              "process control are excluded); YOU do not click things yourself.")
    else:
        pc = ("Control the rest of the PC: ON for OpenCode agents inside an ask (click, type, screenshots, apps, clipboard, scraping; PowerShell, registry, files and "
              "process control are excluded). YOU do not click things yourself: start an ask for it.")
    return [pc,
            "Add, edit or remove MCP servers by voice: NOT built. You can only report them and switch PC control on or off.",
            "Change folder locations by voice: NOT built; you can open the Locations page.",
            "Read out or take a web address reliably from speech: NOT reliable; ask the user to type the URL in the text box.",
            "Edit code or documents directly: NOT possible; that is what an ask (a mission) is for."]


# rule patterns for the obvious commands (matched against the lower-cased utterance)
COMMANDS = [
    {"id": "open_missions", "action": ("open_page", {"page": "missions"}), "rx": [r"\b(open|show|go to|take me to|bring up|view)\b.*\b(missions?|asks?)\b", r"^(the )?missions?( page)?$"]},
    {"id": "open_agents", "action": ("open_page", {"page": "agents"}), "rx": [r"\b(open|show|go to|take me to|bring up|view)\b.*\bagents?\b", r"^(the )?agents?( page)?$"]},
    {"id": "open_graph", "action": ("open_page", {"page": "graph"}), "rx": [r"\b(open|show|go to|take me to|bring up|view)\b.*\b(graph|projects map)\b", r"^(the )?graph$"]},
    {"id": "open_locations", "action": ("open_page", {"page": "locations"}), "rx": [r"\b(open|show|go to|take me to|bring up|change|edit)\b.*\b(locations?|settings|setup|folders?|paths?)\b"]},
    {"id": "open_hub", "action": ("open_page", {"page": "hub"}), "rx": [r"\b(go|take me|back)\b.*\b(home|hub|main menu|dashboard)\b", r"^(home|main menu|dashboard)$"]},
    {"id": "new_ask", "action": ("new_ask", None), "rx": [r"^ask (?:the )?hub (?:to |for )?(?P<arg>.+)$", r"^(?:please )?(?:start |make |create )?(?:a )?(?:new )?(?:ask|mission)(?: to| for| about| that)? (?P<arg>.+)$"]},
    {"id": "status", "action": ("status", {}), "rx": [r"\b(status|what(?:'s| is| are)? (?:waiting|running|happening|going on)|anything (?:waiting|needs me)|any updates?|inbox)\b"]},
    {"id": "pause_all", "action": ("pause", {}), "rx": [r"\b(stop|pause|halt)\b.*\b(everything|all|running|agents?|asks?|missions?)\b"]},
]
_BY_ID = {c["id"]: c for c in COMMANDS}
INTRO = "Good evening. I can open pages, report on your asks, or start an ingest. State your objective."
_GREET = re.compile(r"^(hello|hi|hey|good (morning|afternoon|evening))\b")


def smalltalk(text: str, history: list) -> "str | None":
    """Instant replies for chit-chat. The introduction is given once per conversation; after that a greeting gets a short, varied answer."""
    t = _clean(text)
    said = [h for h in (history or []) if h.get("role") in ("assistant", "hub")]
    n = len(said)
    if re.search(r"\bhow are you\b", t):
        return "I'm operational. How may I assist?"
    if re.fullmatch(r"(?:(?:okay|ok|alright|right|yes|yeah)\s*)+", t):
        return "Acknowledged. State your next request when ready."
    if re.fullmatch(r"(?:stop|cancel|never mind|that's enough|that is enough)", t):
        return "Understood. I'll stand by."
    if _GREET.search(t):
        if not any("I can open pages" in str(h.get("text", "")) for h in said):
            return INTRO
        if "again" in t:
            return "Good evening. What do you need?"
        return ["Good evening. How may I assist?", "I'm listening. State your request.", "Good evening. What do you need?"][n % 3]
    if re.search(r"^(thanks|thank you|cheers)\b", t):
        return ["You're welcome.", "At your service.", "Certainly."][n % 3]
    return None


def _clean(text: str) -> str:
    t = re.sub(r"[^\w\s'’-]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t.replace("’", "'")).strip()


def match_rules(text: str) -> "tuple[dict, str, float] | None":
    t = _clean(text)
    if not t:
        return None
    for c in [_BY_ID["new_ask"], _BY_ID["pause_all"]] + [x for x in COMMANDS if x["id"] not in ("new_ask", "pause_all")]:
        for rx in c["rx"]:
            m = re.search(rx, t)
            if m:
                arg = (m.groupdict().get("arg") or "").strip()
                if c["id"] == "new_ask" and len(arg) < 3:
                    continue
                return c, arg, 1.0
    return None


# ── the hub, as the assistant sees it ────────────────────────────────────────────────────────────────────────────────
_WAITING = ("needs_input", "plan_ready", "awaiting_review", "paused")
_SHORT = {"needs_input": "waiting for answers", "plan_ready": "plan ready, waiting for you to run it", "awaiting_review": "finished, waiting for your review",
          "paused": "paused", "running": "running", "queued": "queued", "failed": "failed", "timed_out": "timed out", "applied": "applied",
          "discarded": "discarded", "orphaned": "recovered from disk"}


def _missions() -> list:
    from . import missions as M
    return sorted((m for m in M.S.m.values() if m.status != "orphaned"), key=lambda m: -(m.created or 0))


def status_line() -> str:
    ms = _missions()
    need = [m for m in ms if m.status in _WAITING]
    run = [m for m in ms if m.status in ("running", "queued")]
    if not need and not run:
        return "Nothing is waiting for you and nothing is running."
    bits = []
    if need:
        bits.append(f"{len(need)} ask{'s' if len(need) != 1 else ''} waiting for you")
    if run:
        bits.append(f"{len(run)} running")
    return ", ".join(bits).capitalize() + "."


def snapshot(mission_id: str | None = None) -> str:
    ms = _missions()[:12]
    lines = []
    for m in ms:
        done = sum(1 for s in (m.plan or []) if s.get("status") == "done")
        prog = f", {done}/{len(m.plan)} steps done" if m.plan else ""
        lines.append(f"- {m.id}: {m.project_name} | {_SHORT.get(m.status, m.status)}{prog} | \"{(m.brief or '').splitlines()[0][:70] if m.brief else ''}\"")
    cur = ""
    if mission_id:
        m = next((x for x in ms if x.id == mission_id), None)
        if m:
            cur = f"\nThe user is looking at ask {m.id} ({m.project_name}) right now."
            if m.status == "needs_input" and m.questions:
                cur += " Its questions: " + "; ".join(q.get("q", "") for q in m.questions[:3]) + "."
            if m.error:
                cur += f" Its error: {m.error[:120]}."
    return ("Asks (newest first):\n" + "\n".join(lines) if lines else "There are no asks yet.") + cur


def _mcp_servers() -> dict:
    try:
        from . import opencode as OCM
        return (json.loads(Path(OCM.OPENCODE_CONFIG).read_text(encoding="utf-8")).get("mcp") or {})
    except Exception:
        return {}


def capabilities_text() -> str:
    can = "\n".join(f"- {k}({v['args']}): {v['desc']}{' [needs the user to say yes first]' if v['confirm'] else ''}" for k, v in ACTIONS.items())
    return "YOU CAN DO (action ids):\n" + can + "\n\nYOU CANNOT DO (say so plainly, and say what would be needed):\n" + "\n".join("- " + x for x in limits())


def help_text() -> str:
    return ("I can open pages, say what's waiting, explain an ask, start a new ask, answer its questions with the defaults, run, apply, discard, pause or resume one, "
            "ingest an app from a git address, and report on MCP servers or switch PC control on and off. I can't click things myself, add MCP servers, or read out web addresses reliably.")


# ── executing actions ────────────────────────────────────────────────────────────────────────────────────────────────
def _find(mid):
    from . import missions as M
    return M.S.m.get(str(mid or "").strip())


def _direct_pc_request(text: str) -> dict | None:
    """Recognise only bounded, launch-only TALK commands. Complex GUI work stays with MCP/Quick Chat."""
    t = _clean(text)
    # More specific actions must precede a generic "open YouTube" match.
    patterns = (
        r"\b(?:search(?: (?:on|in))? youtube(?: for)?|search youtube for|open youtube (?:and|then) search(?: for)?)\s+(.+)",
        r"\byoutube\s+(?:search|search for)\s+(.+)",
    )
    for pattern in patterns:
        m = re.search(pattern, t)
        if m and len(m.group(1).strip()) >= 2:
            query = m.group(1).strip()
            return {"kind": "url", "value": "https://www.youtube.com/results?search_query=" + quote_plus(query), "label": "that YouTube search"}
    if re.search(r"\b(open|launch|start)\b.*\b(edge|browser)\b", t):
        return {"kind": "edge"}
    if re.search(r"\b(open|launch|start|go to|take me to)\b.*\byoutube\b", t):
        return {"kind": "url", "value": "https://www.youtube.com/", "label": "YouTube"}
    if re.search(r"\b(open|launch|start|go to|take me to)\b.*\bgoogle\b", t):
        return {"kind": "url", "value": "https://www.google.com/", "label": "Google"}
    m = re.search(r"\b(?:search(?: (?:the )?(?:web|internet))?(?: for)?|google|look up)\s+(.+)", t)
    if m:
        query = m.group(1).strip()
        query = re.sub(r"\b(?:in|on|using) (?:the )?(?:edge|browser|google)\b", "", query).strip()
        if len(query) >= 2:
            return {"kind": "url", "value": "https://www.google.com/search?q=" + quote_plus(query), "label": "a web search"}
    return None

def _edge_executable() -> Path | None:
    roots = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]
    tails = [
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for root, tail in zip(roots, tails):
        candidate = Path(root, *tail) if root else None
        if candidate and candidate.is_file():
            return candidate
    found = shutil.which("msedge.exe") or shutil.which("msedge")
    return Path(found) if found else None


def _launch_edge(url: str | None = None) -> None:
    executable = _edge_executable()
    if executable:
        subprocess.Popen([str(executable), *( [url] if url else [] )], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return
    # Windows' registered Edge protocol is a safe fallback because `url` is generated above.
    os.startfile("microsoft-edge:" + (url or ""))


def _label(aid: str, args: dict) -> str:
    m = _find(args.get("mission")) if args.get("mission") else None
    on = f" for {m.project_name}" if m else ""
    return {"answer_defaults": "Answer with the defaults" + on, "run_plan": "Run the plan" + on, "apply": "Apply the work" + on, "discard": "Discard the ask" + on,
            "pause": "Pause " + (m.project_name if m else "every running ask"), "resume": "Resume" + on, "ingest_app": "Ingest " + str(args.get("url", ""))[:60],
            "pc_control": "Switch PC control " + str(args.get("state", ""))}.get(aid, aid)


async def run_action(aid: str, args: dict) -> dict:
    """Run one action. Returns {say, url?}; a refusal is a normal answer, not an error."""
    from . import missions as M
    args = args if isinstance(args, dict) else {}
    if aid not in ACTIONS:
        return {"say": "I don't have that ability."}
    try:
        if aid == "open_page":
            page = str(args.get("page", "")).lower()
            return {"say": f"Opening {page}.", "url": PAGES[page]} if page in PAGES else {"say": "I can open missions, agents, graph, locations or the hub."}
        if aid == "status":
            need = [m for m in _missions() if m.status in _WAITING][:4]
            more = ("  " + " ".join(f"{m.project_name}: {_SHORT[m.status]}." for m in need)) if need else ""
            return {"say": status_line() + more}
        if aid == "list_projects":
            from ..agent_knowledge.projects import discover_projects
            ps = [p for p in discover_projects() if not p.get("readonly")]
            return {"say": f"There are {len(ps)} project folders. Some of them: " + ", ".join(p["name"] for p in ps[:6]) + "."}
        if aid == "list_agents":
            ags = [a for a in agent_knowledge.list_agents() if a["name"] not in agent_knowledge.UTILITY_AGENTS]
            return {"say": f"{len(ags)} agents, including " + ", ".join(a["name"] for a in ags[:7]) + ". Open the agents page for what each one does."}
        if aid == "mcp_status":
            s = _mcp_servers()
            if not s:
                return {"say": "No MCP servers are configured for OpenCode. So I can work inside the hub and its asks, but I can't control other programs or files on this PC. A Windows MCP server would add that, and I'd need your approval to install it."}
            names = ", ".join(f"{k}{'' if v.get('enabled', True) else ' (switched off)'}" for k, v in s.items())
            extra = " Say enable PC control to switch it on." if any(not v.get("enabled", True) for v in s.values()) else ""
            return {"say": f"OpenCode has {len(s)} MCP server{'s' if len(s) != 1 else ''}: {names}. I can report on them and switch PC control on or off, but not add or change servers.{extra}"}
        if aid == "pc_app":
            from . import pc_control as PC
            return await PC.launch_app(str(args.get("app") or ""), str(args.get("request") or args.get("app") or ""))
        if aid == "pc_direct":
            from . import mcp as MCP
            if str(args.get("state") or "").lower() == "on":
                MCP.set_enabled("windows", True)
            win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
            if not win or not win["installed"]:
                return {"say": "PC control is not installed."}
            if not win["enabled"]:
                return {"say": "PC control is off. Switch on the wireframe PC button beside TALK, then ask again."}
            kind, value = str(args.get("kind") or ""), str(args.get("value") or "")
            if kind == "edge":
                _launch_edge()
                return {"say": "Opening Edge."}
            if kind == "url" and value.startswith("https://"):
                _launch_edge(value)
                return {"say": "Opening " + str(args.get("label") or "that page") + " in Edge."}
            return {"say": "I can directly open Edge, YouTube, Google, or a web search. For other PC work, I will use the PC agent."}
        if aid == "pc_task":
            from . import mcp as MCP
            from . import opencode as OCM
            task = str(args.get("text", "")).strip()
            if not task:
                return {"say": "Tell me what you would like the PC agent to do."}
            if str(args.get("state", "")).lower() == "on":
                MCP.set_enabled("windows", True)
                await OCM.OC.stop_project(OCM.SCRATCH_SLUG)
            win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
            if not win or not win["installed"]:
                return {"say": "PC control is not installed."}
            if not win["enabled"]:
                return {"say": "PC control is off. Switch on the wireframe PC button, then ask again."}
            rt = await OCM.OC.open_scratch()
            status, session = await rt._api("POST", "session", json={})
            if not (status and status < 400 and isinstance(session, dict)):
                return {"say": "I could not start a Quick Chat for that PC task."}
            sid = session.get("id") or session.get("sessionID")
            prompt = {"parts": [{"type": "text", "text": "Use the Windows MCP tools to fulfil this explicit desktop request. Do not edit project files. Briefly report what you did.\n\nREQUEST: " + task}]}
            status, _ = await rt._api("POST", f"session/{sid}/prompt_async", json=prompt, timeout=15)
            if not status or status >= 400:
                asyncio.create_task(rt._api("POST", f"session/{sid}/message", json=prompt, timeout=1800))
            ui = await rt.ui_dir()
            return {"say": "Opening a fresh Quick Chat to carry that out.", "url": rt.open_url("127.0.0.1") + f"/{ui}/session/{sid}"}
        if aid == "pc_control":
            from . import mcp as MCP
            state = str(args.get("state", "")).lower()
            if state not in ("on", "off"):
                return {"say": "Please specify whether PC control should be on or off."}
            want = state == "on"
            try:
                r = MCP.set_enabled("windows", want)
            except KeyError:
                return {"say": "PC control isn't installed, so there's nothing to switch."}
            except FileNotFoundError as exc:
                return {"say": "I can't switch it on: " + str(exc)}
            message = (f"PC control is {'on' if want else 'off'}." if r["changed"] else f"PC control was already {'on' if want else 'off'}.")
            return {"say": message + " This setting is used when an OpenCode workspace or mission is prepared. Restart existing workspaces to reload it; an already prepared mission may retain its previous setting."}
        if aid == "new_ask":
            text = str(args.get("text", "")).strip()
            if len(text) < 3:
                return {"say": "What should the new ask say?"}
            url = "/missions?ask=" + quote(text) + (("&project=" + quote(str(args["project"]))) if args.get("project") else "")
            return {"say": "Opening a new ask with that.", "url": url}
        if aid == "open_mission":
            m0 = _find(args.get("mission"))
            if not m0:
                return {"say": "I can't find that ask."}
            return {"say": "Opening it.", "url": "/missions?open=" + m0.id}
        if aid == "ingest_app":
            url = str(args.get("url", "")).strip()
            if re.match(r"^[\w.-]+/[\w.-]+$", url):
                url = "https://github.com/" + url                      # "owner/repo" is easy to say; a full URL is not
            if not re.match(r"^(https?://|git@)", url):
                return {"say": "I need a git address I can trust. Speech makes those unreliable, so please type it in the box, or say it as owner slash repo."}
            m = await M.dispatch_ingest(url)
            return {"say": f"Started ingesting {m.project_name}. It will wait in your inbox for review before anything is wired in.", "url": "/missions"}
        if aid == "pause" and not args.get("mission"):
            n = 0
            for m in list(M.S.m.values()):
                if m.status == "running":
                    await M.abort(m.id)
                    n += 1
            return {"say": f"Paused {n} running ask{'s' if n != 1 else ''}." if n else "Nothing was running."}
        m = _find(args.get("mission"))
        if aid in ("mission_info", "answer_defaults", "run_plan", "apply", "discard", "pause", "resume") and not m:
            return {"say": "I can't find that ask. Tell me the project name, or open Missions and pick it."}
        if aid == "mission_info":
            done = sum(1 for s in (m.plan or []) if s.get("status") == "done")
            bits = [f"{m.project_name} is {_SHORT.get(m.status, m.status)}."]
            if m.plan:
                bits.append(f"{done} of {len(m.plan)} steps done.")
            if m.status == "needs_input":
                bits.append("It asks: " + "; ".join(q.get("q", "") for q in (m.questions or [])[:3]) + ".")
            if m.verify:
                bits.append("Hub checks " + ("passed." if m.verify.get("ok") else "failed."))
            nxt = {"needs_input": "Say answer with defaults, or open it to choose.", "plan_ready": "Say run the plan, or open it to edit the steps.",
                   "awaiting_review": "Say apply it, or open it to read the result first.", "paused": "Say resume.", "failed": "Say resume, or open it to see why."}.get(m.status)
            return {"say": " ".join(bits + ([nxt] if nxt else []))}
        need_state = {"answer_defaults": ("needs_input",), "run_plan": ("plan_ready",), "apply": ("awaiting_review",), "resume": ("paused", "failed", "timed_out", "awaiting_review")}
        if aid in need_state and m.status not in need_state[aid]:
            return {"say": f"I can't do that: {m.project_name} is {_SHORT.get(m.status, m.status)}."}
        if aid == "answer_defaults":
            await M.answer(m.id, [])
            return {"say": f"Answered {m.project_name}'s questions with the defaults. It's planning now."}
        if aid == "run_plan":
            await M.run_plan(m.id)
            return {"say": f"Started the plan for {m.project_name}."}
        if aid == "apply":
            r = await M.apply(m.id)
            return {"say": f"Applied {m.project_name}." if r.get("ok") else "It was not merged: " + str(r.get("reason") or r.get("output") or "see the Missions page")[:140]}
        if aid == "discard":
            await M.discard(m.id)
            return {"say": f"Discarded the {m.project_name} ask."}
        if aid == "pause":
            await M.abort(m.id)
            return {"say": f"Paused {m.project_name}."}
        if aid == "resume":
            await M.resume(m.id)
            return {"say": f"Resuming {m.project_name}."}
    except web.HTTPException as exc:
        return {"say": "I can't do that: " + (exc.text or exc.reason or "it was refused")[:140]}
    except Exception as exc:
        logger.warning("voice action %s failed: %s", aid, exc)
        return {"say": "That didn't work: " + str(exc)[:120]}
    return {"say": "I don't know how to do that yet."}


# ── the reply ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _reply(say: str, action: "tuple[str, dict] | None", backend: str, heard: str) -> dict:
    out = {"say": say, "action": None, "confirm": False, "url": None, "backend": backend, "heard": heard}
    if action:
        aid, args = action
        out["action"] = {"id": aid, "args": args, "label": _label(aid, args)}
        out["confirm"] = ACTIONS[aid]["confirm"]
        if aid == "open_page" and args.get("page") in PAGES:
            out["url"] = PAGES[args["page"]]
        elif aid == "open_mission" and args.get("mission"):
            out["url"] = "/missions?open=" + quote(str(args["mission"]))
        elif aid == "new_ask":
            out["url"] = "/missions?ask=" + quote(str(args.get("text", ""))) + (("&project=" + quote(str(args["project"]))) if args.get("project") else "")
    return out


def _schema() -> dict:
    return {"type": "object", "properties": {
        "say": {"type": "string"},
        "action": {"type": "string", "enum": ["none"] + list(ACTIONS)},
        "page": {"type": "string"}, "mission": {"type": "string"}, "text": {"type": "string"}, "project": {"type": "string"}, "url": {"type": "string"}, "state": {"type": "string", "enum": ["on", "off"]}},
        "required": ["say", "action"]}


_SYSTEM = (
    "You are the voice of Agent Hub, a personal hub that runs AI 'asks' (missions) on the user's projects and fronts a few apps. You are talking "
    "aloud, so answer in one or two short plain sentences, British English, no lists, no markdown. Be professional, warm and respectful; "
    "avoid sarcasm, jokes about failures, curt replies like 'Yes?', and repeating your introduction. Use ONLY the facts in HUB STATE; never invent "
    "an ask, a project or a result. If the user wants something you can do, set action to its id and fill the fields it needs (mission = an exact "
    "ask id from HUB STATE); otherwise action is none. When the user says open it, show me or read it about an ask, use open_mission. Always put a short sentence in say. Actions that need a yes are only proposed: say what you are about to do and ask for a yes. "
    "If the user asks for something you cannot do, say so plainly and say what would be needed. If it is unclear which ask they mean, ask one short "
    "question instead of guessing. If they just chat, chat back briefly and offer what you can do.\n\n")


async def _llm(text: str, history: list, mission_id: "str | None") -> "dict | None":
    chain = [x for x in agent_knowledge.model_chain(None, None) if x.startswith("ollama/")]
    if not chain:
        return None
    msgs = [{"role": "system", "content": _SYSTEM + capabilities_text() + "\n\nHUB STATE:\n" + snapshot(mission_id)}]
    for h in (history or [])[-8:]:
        role = "assistant" if h.get("role") in ("assistant", "hub") else "user"
        msgs.append({"role": role, "content": str(h.get("text", ""))[:400]})
    msgs.append({"role": "user", "content": text})
    body = {"stream": False, "format": _schema(), "options": {"temperature": 0.4, "num_predict": 220, "num_ctx": 8192}, "messages": msgs}
    for mdl in chain[:2]:
        body["model"] = mdl.split("/", 1)[1]
        try:
            try:
                d = await DEC._ollama_raw(body)
            except Exception:
                from . import missions as M
                if not await M._ensure_ollama():
                    raise
                d = await DEC._ollama_raw(body)
            raw = (d.get("message") or {}).get("content") or "{}"
            j = json.loads(raw)
            if isinstance(j, dict) and (str(j.get("say") or "").strip() or str(j.get("action") or "none") != "none"):
                return j                                            # an action with no spoken text is fine: the action's own result gets spoken
            logger.info("voice: %s gave nothing usable: %s", mdl, raw[:160])
        except Exception as exc:
            logger.info("voice: %s failed: %s", mdl, exc)
    return None


async def chat(text: str, history: "list | None" = None, mission_id: "str | None" = None, use_model: bool = True) -> dict:
    heard = text
    hit = match_rules(text)
    if hit:
        c, arg, _p = hit
        aid, args = c["action"]
        args = {"text": arg} if aid == "new_ask" else dict(args or {})
        say = {"status": status_line(), "pause": "Pause every running ask? Say yes to confirm."}.get(aid) or (f"Opening {args.get('page')}." if aid == "open_page" else f"Starting a new ask: {args.get('text')}.")
        return _reply(say, (aid, args), "rules", heard)
    t = _clean(text)
    pc = re.fullmatch(r"(?:please )?(?:(enable|start|activate|disable) (?:pc control|mcp)|(?:switch|turn) (?:pc control|mcp) (on|off))(?: please)?", t)
    if pc:
        state = "on" if (pc.group(1) in ("enable", "start", "activate") or pc.group(2) == "on") else "off"
        return _reply(f"Turning PC control {state}.", ("pc_control", {"state": state}), "rules", heard)
    if re.fullmatch(r"(?:what (?:mcp tools|pc control tools)(?: are available)?|mcp status|pc control status)", t):
        return _reply("", ("mcp_status", {}), "rules", heard)
    direct = _direct_pc_request(text)
    if direct:
        from . import mcp as MCP
        win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
        wants_on = bool(re.search(r"\b(?:enable|start|activate|turn on|switch on)\s+(?:pc control|mcp)\b", t))
        if win and (win["enabled"] or wants_on):
            if wants_on:
                direct["state"] = "on"
                return _reply("Turning PC control on and carrying that out directly.", ("pc_direct", direct), "rules", heard)
            return _reply("Carrying that out directly.", ("pc_direct", direct), "rules", heard)
        return _reply("PC control is off. Switch on the wireframe PC button beside TALK, then I can directly open Edge, YouTube, Google, or a web search.", None, "rules", heard)
    from . import pc_control as PC
    task = PC.classify_request(text)
    if task and task["kind"] == "launch_app":
        from . import mcp as MCP
        win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
        if win and win["enabled"]:
            return _reply(f"Opening {PC.display_app_name(task['app'])} through PC control.", ("pc_app", {"app": task["app"], "request": text}), "rules", heard)
        return _reply("PC control is off. Switch on the wireframe PC button beside TALK, then ask me to open the application.", None, "rules", heard)
    if re.search(r"\b(open|launch|start)\b.*\b(chrome|firefox|notepad)\b", t):
        from . import mcp as MCP
        win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
        wants_on = bool(re.search(r"\b(?:enable|turn on|switch on)\s+(?:pc control|mcp)\b", t))
        if (win and win["enabled"]) or wants_on:
            say = "I will switch PC control on and hand that to a fresh Quick Chat." if wants_on else "I will hand that to a fresh Quick Chat with PC control."
            return _reply(say, ("pc_task", {"text": text, "state": "on" if wants_on else ""}), "rules", heard)
        return _reply("PC control is off. Switch on the wireframe PC button beside TALK, then I can hand that to the PC agent.", None, "rules", heard)
    chit = smalltalk(text, history or [])
    if chit:
        return _reply(chit, None, "rules", heard)
    if re.search(r"^(help|what can you do|what do you do|what are your limits)\b", t):
        return _reply(help_text(), None, "rules", heard)
    if use_model:
        try:
            got = await asyncio.wait_for(_llm(text, history or [], mission_id), timeout=35)
        except asyncio.TimeoutError:
            return _reply("That response took too long. Please try again, or use a simple command such as open missions.", None, "rules", heard)
        if got:
            j, aid = got, str(got.get("action") or "none")
            args = {k: j[k] for k in ("page", "mission", "text", "project", "url", "state") if j.get(k)}
            if aid == "pc_control" and args.get("state") not in ("on", "off"):
                return _reply("Would you like PC control switched on or off?", None, "model", heard)
            if aid in ("open_mission", "mission_info") and not args.get("mission") and mission_id:
                args["mission"] = mission_id                      # "open it" while an ask is open means that ask
            action = (aid, args) if aid in ACTIONS else None
            if action and action[0] in ("open_mission", "mission_info", "answer_defaults", "run_plan", "apply", "discard", "resume") and not _find(args.get("mission")):
                return _reply("Which ask do you mean? Tell me the project name.", None, "model", heard)
            say = str(j.get("say") or "").strip()[:400]
            if action and action[0] == "open_mission":
                info = (await run_action("mission_info", args))["say"]
                return _reply("Opening it. " + info, action, "model", heard)
            return _reply(say, action, "model", heard)
        return _reply("My language model didn't give me anything I could use for that. I can still open pages, say what's waiting, or start an ask. Try asking again, or say what you'd like to do.", None, "rules", heard)
    return _reply("I did not catch a command. Try 'open missions', 'status' or 'new ask to write a post'.", None, "rules", heard)


async def _body(request: web.Request) -> dict:
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@routes.post("/api/voice/chat")
async def api_chat(request: web.Request) -> web.Response:
    b = await _body(request)
    text = str(b.get("text") or "").strip()[:500]
    if not text:
        raise web.HTTPBadRequest(text="no text")
    return web.json_response(await chat(text, b.get("history") if isinstance(b.get("history"), list) else [], b.get("mission") or None))


@routes.post("/api/voice/act")
async def api_act(request: web.Request) -> web.Response:
    b = await _body(request)
    return web.json_response(await run_action(str(b.get("id", "")), b.get("args") or {}))


# ── local speech-to-text ─────────────────────────────────────────────────────────────────────────────────────────────
_MODEL: dict = {}
_LOCK = asyncio.Lock()
_HALLUCINATIONS = {"you", "thank you for watching", "thanks for watching", "bye"}


def _cached_model_name() -> "str | None":
    root = Path(os.environ.get("HF_HOME") or (Path(os.environ.get("USERPROFILE") or Path.home()) / ".cache" / "huggingface")) / "hub"
    for name in ("base", "tiny", "small"):
        snaps = root / f"models--Systran--faster-whisper-{name}" / "snapshots"
        if snaps.is_dir() and any(snaps.iterdir()):
            return name
    return None


def whisper_status() -> dict:
    if RT.PACKAGED:
        from .onboarding import state
        name = state().get("speech_model")
        ready = (name in ("tiny", "base", "small") and RT.python_for("speech").is_file()
                 and (RT.STATE / "models" / (name + ".ready")).is_file())
        return {"whisper": bool(ready), "model": name if ready else None,
                "note": "" if ready else "Open Setup tools → TALK speech to install speech and choose a model.",
                "setup_url": "/onboarding#speech"}
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return {"whisper": False, "model": None, "note": "faster-whisper is not installed"}
    name = _cached_model_name()
    return {"whisper": bool(name), "model": name, "note": "" if name else "no faster-whisper model is cached on this machine (nothing is downloaded automatically)"}


def _load_model(name: str):
    if name not in _MODEL:
        from faster_whisper import WhisperModel
        _MODEL[name] = WhisperModel(name, device="cpu", compute_type="int8", local_files_only=True)
    return _MODEL[name]


def _transcribe_file(path: str, name: str, lang: "str | None") -> str:
    if RT.PACKAGED:
        r = RT.run([str(RT.python_for("speech")), str(RT.ASSETS / "packaging" / "speech_worker.py"),
                    "transcribe", name, str(RT.STATE / "models"), path, lang or ""], 180)
        if r.returncode:
            raise RuntimeError(r.stderr[-1000:])
        text = json.loads(r.stdout)["text"]
        return "" if _clean(text) in _HALLUCINATIONS else text
    segs, _info = _load_model(name).transcribe(path, language=lang, vad_filter=True, beam_size=1, condition_on_previous_text=False)
    text = " ".join(s.text.strip() for s in segs).strip()
    return "" if _clean(text) in _HALLUCINATIONS else text


@routes.get("/api/voice/status")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, whisper_status))


@routes.post("/api/voice/transcribe")
async def api_transcribe(request: web.Request) -> web.Response:
    st = whisper_status()
    if not st["whisper"]:
        raise web.HTTPNotImplemented(text=st["note"])
    data = await request.read()
    if not data or len(data) > 8 * 1024 * 1024:
        raise web.HTTPBadRequest(text="send 1 byte to 8 MB of audio")
    ct = (request.content_type or "").lower()
    fd, path = tempfile.mkstemp(suffix=".wav" if "wav" in ct else ".ogg" if "ogg" in ct else ".mp4" if "mp4" in ct else ".webm")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        t0 = time.time()
        async with _LOCK:
            text = await asyncio.get_running_loop().run_in_executor(None, _transcribe_file, path, st["model"], request.query.get("lang", "en") or None)
        return web.json_response({"text": text, "model": st["model"], "seconds": round(time.time() - t0, 2)})
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ── speaking: Microsoft neural voices via edge-tts (the reply text is sent, never your audio) ───────────────────────────
VOICES = [
    {"id": "smith", "name": "Smith · Australian, low and measured", "voice": "en-AU-WilliamNeural", "rate": "-10%", "pitch": "-12Hz"},
    {"id": "smith-deep", "name": "Smith · deeper and slower", "voice": "en-AU-WilliamNeural", "rate": "-14%", "pitch": "-22Hz"},
    {"id": "sonia", "name": "Sonia · British, female", "voice": "en-GB-SoniaNeural", "rate": "+4%", "pitch": "+0Hz"},
    {"id": "ryan", "name": "Ryan · British, male", "voice": "en-GB-RyanNeural", "rate": "+2%", "pitch": "+0Hz"},
    {"id": "libby", "name": "Libby · British, female", "voice": "en-GB-LibbyNeural", "rate": "+4%", "pitch": "+0Hz"},
    {"id": "thomas", "name": "Thomas · British, male", "voice": "en-GB-ThomasNeural", "rate": "+2%", "pitch": "+0Hz"},
    {"id": "aria", "name": "Aria · American, female", "voice": "en-US-AriaNeural", "rate": "+4%", "pitch": "+0Hz"},
    {"id": "guy", "name": "Guy · American, male", "voice": "en-US-GuyNeural", "rate": "+2%", "pitch": "+0Hz"},
    {"id": "natasha", "name": "Natasha · Australian, female", "voice": "en-AU-NatashaNeural", "rate": "+4%", "pitch": "+0Hz"},
]
_VOICE_BY_ID = {v["id"]: v for v in VOICES}
_TTS_CACHE: dict = {}


@routes.get("/api/voice/voices")
async def api_voices(request: web.Request) -> web.Response:
    if RT.PACKAGED:
        ok = RT.python_for("speech").is_file()
    else:
        try:
            import edge_tts  # noqa: F401
            ok = True
        except Exception:
            ok = False
    return web.json_response({"voices": [{"id": v["id"], "name": v["name"]} for v in VOICES], "default": VOICES[0]["id"], "neural": ok})


def _speakable(text: str) -> str:
    t = re.sub(r"[*_`#>\[\]]", "", text or "")
    return re.sub(r"\s+", " ", t).strip()[:600]


@routes.post("/api/voice/speak")
async def api_speak(request: web.Request) -> web.Response:
    b = await _body(request)
    text = _speakable(str(b.get("text") or ""))
    v = _VOICE_BY_ID.get(str(b.get("voice") or ""), VOICES[0])
    if not text:
        raise web.HTTPBadRequest(text="no text")
    key = (text, v["id"])
    if key in _TTS_CACHE:
        return web.Response(body=_TTS_CACHE[key], content_type="audio/mpeg")
    if RT.PACKAGED and not RT.python_for("speech").is_file():
        raise web.HTTPNotImplemented(text="Open Setup tools → TALK speech first.")
    if not RT.PACKAGED:
        try:
            import edge_tts
        except Exception:
            raise web.HTTPNotImplemented(text="edge-tts is not installed")

    async def go() -> bytes:
        if RT.PACKAGED:
            # Neural TTS lives in the managed speech runtime, not in the Hub.
            proc = await asyncio.create_subprocess_exec(
                str(RT.python_for("speech")), str(RT.ASSETS / "packaging" / "speech_worker.py"), "speak",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                out, err = await proc.communicate(json.dumps({"text": text, **v}).encode("utf-8"))
                if proc.returncode:
                    raise RuntimeError(err.decode(errors="replace")[-300:])
                return out
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
        buf = b""
        async for ch in edge_tts.Communicate(text, v["voice"], rate=v["rate"], pitch=v["pitch"]).stream():
            if ch["type"] == "audio":
                buf += ch["data"]
        return buf
    try:
        audio = await asyncio.wait_for(go(), timeout=20)
    except Exception as exc:
        raise web.HTTPServiceUnavailable(text=f"the neural voice service did not answer: {str(exc)[:80]}")
    if not audio:
        raise web.HTTPServiceUnavailable(text="no audio came back")
    if len(_TTS_CACHE) > 30:
        _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
    _TTS_CACHE[key] = audio
    return web.Response(body=audio, content_type="audio/mpeg")


@routes.get("/smith-icon.png")
async def smith_icon(request: web.Request) -> web.Response:
    from .. import agents_ui
    return web.Response(body=base64.b64decode(agents_ui._SMITH_D_B64), content_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


