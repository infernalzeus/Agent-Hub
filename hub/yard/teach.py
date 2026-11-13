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


GRADES = ("right", "partly", "wrong", "skip", "delete")       # skip: do not ask again; delete: remove it, it is used for nothing
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
    if g in ("skip", "delete"):
        return g, None, None
    if g == "right":
        return g, True, None
    if g == "partly":
        return g, None, cause
    return g, (None if cause in NOT_THE_ROUTERS_FAULT else False), cause


def _runs_since(at: float, text: str) -> "dict | None":
    """The desktop agent's try that followed this request, if there was one: its steps are what a multi-step grade is about."""
    import json
    from ..runtime import STATE
    try:
        lines = (STATE / "data" / "desktop_agent_runs.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    stop = {"can", "you", "open", "apple", "music", "please", "play", "something", "from", "the", "list", "playlist", "for", "and", "some"}
    words = {w.strip(".,?!") for w in text.casefold().split()} - stop
    best, score = None, 0
    for raw in lines:
        try:
            r = json.loads(raw)
        except ValueError:
            continue
        if not (at - 5 <= float(r.get("at") or 0) <= at + 900):
            continue
        goal = {w.strip(".,?!") for w in str(r.get("goal", "")).casefold().split()} - stop
        n = len(words & goal) + (0.5 if not words and not goal else 0)
        if n > score or (best is None and not words):
            best, score = r, n
    return best


def _unlabelled(limit: int = 100) -> "tuple[list[dict], int]":
    from ..features import binning as BIN
    rows = BIN._rows()
    answered = {r.get("of") for r in rows if r.get("kind") == "verdict" and r.get("by") == "teach"}
    from ..yard import settings as YS
    since = YS.fresh_since()                                  # after a FRESH START only new requests are offered
    said = [r for r in rows if r.get("kind") not in ("outcome", "verdict") and r.get("at") and r.get("text") and (not since or r["at"] >= since)]
    left = [r for r in said if r["at"] not in answered and not any(v.get("of") == r["at"] and isinstance(v.get("ok"), bool) for v in rows if v.get("kind") == "verdict")]
    # Most useful first (uncertainty sampling): a decision the rules were unsure about, or that tev had to be asked, teaches more than one that was obvious,
    # so you can stop early without losing the best labels. Ties: newest first.
    def info(r: dict) -> float:
        if r.get("by") == "you":
            return 0.05                                        # your own earlier correction: already known
        c = r.get("confidence")
        base = 0.5 if not isinstance(c, (int, float)) else max(0.0, 1.0 - abs(float(c) - 0.75) * 2.0)      # most to learn near the 0.75 cut-off
        return base + (0.3 if r.get("asked") else 0.0)
    left.sort(key=lambda r: (-info(r), -r["at"]))
    items = []
    for r in left[:limit]:
        item = {"of": r["at"], "text": str(r["text"])[:200], "chosen": str(r.get("bin")), "said": str(r.get("said") or "")[:160], "by": str(r.get("by") or "rules")}
        run = _runs_since(r["at"], str(r["text"])) if r.get("bin") in ("app_task", "launch_app", "pc_direct") else None
        if run:
            item["steps"] = [{"n": t.get("step", i) + 1, "what": str(t.get("control") or t.get("do") or "")[:90], "changed": t.get("changed"), "ms": t.get("ms")} for i, t in enumerate(run.get("trace") or [])]
            item["model"] = run.get("model")
            item["run_said"] = str(run.get("say") or "")[:140]
        items.append(item)
    return items, len(left)


@routes.get("/api/learning/teach")
async def api_items(request: web.Request) -> web.Response:
    from ..features import binning as BIN
    items, left = _unlabelled()
    from ..yard import settings as YS
    rows = BIN._rows()
    said = [r for r in rows if r.get("kind") not in ("outcome", "verdict") and r.get("at") and r.get("text")]
    since = YS.fresh_since()
    status = {"logged": len(said), "since_fresh": sum(1 for r in said if not since or r["at"] >= since), "last": max((r["at"] for r in said), default=0), "fresh": since}
    return web.json_response({"status": status, "order": "most useful first: unsure decisions before obvious ones", "items": items, "left": left, "bins": [{"id": b, "help": BIN_HELP.get(b, "")} for b in BIN.BINS], "causes": CAUSES})


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
        row["failed_step"] = step
    bad = b.get("bad_steps")
    if isinstance(bad, list):
        row["bad_steps"] = [n for n in bad if isinstance(n, int) and 0 < n < 100][:20]      # which steps of a multi-step task went wrong
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
    from ..yard import settings as YS
    since = YS.fresh_since()
    gone = {k for k, v in LRN._jsonl_dict(LRN.MISSION_LABELS).items() if isinstance(v, dict) and v.get("grade") in ("skip", "delete")}
    rows = [m for m in rows if m.id not in gone and (not since or (m.created or 0) >= since)]
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


@routes.get("/api/learning/learned")
async def api_learned(request: web.Request) -> web.Response:
    """What your taps have changed. Today exactly one thing acts on them: a sentence you corrected is routed the way you said."""
    from ..features import binning as BIN, learning as LRN
    rows = BIN._rows()
    fixes = BIN.corrections()
    used: dict = {}
    for r in rows:
        if r.get("by") == "you" and r.get("text"):
            k = BIN._norm(r["text"])
            used[k] = used.get(k, 0) + 1
    corrections = [{"text": v["text"], "was": v.get("was"), "now": v["bin"], "used": used.get(k, 0), "at": v.get("at")} for k, v in fixes.items()]
    corrections.sort(key=lambda c: -(c["at"] or 0))
    summ = (await api_summary(request)).text
    import json
    st = LRN.status()
    route = st["per_kind"]["route"]
    heard = json.loads(summ).get("causes", {}).get("heard", 0)
    return web.json_response({"corrections": corrections, "summary": json.loads(summ), "route_labelled": route["labelled"], "route_events": route["events"],
                              "label_goal": 100, "speech_misses": heard,
                              "acting_now": "Only your corrections of exact sentences. Everything else is recorded or practised, and nothing else changes what the Hub does.",
                              "not_yet": ["A router that generalises from your labels (needs about 100 exact labels)", "A speech-to-text fix (the misses are only counted)", "Routine confidence from your grades"]})


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
body{background:#080c28;color:var(--text);font:13px/1.45 Outfit,system-ui,sans-serif;padding:12px max(14px,env(safe-area-inset-left)) 28px}
main{max-width:640px;margin:0 auto}
html.hub-embed h1{display:none}h1{font:800 16px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent)}
p.sub{color:var(--mute);margin:4px 0 8px;font-size:12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:10px 12px;margin:8px 0}
.said{font-size:15px;line-height:1.35;margin-bottom:6px}.bin{color:var(--accent);font-weight:600}.mute{color:var(--mute);font-size:13px}
.row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
button,select{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.05em;border-radius:7px;padding:7px 12px;border:1px solid var(--accent);background:var(--panel);color:var(--accent);cursor:pointer;min-height:34px}
button.no{border-color:var(--red);color:var(--red)}button.part{border-color:var(--amber);color:var(--amber)}input.step{width:130px;font:14px Outfit,system-ui,sans-serif;color:var(--text);background:rgba(8,12,40,.9);border:1px solid var(--border);border-radius:8px;padding:8px 10px}button.skip{border-color:var(--border);color:var(--mute)}
.opts{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.opts button{padding:6px 11px;min-height:34px;font-size:11px}.opts button.on{background:var(--accent);color:#04120a}.steps{margin:10px 0;border:1px solid var(--border);border-radius:8px;overflow:hidden}.steps label{display:flex;gap:10px;align-items:flex-start;padding:7px 10px;border-bottom:1px solid var(--border);font-size:13px;cursor:pointer}.steps label:last-child{border-bottom:0}.steps label.bad{background:rgba(255,92,92,.1)}.steps .n{color:var(--mute);min-width:22px}.steps .nochg{color:var(--amber);font-size:12px}.h{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--mute);margin:12px 0 2px}.effect{color:var(--mute);font-size:12.5px;margin-top:8px}select{font-weight:400;letter-spacing:0;max-width:100%}
textarea{width:100%;font:14px Outfit,system-ui,sans-serif;color:var(--text);background:rgba(8,12,40,.9);border:1px solid var(--border);border-radius:8px;padding:8px 10px;resize:vertical}
.count{color:var(--amber);font-size:13px}
.seg{display:flex;gap:8px;margin:6px 0 10px}.seg button.on{background:var(--accent);color:#04120a}
.chip{border:1px solid var(--border);border-radius:99px;padding:2px 10px;font-size:12px;color:var(--mute);margin-right:6px;display:inline-block}.chip.ok{color:var(--accent);border-color:var(--accent)}.chip.no{color:var(--red);border-color:var(--red)}
</style></head><body><main>
<h1>TEACH</h1>
<div class="seg"><button type="button" id="s-req" class="on">REQUESTS</button><button type="button" id="s-mis">MISSIONS</button><button type="button" id="s-task">PC TASKS</button></div>
<div class="count" id="count"></div>
<div id="card"></div>
</main>
<script>
(function(){
  let items=[],bins=[],causes={},i=0,left=0;
  const $=id=>document.getElementById(id),el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  async function load(){const r=await fetch('/api/learning/teach',{cache:'no-store'});const j=await r.json();items=j.items;window.__teachStatus=j.status||{};bins=j.bins;causes=j.causes||{};left=j.left;i=0;show();}
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
    const c=$('card');c.replaceChildren();$('count').textContent=left?left+' left to answer. SKIP hides one for good.':'';
    const it=items[i];
    if(!it){const s=window.__teachStatus||{};const msg=left?'That is the batch. Reload for more.':(s.logged===0?'Nothing has been logged yet.':s.since_fresh===0?'Nothing to answer: '+s.logged+' earlier request'+(s.logged===1?' is':'s are')+' kept apart since the fresh start (the last was '+new Date(s.last*1000).toLocaleDateString()+'), and no new request has been logged since. Requests appear here as you use Talk and the router decides what you meant.':'Nothing left to answer. Thank you.');c.appendChild(el('div','card',msg));return;}
    const card=el('div','card');card.appendChild(el('div','said','“'+it.text+'”'));
    const p=el('div','mute','The Hub took that as: ');p.appendChild(el('span','bin',help(it.chosen)));p.append(' (chosen by '+(it.by==='you'?'your earlier correction':it.by)+')');card.appendChild(p);
    if(it.said)card.appendChild(el('div','mute','It said: '+it.said));
    let bad=new Set();
    if(it.steps&&it.steps.length){
      card.appendChild(el('div','h','IT TOOK '+it.steps.length+' STEP'+(it.steps.length>1?'S':'')+(it.model?' · MODEL '+it.model:'')+(it.run_said?' · "'+it.run_said+'"':'')));
      const box=el('div','steps');
      it.steps.forEach(s=>{const lab=el('label'),cb=el('input');cb.type='checkbox';cb.onchange=()=>{cb.checked?bad.add(s.n):bad.delete(s.n);lab.classList.toggle('bad',cb.checked);};
        lab.append(cb,el('span','n',s.n+'.'),el('span',null,s.what||'(a key press)'));if(s.changed===false)lab.append(el('span','nochg','nothing changed'));if(s.ms)lab.append(el('span','mute',(s.ms/1000).toFixed(1)+' s'));box.appendChild(lab);});
      card.appendChild(box);card.appendChild(el('div','mute','Tick the steps that went wrong. Leave all unticked if none did.'));
    }
    let grade=null,cause='';
    const row=el('div','row'),yes=el('button',null,'RIGHT'),part=el('button','part','PARTLY'),no=el('button','no','WRONG'),skip=el('button','skip','SKIP'),del_=el('button','skip','DELETE');del_.title='Remove this for good. It is used for nothing and never comes back.';skip.title='Do not ask about this again';
    const why=el('div');card.appendChild(row);card.appendChild(why);
    const why_h=el('div','h','WHY? (OPTIONAL BUT THIS IS WHAT IT LEARNS FROM)');why.appendChild(why_h);
    const opts=el('div','opts');Object.keys(causes).forEach(k=>{const b=el('button',null,causes[k]);b.type='button';b.onclick=()=>{cause=cause===k?'':k;opts.querySelectorAll('button').forEach(x=>x.classList.remove('on'));if(cause)b.classList.add('on');};opts.appendChild(b);});why.appendChild(opts);
    const sel=el('select');const s0=el('option',null,'If the Hub chose wrongly, it should have been...');s0.value='';sel.appendChild(s0);bins.filter(b=>b.id!==it.chosen).forEach(b=>{const o=el('option',null,b.help||b.id);o.value=b.id;sel.appendChild(o);});why.appendChild(sel);
    const note=el('textarea');note.placeholder='In your own words: what you said, what you saw, what went wrong. If the transcript was nonsense, say so here.';note.rows=3;note.maxLength=300;why.appendChild(note);
    why.appendChild(el('div','effect','What this does: WRONG with a "should have been" makes the Hub route this exact sentence that way from now on. The reason and notes are kept and counted on the LEARNED tab; a speech-to-text miss is counted separately and is not held against the router.'));
    const save=el('button',null,'SAVE');save.hidden=true;
    const paint=()=>{[yes,part,no].forEach(b=>b.classList.remove('on'));({right:yes,partly:part,wrong:no})[grade]&&({right:yes,partly:part,wrong:no})[grade].classList.add('on');save.hidden=!(grade==='partly'||grade==='wrong');save.textContent='SAVE '+(grade||'').toUpperCase();};
    const send1=(g)=>send('/api/learning/teach',Object.assign({of:it.of},g),()=>{left=Math.max(0,left-1);i++;show();});
    const full=(g)=>({grade:g,cause:cause||undefined,correct:sel.value||undefined,bad_steps:[...bad].sort((a,b)=>a-b),step:bad.size?[...bad][0]:undefined,note:note.value||undefined});
    yes.onclick=()=>send1(full('right'));skip.onclick=()=>send1({grade:'skip'});del_.onclick=()=>send1({grade:'delete'});
    part.onclick=()=>{grade='partly';paint();};no.onclick=()=>{grade='wrong';paint();};save.onclick=()=>send1(full(grade));
    row.append(yes,part,no,skip,del_,save);c.appendChild(card);
  }
  async function missions(){const c=$('card');c.replaceChildren();$('count').textContent='Newest first. APPLY already counts as a yes and DISCARD as a no; tap for the rest.';
    let j;try{j=await (await fetch('/api/learning/teach/missions',{cache:'no-store'})).json();}catch(e){c.textContent='Could not read the missions: '+e.message;return;}
    if(!j.missions.length){c.appendChild(el('div','card','No missions yet.'));return;}
    j.missions.forEach(m=>{const card=el('div','card');card.appendChild(el('div','said',m.brief||'(no brief)'));
      const meta=el('div','mute');meta.append(el('span','chip',m.project||''),el('span','chip',m.model||''),el('span','chip',m.status));
      if(m.checks!==null)meta.append(el('span','chip '+(m.checks?'ok':'no'),m.checks?'its checks passed':'its checks failed'));
      if(m.verdict!==null&&m.verdict!==undefined)meta.append(el('span','chip '+(m.verdict?'ok':'no'),(m.verdict?'good':'bad')+' ('+m.decided_by+')'));
      card.appendChild(meta);
      const row=el('div','row'),g=el('button',null,'GOOD'),pt=el('button','part','PARTLY'),b=el('button','no','BAD'),hide=el('button','skip','HIDE'),rm=el('button','skip','DELETE');hide.title='Do not show this again';rm.title='Remove this for good; it is used for nothing';
      const save=(x)=>send('/api/learning/teach/mission',Object.assign({id:m.id},x),missions);
      hide.onclick=()=>save({grade:'skip'});rm.onclick=()=>save({grade:'delete'});g.onclick=()=>save({grade:'right'});pt.onclick=()=>detail(row,'partly',false,null,save);b.onclick=()=>detail(row,'wrong',false,null,save);
      row.append(g,pt,b,hide,rm);card.appendChild(row);c.appendChild(card);});}
  // PC TASKS: what the Hub did on this PC while shadow mode was on, with the evidence that it worked and how sure it is
  const pctc=v=>Math.round(v*100)+' %';
  async function tasks(){const c=$('card');c.replaceChildren();let j;
    try{j=await (await fetch('/api/yard/evidence',{cache:'no-store'})).json();}catch(e){c.textContent='Could not read the evidence: '+e.message;return;}
    $('count').textContent=j.on?'Newest first. EXPERIMENTAL: kept on this PC only, the newest '+j.keep+'.':'Shadow mode is OFF, so nothing new is being kept. Turn it on from the R panel.';
    const cal=el('div','card');cal.append(el('div','h','HOW SURE vs WHAT YOU SAID'));
    const g=j.calibration.filter(b=>b.graded);cal.append(el('div','mute',g.length?g.map(b=>b.band+': '+b.right+' of '+b.graded+' right').join('  ·  '):'Nothing graded yet. Each RIGHT or WRONG you tap here is one exact label for the confidence number.'));c.appendChild(cal);
    if(!j.items.length){c.appendChild(el('div','card','No PC task has been kept yet. With shadow mode on, ask the Hub to open an app and do something in it.'));return;}
    j.items.forEach(t=>{const card=el('div','card');card.appendChild(el('div','said',t.goal||'(a task)'));
      const meta=el('div','mute');meta.append(el('span','chip',t.app||''),el('span','chip',t.way),el('span','chip',t.seconds+' s'),el('span','chip '+(t.ok?'ok':'no'),t.ok?'it said done':'it said failed'));
      meta.append(el('span','chip '+(t.confidence>=0.9?'ok':t.confidence>=0.6?'':'no'),'confidence '+pctc(t.confidence)+(t.capped?' (capped: nothing independent checked it)':'')));card.appendChild(meta);
      const why=el('div','steps');t.why.forEach(w=>{const l=el('label');l.append(el('span','n',w.startsWith('warning')?'!':'✓'),el('span',null,w.replace(/^warning: /,'')));if(w.startsWith('warning'))l.classList.add('bad');why.appendChild(l);});card.appendChild(why);
      if(t.pics&&t.pics.length){const pics=el('div','row');t.pics.forEach(w=>{const f=el('div');f.append(el('div','h',w.toUpperCase()));const im=el('img');im.src='/api/yard/evidence/'+t.id+'/'+w+'.jpg';im.alt=w+' picture of the screen';im.loading='lazy';im.style.cssText='max-width:100%;width:290px;border:1px solid var(--border);border-radius:8px';f.append(im);pics.append(f);});card.appendChild(pics);}
      else card.appendChild(el('div','mute','No picture was kept for this one.'));
      const row=el('div','row'),yes=el('button',null,'RIGHT'),no=el('button','no','WRONG'),rp=el('button','part','REPLAY'),sk=el('button','skip','HIDE'),dl=el('button','skip','DELETE');const msg=el('span','mute');sk.title='Do not show this again';dl.title='Remove this task, its pictures and its label for good';
      const lab=g=>fetch('/api/yard/evidence/'+t.id+'/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({grade:g})}).then(()=>tasks());
      yes.onclick=()=>lab('right');no.onclick=()=>lab('wrong');sk.onclick=()=>lab('skip');dl.onclick=()=>fetch('/api/yard/evidence/'+t.id,{method:'DELETE'}).then(()=>tasks());
      rp.hidden=!t.routine;rp.title='Plays the saved routine again on this PC so you can see it';
      rp.onclick=async()=>{if(!confirm('Replay this routine now? It will press things on this PC.'))return;rp.disabled=true;msg.textContent='Replaying...';try{const r=await fetch('/api/yard/evidence/'+t.id+'/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});msg.textContent=r.ok?((await r.json()).say||'done'):(await r.text());}catch(e){msg.textContent=String(e);}rp.disabled=false;};
      row.append(yes,no,rp,sk,dl,msg);if(t.label&&(t.label.grade==='right'||t.label.grade==='wrong'))row.append(el('span','chip '+(t.label.grade==='right'?'ok':'no'),'you said '+t.label.grade));card.appendChild(row);c.appendChild(card);});}
  const segs={'s-req':show,'s-mis':missions,'s-task':tasks};
  Object.keys(segs).forEach(k=>$(k).onclick=()=>{Object.keys(segs).forEach(o=>$(o).classList.toggle('on',o===k));segs[k]();});
  load().catch(e=>{$('card').textContent='Could not read the decision log: '+e.message;});
})();
</script></body></html>
"""


@routes.get("/teach")
async def teach_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
