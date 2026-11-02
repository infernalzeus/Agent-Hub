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

RULES = """You are the doctor for Agent Hub, a Python (aiohttp) app. Your working copy is a private git worktree of its repository;
nothing you change reaches the running Hub until the owner presses APPLY, and the owner restarts it. Rules:
- Find the cause first. Say what you found in one or two sentences before you change anything.
- Make the smallest change that fixes it. Do not reformat or rename. Do not touch state or secrets: hub/*.json, hub/data, logs/, tokens, keys.
- The Hub's code is hub/*.py, hub/features/*.py and hub/static/*.js; app.py registers the features; pages are built in hub/ui.py.
- Check your work: `python -c "import hub.ui, app"` must work, `node --check` every JavaScript file you edit, and run pytest if tests exist in this copy.
- Never restart, stop or start the Hub, and never call its power or shutdown endpoints.
- End with a line starting DONE: that says what you changed and why, or what you found if no change is needed."""


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
    keep = {k: b[k] for k in ("hub", "apps", "missions", "local_model_server", "disk_free_gb")}
    return restart_timing() + "FACTS FROM /api/diagnose:\n" + json.dumps(keep, indent=1)[:2500] + "\n\nRECENT WARNINGS AND ERRORS (secrets removed):\n" + "\n".join(b["problems"][-20:])[:5000]


def brief_for(text: str) -> str:
    text = (text or "").strip()
    ask = text or "Nothing specific was reported. Look at the facts and the recent warnings and say whether anything is wrong; fix it only if it clearly is."
    return f"{RULES}\n\nTHE OWNER SAYS:\n{ask}\n\n{facts()}"


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
    m = await _dispatch(brief_for(text), runtime, model)
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
    return web.json_response({"ok": True, "mission": m["id"], "runtime": runtime})


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
    return web.json_response({"runtime": default_runtime(), "problems": b["problems"][-12:], "hub": b["hub"], "apps": b["apps"], "disk_free_gb": b["disk_free_gb"], "missions": rows})


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
</style></head><body>
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
 $('facts').innerHTML='<span class="'+(bad||apps.length?'warn':'ok')+'">'+(bad||apps.length?bad+' recent warning(s)':'No recent warnings')+'</span>  ·  Hub v'+esc(s.hub.version)+' up '+Math.round(s.hub.uptime_s/60)+' min  ·  disk free '+esc(JSON.stringify(s.disk_free_gb))+(apps.length?'\\n'+esc(apps.join('\\n')):'')+(bad?'\\n\\n'+esc(s.problems.join('\\n')):'');
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
