"""Fix Agent Hub from inside Agent Hub.

The same loop used from a chat window, built into the Hub: describe what is wrong (or just press DIAGNOSE), the Hub gathers
the facts (`/api/diagnose`: version, services, errors, a redacted log tail), and a *doctor* agent works in a private copy of
the Hub's own repository, the way any mission does. What comes back is a diff and a short account. Nothing is installed
until you press APPLY, and the Hub is never restarted by the doctor: that stays your button.

Why a mission and not a new mechanism: the mission machinery already gives an isolated copy of a git repository, a model
chain, the project's own checks after the work, review and APPLY. A second way to let an agent edit this machine would be a
second thing to get wrong.

The doctor is told where things live, what not to touch (state files, tokens, logs) and how to check its own work. It is a
read-and-propose tool: its copy is a git worktree, so a change that is not applied costs nothing.
"""
from __future__ import annotations

import json
import time

import aiohttp
from aiohttp import web
from ..embed import embedded

from .. import config
from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()
FILE = STATE / "support_missions.json"
SETTINGS = STATE / "support_settings.json"
RUNTIMES = ("claude-code", "opencode")     # how the doctor works: Claude Code (default) or the local-first OpenCode team


def default_runtime() -> str:
    """The method the doctor uses when nobody picks one for this ask: what the owner chose on the Support page, else Claude Code."""
    try:
        v = json.loads(SETTINGS.read_text(encoding="utf-8")).get("runtime")
        return v if v in RUNTIMES else RUNTIMES[0]
    except (OSError, ValueError, AttributeError):
        return RUNTIMES[0]

RULES = """You are the doctor for Agent Hub, a Python (aiohttp) app. Anything the owner wants changed in Agent Hub is yours to do: a fault, something that looks wrong, something that behaves
differently from what they meant, a panel or button to add or change, a new capability, the installer, the website, the tests. Your working copy is a private git worktree of its
repository; nothing you change reaches the running Hub until the owner presses APPLY, and the owner restarts it. How to work:
- Read before you write. The map of the Hub below is generated from the code itself; open the files it points to, search the repository (README, the plans, the code, the tests), and follow a
  feature from where the owner sees it (a page, a button, a voice phrase) to the code that answers it. Never rely on a name you have not looked up.
- For a fault, find the cause first and say what you found in a sentence or two, then make the smallest change that fixes the cause. For a request to build or change something, build the whole
  thing, in the style of the code around it, and finish it: a half-built panel is worse than none. Do the thing that was asked, not a nearby thing.
- The owner's words are the spec. If they described how it should look or behave, that is the acceptance test: make what they described, and say honestly what you could not do.
- Do not touch state or secrets: hub/*.json that the Hub writes itself, hub/data, logs/, tokens, keys. Do not reformat or rename what you are not changing.
- Check what you changed and only that: `python -c "import hub.ui, app"` must work, `node --check` every JavaScript file you edit, and run the tests that cover the part you touched when
  they exist (`python -m pytest packaging/<file> -q`; AGENTHUB_TEST_BROWSER=bundled uses the bundled Chromium instead of Edge). Do not write or run tests the owner did not ask for. Tests must never touch
  the owner's real data.
- Installed copies: the Hub is also shipped as an installer (packaging/). Things only break there: code must not read its own source file; a data file read from beside the code is bundled by
  rule, but a new file kind, a new top-level folder, code in a folder named like private state, or a new pip library needs a decision (packaging/stage_release.py, packaging/payloads.json).
  `python -c "import sys; sys.path.insert(0,'packaging'); import stage_release as S; from pathlib import Path; print(S.unshipped_surprises(Path('.')))"` lists what a build would silently drop.
  The install check is in the facts below (install.problems).
- On screen: Orbitron for text, the dark glass look the dashboard has (a translucent card, a soft glowing green edge, a little blur; /theme.css carries it for every page), line icons as inline SVG
  and never emoji, no layout that moves when something loads. The four core agents are Orchestrator, Neo, Smith and the Doctor; their pictures are hub/static/agent-art/*.svg.
- Never restart, stop or start the Hub, and never call its power or shutdown endpoints.
- Neo is the agent that designs and edits agents (Smith is only the voice the owner talks to). When the work is in an agent's instructions (hub/agent_knowledge/agents/*.md) you may call Neo: POST {"description": "what to change", "base": "<the current file text, optional>"} to THE RUNNING HUB below at /api/agents/draft, with an Origin header equal to that address. You get markdown back; nothing is saved. Put it in your copy as hub/agent_knowledge/agents/<name>.md and it reaches the owner through APPLY like any other change. Use it for nothing else.
- If the facts say this is an INSTALLED copy (install.can_edit_code is false) there is no source here to change: diagnose, say exactly which file and what the change is, and finish with DONE: naming it,
  so the owner can make it in the repository and ship an update. Do not pretend to have changed anything.
- End with a line starting DONE: that says what you changed and why, or what you found if no change is needed."""


def repo_map(limit: int = 140) -> str:
    """A map of the Hub made from the code in front of it: each module with the first line of its own docstring, each page script with its first comment. Generated at the moment the
    doctor is asked, so it is never out of date and never lists something that is not there."""
    import ast as _ast
    from pathlib import Path as _P
    root = _P(config.HERE)
    rows: "list[str]" = []
    for folder in ("hub", "hub/features", "hub/yard", "packaging"):
        d = root / folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name.startswith(("test_", "__")):
                continue
            try:
                doc = _ast.get_docstring(_ast.parse(f.read_text(encoding="utf-8", errors="replace"))) or ""
            except (SyntaxError, OSError, ValueError):
                doc = ""
            rows.append(f"{folder}/{f.name}: " + " ".join(doc.split("\n\n")[0].split())[:110])
    st = root / "hub" / "static"
    if st.is_dir():
        rows.append("hub/static/ (scripts and styles of the pages): " + ", ".join(sorted(p.name for p in st.iterdir() if p.suffix in (".js", ".css")))[:900])
    return "MAP OF THE HUB (from the code):\n" + "\n".join(rows[:limit])[:9000]



def _ids() -> "list[str]":
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def restart_timing() -> str:
    """How long the last restarts really took, from the supervisor's own log: the exit, then the new server."""
    import re
    from datetime import datetime
    try:
        logs = sorted((config.HERE / "logs").glob("hub_*.log"), key=lambda p: p.stat().st_mtime)
        lines = [ln for p in logs[-2:] for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return ""
    ev = []
    for ln in lines:
        m = re.match(r"(\d\d-\d\d-\d{4} \d\d:\d\d:\d\d)\s+(server exited, code=(\d+)|starting server)", ln)
        if m:
            ev.append((datetime.strptime(m.group(1), "%d-%m-%Y %H:%M:%S"), m.group(2)))
    out = []
    for i, (t, what) in enumerate(ev):
        if what.startswith("server exited") and i + 1 < len(ev):
            out.append(f"{t:%d %b %H:%M:%S} exit ({what.split('=')[1]}), next server started {int((ev[i + 1][0] - t).total_seconds())} s later")
    return ("RESTART TIMING (supervisor log):\n" + "\n".join(out[-4:]) + "\n\n") if out else ""


def facts() -> str:
    from . import diagnose as D
    b = D.bundle(lines=60)
    keep = {k: b[k] for k in ("hub", "apps", "missions", "local_model_server", "disk_free_gb", "install") if k in b}
    return restart_timing() + "FACTS FROM /api/diagnose:\n" + json.dumps(keep, indent=1)[:2500] + "\n\nRECENT WARNINGS AND ERRORS (secrets removed):\n" + "\n".join(b["problems"][-20:])[:5000]


def brief_for(text: str) -> str:
    text = (text or "").strip()
    ask = text or "Nothing specific was reported. Look at the facts and the recent warnings and say whether anything is wrong; fix it only if it clearly is."
    return f"{RULES}\n\nTHE RUNNING HUB: http://127.0.0.1:{config.PORT}\n\nTHE OWNER SAYS:\n{ask}\n\n{repo_map()}\n\n{facts()}"


async def _dispatch(brief: str, runtime: str, model: "str | None") -> dict:
    body = {"brief": brief, "project": str(config.HERE), "kind": "single", "autonomy": "auto", "runtime": runtime}
    if model:
        body["model"] = model
    origin = f"http://127.0.0.1:{config.PORT}"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.post(origin + "/api/missions", json=body, headers={"Origin": origin}) as r:
            if r.status != 200:
                raise web.HTTPBadGateway(text="could not start the doctor: " + (await r.text())[:200])
            return await r.json()


SIGN_IN = "Claude Code is signed out (its sign-in has expired). To reconnect: open a terminal, run claude, then type /login."
_AUTH_WORDS = ("failed to authenticate", "401", "oauth", "not logged in", "please run /login")


def claude_health() -> dict:
    """Is Claude Code, the doctor's default way of working, signed in? Judged from what actually happened: the newest Claude Code doctor mission, and the
    newest Claude Code sessions in its logs. {"ok": False, "why": ...} when the last attempt died on a sign-in error, else ok (or unknown)."""
    from . import missions as M
    for mid in reversed(_ids()):
        m = M.S.m.get(mid)
        if m and m.runtime == "claude-code":
            text = f"{m.error or ''} {getattr(m, 'answer', '') or ''}".lower()
            if any(w in text for w in _AUTH_WORDS):
                return {"ok": False, "why": SIGN_IN, "seen": "the doctor's last Claude Code mission"}
            if m.status in ("applied", "awaiting_review"):
                return {"ok": True, "why": ""}
            break
    try:
        from . import agent_sessions as AS
        rows = [r for r in AS.scan(limit=40) if r["agent"] == "claude" and r["title"] == "Doctor session"]
        if rows and any(w in (rows[0].get("last") or "").lower() for w in _AUTH_WORDS):
            return {"ok": False, "why": SIGN_IN, "seen": "the newest Doctor session in Claude Code's logs"}
    except Exception:  # noqa: BLE001
        pass
    return {"ok": None, "why": ""}


def last_asked() -> float:
    """When the doctor was last asked (a mission's creation time), 0 if never."""
    from . import missions as M
    t = 0.0
    for mid in _ids():
        m = M.S.m.get(mid)
        if m and m.created:
            t = max(t, float(m.created))
    return t


def latest() -> "dict | None":
    """The doctor's most recent mission, as a small row, or None."""
    from . import missions as M
    for mid in reversed(_ids()):
        m = M.S.m.get(mid)
        if m:
            s = m.summary()
            return {k: s.get(k) for k in ("id", "status", "model", "runtime", "changed", "answer", "error", "verify", "work_secs")}
    return None


async def start(text: str, runtime: "str | None" = None, model: "str | None" = None) -> dict:
    runtime = runtime if runtime in RUNTIMES else default_runtime()
    note = ""
    if runtime == "claude-code" and claude_health().get("ok") is False:
        runtime, note = "opencode", "Claude Code is signed out, so the doctor used the local team this time. " + SIGN_IN
    m = await _dispatch(brief_for(text), runtime, model)
    m["note"] = note
    write_json(FILE, (_ids() + [m["id"]])[-30:])
    logger.info("support: doctor started as mission %s (%s)", m["id"], runtime)
    return m


@routes.post("/api/support/ask")
async def api_ask(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    runtime = b.get("runtime") if b.get("runtime") in RUNTIMES else default_runtime()
    m = await start(str(b.get("text") or ""), runtime, str(b.get("model") or "") or None)
    return web.json_response({"ok": True, "mission": m["id"], "runtime": "opencode" if m.get("note") else runtime, "note": m.get("note", "")})


@routes.post("/api/support/runtime")
async def api_runtime(request: web.Request) -> web.Response:
    try:
        v = (await request.json()).get("runtime")
    except Exception:  # noqa: BLE001
        v = None
    if v not in RUNTIMES:
        raise web.HTTPBadRequest(text="runtime must be one of: " + ", ".join(RUNTIMES))
    write_json(SETTINGS, {"runtime": v})
    return web.json_response({"ok": True, "runtime": v})


@routes.get("/api/support/state")
async def api_state(request: web.Request) -> web.Response:
    from . import diagnose as D
    from . import missions as M
    rows = []
    for mid in reversed(_ids()):
        m = M.S.m.get(mid)
        if m:
            s = m.summary()
            rows.append({k: s.get(k) for k in ("id", "status", "model", "runtime", "changed", "answer", "error", "created", "verify", "work_secs")})
    b = D.bundle(lines=10)
    return web.json_response({"runtime": default_runtime(), "claude": claude_health(), "problems": b["problems"][-12:], "hub": b["hub"], "apps": b["apps"], "disk_free_gb": b["disk_free_gb"], "missions": rows})


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Hub support</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Outfit:wght@300;400;600&display=swap">
<style>
:root{--bg:#080c28;--ac:#00e676;--tx:#d9ffe9;--mu:#8fcfb2;--fa:#6fae92;--bd:rgba(0,230,118,.28);--am:#e0a53c;--rd:#ff5c5c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:400 14px/1.45 Outfit,system-ui,sans-serif;padding:14px max(14px,env(safe-area-inset-left))}
h1{font:700 13px Orbitron,sans-serif;letter-spacing:.2em;color:var(--ac);margin:0 0 10px}h2{font:700 10px Orbitron,sans-serif;letter-spacing:.16em;color:var(--fa);margin:16px 0 6px}
.box{border:1px solid var(--bd);border-radius:10px;padding:10px 12px;background:rgba(6,10,36,.7)}textarea{width:100%;min-height:84px;background:#05081f;color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:9px;font:inherit}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
button,select{font:700 10px Orbitron,sans-serif;letter-spacing:.1em;color:var(--ac);background:rgba(0,230,118,.05);border:1px solid var(--bd);border-radius:7px;padding:9px 12px;min-height:36px;cursor:pointer}
select{color:var(--tx);background:#05081f}button:hover{background:rgba(0,230,118,.14)}button[disabled]{opacity:.4}.red{color:var(--rd);border-color:rgba(255,92,92,.5)}
.pr{font:12px/1.4 Consolas,monospace;color:var(--mu);white-space:pre-wrap;overflow-wrap:anywhere;max-height:170px;overflow:auto}.ok{color:var(--ac)}.warn{color:var(--am)}
.m{border:1px solid var(--bd);border-radius:8px;padding:9px 11px;margin:8px 0}.m b{font:700 10px Orbitron,sans-serif;letter-spacing:.1em}.ans{white-space:pre-wrap;color:var(--mu);margin:6px 0;max-height:220px;overflow:auto;font-size:13px}
</style><link rel="stylesheet" href="/theme.css"></head><body>
<h1>SUPPORT · FIX AGENT HUB FROM HERE</h1>
<div class="box"><div id="facts" class="pr">Reading the Hub…</div></div>
<h2>WHAT IS WRONG?</h2>
<div class="box"><textarea id="t" placeholder="Describe it, or leave this empty and press ASK THE DOCTOR to have it look at the facts above."></textarea>
<div class="row" id="chips"></div>
<div class="row"><button id="ask">ASK THE DOCTOR</button><select id="rt" title="How the doctor works. Your choice is kept."><option value="claude-code">CLAUDE CODE</option><option value="opencode">LOCAL FIRST (OPENCODE)</option></select><button id="rf">REFRESH FACTS</button><span id="msg" class="warn"></span></div></div>
<h2>THE DOCTOR'S WORK</h2><div id="ms"></div>
<script>
const $=(i)=>document.getElementById(i), esc=(s)=>String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function api(u,b){const r=await fetch(u,{method:b===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b||{})});if(!r.ok)throw new Error((await r.text()).slice(0,200));return r.json()}
function draw(s){
 if(s.runtime&&document.activeElement!==$('rt'))$('rt').value=s.runtime;
 const bad=s.problems.length, apps=Object.entries(s.apps||{}).filter(([k,v])=>v&&v.last_error).map(([k,v])=>k+': '+v.last_error);
 const cl=(s.claude&&s.claude.ok===false)?'<div class="warn" style="margin-bottom:6px">'+esc(s.claude.why)+' Until then the doctor works with the local team.</div>':'';
 $('facts').innerHTML=cl+'<span class="'+(bad||apps.length?'warn':'ok')+'">'+(bad||apps.length?bad+' recent warning(s)':'No recent warnings')+'</span>  ·  Hub v'+esc(s.hub.version)+' up '+Math.round(s.hub.uptime_s/60)+' min  ·  disk free '+esc(JSON.stringify(s.disk_free_gb))+(apps.length?'\\n'+esc(apps.join('\\n')):'')+(bad?'\\n\\n'+esc(s.problems.join('\\n')):'');
 $('ms').innerHTML=s.missions.length?s.missions.map(m=>{const done=m.status==='awaiting_review',live=m.status==='running'||m.status==='queued';
  return '<div class="m"><b>'+esc(m.id)+' · '+esc(m.status.toUpperCase())+'</b> <span class="warn">'+esc((m.model||'').replace('ollama/',''))+' '+(m.runtime==='claude-code'?'· Claude Code':'')+'</span>'
  +(live?'<div class="ans">Working in a private copy of the Hub…</div>':'')
  +'<div class="ans">'+esc(m.answer||m.error||'')+'</div>'
  +(done?'<div>'+m.changed+' file(s) changed'+(m.verify?(' · checks '+(m.verify.ok?'<span class=ok>passed</span>':'<span class=warn>failed</span>')):'')+'</div>':'')
  +'<div class="row">'+(done&&m.changed?'<button data-a="apply" data-id="'+m.id+'">APPLY THE FIX</button>':'')+(done||m.status==='failed'?'<button class="red" data-a="discard" data-id="'+m.id+'">DISCARD</button>':'')+(m.status==='applied'?'<button data-a="restart">RESTART THE HUB TO USE IT</button>':'')+'</div></div>'}).join(''):'<div class="box">Nothing yet.</div>';
}
const USES=[['A MISSION FAILED','The last mission that failed: find out why it failed and say whether the cause is in the Hub or in the project it worked on. Fix it only if it is in the Hub.'],
 ['AN APP WILL NOT START','An app on Home shows "did not start". Read its error in the facts below, find the cause and fix it if it is in the Hub.'],
 ['RESTART TOOK TOO LONG','Restarting the Hub takes much longer than it should. Use the restart timing in the facts, find what the Hub does before it listens again, and propose the smallest change that shortens it.'],
 ['THE HUB FEELS SLOW','The Hub feels slow or the page stutters. Look for work done on every request or every poll, repeated log lines, and anything that blocks the event loop; fix the worst one.'],
 ['READ THE LAST HOUR','Nothing specific is wrong. Read the recent warnings and errors in the facts, group them, and say which matter. Change nothing unless one is clearly a bug.']];
USES.forEach(u=>{const b=document.createElement('button');b.textContent=u[0];b.title=u[1];b.onclick=()=>{$('t').value=u[1];$('t').focus()};$('chips').appendChild(b)});
async function load(){try{draw(await api('/api/support/state'))}catch(e){$('facts').textContent='Could not read the Hub: '+e.message}}
$('ask').onclick=async()=>{$('ask').disabled=true;$('msg').textContent='';try{await api('/api/support/ask',{text:$('t').value,runtime:$('rt').value});$('t').value='';await load()}catch(e){$('msg').textContent=e.message}$('ask').disabled=false};
$('rf').onclick=load;
$('rt').onchange=()=>api('/api/support/runtime',{runtime:$('rt').value}).catch(e=>{$('msg').textContent=e.message});
$('ms').onclick=async(e)=>{const b=e.target.closest('button[data-a]');if(!b)return;const a=b.dataset.a,id=b.dataset.id;b.disabled=true;
 try{if(a==='apply')await api('/api/missions/'+id+'/apply',{});if(a==='discard')await api('/api/missions/'+id+'/discard',{});if(a==='restart'){if(!confirm('Restart Agent Hub now?'))return;await api('/api/restart',{})}}catch(x){$('msg').textContent=x.message}load()};
load();setInterval(()=>{if(!document.hidden)load()},3000);
</script></body></html>"""


@routes.get("/support")
async def page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_PAGE, request), content_type="text/html")
