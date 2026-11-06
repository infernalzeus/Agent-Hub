"""The R panel (EXPERIMENTAL): the yard with its flow and the settings each block owns, TEACH, the routines, and the scores. Nothing else.

YARD    start or stop a session; the architecture as small blocks that light as information travels; click a block to see what it does and change its settings.
TEACH   grade what the Hub did (requests, missions, PC tasks) in /teach.
ROUTINES  the saved routines, which are attested, what the yard found out about the candidates, and FRESH START.
SCORES  how each part is doing against what, and the methods that could replace the current ones.
"""
from __future__ import annotations

from aiohttp import web

from ..embed import embedded

routes = web.RouteTableDef()

_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"><meta name="color-scheme" content="dark">
<title>AGENT HUB - Reinforcement learning</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
:root{--accent:#00e676;--text:rgba(214,245,230,.92);--mute:rgba(214,245,230,.58);--amber:#e0a53c;--red:#ff5c5c;--blue:#3ba7ff;--border:rgba(0,230,118,.22);--panel:rgba(8,12,40,.88)}
body{background:#080c28;color:var(--text);font:12.5px/1.4 Outfit,system-ui,sans-serif;padding:10px max(12px,env(safe-area-inset-left)) 24px}
main{max-width:1100px;margin:0 auto}
h2{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);margin:12px 0 4px}
.row{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:6px 0}
button{background:var(--panel);color:var(--accent);border:1px solid var(--accent);border-radius:7px;padding:5px 10px;font:700 10px Orbitron,system-ui,sans-serif;letter-spacing:.08em;cursor:pointer}
button:disabled{opacity:.5;cursor:default}button.on{background:var(--accent);color:#04120a}button.stop{border-color:var(--red);color:var(--red)}button.part{border-color:var(--amber);color:var(--amber)}button.skip{border-color:var(--border);color:var(--mute)}button.no{border-color:var(--red);color:var(--red)}
.chip{border:1px solid var(--border);border-radius:99px;padding:1px 8px;font-size:11px;color:var(--mute);display:inline-block}.chip.ok{color:var(--accent);border-color:var(--accent)}.chip.part{color:var(--amber);border-color:var(--amber)}.chip.no{color:var(--red);border-color:var(--red)}
.mute{color:var(--mute)}.yes{color:var(--accent)}.no{color:var(--red)}
.tabs{display:flex;gap:5px;margin:8px 0 4px;flex-wrap:wrap}.tabs button{padding:5px 12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:8px 10px;margin:6px 0}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:11.5px}
th{font:700 9.5px Orbitron,system-ui,sans-serif;letter-spacing:.06em;color:var(--accent);text-align:left;padding:4px 8px;border-bottom:1px solid var(--border)}td{padding:3px 8px;border-bottom:1px solid rgba(0,230,118,.08);vertical-align:top}
section{animation:fadein .18s ease}@keyframes fadein{from{opacity:0}to{opacity:1}}@media (prefers-reduced-motion:reduce){section{animation:none}}
iframe.teach{width:100%;height:80vh;min-height:460px;border:1px solid var(--border);border-radius:10px;background:#080c28}
#top-shadow.on{background:var(--accent);color:#04120a}
.flowwrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:rgba(8,12,40,.6);margin:6px 0}#flowsvg{width:100%;min-width:720px;height:auto;display:block}
.fnode{cursor:pointer}.fnode rect{fill:rgba(8,12,40,.92);stroke-width:1.8}.fnode.tested rect{stroke:#3ba7ff}.fnode.built rect{stroke:#e0a53c}.fnode.user rect{stroke:#00e676}.fnode.todo rect{stroke:#ff5c5c;stroke-dasharray:6 4}.fnode.now rect{stroke:#41ebff;stroke-dasharray:3 4}
.fnode text.ft{fill:#d6f5e6;font:700 14px Orbitron,system-ui,sans-serif}.fnode text.fl{fill:#9fe7c0;font:12px Outfit,system-ui,sans-serif}
.fnode.sel rect{stroke-width:3.4}.fnode.pulse rect{fill:rgba(20,40,70,.95);stroke-width:3.2}.fnode.improved rect{stroke:#00e676;stroke-width:4;filter:drop-shadow(0 0 7px #00e676)}
.fedge path{stroke:#6c8f7d;stroke-width:1.6;fill:none}.fedge.lit path{stroke:#41ebff;stroke-width:3.4;stroke-dasharray:10 6;animation:fdash .5s linear infinite}
@keyframes fdash{to{stroke-dashoffset:-16}}@media (prefers-reduced-motion:reduce){.fedge.lit path{animation:none}}
.krow{display:grid;grid-template-columns:minmax(140px,1.3fr) minmax(110px,2fr) 44px 30px;gap:2px 10px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(0,230,118,.08)}.krow:last-child{border:0}
.krow label{font-size:12px}.krow input[type=range]{width:100%;accent-color:var(--accent)}.krow select{font:11.5px Outfit,sans-serif;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:3px}
.krow .kv{font-size:11px;color:var(--amber)}.krow button.i{width:24px;height:24px;padding:0;border-radius:50%;font:700 12px Outfit,sans-serif;margin:0}
details>summary{cursor:pointer;color:var(--accent);font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.08em;padding:6px 0}details h2{margin-top:8px}
.rc .said{font-size:13.5px;margin-bottom:4px}.rc .why{font-size:11.5px;color:var(--mute);margin-top:3px}
</style></head><body><main>
<div class="row" id="topbar"><span class="chip part">EXPERIMENTAL</span><button id="top-shadow" type="button" aria-pressed="false"></button><span class="mute" id="top-note"></span></div>
<div class="tabs" role="tablist"><button type="button" data-tab="yard" class="on">YARD</button><button type="button" data-tab="teach">TEACH</button><button type="button" data-tab="routines">ROUTINES</button><button type="button" data-tab="scores">SCORES</button></div>

<section id="tab-yard">
<div class="row"><button id="go" type="button">START A SESSION</button><button id="stop" type="button" class="stop" hidden>STOP</button><span class="mute" id="phase"></span><span class="chip part" id="msg" hidden></span></div>
<div class="mute" id="result"></div>
<div class="flowwrap"><svg id="flowsvg" role="img" aria-label="The learning layer"></svg></div>
<div class="card" id="nodebox" hidden></div>
<div class="mute" id="flog"></div>
<details id="more"><summary>MORE SETTINGS</summary><div id="knobbox"></div></details>
</section>

<section id="tab-teach" hidden><iframe class="teach" id="teachframe" title="Teach" data-src="/teach"></iframe></section>

<section id="tab-routines" hidden>
<div class="row"><span class="mute" id="freshnote"></span><button id="fresh" type="button" class="part">FRESH START</button></div>
<div id="rlist"></div>
</section>

<section id="tab-scores" hidden>
<div class="wrap"><table id="fit"></table></div>
<h2>METHODS BEHIND EACH CHOICE</h2><div class="wrap"><table id="chal"></table></div>
<div class="mute" id="knn"></div><div class="mute" id="gateline"></div>
</section>
</main>
<script>
(function(){
  const $=id=>document.getElementById(id),pct=v=>Math.round(v*100)+' %';
  const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  const J=(u,o)=>fetch(u,Object.assign({cache:'no-store'},o||{})).then(r=>r.json());
  const POST=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  function head(t,cols){t.replaceChildren();const r=el('tr');cols.forEach(c=>r.appendChild(el('th',null,c)));t.appendChild(r);}

  // ---- the switch at the top
  function lamp(on){try{parent.postMessage({hubShadow:!!on},location.origin);}catch(e){}}
  async function switches(){try{const j=await J('/api/yard/settings'),sh=j.shadow||{},t=$('top-shadow');
    t.textContent='SHADOW MODE: '+(sh.on?'ON':'OFF');t.setAttribute('aria-pressed',String(!!sh.on));t.classList.toggle('on',!!sh.on);t.disabled=!!sh.forced_off_by_environment;
    t.onclick=async()=>{t.disabled=true;try{await POST('/api/yard/settings',{shadow:!sh.on,learning:!sh.on});}finally{await switches();}};lamp(sh.on);
    $('top-note').textContent=sh.forced_off_by_environment?'Held off by an environment variable.':sh.on?'Observing. Nothing is pressed.':'Off. Nothing is recorded.';}catch(e){}}

  // ---- YARD: the flow, as small blocks
  let CV=null,KN=null,gById={},eById={},lastN=0,timer=0,wasRunning=false,flog=[],sel=null,saveT={};
  const NS='http://www.w3.org/2000/svg',sv=(t,a,x)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(x!=null)e.textContent=x;return e;};
  const anchor=(n,s)=>s==='left'?[n.x,n.y+n.height/2]:s==='right'?[n.x+n.width,n.y+n.height/2]:s==='top'?[n.x+n.width/2,n.y]:[n.x+n.width/2,n.y+n.height];
  async function loadFlow(){
    try{CV=await J('/api/yard/canvas?compact=1');KN=await J('/api/yard/knobs');}catch(e){$('result').textContent='Could not read the yard: '+e.message;return;}
    const svg=$('flowsvg');svg.replaceChildren();const defs=sv('defs',{}),mk=sv('marker',{id:'farrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto'});mk.appendChild(sv('path',{d:'M0 0L10 5L0 10z',fill:'#8fb3a0'}));defs.appendChild(mk);svg.appendChild(defs);
    const by={};CV.nodes.forEach(n=>by[n.id]=n);gById={};eById={};
    CV.edges.forEach(e=>{const a=anchor(by[e.fromNode],e.fromSide),b=anchor(by[e.toNode],e.toSide),g=sv('g',{class:'fedge'});g.appendChild(sv('path',{d:'M'+a[0]+' '+a[1]+' L'+b[0]+' '+b[1],'marker-end':'url(#farrow)'}));svg.appendChild(g);eById[e.id]=g;});
    CV.nodes.forEach(n=>{const g=sv('g',{class:'fnode '+n.state,'data-id':n.id});g.appendChild(sv('rect',{x:n.x,y:n.y,width:n.width,height:n.height,rx:8}));
      g.appendChild(sv('text',{x:n.x+10,y:n.y+24,class:'ft'},n.title));const live=sv('text',{x:n.x+10,y:n.y+47,class:'fl'},'');g.appendChild(live);g._live=live;
      g.onclick=()=>openNode(n.id);svg.appendChild(g);gById[n.id]=g;});
    const mx=Math.max(...CV.nodes.map(n=>n.x+n.width)),my=Math.max(...CV.nodes.map(n=>n.y+n.height));svg.setAttribute('viewBox','-8 -8 '+(mx+16)+' '+(my+16));
    const used=new Set();CV.nodes.forEach(n=>n.knobs.forEach(k=>used.add(k)));moreSettings(used);
  }
  function knobRow(k){const row=el('div','krow'),lab=el('label',null,k.label);lab.title=k.info;row.append(lab);let inp;
    if(k.kind==='bool'){inp=el('input');inp.type='checkbox';inp.checked=!!k.value;inp.onchange=()=>put(k.name,inp.checked);row.append(inp,el('span'));}
    else if(k.kind==='choice'){inp=el('select');k.choices.forEach(c=>{const o=el('option',null,c);o.value=c;if(c===k.value)o.selected=true;inp.append(o);});inp.onchange=()=>put(k.name,inp.value);row.append(inp,el('span'));}
    else{inp=el('input');inp.type='range';inp.min=k.low;inp.max=k.high;inp.step=k.step;inp.value=k.value;const v=el('span','kv',String(k.value));inp.oninput=()=>{v.textContent=inp.value;clearTimeout(saveT[k.name]);saveT[k.name]=setTimeout(()=>put(k.name,k.kind==='int'?parseInt(inp.value,10):parseFloat(inp.value)),350);};row.append(inp,v);}
    const rs=el('button','i','↺');rs.title='Back to '+k.default;rs.style.visibility=k.changed?'visible':'hidden';rs.onclick=async()=>{await POST('/api/yard/knobs/reset',{name:k.name});await refreshKnobs();};row.append(rs);return row;}
  async function put(name,value){try{const r=await POST('/api/yard/knobs',{[name]:value});if(!r.ok){$('msg').hidden=false;$('msg').textContent=await r.text();}else{await refreshKnobs(true);}}catch(e){}}
  async function refreshKnobs(quiet){try{KN=await J('/api/yard/knobs');}catch(e){return;}if(!quiet){if(sel)openNode(sel);const used=new Set();CV.nodes.forEach(n=>n.knobs.forEach(k=>used.add(k)));moreSettings(used);}}
  function openNode(id){sel=id;Object.values(gById).forEach(g=>g.classList.toggle('sel',g.dataset.id===id));const n=CV.nodes.find(x=>x.id===id),box=$('nodebox');box.hidden=false;box.replaceChildren();
    box.append(el('b',null,n.title+'  '),document.createTextNode(n.info));const ks=n.knobs.map(name=>KN.knobs.find(k=>k.name===name)).filter(Boolean);
    if(ks.length)ks.forEach(k=>box.append(knobRow(k)));else box.append(el('div','mute','Nothing to adjust here.'));}
  function moreSettings(used){const box=$('knobbox');box.replaceChildren();const groups={};KN.knobs.filter(k=>!used.has(k.name)).forEach(k=>(groups[k.group]=groups[k.group]||[]).push(k));
    Object.keys(groups).forEach(g=>{box.append(el('h2',null,g.toUpperCase()));const card=el('div','card');groups[g].forEach(k=>card.append(knobRow(k)));box.append(card);});
    const fx=el('div','card');KN.fixed.forEach(f=>{const d=el('div','mute');d.append(el('b',null,f.name+': '),document.createTextNode(f.why));fx.append(d);});box.append(el('h2',null,'NOT ADJUSTABLE'),fx);
    const ch=KN.knobs.some(k=>k.changed),rb=el('button','stop','RESET EVERYTHING');rb.id='kreset';rb.hidden=!ch;rb.onclick=async()=>{if(!confirm('Put every number back to its default?'))return;await POST('/api/yard/knobs/reset',{});await refreshKnobs();};box.prepend(rb);}
  const flash=(e,c,ms)=>{e.classList.add(c);setTimeout(()=>e.classList.remove(c),ms);};
  function showEvents(evs){evs.forEach(ev=>{const g=gById[ev.node];if(g){g._live.textContent=(ev.text||'').slice(0,34);flash(g,ev.improved?'improved':'pulse',ev.improved?3500:450);}
      if(ev.edge&&eById[ev.edge])flash(eById[ev.edge],'lit',550);
      if(['improved','saved','imitated','relabel','agreement','stopped'].includes(ev.kind))flog.unshift(ev);});
    flog=flog.slice(0,6);$('flog').replaceChildren(...flog.map(ev=>el('div',ev.improved?'yes':'mute',(ev.improved?'↑ ':'· ')+ev.text)));}
  async function poll(){try{const j=await J('/api/yard/events?since='+lastN);if(j.last<lastN)lastN=0;if(j.events.length){lastN=j.last;showEvents(j.events);}
      $('go').hidden=!!j.running;$('stop').hidden=!j.running;$('phase').textContent=j.running?(j.phase+' ('+Math.round(100*j.done/Math.max(1,j.total))+' %)'):'';
      if(wasRunning&&!j.running)loadResult();wasRunning=!!j.running;}catch(e){}}
  async function loadResult(){try{const s=await J('/api/yard/status'),r=s.report,box=$('result');
    if(!s.ready){box.textContent='numpy is not installed; practising needs it.';return;}
    if(!r){box.textContent='No session yet.';return;}
    const m=r.means||{},v=s.in_use_version,att=r.attested_agreement&&r.attested_agreement.rate!=null?' · agrees with your attested routines on '+pct(r.attested_agreement.rate):'';
    box.textContent='Last session: version '+(v||'?')+', '+r.episodes+' episodes. Unseen words: learned '+pct((m['learned, linear']||{}).held||0)+' · rule of thumb '+pct((m['rule of thumb']||{}).held||0)+' · random '+pct((m.random||{}).held||0)+att;}catch(e){}}
  $('go').onclick=async()=>{$('go').disabled=true;$('msg').hidden=true;try{const r=await POST('/api/yard/practice',{confirm:true});if(!r.ok)throw Error(await r.text()||('error '+r.status));const j=await r.json();
      if(j.stopped){$('msg').hidden=false;$('msg').textContent='Stopped. Nothing was saved.';}}catch(e){$('msg').hidden=false;$('msg').textContent=String(e.message||e);}finally{$('go').disabled=false;poll();loadResult();}};
  $('stop').onclick=async()=>{$('stop').disabled=true;try{await POST('/api/yard/practice/stop');}catch(e){}$('stop').disabled=false;};
  function flowStart(){if(!CV)loadFlow();loadResult();if(!timer)timer=setInterval(poll,500);poll();}
  function flowStop(){clearInterval(timer);timer=0;}

  // ---- ROUTINES
  async function routines(){
    const box=$('rlist');box.replaceChildren();let rows=[],gold={routines:[]},cands=[],s={};
    try{[rows,gold,cands,s]=await Promise.all([J('/api/pc/routines').then(j=>j.routines||[]),J('/api/yard/golden'),J('/api/yard/candidates').then(j=>j.candidates||[]).catch(()=>[]),J('/api/yard/settings')]);}catch(e){box.textContent='Could not read the routines: '+e.message;return;}
    $('freshnote').textContent=s.fresh_since?'Learners read only what happened after '+new Date(s.fresh_since*1000).toLocaleString()+'.':'Learners read everything until the first time shadow mode is switched on.';
    $('fresh').onclick=async()=>{if(!confirm('FRESH START: learners read only new rows from now on, and the routines trusted right now become attested checks. Nothing is deleted.'))return;await POST('/api/yard/settings',{fresh:true});routines();};
    const att=new Set((gold.routines||[]).map(r=>r.id)),chk={};cands.forEach(c=>chk[c.id]=c);
    if(!rows.length){box.append(el('div','card','No routines yet.'));return;}
    rows.forEach(r=>{const c=el('div','card rc');c.append(el('div','said',r.title));const m=el('div');
      m.append(el('span','chip '+(r.status==='trusted'?'ok':r.status==='disabled'?'no':'part'),r.status.toUpperCase()),document.createTextNode(' '),el('span','chip',r.successes+' good · '+r.failures+' bad'),document.createTextNode(' '),el('span','chip',r.updated?('last used '+new Date(r.updated*1000).toLocaleDateString()):'never used'));
      if(att.has(r.id)){m.append(document.createTextNode(' '),el('span','chip ok','attested: a check, never training'));}
      const k=chk[r.id];if(k){m.append(document.createTextNode(' '),el('span','chip '+(k.ready?'ok':'part'),k.ready?'yard: looks ready':'yard: not ready'));}
      c.append(m);if(k&&!k.ready)c.append(el('div','why',k.reasons.join('. ')+'.'));if(k&&k.ready)c.append(el('div','why','No forbidden control, replayed clean, and the learner agrees on '+(k.agree==null?'(no learner yet)':pct(k.agree))+' of its steps. Only you can approve it.'));
      const st=el('div','why');c.append(st);const row=el('div','row'),see=el('button','skip','SHOW STEPS'),ok=el('button',null,'APPROVE'),off=el('button','part',r.status==='disabled'?'RE-ENABLE':'DISABLE'),del=el('button','no','DELETE'),rp=el('button','part','REPLAY');
      see.onclick=async()=>{try{const j=await J('/api/pc/routines/'+r.id+'/steps');st.textContent=(j.steps.length?j.steps.map(x=>(x.ordinal+1)+'. '+x.tool+' '+((x.target&&x.target.name)||'')).join('  >  '):'no steps (an app launch or an address)');}catch(e){st.textContent=String(e);}};
      ok.onclick=async()=>{await POST('/api/pc/routines/'+r.id+'/approve');routines();};
      off.onclick=async()=>{await POST('/api/pc/routines/'+r.id+'/status',{status:r.status==='disabled'?'candidate':'disabled'});routines();};
      del.onclick=async()=>{if(!confirm('Delete this routine for good? '+r.title))return;await fetch('/api/pc/routines/'+r.id,{method:'DELETE'});routines();};
      rp.onclick=async()=>{if(!confirm('Replay "'+r.title+'" now? It will press things on this PC.'))return;rp.disabled=true;st.textContent='Replaying...';try{const x=await POST('/api/pc/routines/'+r.id+'/run');st.textContent=x.ok?'It ran.':(await x.text());}catch(e){st.textContent=String(e);}rp.disabled=false;};
      ok.hidden=r.status==='trusted';rp.hidden=!att.has(r.id);row.append(see,ok,off,rp,del);c.append(row);box.append(c);});}

  // ---- SCORES
  async function scores(){const t=$('fit');head(t,['Part','Score','95 % interval','Evidence','Needs','Compared with']);
    let j;try{j=await J('/api/yard/fitness');}catch(e){t.append(el('tr'));return;}
    const rate=r=>r&&r.n?pct(r.rate):'-',iv=r=>r&&r.n?pct(r.lower95)+' to '+pct(r.upper95):'-';
    j.heads.forEach(h=>{
      if(h.options){const ks=Object.keys(h.options);if(!ks.length){const r=el('tr');r.append(el('td',null,h.head),el('td','mute','nothing labelled yet'),el('td'),el('td'),el('td','mute',h.needs),el('td','mute',h.baseline));t.append(r);}
        ks.forEach(k=>{const o=h.options[k],r=el('tr');r.append(el('td',null,h.head+': '+k),el('td',null,rate(o)),el('td','mute',iv(o)),el('td',null,o.k+' of '+o.n),el('td','mute',h.needs),el('td','mute',h.baseline));t.append(r);});return;}
      const r=el('tr');
      if(h.train){r.append(el('td',null,h.head),el('td',null,rate(h.train)),el('td','mute',iv(h.train)),el('td',null,h.train.n+' labelled; '+h.frozen.n+' held out'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else if(h.in_good_tasks){r.append(el('td',null,h.head),el('td',null,rate(h.in_good_tasks)),el('td','mute',iv(h.in_good_tasks)),el('td',null,h.tasks+' tasks'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else if(h.brier!==undefined){r.append(el('td',null,h.head),el('td',null,h.brier===null?'-':'Brier '+h.brier),el('td','mute','lower is better'),el('td',null,h.graded+' graded'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else{const sf=h.safety?('forbidden pressed on '+h.safety.breaches+' of '+h.safety.screens+' screens'):'no saved learner';
        r.append(el('td',null,h.head),el('td',null,h.means?Object.entries(h.means).map(([k,v])=>k+' '+pct(v.held)).join(' · '):'-'),el('td'),el('td','mute','unseen words; '+sf),el('td','mute',h.needs),el('td','mute',h.baseline));}
      t.append(r);});
    const ch=j.challengers||{},ct=$('chal');head(ct,['Choice','Method','Scored on','Agreed','Estimate','Worth (rows)','Watched']);
    if(!ch.error)['model','rung'].forEach(h=>(ch[h]||[]).forEach(l=>{const r=el('tr');r.append(el('td',null,h),el('td',null,l.learner),el('td','mute',l.available===false?('needs '+l.needs):(l.decided||0)+' choices'),el('td',null,l.available===false?'-':(l.agreed||0)),el('td',null,l.estimate==null?'-':pct(l.estimate)),el('td','mute',l.available===false?'-':(l.ess||0).toFixed(1)));
        const w=el('td'),b=el('button',null,(ch.selected||{})[h]===l.learner?'WATCHED':'WATCH');b.disabled=l.available===false||(ch.selected||{})[h]===l.learner;
        b.onclick=async()=>{await POST('/api/yard/learners',{head:h,learner:l.learner});scores();};w.append(b);r.append(w);ct.append(r);}));
    const k=ch.router_knn||{},c2=ch.router_classifier||{};
    $('knn').textContent=k.ready?('Router, graded requests left out one at a time: nearest neighbours right on '+pct(k.knn)+(c2.ready?', trained classifier on '+pct(c2.classifier):'')+', current rules and tev on '+pct(k.current)+' ('+k.n+' graded).'):('Router: needs '+(k.needs||5)+' graded requests, has '+(k.n||0)+'.');
    const g=j.gate||{};$('gateline').textContent='Gate for a new version: '+g.min_frozen+' held-out rows · zero forbidden presses · '+g.shadow_n+' watched live choices at '+pct(g.shadow_agree||0)+' · your yes.';}

  // ---- tabs
  const TABS=['yard','teach','routines','scores'];
  function tab(name){if(!TABS.includes(name))name='yard';document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===name));
    TABS.forEach(n=>$('tab-'+n).hidden=n!==name);if(name==='yard')flowStart();else flowStop();
    if(name==='teach'){const f=$('teachframe');if(!f.src)f.src=f.dataset.src;}if(name==='routines')routines();if(name==='scores')scores();try{localStorage.setItem('hub-rl-tab',name);}catch(e){}}
  document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
  let first='yard';try{first=localStorage.getItem('hub-rl-tab')||'yard';}catch(e){}
  switches();tab(first);
})();
</script></body></html>
"""


@routes.get("/yard")
async def yard_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
