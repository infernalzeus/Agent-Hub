"""TEACH: tap RIGHT or WRONG on what the Hub decided for things you already asked it.

The learning plan is short of exact labels (10 of the 100 the routing learner wants). Every tap here is one exact label, written as the
same `verdict` line the router already writes when you say "no, I meant...", so nothing new has to learn how to read it. A WRONG may name
the bin it should have been, which is the one thing a classifier can learn from directly.

Reads the decision log (hub/utterance_decisions.jsonl). Shows only decisions that have no exact label yet. Writes one line per tap.
"""
from __future__ import annotations

import time

from aiohttp import web

from ..embed import embedded

routes = web.RouteTableDef()

BIN_HELP = {
    "launch_app": "open an app", "app_task": "do something inside an app", "pc_direct": "press or type on the PC right now",
    "lookup_routine": "look up a saved routine", "lookup_agent": "ask an agent", "hub_command": "a Hub command (open a page, ingest, status)",
    "conversation": "just talk", "personal_fact": "remember or recall a fact about you",
}


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
    return web.json_response({"items": items, "left": left, "bins": [{"id": b, "help": BIN_HELP.get(b, "")} for b in BIN.BINS]})


@routes.post("/api/learning/teach")
async def api_tap(request: web.Request) -> web.Response:
    from ..features import binning as BIN
    try:
        b = await request.json()
        of, ok = float(b["of"]), b["ok"]
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"of": the decision id, "ok": true|false, "correct": optional bin}')
    if not isinstance(ok, bool):
        raise web.HTTPBadRequest(text="ok must be true or false")
    if not any(r.get("at") == of and r.get("kind") not in ("outcome", "verdict") for r in BIN._rows()):
        raise web.HTTPNotFound(text="no such decision")
    row = {"kind": "verdict", "at": round(time.time(), 1), "of": of, "ok": ok, "by": "teach"}
    correct = b.get("correct")
    if not ok and isinstance(correct, str) and correct in BIN.BINS:
        row["correct"] = correct
    BIN._append(row)
    return web.json_response({"ok": True})


_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>AGENT HUB - Teach</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--accent:#00e676;--text:rgba(214,245,230,.92);--mute:rgba(214,245,230,.58);--amber:#e0a53c;--red:#ff5c5c;--border:rgba(0,230,118,.25);--panel:rgba(8,12,40,.9)}
body{background:#080c28;color:var(--text);font:15px/1.5 Outfit,system-ui,sans-serif;padding:18px max(16px,env(safe-area-inset-left)) 40px}
main{max-width:640px;margin:0 auto}
h1{font:800 20px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent)}
p.sub{color:var(--mute);margin:6px 0 14px;font-size:13px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0}
.said{font-size:20px;line-height:1.35;margin-bottom:10px}.bin{color:var(--accent);font-weight:600}.mute{color:var(--mute);font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
button,select{font:700 13px Orbitron,system-ui,sans-serif;letter-spacing:.06em;border-radius:8px;padding:11px 18px;border:1px solid var(--accent);background:var(--panel);color:var(--accent);cursor:pointer;min-height:44px}
button.no{border-color:var(--red);color:var(--red)}button.skip{border-color:var(--border);color:var(--mute)}
select{font-weight:400;letter-spacing:0;max-width:100%}
.count{color:var(--amber);font-size:13px}
</style></head><body><main>
<h1>TEACH</h1>
<p class="sub">Things you already asked, and what the Hub thought you wanted. Tap RIGHT or WRONG. Each tap is one exact label for the learner; nothing else changes.</p>
<div class="count" id="count"></div>
<div id="card"></div>
</main>
<script>
(function(){
  let items=[],bins=[],i=0,left=0;
  const $=id=>document.getElementById(id),el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  async function load(){const r=await fetch('/api/learning/teach',{cache:'no-store'});const j=await r.json();items=j.items;bins=j.bins;left=j.left;i=0;show();}
  function help(b){const x=bins.find(y=>y.id===b);return x&&x.help?x.help:b;}
  async function tap(ok,correct){const it=items[i];try{await fetch('/api/learning/teach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({of:it.of,ok:ok,correct:correct||undefined})});}catch(e){}left=Math.max(0,left-1);i++;show();}
  function show(){
    const c=$('card');c.replaceChildren();$('count').textContent=left?left+' still without a label':'';
    const it=items[i];
    if(!it){c.appendChild(el('div','card',left?'That is the batch. Reload for more.':'Nothing left to label. Thank you.'));return;}
    const card=el('div','card');card.appendChild(el('div','said','“'+it.text+'”'));
    const p=el('div','mute','The Hub took that as: ');p.appendChild(el('span','bin',help(it.chosen)));card.appendChild(p);
    if(it.said)card.appendChild(el('div','mute','It said: '+it.said));
    const row=el('div','row'),yes=el('button',null,'RIGHT'),no=el('button','no','WRONG'),skip=el('button','skip','SKIP');
    yes.onclick=()=>tap(true);skip.onclick=()=>{i++;show();};
    no.onclick=()=>{row.replaceChildren();const sel=el('select');const o0=el('option',null,'It should have been...');o0.value='';sel.appendChild(o0);
      bins.filter(b=>b.id!==it.chosen).forEach(b=>{const o=el('option',null,b.help||b.id);o.value=b.id;sel.appendChild(o);});
      const done=el('button','no','SAVE WRONG');done.onclick=()=>tap(false,sel.value);row.append(sel,done);};
    row.append(yes,no,skip);card.appendChild(row);c.appendChild(card);
  }
  load().catch(e=>{$('card').textContent='Could not read the decision log: '+e.message;});
})();
</script></body></html>
"""


@routes.get("/teach")
async def teach_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
