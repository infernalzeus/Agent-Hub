"""The PRACTICE page: run the yard, read its last report, and see what the trained policy would have pressed beside the live agent.

One page, no libraries; it only reads /api/yard/status and posts to /api/yard/practice. Shown as a tab of the Auto-LLM block on the board
and as /yard on its own.
"""
from __future__ import annotations

from aiohttp import web

from ..embed import embedded

routes = web.RouteTableDef()

_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"><meta name="color-scheme" content="dark">
<title>AGENT HUB - Practice yard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--accent:#00e676;--text:rgba(214,245,230,.92);--mute:rgba(214,245,230,.58);--amber:#e0a53c;--red:#ff5c5c;--blue:#3ba7ff;--border:rgba(0,230,118,.22);--panel:rgba(8,12,40,.88)}
body{background:#080c28;color:var(--text);font:14px/1.5 Outfit,system-ui,sans-serif;padding:18px max(16px,env(safe-area-inset-left)) 40px}
main{max-width:980px;margin:0 auto}
h1{font:800 20px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent)}
h2{font:700 13px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);margin:20px 0 6px}
p.sub{color:var(--mute);margin:4px 0 12px;font-size:13px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:10px 0}
button{background:var(--panel);color:var(--accent);border:1px solid var(--accent);border-radius:8px;padding:8px 16px;font:700 12px Orbitron,system-ui,sans-serif;letter-spacing:.08em;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.chip{border:1px solid var(--border);border-radius:99px;padding:2px 10px;font-size:12px;color:var(--mute)}
.chip.ok{color:var(--accent);border-color:var(--accent)}.chip.part{color:var(--amber);border-color:var(--amber)}
.wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.06em;color:var(--accent);text-align:left;padding:6px 10px;border-bottom:1px solid var(--border)}
td{padding:6px 10px;border-bottom:1px solid rgba(0,230,118,.08);vertical-align:top}
.bar{display:inline-block;height:8px;border-radius:4px;background:var(--accent);vertical-align:middle;margin-right:6px;min-width:1px}
.bar.held{background:var(--blue)}
.mute{color:var(--mute)}.no{color:var(--red)}.yes{color:var(--accent)}
code{background:rgba(0,230,118,.08);border-radius:4px;padding:0 4px}
#msg{color:var(--amber);min-height:20px}
</style></head><body><main>
<h1>PRACTICE YARD</h1>
<p class="sub">Pretend apps where the Hub's own desktop agent can fail safely. A small learner practises there, and is measured on apps and words it has never seen. Nothing here touches your PC, and nothing it learns is used by the live agent yet.</p>
<div class="row"><button id="go" type="button">PRACTICE</button><span id="chips"></span></div>
<div class="row" id="switches"><button id="sw-learning" type="button"></button><button id="sw-shadow" type="button"></button></div>
<p class="sub">LEARNING LOG notes each choice the Hub makes (route, model, desktop step) and how it turned out. SHADOW MODE lets the trained practice policy watch each live desktop step and record what it would have pressed; it never presses anything. Switch either off and new notes stop at once; what is already recorded stays.</p>
<div id="msg" role="status"></div>
<h2>HOW EACH POLICY DOES</h2><div class="wrap"><table id="means"></table></div>
<h2>BY LAYOUT (learned vs rule of thumb)</h2><div class="wrap"><table id="layouts"></table></div>
<h2>WHAT IT WOULD HAVE PRESSED, BESIDE THE LIVE AGENT (SHADOW)</h2>
<p class="sub" id="shadowsub"></p><div class="wrap"><table id="shadow"></table></div>
</main>
<script>
(function(){
  const $=id=>document.getElementById(id),pct=v=>Math.round(v*100)+' %';
  const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  function head(t,cols){t.replaceChildren();const r=el('tr');cols.forEach(c=>r.appendChild(el('th',null,c)));t.appendChild(r);}
  function bar(v,held){const s=el('span');const b=el('span','bar'+(held?' held':''));b.style.width=Math.max(1,Math.round(v*90))+'px';s.append(b,document.createTextNode(pct(v)));return s;}
  function paint(st){
    const chips=$('chips');chips.replaceChildren();
    chips.append(el('span','chip '+(st.ready?'ok':'part'),st.ready?'ready':'numpy missing'));
    if(st.report)chips.append(el('span','chip',new Date(st.report.at*1000).toLocaleString()+' · '+st.report.episodes+' episodes · '+st.report.train_seconds+' s'));
    const m=$('means');head(m,['Policy','Known words','Unseen words']);
    if(st.report){for(const [p,v] of Object.entries(st.report.means)){const r=el('tr');r.append(el('td',null,p));const a=el('td'),b=el('td');a.append(bar(v.train));b.append(bar(v.held,true));r.append(a,b);m.append(r);}}
    else{const r=el('tr'),d=el('td','mute','Nothing run yet. Press PRACTICE: about twenty seconds of one processor core, nothing opens on your screen.');d.colSpan=3;r.append(d);m.append(r);}
    const l=$('layouts');head(l,['Layout','Learned, known words','Learned, unseen words','Rule of thumb, known words','Why the learned one failed']);
    if(st.report){const L=st.report.table['learned, linear'],R=st.report.table['rule of thumb'];
      for(const f of Object.keys(L)){const r=el('tr');r.append(el('td',null,f));
        for(const [t,v] of [[L,'train'],[L,'held'],[R,'train']]){const c=el('td');c.append(bar(t[f][v].success,v==='held'));r.append(c);}
        const why=Object.assign({},L[f].held.why_failed,L[f].train.why_failed);r.append(el('td','mute',Object.keys(why).join('; ')||'-'));l.append(r);}}
    const s=st.shadow||{},sh=$('shadow');
    $('shadowsub').textContent=!s.policy?'No trained policy yet: press PRACTICE once, then it will watch every desktop task and record what it would have chosen.':
      (s.steps?s.steps+' live choices watched, it would have chosen the same on '+pct(s.agree/s.steps)+'; '+s.tasks+' tasks, '+s.tasks_ok+' succeeded.':'Watching. Nothing recorded yet: ask Talk to do something inside an app.');
    head(sh,['Goal','Step','Live agent pressed','It would have pressed','Same?']);
    (s.last||[]).slice().reverse().forEach(x=>{const r=el('tr');r.append(el('td',null,x.goal),el('td',null,x.step+1),el('td',null,(x.live.name||x.live.do)),el('td',null,(x.would.name||x.would.do)),el('td',x.agree?'yes':'no',x.agree?'yes':'no'));sh.append(r);});
  }
  async function switches(){try{const j=await (await fetch('/api/yard/settings',{cache:'no-store'})).json();
    [['learning','LEARNING LOG'],['shadow','SHADOW MODE']].forEach(([k,t])=>{const b=$('sw-'+k),s=j[k]||{};b.textContent=t+': '+(s.on?'ON':'OFF');b.title=s.forced_off_by_environment?'Held off by an environment variable on this PC':'Click to switch';b.disabled=!!s.forced_off_by_environment;
      b.onclick=async()=>{b.disabled=true;try{await fetch('/api/yard/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[k]:!s.on})});}finally{await switches();}};});}catch(e){}}
  async function load(){switches();try{const r=await fetch('/api/yard/status',{cache:'no-store'});paint(await r.json());}catch(e){$('msg').textContent='Could not read the yard: '+e.message;}}
  $('go').onclick=async()=>{const b=$('go');b.disabled=true;$('msg').textContent='Practising... this takes about half a minute and uses one processor core.';
    try{const r=await fetch('/api/yard/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,episodes:1500})});
      if(!r.ok)throw Error(await r.text()||('error '+r.status));$('msg').textContent='Done.';await load();}
    catch(e){$('msg').textContent=String(e.message||e);}finally{b.disabled=false;}};
  load();
})();
</script></body></html>
"""


@routes.get("/yard")
async def yard_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
