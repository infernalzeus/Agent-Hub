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
<title>AGENT HUB - Reinforcement learning</title>
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
header.top{margin-bottom:4px}html.hub-embed header.top h1{display:none}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.flow{display:flex;gap:6px;align-items:stretch;flex-wrap:wrap;margin:14px 0 6px}
.step{flex:1 1 130px;min-width:120px;background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px 12px;position:relative}
.step .n{font:700 10px Orbitron,system-ui,sans-serif;letter-spacing:.1em;color:var(--mute)}.step .t{font:700 13px Orbitron,system-ui,sans-serif;letter-spacing:.06em;color:var(--accent);margin:2px 0}
.step .d{font-size:12px;color:var(--mute);line-height:1.4}.step .v{margin-top:6px;font-size:13px;color:var(--text)}.step .v b{color:var(--accent)}
.step.now{border-color:var(--accent);box-shadow:0 0 14px rgba(0,230,118,.18)}.step.wait{opacity:.7}
.words{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.words div{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:8px 12px;font-size:12.5px}.words b{display:block;color:var(--accent);font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.06em;margin-bottom:2px}.words span{color:var(--mute)}
#next .a{display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid rgba(0,230,118,.08)}#next .a:last-child{border:0}#next .a span{flex:1}
section{animation:fadein .18s ease}@keyframes fadein{from{opacity:0}to{opacity:1}}@media (prefers-reduced-motion:reduce){section{animation:none}}
button.i{width:26px;height:26px;padding:0;border-radius:50%;font:700 13px Outfit,system-ui,sans-serif;letter-spacing:0;display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;margin-left:8px}
.infobox{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px;line-height:1.55}.infobox[hidden]{display:none}.infobox b{color:var(--accent)}.infobox ul{margin:6px 0 0 18px}.infobox li{margin:2px 0}
.tabs{display:flex;gap:8px;margin:12px 0 4px;flex-wrap:wrap}.tabs button{padding:8px 14px}.tabs button.on{background:var(--accent);color:#04120a}
.prog{display:none;margin:6px 0}.prog.on{display:block}.prog .track{height:8px;border-radius:4px;background:rgba(0,230,118,.12);overflow:hidden}.prog .fill{height:100%;background:var(--accent);width:0}
.stop{border-color:var(--red);color:var(--red)}iframe.teach{width:100%;height:68vh;min-height:420px;border:1px solid var(--border);border-radius:10px;background:#080c28}
</style></head><body><main>
<header class="top"><h1>REINFORCEMENT LEARNING</h1><p class="sub">The Hub records each choice it makes, you grade them, and the grades change what it does. Today only one thing acts on your grades: a sentence you correct is routed your way from then on. The rest records or practises. See LEARNED.</p></header>
<div class="tabs" role="tablist"><button type="button" data-tab="overview" class="on">OVERVIEW</button><button type="button" data-tab="practice">YARD</button><button type="button" data-tab="teach">TEACH</button><button type="button" data-tab="learned">LEARNED</button><button type="button" data-tab="routines">ROUTINES</button><button type="button" data-tab="status">STATUS</button></div>
<section id="tab-overview">
<div class="flow" id="flow"></div>
<h2>WHAT TO DO NEXT</h2><div id="next" class="card"></div>
</section>
<section id="tab-practice">
<p class="sub">Pretend music apps where a learner tries to play a playlist, again and again. Nothing here touches your PC.<button type="button" class="i" data-info="info-yard" title="Details" aria-label="Details about the yard">i</button></p>
<div class="infobox" id="info-yard" hidden><b>What the button does.</b> START A SESSION trains two small learners for about a minute on eight pretend app designs, then tests them. It uses one processor core and opens nothing on your screen. <b>STOP</b> ends it straight away and throws that session away; the last finished results stay. You never have to stop it: it ends by itself.<br><br><b>The tables.</b><ul><li><b>Method</b> (the word &ldquo;policy&rdquo; in the code) is just a way of deciding what to press. Four are compared: random, the rule of thumb the Hub already uses, and two learned ones.</li><li><b>Known words / unseen words</b>: apps use different words for the same button (Play, Start, Listen now). &ldquo;Unseen&rdquo; tests it on words it never practised, which shows whether it learned the layout or only memorised words.</li><li><b>Layouts</b>: eight pretend app designs, each with its own trap (below).</li><li><b>Shadow</b>: during real PC tasks the learner watches the live agent and writes down what it would have pressed. It never presses anything.</li></ul><b>The eight layouts.</b><ul><li><b>direct</b>: the playlist is on the home screen with its own Play button (the easy one).</li><li><b>modal</b>: a welcome dialog blocks everything until you press Not now.</li><li><b>search</b>: no playlists listed; type its name in the search box first.</li><li><b>menu</b>: the playlist page has no Play button; it is under More options.</li><li><b>long</b>: a list of 30 with the target far down.</li><li><b>unnamed</b>: the Play button is an icon with no name (a real agent cannot see those; always fails, on purpose).</li><li><b>tabs</b>: the playlists are under a Library tab.</li><li><b>confirm</b>: pressing Play opens &ldquo;Resume or start over?&rdquo; that must be answered.</li></ul></div>
<div class="row"><button id="go" type="button">START A SESSION</button><button id="stop" type="button" class="stop" hidden>STOP</button><span id="chips"></span></div>
<div class="prog" id="prog"><div class="mute" id="phase"></div><div class="track"><div class="fill" id="fill"></div></div></div>
<div id="msg" role="status"></div>
<h2>HOW EACH METHOD DOES</h2><div class="wrap"><table id="means"></table></div>
<h2>BY LAYOUT (learned vs the Hub's rule of thumb)</h2><div class="wrap"><table id="layouts"></table></div>
<h2>WHAT IT WOULD HAVE PRESSED, BESIDE THE LIVE AGENT (SHADOW)</h2>
<p class="sub" id="shadowsub"></p><div class="wrap"><table id="shadow"></table></div>
</section>
<section id="tab-teach" hidden>
<p class="sub">Tell the Hub what was right or wrong in things that really happened.<button type="button" class="i" data-info="info-teach" title="Details" aria-label="Details about teach">i</button></p>
<div class="infobox" id="info-teach" hidden><b>REQUESTS</b> shows things you said to the Hub and what it took you to mean. Tap <b>RIGHT</b> if it understood, <b>WRONG</b> if not (and say what you meant). <b>MISSIONS</b> shows your latest jobs for coding agents, newest first. Tap <b>GOOD</b> or <b>BAD</b>. If you already pressed APPLY the Hub counts it as good, DISCARD as bad; your tap beats that.<br><br>Each tap is one exact result. The learners are short of these: they need about a hundred and have about ten. Nothing else changes when you tap.</div>
<iframe class="teach" id="teachframe" title="Teach" data-src="/teach"></iframe>
</section>
<section id="tab-learned" hidden><p class="sub" id="lsub"></p><div class="card" id="lnow"></div><h2>CORRECTIONS NOW IN FORCE</h2><div class="wrap"><table id="lfix"></table></div><h2>YOUR GRADES</h2><div class="wrap"><table id="lgrades"></table></div><h2>NOT BUILT YET</h2><div class="card" id="lnot"></div></section>
<section id="tab-routines" hidden><p class="sub">Saved ways of doing things on this PC. A CANDIDATE has not been replayed cleanly twice; TRUSTED replays with no model. Read the steps, then APPROVE what is right and DELETE what is junk.</p><div id="rlist"></div></section>
<section id="tab-status" hidden>
<h2>SWITCHES<button type="button" class="i" data-info="info-status" title="Details" aria-label="Details about status">i</button></h2>
<div class="infobox" id="info-status" hidden><b>LEARNING LOG</b> writes down each choice the Hub makes and how it turned out; switch it off and new notes stop. <b>SHADOW MODE</b> lets the trained learner watch real PC tasks and note what it would have done; it never acts. Below: how many choices exist and how many have an exact result, what each later step is still waiting for, and the <b>bandits</b> (the simplest learners: a tally of how often each option worked; they say nothing until two options have three results each).</div>
<div class="row" id="switches"><button id="sw-learning" type="button"></button><button id="sw-shadow" type="button"></button></div>

<h2>HOW MUCH THERE IS TO LEARN FROM</h2><p class="sub" id="statsub"></p><div class="wrap"><table id="kinds"></table></div>
<h2>WHAT EACH LATER STEP STILL NEEDS</h2><div class="wrap"><table id="needs"></table></div>
<h2>SAVED LEARNERS</h2><p class="sub" id="versionsub">Each finished session saves its learner. The one the shadow mode watches with is replaced only by a learner at least as good on unseen words; older ones are kept so any can be restored.</p><div class="wrap"><table id="versions"></table></div>
<h2>THE BANDITS, REPLAYED AGAINST THE LOG</h2><p class="sub">A bandit is a tally of how often each option worked. It has no opinion until two options have three exact results each.</p><div class="wrap"><table id="bandits"></table></div>
</section>
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
    const m=$('means');head(m,['Method','Known words','Unseen words']);
    if(st.report){for(const [p,v] of Object.entries(st.report.means)){const r=el('tr');r.append(el('td',null,p));const a=el('td'),b=el('td');a.append(bar(v.train));b.append(bar(v.held,true));r.append(a,b);m.append(r);}}
    else{const r=el('tr'),d=el('td','mute','Nothing run yet. Press START A SESSION: about a minute of one processor core, nothing opens on your screen.');d.colSpan=3;r.append(d);m.append(r);}
    const l=$('layouts');head(l,['Layout','Learned, known words','Learned, unseen words','Rule of thumb, known words','Why the learned one failed']);
    if(st.report){const L=st.report.table['learned, linear'],R=st.report.table['rule of thumb'];
      for(const f of Object.keys(L)){const r=el('tr');r.append(el('td',null,f));
        for(const [t,v] of [[L,'train'],[L,'held'],[R,'train']]){const c=el('td');c.append(bar(t[f][v].success,v==='held'));r.append(c);}
        const why=Object.assign({},L[f].held.why_failed,L[f].train.why_failed);r.append(el('td','mute',Object.keys(why).join('; ')||'-'));l.append(r);}}
    const s=st.shadow||{},sh=$('shadow');
    $('shadowsub').textContent=!s.policy?'No trained learner yet: start one session, then it will watch every desktop task and record what it would have chosen.':
      (s.steps?s.steps+' live choices watched, it would have chosen the same on '+pct(s.agree/s.steps)+'; '+s.tasks+' tasks, '+s.tasks_ok+' succeeded.':'Watching. Nothing recorded yet: ask Talk to do something inside an app.');
    head(sh,['Goal','Step','Live agent pressed','It would have pressed','Same?']);
    (s.last||[]).slice().reverse().forEach(x=>{const r=el('tr');r.append(el('td',null,x.goal),el('td',null,x.step+1),el('td',null,(x.live.name||x.live.do)),el('td',null,(x.would.name||x.would.do)),el('td',x.agree?'yes':'no',x.agree?'yes':'no'));sh.append(r);});
  }
  async function switches(){try{const j=await (await fetch('/api/yard/settings',{cache:'no-store'})).json();
    [['learning','LEARNING LOG'],['shadow','SHADOW MODE']].forEach(([k,t])=>{const b=$('sw-'+k),s=j[k]||{};b.textContent=t+': '+(s.on?'ON':'OFF');b.title=s.forced_off_by_environment?'Held off by an environment variable on this PC':'Click to switch';b.disabled=!!s.forced_off_by_environment;
      b.onclick=async()=>{b.disabled=true;try{await fetch('/api/yard/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[k]:!s.on})});}finally{await switches();}};});}catch(e){}}
  let timer=0;
  function progress(p){const on=!!(p&&p.running);$('prog').classList.toggle('on',on);$('stop').hidden=!on;$('go').disabled=on;
    if(on){$('phase').textContent=p.phase+' ('+Math.round(100*p.done/Math.max(1,p.total))+' %)';$('fill').style.width=(100*p.done/Math.max(1,p.total))+'%';}return on;}
  async function load(){switches();try{const r=await fetch('/api/yard/status',{cache:'no-store'});const j=await r.json();paint(j);if(progress(j.progress)&&!timer)timer=setInterval(poll,1200);}catch(e){$('msg').textContent='Could not read the yard: '+e.message;}}
  async function poll(){try{const j=await (await fetch('/api/yard/status',{cache:'no-store'})).json();if(!progress(j.progress)){clearInterval(timer);timer=0;paint(j);}}catch(e){}}
  async function status(){try{const j=await (await fetch('/api/learning/status',{cache:'no-store'})).json();
    const k=$('kinds');head(k,['Kind of choice','Recorded','With an exact label','Only a hint']);
    for(const [n,v] of Object.entries(j.per_kind||{})){const r=el('tr');r.append(el('td',null,({route:'what you asked for (routing)',model:'which model did a mission',rung:'how a PC task was done',persona:'which agent got a step (recorded only)',fix:'Doctor fixes you applied or discarded (recorded only)'})[n]||n),el('td',null,v.events),el('td',null,v.labelled),el('td',null,v.weak||0));k.append(r);}
    $('statsub').textContent='Nothing learns from this live yet: it is recorded, and used to decide when a learner is ready.';
    const nd=$('needs');head(nd,['Step','Needs','Have','Want','Ready?']);
    for(const [n,v] of Object.entries(j.needs||{})){const r=el('tr');r.append(el('td',null,n),el('td','mute',v.needs),el('td',null,v.have),el('td',null,v.want),el('td',v.ready?'yes':'mute',v.ready?'yes':'not yet'));nd.append(r);}
    try{const y=await (await fetch('/api/yard/status',{cache:'no-store'})).json();const vt=$('versions');head(vt,['Version','When','Episodes','Known words','Unseen words','Used by shadow?']);
      (y.versions||[]).slice().reverse().forEach(v=>{const r=el('tr');r.append(el('td',null,'v'+v.n),el('td',null,new Date(v.at*1000).toLocaleString()),el('td',null,v.episodes),el('td',null,pct(v.known)),el('td',null,pct(v.held)),el('td',y.in_use_version===v.n?'yes':'mute',y.in_use_version===v.n?'in use':(v.in_use_ever?'was':'kept, not better')));vt.append(r);});
      if(!(y.versions||[]).length){const r=el('tr'),d=el('td','mute','No session finished yet.');d.colSpan=6;r.append(d);vt.append(r);}}catch(e){}
    const b=$('bandits');head(b,['Choice','Decisions','Had an opinion','Agreed with what was chosen','Differed']);
    for(const [n,v] of Object.entries(j.bandits||{})){const r=el('tr');r.append(el('td',null,n),el('td',null,v.decided),el('td',null,v.had_an_opinion),el('td',null,v.agreed),el('td',null,v.differed));b.append(r);}
  }catch(e){}}
  async function overview(){
    let a={},y={},t={left:0};
    try{a=await (await fetch('/api/learning/status',{cache:'no-store'})).json();}catch(e){}
    try{y=await (await fetch('/api/yard/status',{cache:'no-store'})).json();}catch(e){}
    const k=a.per_kind||{},route=k.route||{events:0,labelled:0},nR=Object.values(k).reduce((n,v)=>n+(v.events||0),0),vers=(y.versions||[]).length,sh=y.shadow||{};
    const steps=[
      ['1','RECORD','The Hub writes down each choice and how it turned out.','<b>'+nR+'</b> choices recorded',nR>0],
      ['2','TEACH','You mark what was right or wrong.','<b>'+route.labelled+'</b> of '+route.events+' requests marked',route.labelled>=100],
      ['3','PRACTISE','A learner tries thousands of times in pretend apps.',vers?('<b>'+vers+'</b> saved, version '+(y.in_use_version||'?')+' in use'):'no session yet',vers>0],
      ['4','WATCH','It watches the live Hub and notes what it would have done.',sh.steps?('<b>'+sh.steps+'</b> choices watched'):(sh.policy?'ready, nothing watched yet':'waiting for a session'),sh.steps>0],
      ['5','USE','Only with your yes, and only if it beats the current way.','not yet: never without you',false]];
    const f=$('flow');f.replaceChildren();let marked=false;
    steps.forEach(([n,t,d,v,done])=>{const s=el('div','step'+(!done&&!marked?' now':'')+(done?'':' wait'));if(!done)marked=true;s.append(el('div','n','STEP '+n),el('div','t',t),el('div','d',d));const vv=el('div','v');vv.innerHTML=v;s.append(vv);f.append(s);});
    const nx=$('next');nx.replaceChildren();const todo=[];
    if(route.events-route.labelled>0)todo.push(['TEACH','Mark '+(route.events-route.labelled)+' past requests as right or wrong. This is the most useful thing you can do.','teach']);
    if(!vers)todo.push(['YARD','Start one practice session (about a minute) so the learner exists.','practice']);
    else if(!sh.steps)todo.push(['USE TALK','Ask the Hub to do something inside an app; the learner will watch and note what it would have pressed.',null]);
    todo.push(['MISSIONS','Mark your latest missions good or bad in TEACH > MISSIONS.','teach']);
    todo.forEach(([b,t,go])=>{const r=el('div','a');r.append(el('span',null,t));if(go){const g=el('button',null,b);g.onclick=()=>tab(go);r.append(g);}else r.append(el('span','chip',b));nx.append(r);});
  }
  async function routines(){
    const box=$('rlist');box.replaceChildren();let rows=[];
    try{rows=(await (await fetch('/api/pc/routines',{cache:'no-store'})).json()).routines||[];}catch(e){box.textContent='Could not read the routines: '+e.message;return;}
    if(!rows.length){box.append(el('div','card','No routines yet.'));return;}
    rows.forEach(r=>{const c=el('div','card');c.append(el('div','said',r.title));
      const m=el('div','mute');m.append(el('span','chip '+(r.status==='trusted'?'ok':r.status==='disabled'?'no':'part'),r.status.toUpperCase()),el('span','chip',r.successes+' good · '+r.failures+' bad'),el('span','chip',r.kind||''));c.append(m);
      const st=el('div','mute','');c.append(st);
      const row=el('div','row'),see=el('button','skip','SHOW STEPS'),ok=el('button',null,'APPROVE'),off=el('button','part',r.status==='disabled'?'RE-ENABLE':'DISABLE'),del=el('button','no','DELETE');
      see.onclick=async()=>{try{const j=await (await fetch('/api/pc/routines/'+r.id+'/steps')).json();st.textContent=(j.steps.length?j.steps.map(s=>(s.ordinal+1)+'. '+s.tool+' '+((s.target&&s.target.name)||'')).join('  >  '):'no steps (an app launch or an address)');}catch(e){st.textContent=String(e);}};
      ok.onclick=async()=>{await fetch('/api/pc/routines/'+r.id+'/approve',{method:'POST'});routines();};
      off.onclick=async()=>{await fetch('/api/pc/routines/'+r.id+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:r.status==='disabled'?'candidate':'disabled'})});routines();};
      del.onclick=async()=>{if(!confirm('Delete this routine for good? '+r.title))return;await fetch('/api/pc/routines/'+r.id,{method:'DELETE'});routines();};
      ok.hidden=r.status==='trusted';row.append(see,ok,off,del);c.append(row);box.append(c);});
  }
  async function learned(){
    let j;try{j=await (await fetch('/api/learning/learned',{cache:'no-store'})).json();}catch(e){$('lsub').textContent='Could not read it: '+e.message;return;}
    $('lsub').textContent='What your taps have changed, and what they have not.';
    const n=$('lnow');n.replaceChildren();n.append(el('div',null,j.acting_now));
    n.append(el('div','mute',j.route_labelled+' of '+j.route_events+' requests have an exact label; the routing learner wants about '+j.label_goal+'. Speech-to-text misses counted so far: '+j.speech_misses+'.'));
    const f=$('lfix');head(f,['Sentence you corrected','The Hub had chosen','Now it chooses','Times used since']);
    if(!j.corrections.length){const r=el('tr'),d=el('td','mute','None yet. In TEACH, tap WRONG, pick what it should have been and SAVE.');d.colSpan=4;r.append(d);f.append(r);}
    j.corrections.forEach(c=>{const r=el('tr');r.append(el('td',null,c.text),el('td','mute',c.was||'?'),el('td','bin',c.now),el('td',null,c.used));f.append(r);});
    const g=$('lgrades');head(g,['What','Count']);
    const rows=Object.entries(j.summary.grades||{}).map(([k,v])=>[k,v]).concat(Object.entries(j.summary.causes||{}).map(([k,v])=>['why: '+(j.summary.cause_help[k]||k),v]));
    if(!rows.length){const r=el('tr'),d=el('td','mute','Nothing graded yet.');d.colSpan=2;r.append(d);g.append(r);}
    rows.forEach(([k,v])=>{const r=el('tr');r.append(el('td',null,k),el('td',null,v));g.append(r);});
    const nn=$('lnot');nn.replaceChildren();j.not_yet.forEach(t=>nn.append(el('div','mute','• '+t)));
  }
  function tab(name){document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===name));
    for(const n of ['overview','practice','teach','learned','routines','status'])$('tab-'+n).hidden=n!==name;
    if(name==='overview')overview();
    if(name==='teach'){const f=$('teachframe');if(!f.src)f.src=f.dataset.src;}if(name==='status')status();if(name==='learned')learned();if(name==='routines')routines();try{localStorage.setItem('hub-rl-tab',name);}catch(e){}}
  document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
  document.querySelectorAll('button.i').forEach(b=>b.onclick=()=>{const x=document.getElementById(b.dataset.info);x.hidden=!x.hidden;});
  $('stop').onclick=async()=>{$('stop').disabled=true;$('msg').textContent='Stopping...';try{await fetch('/api/yard/practice/stop',{method:'POST'});}catch(e){}};
  $('go').onclick=async()=>{const b=$('go');b.disabled=true;$('msg').textContent='Running a session: about a minute of one processor core. STOP ends it at once.';$('stop').hidden=false;$('stop').disabled=false;
    if(!timer)timer=setInterval(poll,1200);
    try{const r=await fetch('/api/yard/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,episodes:1500})});
      if(!r.ok)throw Error(await r.text()||('error '+r.status));const j=await r.json();$('msg').textContent=j.stopped?'Stopped. Nothing was saved; the last finished report is still shown.':'Done.';await load();}
    catch(e){$('msg').textContent=String(e.message||e);}finally{b.disabled=false;$('stop').hidden=true;$('prog').classList.remove('on');}};
  let first='overview';try{first=localStorage.getItem('hub-rl-tab')||'overview';}catch(e){}
  load();tab(first);
})();
</script></body></html>
"""


@routes.get("/yard")
async def yard_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
