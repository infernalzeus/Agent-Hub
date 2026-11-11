"""Run record: what the desktop agent did on a task, step by step, so a person can check it.

Why: "open Apple Music and play my ADHD playlist" can take 70 seconds and seven steps of which two mattered. The run trace kept each step's text and time but no
picture, nobody could see what the agent saw, and the only way to keep the good steps was a rule (`_trim`). Now every run is a folder:

    data/runs/<id>/run.json      goal, app, model, ok, total ms, window + signature, the steps the agent pressed, and one entry per model decision
                                 (decision ms, press ms, what it did and why, whether the screen changed, which picture)
    data/runs/<id>/<n>.jpg       the app's window after step n (about 40 KB, this PC only)

The page /runs lists the runs, shows each step with its picture and times, lets you tick the steps that were right, SAVE them as a routine (a candidate: it still has to be
replayed clean twice or approved) and REPLAY that routine as a test with a clock. A run is deleted with its pictures. Nothing here presses anything by itself except REPLAY,
which goes through the routine runner and its stop signal."""
from __future__ import annotations

import json
import re
import shutil
import time

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()
KEEP = 40                                    # runs kept; the oldest go with their pictures
_ID = re.compile(r"^[0-9a-f]{6,16}$")


def _root():
    return STATE / "data" / "runs"


def _dir(rid: str):
    if not _ID.match(rid or ""):
        raise web.HTTPNotFound(text="no such run")
    return _root() / rid


def keep_shot(rid: str, step: int, jpeg: bytes) -> str:
    """Store the picture of one step; returns the name the run record refers to it by."""
    if not _ID.match(rid or "") or not jpeg:
        return ""
    d = _root() / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{int(step):03d}.jpg").write_bytes(jpeg)
    return f"{int(step):03d}.jpg"


def write(rid: str, goal: str, app: str, model: str, got: dict, ms: float) -> None:
    """Keep one try. `got` is what the step loop returned: ok, say, trace (one entry per model decision), steps (the presses that worked), first (the window tree it started from)."""
    from . import pc_control as PC
    first = got.get("first") or []
    window, signature = "", {}
    try:
        window = next((n["window"] for n in first if n.get("control") == "window" and PC.canonical_app_name(app) in n["name"].casefold()), "")
        if window:
            signature = PC.ui_signature(PC.flatten(first), window)
    except Exception as exc:  # noqa: BLE001 - a run without a signature can still be read, only not saved
        logger.info("run_record: no window signature: %s", exc)
    d = _root() / rid
    d.mkdir(parents=True, exist_ok=True)
    row = {"id": rid, "at": time.time(), "goal": goal, "app": app, "model": model, "ok": bool(got.get("ok")), "verified": got.get("verified"), "say": str(got.get("say") or "")[:300],
           "ms": int(ms), "window": window, "signature": signature,
           "trace": [{k: v for k, v in t.items() if k in ("step", "ms", "press_ms", "do", "control", "why", "changed", "verified", "error", "shot", "press", "raw")} for t in (got.get("trace") or [])],
           "presses": [{k: v for k, v in s.items() if not k.startswith("_")} for s in (got.get("steps") or [])]}
    (d / "run.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    _prune()


def _prune() -> None:
    try:
        runs = sorted((p for p in _root().iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in runs[KEEP:]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass


def _load(rid: str) -> dict:
    try:
        return json.loads((_dir(rid) / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise web.HTTPNotFound(text="no such run")


def summary(row: dict) -> dict:
    tr = row.get("trace") or []
    return {"id": row["id"], "at": row.get("at"), "goal": row.get("goal"), "app": row.get("app"), "model": row.get("model"), "ok": row.get("ok"), "verified": row.get("verified"),
            "ms": row.get("ms"), "steps": len(tr), "useful": sum(1 for t in tr if t.get("changed")), "say": row.get("say")}


@routes.get("/api/runs")
async def api_list(request: web.Request) -> web.Response:
    out = []
    try:
        for p in sorted((p for p in _root().iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                out.append(summary(json.loads((p / "run.json").read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue
    except OSError:
        pass
    return web.json_response({"runs": out})


@routes.get("/api/runs/{id}")
async def api_one(request: web.Request) -> web.Response:
    return web.json_response(_load(request.match_info["id"]))


@routes.get("/api/runs/{id}/shot/{name}")
async def api_shot(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    if not re.match(r"^\d{3}\.jpg$", name):
        raise web.HTTPNotFound()
    f = _dir(request.match_info["id"]) / name
    if not f.is_file():
        raise web.HTTPNotFound(text="no picture for that step")
    return web.Response(body=f.read_bytes(), content_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@routes.delete("/api/runs/{id}")
async def api_delete(request: web.Request) -> web.Response:
    shutil.rmtree(_dir(request.match_info["id"]), ignore_errors=True)
    return web.json_response({"ok": True})


@routes.post("/api/runs/{id}/save")
async def api_save(request: web.Request) -> web.Response:
    """Keep the ticked steps as a routine. `keep` is the list of step numbers (the `step` of each decision) the person says were right, in the order they happened.
    Only decisions that pressed something carry a press; ticking a step that pressed nothing keeps nothing."""
    from . import pc_control as PC
    row = _load(request.match_info["id"])
    try:
        keep = [int(x) for x in (await request.json()).get("keep", [])]
    except (ValueError, TypeError, AttributeError):
        raise web.HTTPBadRequest(text="keep must be a list of step numbers")
    by_step = {t["step"]: t for t in row["trace"] if "step" in t}
    presses = row.get("presses") or []
    steps = []
    for n in sorted(set(keep)):
        t = by_step.get(n)
        if t is not None and isinstance(t.get("press"), int) and 0 <= t["press"] < len(presses):
            steps.append(presses[t["press"]])
    if not steps:
        return web.json_response({"ok": False, "reason": "none of the ticked steps pressed anything"})
    if not row.get("window") or not row.get("signature"):
        return web.json_response({"ok": False, "reason": "this run did not record its window, so it cannot be saved as a routine"})
    old = PC.routine_for_do(row["app"], row["goal"])
    saved = PC.save_ui_routine(old["intent"] if old else PC.do_intent(row["app"], row["goal"]), f"{PC.display_app_name(row['app'])}: {row['goal']}".strip(), row["window"], steps, row["signature"])
    return web.json_response({"ok": True, "routine": saved["id"], "steps": len(steps), "status": saved["status"]})


@routes.get("/runs")
async def page(request: web.Request) -> web.Response:
    return web.Response(text=_PAGE, content_type="text/html", headers={"Cache-Control": "no-store"})


_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Runs</title>
<link rel="stylesheet" href="/theme.css"><style>
body{margin:0;background:#080c28;color:#d6f5e6;font:13px/1.45 Outfit,system-ui,sans-serif;padding:14px}
h1{font:900 15px Orbitron,monospace;letter-spacing:2px;color:#00e676;margin:0 0 10px}
.run{border:1px solid rgba(0,230,118,.25);border-radius:10px;padding:9px 11px;margin:8px 0;background:rgba(8,12,40,.7)}
.run b{color:#00e676}.mute{color:rgba(214,245,230,.6)}.bad{color:#ff6b6b}.ok{color:#00e676}
button{font:700 10px Orbitron,monospace;letter-spacing:1px;background:rgba(6,10,36,.7);color:#d6f5e6;border:1px solid rgba(0,230,118,.4);border-radius:8px;padding:6px 10px;cursor:pointer}
button:hover{border-color:#00e676}table{border-collapse:collapse;width:100%;margin:8px 0}th{font:700 9px Orbitron,monospace;letter-spacing:1px;text-align:left;color:#00e676;padding:4px 6px}
td{padding:6px;border-top:1px solid rgba(0,230,118,.15);vertical-align:top}td img{width:150px;border-radius:6px;border:1px solid rgba(0,230,118,.25);cursor:zoom-in;display:block}
tr.useless td{opacity:.62}.big{position:fixed;inset:0;background:rgba(4,6,20,.92);display:grid;place-items:center;z-index:9}.big img{max-width:94vw;max-height:92vh;border-radius:8px}
</style></head><body><h1>RUNS</h1><p class="mute">What the desktop agent did, step by step. Tick the steps that were right and save them as a routine; replay it to see how long it takes.</p><div id="list"></div><div id="one"></div>
<script>
const $=id=>document.getElementById(id),esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const sec=ms=>ms==null?'-':(ms/1000).toFixed(1)+' s';
async function list(){const j=await (await fetch('/api/runs')).json();const L=$('list');L.replaceChildren();
  if(!j.runs.length){L.innerHTML='<p class="mute">No runs yet. Ask Smith to open an app and do something in it.</p>';return;}
  j.runs.forEach(r=>{const d=document.createElement('div');d.className='run';
    d.innerHTML='<b>'+esc(r.goal)+'</b> <span class="mute">in '+esc(r.app)+' · '+esc(r.model)+'</span><br><span class="'+(r.ok?'ok':'bad')+'">'+(r.ok?(r.verified===false?'played something else':'worked'):'did not work')+'</span> · '+sec(r.ms)+' · '+r.steps+' steps, '+r.useful+' changed the screen · '+new Date(r.at*1000).toLocaleString()+' <button data-open>OPEN</button> <button data-del>DELETE</button>';
    d.querySelector('[data-open]').onclick=()=>one(r.id);d.querySelector('[data-del]').onclick=async()=>{await fetch('/api/runs/'+r.id,{method:'DELETE'});$('one').replaceChildren();list();};L.append(d);});}
async function one(id){const r=await (await fetch('/api/runs/'+id)).json();const box=$('one');
  const rows=r.trace.map(t=>{const pressed=typeof t.press==='number';const good=t.changed||t.verified;
    return '<tr class="'+(good?'':'useless')+'"><td><input type="checkbox" data-n="'+t.step+'" '+(pressed&&good?'checked':'')+(pressed?'':' disabled')+'></td><td>'+(t.step+1)+'</td><td>'+esc(t.do||(t.error?'error':''))+'<br><span class="mute">'+esc(t.control||'')+'</span></td><td class="mute">'+esc(t.why||t.error||'')+'</td><td>'+sec(t.ms)+'<br><span class="mute">press '+sec(t.press_ms)+'</span></td><td>'+(t.changed?'<span class="ok">screen changed</span>':(pressed?'<span class="bad">nothing changed</span>':''))+(t.verified?'<br><span class="ok">checked: playing</span>':'')+'</td><td>'+(t.shot?'<img src="/api/runs/'+id+'/shot/'+t.shot+'" alt="">':'<span class="mute">no picture</span>')+'</td></tr>';}).join('');
  box.innerHTML='<h1>'+esc(r.goal)+'</h1><p>'+esc(r.say)+' <span class="mute">total '+sec(r.ms)+', model '+esc(r.model)+'</span></p><table><tr><th></th><th>#</th><th>DID</th><th>WHY</th><th>TIME</th><th>RESULT</th><th>WINDOW AFTER</th></tr>'+rows+'</table><button id="save">SAVE TICKED STEPS AS A ROUTINE</button> <button id="rep" hidden>REPLAY IT AS A TEST</button> <span id="msg" class="mute"></span>';
  box.querySelectorAll('img').forEach(i=>i.onclick=()=>{const b=document.createElement('div');b.className='big';b.innerHTML='<img src="'+i.src+'">';b.onclick=()=>b.remove();document.body.append(b);});
  let rid='';$('save').onclick=async()=>{const keep=[...box.querySelectorAll('[data-n]:checked')].map(x=>Number(x.dataset.n));
    const j=await (await fetch('/api/runs/'+id+'/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keep})})).json();
    $('msg').textContent=j.ok?('Saved '+j.steps+' steps as a '+j.status+' routine.'):(j.reason||'Not saved.');if(j.ok){rid=j.routine;$('rep').hidden=false;}};
  $('rep').onclick=async()=>{$('msg').textContent='Replaying...';const t0=performance.now();let j={};try{j=await (await fetch('/api/pc/routines/'+rid+'/run?test=1',{method:'POST'})).json();}catch(e){}
    $('msg').textContent=(j.ok?'Replayed clean in ':'Replay failed after ')+sec(performance.now()-t0)+(j.say?' - '+j.say:'')+'. The first run took '+sec(r.ms)+'.';};}
list();
</script></body></html>"""
