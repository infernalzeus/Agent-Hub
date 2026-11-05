"""TEACH: tap RIGHT or WRONG on what the Hub decided for things you already asked it.

The learning plan is short of exact labels (10 of the 100 the routing learner wants). Every tap here is one exact label, written as the
same `verdict` line the router already writes when you say "no, I meant...", so nothing new has to learn how to read it. A WRONG may name
the bin it should have been, which is the one thing a classifier can learn from directly.

Reads the decision log (hub/utterance_decisions.jsonl). Shows only decisions that have no exact label yet. Writes one line per tap.
"""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

from ..embed import embedded

routes = web.RouteTableDef()

BIN_HELP = {
    "launch_app": "open an app", "app_task": "do something inside an app", "pc_direct": "press or type on the PC right now",
    "lookup_routine": "look up a saved routine", "lookup_agent": "ask an agent", "hub_command": "a Hub command (open a page, ingest, status)",
    "conversation": "just talk", "personal_fact": "remember or recall a fact about you",
}


GRADES = ("right", "partly", "wrong")
# WHY a thing went wrong. "heard", "app" and "steps" are not the router's fault, so they must not be counted against it: a garbled transcript is a
# speech-to-text lesson, an app that changed is a routine lesson. Only "hub" (and "wording", which asks the Hub to ask back) blame the decision itself.
CAUSES = {"hub": "the Hub chose badly", "heard": "it heard me wrongly (speech to text)", "wording": "I said it badly / it was unclear",
          "app": "the app or page was not as expected", "steps": "right choice, a step in it failed", "other": "something else"}
NOT_THE_ROUTERS_FAULT = ("heard", "app", "steps")


def _grade(b: dict) -> "tuple[str, bool | None, str | None]":
    """(grade, ok-for-the-router, cause). `ok` stays None (no exact label) for a partial result or a fault that was not the router's."""
    g = b.get("grade")
    if g not in GRADES:
        ok = b.get("ok")
        if not isinstance(ok, bool):
            raise web.HTTPBadRequest(text='send "grade": right|partly|wrong (or "ok": true|false)')
        g = "right" if ok else "wrong"
    cause = b.get("cause") if b.get("cause") in CAUSES else None
    if g == "right":
        return g, True, None
    if g == "partly":
        return g, None, cause
    return g, (None if cause in NOT_THE_ROUTERS_FAULT else False), cause


def _unlabelled(limit: int = 100) -> "tuple[list[dict], int]":
    from ..features import binning as BIN, learning as LRN
    labelled = {e["at"] for e in LRN._route_events() if e["ok"] is not None}
    rows = [r for r in BIN._rows() if r.get("kind") not in ("outcome", "verdict") and r.get("at") and r.get("text")]
    left = [r for r in rows if r["at"] not in labelled]
    left.sort(key=lambda r: r["at"], reverse=True)
    items = [{"of": r["at"], "text": str(r["text"])[:200], "chosen": str(r.get("bin")), "said": str(r.get("said") or "")[:160]} for r in left[:limit]]
    return items, len(left)


@routes.get("/api/learning/teach")
async def api_items(request: web.Request) -> web.Response:
    from ..features import binning as BIN
    items, left = _unlabelled()
    return web.json_response({"items": items, "left": left, "bins": [{"id": b, "help": BIN_HELP.get(b, "")} for b in BIN.BINS], "causes": CAUSES})


@routes.post("/api/learning/teach")
async def api_tap(request: web.Request) -> web.Response:
    from ..features import binning as BIN
    try:
        b = await request.json()
        of = float(b["of"])
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"of": the decision id, "grade": "right|partly|wrong", "cause": optional, "correct": optional bin, "note": optional}')
    grade, ok, cause = _grade(b)
    if not any(r.get("at") == of and r.get("kind") not in ("outcome", "verdict") for r in BIN._rows()):
        raise web.HTTPNotFound(text="no such decision")
    row = {"kind": "verdict", "at": round(time.time(), 1), "of": of, "grade": grade, "by": "teach"}
    if ok is not None:
        row["ok"] = ok
    if cause:
        row["cause"] = cause
    correct = b.get("correct")
    if grade != "right" and isinstance(correct, str) and correct in BIN.BINS and ok is not None:
        row["correct"] = correct
    step = b.get("step")
    if isinstance(step, int) and 0 < step < 100:
        row["failed_step"] = step                              # which step of a multi-step task went wrong
    note = b.get("note")
    if isinstance(note, str) and note.strip():
        row["note"] = note.strip()[:300]                      # why it was wrong, in your words
    BIN._append(row)
    return web.json_response({"ok": True})


def _missions(limit: int = 12) -> "list[dict]":
    """The most recent missions, newest first, with what is already known about each: did the project's own checks pass, and what did you decide."""
    from ..features import learning as LRN
    try:
        from ..features import missions as M
        rows = sorted(M.S.m.values(), key=lambda m: m.created or 0, reverse=True)
    except Exception:  # noqa: BLE001
        return []
    human = LRN.mission_verdicts()
    out = []
    for m in rows[:limit]:
        v = m.verify if isinstance(getattr(m, "verify", None), dict) else {}
        out.append({"id": m.id, "brief": str(m.brief or "").strip().splitlines()[0][:140] if m.brief else "", "project": m.project_name, "status": m.status,
                    "model": m.model or m.agent or "", "checks": v.get("ok") if isinstance(v.get("ok"), bool) else None,
                    "verdict": human.get(m.id), "decided_by": ("you tapped" if m.id in LRN._jsonl_dict(LRN.MISSION_LABELS) else "you " + m.status) if m.id in human else ""})
    return out


@routes.get("/api/learning/teach/summary")
async def api_summary(request: web.Request) -> web.Response:
    """How the person has graded things, and WHY it went wrong: the numbers the Doctor and the learner read."""
    from ..features import binning as BIN, learning as LRN
    grades: dict = {}
    causes: dict = {}
    for r in BIN._rows():
        if r.get("kind") == "verdict" and r.get("by") == "teach":
            g = r.get("grade") or ("right" if r.get("ok") else "wrong")
            grades[g] = grades.get(g, 0) + 1
            if r.get("cause"):
                causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    for v in LRN._jsonl_dict(LRN.MISSION_LABELS).values():
        if isinstance(v, dict):
            g = v.get("grade") or ("right" if v.get("ok") else "wrong")
            grades["mission " + g] = grades.get("mission " + g, 0) + 1
            if v.get("cause"):
                causes[v["cause"]] = causes.get(v["cause"], 0) + 1
    return web.json_response({"grades": grades, "causes": causes, "cause_help": CAUSES,
                              "not_the_routers_fault": list(NOT_THE_ROUTERS_FAULT)})


@routes.get("/api/learning/teach/missions")
async def api_missions(request: web.Request) -> web.Response:
    return web.json_response({"missions": await asyncio.get_running_loop().run_in_executor(None, _missions)})


@routes.post("/api/learning/teach/mission")
async def api_mission_tap(request: web.Request) -> web.Response:
    from ..features import learning as LRN
    from ..runtime import write_json
    try:
        b = await request.json()
        mid = str(b["id"])[:40]
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"id": mission id, "grade": "right|partly|wrong"}')
    grade, ok, cause = _grade(b)
    if mid not in {m["id"] for m in _missions(200)}:
        raise web.HTTPNotFound(text="no such mission")
    labels = LRN._jsonl_dict(LRN.MISSION_LABELS)
    labels[mid] = {"grade": grade, "at": time.time()}
    if ok is not None:
        labels[mid]["ok"] = ok
    if cause:
        labels[mid]["cause"] = cause
    note = b.get("note")
    if isinstance(note, str) and note.strip():
        labels[mid]["note"] = note.strip()[:300]
    write_json(LRN.MISSION_LABELS, labels)
    return web.json_response({"ok": True})


_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>AGENT HUB - Teach</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--accent:#00e676;--text:rgba(214,245,230,.92);--mute:rgba(214,245,230,.58);--amber:#e0a53c;--red:#ff5c5c;--border:rgba(0,230,118,.25);--panel:rgba(8,12,40,.9)}
body{background:#080c28;color:var(--text);font:15px/1.5 Outfit,system-ui,sans-serif;padding:18px max(16px,env(safe-area-inset-left)) 40px}
main{max-width:640px;margin:0 auto}
html.hub-embed h1{display:none}h1{font:800 20px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent)}
p.sub{color:var(--mute);margin:6px 0 14px;font-size:13px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0}
.said{font-size:20px;line-height:1.35;margin-bottom:10px}.bin{color:var(--accent);font-weight:600}.mute{color:var(--mute);font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
button,select{font:700 13px Orbitron,system-ui,sans-serif;letter-spacing:.06em;border-radius:8px;padding:11px 18px;border:1px solid var(--accent);background:var(--panel);color:var(--accent);cursor:pointer;min-height:44px}
button.no{border-color:var(--red);color:var(--red)}button.part{border-color:var(--amber);color:var(--amber)}input.step{width:130px;font:14px Outfit,system-ui,sans-serif;color:var(--text);background:rgba(8,12,40,.9);border:1px solid var(--border);border-radius:8px;padding:8px 10px}button.skip{border-color:var(--border);color:var(--mute)}
select{font-weight:400;letter-spacing:0;max-width:100%}
textarea{width:100%;font:14px Outfit,system-ui,sans-serif;color:var(--text);background:rgba(8,12,40,.9);border:1px solid var(--border);border-radius:8px;padding:8px 10px;resize:vertical}
.count{color:var(--amber);font-size:13px}
.seg{display:flex;gap:8px;margin:6px 0 10px}.seg button.on{background:var(--accent);color:#04120a}
.chip{border:1px solid var(--border);border-radius:99px;padding:2px 10px;font-size:12px;color:var(--mute);margin-right:6px;display:inline-block}.chip.ok{color:var(--accent);border-color:var(--accent)}.chip.no{color:var(--red);border-color:var(--red)}
</style></head><body><main>
<h1>TEACH</h1>
<p class="sub">Things you already asked, and what the Hub thought you wanted. Tap RIGHT or WRONG. Each tap is one exact label for the learner; nothing else changes.</p>
<div class="seg"><button type="button" id="s-req" class="on">REQUESTS</button><button type="button" id="s-mis">MISSIONS</button></div>
<div class="count" id="count"></div>
<div id="card"></div>
</main>
<script>
(function(){
  let items=[],bins=[],causes={},i=0,left=0;
  const $=id=>document.getElementById(id),el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  async function load(){const r=await fetch('/api/learning/teach',{cache:'no-store'});const j=await r.json();items=j.items;bins=j.bins;causes=j.causes||{};left=j.left;i=0;show();}
  function help(b){const x=bins.find(y=>y.id===b);return x&&x.help?x.help:b;}
  async function send(url,body,next){try{await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch(e){}next();}
  // PARTLY and WRONG ask what actually happened: whose fault it was (a garbled transcript is not the router's), which step, and your own words
  function detail(row,grade,withBins,it,save){
    row.replaceChildren();
    const why=el('select');const o0=el('option',null,'Why was it '+(grade==='partly'?'only partly right':'wrong')+'?');o0.value='';why.appendChild(o0);
    Object.keys(causes).forEach(k=>{const o=el('option',null,causes[k]);o.value=k;why.appendChild(o);});
    row.appendChild(why);
    let sel=null;if(withBins){sel=el('select');const s0=el('option',null,'It should have been...');s0.value='';sel.appendChild(s0);bins.filter(b=>b.id!==it.chosen).forEach(b=>{const o=el('option',null,b.help||b.id);o.value=b.id;sel.appendChild(o);});row.appendChild(sel);}
    const step=el('input','step');step.type='number';step.min=1;step.max=99;step.placeholder='Failed step #';step.title='For a task with several steps: which one went wrong (optional)';row.appendChild(step);
    const note=el('textarea');note.placeholder='In your own words (optional): what you said, what you saw, what you think went wrong. If the transcript was nonsense, say so.';note.rows=3;note.maxLength=300;row.appendChild(note);
    const done=el('button',grade==='partly'?'part':'no','SAVE '+(grade==='partly'?'PARTLY':'WRONG'));
    done.onclick=()=>save({grade:grade,cause:why.value||undefined,correct:sel&&sel.value||undefined,step:step.value?parseInt(step.value,10):undefined,note:note.value||undefined});
    row.appendChild(done);
  }
  function show(){
    const c=$('card');c.replaceChildren();$('count').textContent=left?left+' still without a label':'';
    const it=items[i];
    if(!it){c.appendChild(el('div','card',left?'That is the batch. Reload for more.':'Nothing left to label. Thank you.'));return;}
    const card=el('div','card');card.appendChild(el('div','said','“'+it.text+'”'));
    const p=el('div','mute','The Hub took that as: ');p.appendChild(el('span','bin',help(it.chosen)));card.appendChild(p);
    if(it.said)card.appendChild(el('div','mute','It said: '+it.said));
    const row=el('div','row'),yes=el('button',null,'RIGHT'),part=el('button','part','PARTLY'),no=el('button','no','WRONG'),skip=el('button','skip','SKIP');
    const save=(g)=>send('/api/learning/teach',Object.assign({of:it.of},g),()=>{left=Math.max(0,left-1);i++;show();});
    yes.onclick=()=>save({grade:'right'});skip.onclick=()=>{i++;show();};
    part.onclick=()=>detail(row,'partly',false,it,save);
    no.onclick=()=>detail(row,'wrong',true,it,save);
    row.append(yes,part,no,skip);card.appendChild(row);c.appendChild(card);
  }
  async function missions(){const c=$('card');c.replaceChildren();$('count').textContent='Newest first. APPLY already counts as a yes and DISCARD as a no; tap for the rest.';
    let j;try{j=await (await fetch('/api/learning/teach/missions',{cache:'no-store'})).json();}catch(e){c.textContent='Could not read the missions: '+e.message;return;}
    if(!j.missions.length){c.appendChild(el('div','card','No missions yet.'));return;}
    j.missions.forEach(m=>{const card=el('div','card');card.appendChild(el('div','said',m.brief||'(no brief)'));
      const meta=el('div','mute');meta.append(el('span','chip',m.project||''),el('span','chip',m.model||''),el('span','chip',m.status));
      if(m.checks!==null)meta.append(el('span','chip '+(m.checks?'ok':'no'),m.checks?'its checks passed':'its checks failed'));
      if(m.verdict!==null&&m.verdict!==undefined)meta.append(el('span','chip '+(m.verdict?'ok':'no'),(m.verdict?'good':'bad')+' ('+m.decided_by+')'));
      card.appendChild(meta);
      const row=el('div','row'),g=el('button',null,'GOOD'),pt=el('button','part','PARTLY'),b=el('button','no','BAD');
      const save=(x)=>send('/api/learning/teach/mission',Object.assign({id:m.id},x),missions);
      g.onclick=()=>save({grade:'right'});pt.onclick=()=>detail(row,'partly',false,null,save);b.onclick=()=>detail(row,'wrong',false,null,save);
      row.append(g,pt,b);card.appendChild(row);c.appendChild(card);});}
  $('s-req').onclick=()=>{$('s-req').classList.add('on');$('s-mis').classList.remove('on');show();};
  $('s-mis').onclick=()=>{$('s-mis').classList.add('on');$('s-req').classList.remove('on');missions();};
  load().catch(e=>{$('card').textContent='Could not read the decision log: '+e.message;});
})();
</script></body></html>
"""


@routes.get("/teach")
async def teach_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
