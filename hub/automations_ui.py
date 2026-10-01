"""The /automations page: what the Hub does on its own, and what is waiting for you.

Built around the two things a person actually comes here to do - answer a run that
is waiting at a gate, and run one by hand to see whether it works before letting a
trigger fire it unattended. Everything else is secondary and sits below them.

Steps are built from the Hub's generated capability list rather than a text box,
so a hub step cannot name an endpoint that does not exist, and the editor can say
which ones will wait for you before you save rather than after.
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AGENT HUB — Automations</title>
<link rel="icon" href="/favicon.png">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;700&family=Outfit:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#070a25;--panel:#0d1247;--bg-mid:#0a0e38;--ink:#e8fff1;--text-muted:#a8cbb9;
 --text-faint:#6f8f80;--accent:#00e676;--amber:#e0a53c;--red:#ff6b6b;
 --border-dim:rgba(0,230,118,.18);--border-bright:rgba(0,230,118,.45)}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#070a25,#10124e);
 color:var(--ink);font-family:Outfit,system-ui,sans-serif;line-height:1.5}
a{color:inherit;text-decoration:none}
.bar{height:56px;display:flex;align-items:center;gap:10px;padding:0 16px;
 border-bottom:1px solid var(--border-dim);background:rgba(7,10,37,.9);position:sticky;top:0;z-index:5}
.brand{font:700 13px Orbitron,monospace;letter-spacing:2px;color:var(--accent)}
.btn{font:600 11px Orbitron,monospace;letter-spacing:1px;color:var(--ink);background:transparent;
 border:1px solid var(--border-dim);border-radius:7px;padding:7px 12px;cursor:pointer}
.btn:hover{border-color:var(--border-bright)}
.btn.go{color:var(--accent);border-color:var(--border-bright)}
.btn.stop{color:var(--red);border-color:rgba(255,107,107,.45)}
.btn:disabled{opacity:.45;cursor:default}
main{max-width:980px;margin:auto;padding:18px 16px 90px}
h2{font:700 11px Orbitron,monospace;letter-spacing:2px;color:var(--text-muted);margin:22px 0 9px}
.card{background:var(--panel);border:1px solid var(--border-dim);border-radius:11px;padding:13px;margin-bottom:11px}
.card.wait{border-color:var(--amber);background:rgba(224,165,60,.07)}
.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.name{font-weight:600}
.chip{font-size:10.5px;border:1px solid var(--border-dim);border-radius:999px;padding:2px 9px;color:var(--text-muted)}
.chip.ok{color:var(--accent);border-color:var(--border-bright)}
.chip.warn{color:var(--amber);border-color:var(--amber)}
.chip.bad{color:var(--red);border-color:var(--red)}
.lp{font-size:12.5px;color:var(--text-muted);margin:7px 0 0}
.steps{margin-top:9px;border-top:1px solid var(--border-dim);padding-top:8px}
.step{display:flex;gap:9px;align-items:baseline;font-size:12.5px;padding:3px 0}
.step .k{font:600 10px Orbitron,monospace;letter-spacing:1px;color:var(--text-faint);min-width:62px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--text-faint);flex:0 0 auto}
.dot.done{background:var(--accent)}.dot.failed{background:var(--red)}
.dot.awaiting_approval{background:var(--amber)}.dot.running{background:var(--accent);animation:p 1.1s infinite}
@keyframes p{50%{opacity:.35}}
input,select,textarea{background:var(--bg-mid);border:1px solid var(--border-dim);color:var(--ink);
 border-radius:7px;padding:8px 10px;font:14px Outfit,sans-serif;width:100%}
textarea{min-height:62px;resize:vertical}
.grid{display:grid;grid-template-columns:120px 1fr;gap:8px;align-items:center;margin-top:8px}
.empty{color:var(--text-faint);font-size:13px}
@media(max-width:720px){.grid{grid-template-columns:1fr}}
</style><link rel="stylesheet" href="/theme.css">
</head><body>
<div class="bar"><a class="btn" href="/">HUB</a><span class="brand">AUTOMATIONS</span>
 <span style="flex:1"></span><a class="btn" href="/missions">MISSIONS</a>
 <button class="btn go" id="new">NEW</button></div>
<main id="main"><div class="empty">loading…</div></main>
<script>
const $=i=>document.getElementById(i);
const esc=s=>(s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const jget=async u=>{const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw new Error(await r.text());return r.json()};
const jsend=async(m,u,b)=>{const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  const t=await r.text();if(!r.ok)throw new Error(t);try{return JSON.parse(t)}catch(e){return {}}};
let D=null, CAPS=[], EDIT=null;

const when=a=>{const t=a.trigger||{};
  if(t.kind==='manual')return 'when you run it';
  if(t.kind==='schedule')return `every ${esc(t.every)} at ${esc(t.at||'09:00')}`;
  return `when ${esc(t.event)}`};

function stepLine(s,rs){
  const st=rs?rs.status:'pending';
  const what=s.kind==='hub'?`${esc(s.method||'GET')} ${esc(s.path)}`
           :s.kind==='mission'?`${esc(s.project)} — ${esc((s.brief||'').slice(0,70))}`
           :esc(s.routine);
  return `<div class="step"><span class="dot ${st}"></span><span class="k">${esc(s.kind)}</span>`
   +`<span>${what}${s.gate?' <span class="chip warn">WAITS FOR YOU</span>':''}</span>`
   +(rs&&rs.note?`<span class="lp" style="margin:0 0 0 auto">${esc(rs.note)}</span>`:'')+`</div>`;
}

function runCard(r){
  const a=(D.automations||[]).find(x=>x.id===r.automation);
  return `<div class="card wait"><div class="row"><b class="name">${esc(r.name)}</b>
    <span class="chip warn">WAITING FOR YOU</span><span class="chip">${esc(r.why||'')}</span>
    <span style="flex:1"></span>
    <button class="btn go" data-ok="${r.id}">APPROVE</button>
    <button class="btn stop" data-no="${r.id}">DECLINE</button></div>
    <div class="lp">This run stopped before a step that is hard to take back. Approving runs that step and carries on.</div>
    <div class="steps">${(r.steps||[]).map(rs=>{
      const s=((a&&a.steps)||[]).find(x=>x.id===rs.id)||{kind:rs.kind};return stepLine(s,rs)}).join('')}</div></div>`;
}

function autoCard(a){
  const last=a.last_run;
  const chip=!last?'<span class="chip">never run</span>'
    :last.status==='done'?'<span class="chip ok">last run ok</span>'
    :last.status==='awaiting_approval'?'<span class="chip warn">waiting</span>'
    :`<span class="chip bad">last run ${esc(last.status)}</span>`;
  return `<div class="card"><div class="row"><b class="name">${esc(a.name)}</b>
    <span class="chip">${when(a)}</span>${chip}
    ${a.enabled?'':'<span class="chip">off</span>'}
    <span style="flex:1"></span>
    <button class="btn" data-run="${a.id}">RUN NOW</button>
    <button class="btn" data-edit="${a.id}">EDIT</button>
    <button class="btn stop" data-del="${a.id}">DELETE</button></div>
    <div class="steps">${(a.steps||[]).map(s=>stepLine(s,(last&&(last.steps||[]).find(x=>x.id===s.id)))).join('')}</div></div>`;
}

function editor(){
  const a=EDIT;
  const t=a.trigger||{kind:'manual'};
  const opt=(v,cur,l)=>`<option value="${v}"${v===cur?' selected':''}>${esc(l||v)}</option>`;
  const evs=Object.entries(D.events||{}).map(([k,v])=>opt(k,t.event,`${k} — ${v}`)).join('');
  return `<div class="card"><div class="row"><b class="name">${a.id?'Edit':'New'} automation</b>
   <span style="flex:1"></span><button class="btn" id="cancel">CANCEL</button>
   <button class="btn go" id="save">SAVE</button></div>
  <div class="grid">
   <label>Name</label><input id="f-name" value="${esc(a.name||'')}" placeholder="what it does, in your words">
   <label>Runs</label><select id="f-trig">${opt('manual',t.kind,'when I run it')}${opt('schedule',t.kind,'on a schedule')}${opt('event',t.kind,'when something happens')}</select>
   ${t.kind==='schedule'?`<label>Every</label><select id="f-every">${opt('daily',t.every)}${opt('weekly',t.every)}${opt('monthly',t.every)}</select>
     <label>At</label><input id="f-at" value="${esc(t.at||'09:00')}" placeholder="09:00">`:''}
   ${t.kind==='event'?`<label>Event</label><select id="f-event">${evs}</select>`:''}
  </div>
  <div class="steps"><div class="lp" style="margin-bottom:6px">Steps run in order. A step marked
   <b>waits for you</b> stops the run and asks before it acts.</div>
   ${(a.steps||[]).map((s,i)=>`<div class="row" style="margin-bottom:6px">
     <span class="k" style="min-width:58px">${i+1}.</span>
     <select data-sk="${i}" style="width:110px">${['hub','mission','routine'].map(k=>opt(k,s.kind)).join('')}</select>
     ${s.kind==='hub'?`<select data-sp="${i}" style="flex:1">${CAPS.map(c=>
         `<option value="${c.method} ${c.path}"${(s.method+' '+s.path)===(c.method+' '+c.path)?' selected':''}>${c.method} ${c.path}${c.consequential?' — waits for you':''}</option>`).join('')}</select>`
      :s.kind==='mission'?`<input data-spr="${i}" style="width:150px" placeholder="project slug" value="${esc(s.project||'')}">
         <input data-sb="${i}" style="flex:1" placeholder="what the agent should do" value="${esc(s.brief||'')}">`
      :`<input data-srt="${i}" style="flex:1" placeholder="recorded routine id" value="${esc(s.routine||'')}">`}
     <label class="lp" style="margin:0"><input type="checkbox" data-sg="${i}" ${s.gate?'checked':''} style="width:auto"> waits</label>
     <button class="btn stop" data-srm="${i}">×</button></div>`).join('')}
   <button class="btn" id="addstep">ADD STEP</button></div>
  <div class="lp" id="err" style="color:var(--red)"></div></div>`;
}

function render(){
  let h='';
  if(EDIT) h+=editor();
  const waiting=(D.waiting||[]);
  if(waiting.length){h+='<h2>WAITING FOR YOU</h2>'+waiting.map(runCard).join('')}
  h+='<h2>AUTOMATIONS</h2>';
  h+=(D.automations||[]).length?(D.automations||[]).map(autoCard).join('')
    :'<div class="card empty">Nothing yet. NEW builds one — steps in order, and any step that publishes, merges or deletes can be set to wait for you.</div>';
  const ev=(D.recent_events||[]);
  if(ev.length){h+='<h2>RECENT EVENTS</h2><div class="card">'+ev.map(e=>
    `<div class="step"><span class="k">${esc(e.kind)}</span><span class="lp" style="margin:0">${esc(JSON.stringify(e.payload).slice(0,110))}</span></div>`).join('')+'</div>'}
  $('main').innerHTML=h;
  wire();
}

function wire(){
  document.querySelectorAll('[data-run]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;b.textContent='RUNNING…';
    try{await jsend('POST',`/api/automations/${b.dataset.run}/run`)}catch(e){alert(e.message)}
    await load()});
  document.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{
    if(!confirm('Delete this automation? Its run history stays.'))return;
    await jsend('DELETE',`/api/automations/${b.dataset.del}`);await load()});
  document.querySelectorAll('[data-ok]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;try{await jsend('POST',`/api/automations/runs/${b.dataset.ok}/approve`,{ok:true})}
    catch(e){alert(e.message)}await load()});
  document.querySelectorAll('[data-no]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;try{await jsend('POST',`/api/automations/runs/${b.dataset.no}/approve`,{ok:false})}
    catch(e){alert(e.message)}await load()});
  document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{
    EDIT=JSON.parse(JSON.stringify((D.automations||[]).find(a=>a.id===b.dataset.edit)));render();
    window.scrollTo({top:0})});
  const c=$('cancel'); if(c)c.onclick=()=>{EDIT=null;render()};
  const add=$('addstep'); if(add)add.onclick=()=>{collect();EDIT.steps.push({kind:'hub',
    method:(CAPS[0]||{}).method||'GET',path:(CAPS[0]||{}).path||'/api/status'});render()};
  document.querySelectorAll('[data-srm]').forEach(b=>b.onclick=()=>{
    collect();EDIT.steps.splice(+b.dataset.srm,1);render()});
  document.querySelectorAll('[data-sk]').forEach(s=>s.onchange=()=>{
    collect();EDIT.steps[+s.dataset.sk]={kind:s.value,gate:false};render()});
  document.querySelectorAll('[data-sp]').forEach(s=>s.onchange=()=>{
    // Re-render so choosing something consequential ticks "waits" for you.
    collect();const st=EDIT.steps[+s.dataset.sp];
    const cap=CAPS.find(c=>c.method+' '+c.path===s.value);
    if(cap&&cap.consequential)st.gate=true;render()});
  const t=$('f-trig'); if(t)t.onchange=()=>{collect();EDIT.trigger={kind:t.value};render()};
  const sv=$('save'); if(sv)sv.onclick=async()=>{
    collect();
    try{await jsend('POST','/api/automations',EDIT);EDIT=null;await load()}
    catch(e){$('err').textContent=e.message}};
}

function collect(){
  if(!EDIT)return;
  const v=i=>{const e=$(i);return e?e.value:undefined};
  EDIT.name=v('f-name')??EDIT.name;
  const k=v('f-trig')||EDIT.trigger.kind;
  EDIT.trigger={kind:k};
  if(k==='schedule'){EDIT.trigger.every=v('f-every')||'daily';EDIT.trigger.at=v('f-at')||'09:00'}
  if(k==='event'){EDIT.trigger.event=v('f-event')||Object.keys(D.events||{})[0]}
  (EDIT.steps||[]).forEach((s,i)=>{
    const sel=document.querySelector(`[data-sp="${i}"]`);
    if(s.kind==='hub'&&sel){const[m,...p]=sel.value.split(' ');s.method=m;s.path=p.join(' ')}
    const pr=document.querySelector(`[data-spr="${i}"]`),br=document.querySelector(`[data-sb="${i}"]`);
    if(pr)s.project=pr.value; if(br)s.brief=br.value;
    const rt=document.querySelector(`[data-srt="${i}"]`); if(rt)s.routine=rt.value;
    const g=document.querySelector(`[data-sg="${i}"]`); if(g)s.gate=g.checked;
  });
}

async function load(){
  D=await jget('/api/automations');
  try{CAPS=(await jget('/api/capabilities')).endpoints||[]}catch(e){CAPS=[]}
  render();
}
$('new').onclick=()=>{EDIT={name:'',trigger:{kind:'manual'},steps:[],enabled:true};render();window.scrollTo({top:0})};
load().catch(e=>{$('main').innerHTML='<div class="card" style="color:var(--red)">Could not load: '+esc(e.message)+'</div>'});
setInterval(()=>{if(!EDIT)load().catch(()=>{})},10000);
</script></body></html>"""


@routes.get("/automations")
async def page(request: web.Request) -> web.Response:
    return web.Response(text=PAGE, content_type="text/html")
