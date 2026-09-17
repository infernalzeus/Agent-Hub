"""The mission board — dispatch and review distributed autonomous agent runs.

A real page (not an overlay): one top bar, its own `← HUB`. Reads
hub/features/missions.py:
  GET  /api/projects
  GET  /api/missions                 board
  POST /api/missions                 {project, brief, kind, agent?, model?}
  GET  /api/missions/{id}            detail + events + children
  GET  /api/missions/{id}/events     SSE
  GET  /api/missions/{id}/diff[?path]
  POST /api/missions/{id}/{abort,apply,discard,retry,continue,dispatch,transcript}
  POST /api/missions/plan/{id}/dispatch-all
  GET  /api/agents                   personas for the New-Mission agent picker
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#080c28">
<title>AGENT HUB — Missions</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c28;--bg-mid:#0d1050;--panel:rgba(8,12,40,0.88);
  --border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);
  --red:#ff5c5c;--amber:#e0a53c;--blue:#3ba7ff;--purple:#b07cd6;
}
html{min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
html,body{height:100%;font-family:'Outfit',system-ui,sans-serif;color:var(--text)}
body{display:flex;flex-direction:column;overflow:hidden}
a{color:var(--accent);text-decoration:none}
button,input,select,textarea{font-family:'Outfit',inherit}
.bar{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--border-dim);flex:0 0 auto;flex-wrap:wrap}
.brand{font-family:'Orbitron',monospace;font-weight:900;letter-spacing:3px;font-size:13px;color:var(--accent);text-shadow:0 0 16px rgba(0,230,118,.35)}
.spacer{flex:1}
.btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1px;padding:9px 12px;min-height:36px;border-radius:6px;
  display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;white-space:nowrap;transition:all .15s;-webkit-tap-highlight-color:transparent}
.btn:hover:not(:disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn.stop{border-color:rgba(255,92,92,.5);color:var(--red)}
.btn.stop:hover:not(:disabled){background:rgba(255,92,92,.1)}
.btn.go{border-color:var(--accent);background:rgba(0,230,118,.12)}
.body{flex:1;display:flex;min-height:0}
.list{width:340px;flex:0 0 auto;border-right:1px solid var(--border-dim);overflow-y:auto;background:var(--panel);padding:8px}
.ck{min-height:32px}
.ck input{width:auto;min-width:20px;min-height:20px}
@media (max-width:720px){
  body{overflow:auto}
  .body{flex-direction:column}
  .list{width:100%;max-height:38vh;border-right:none;border-bottom:1px solid var(--border-dim)}
  .detail{min-height:60vh}
  .bar{gap:8px}
  .bar .btn{flex:1 1 auto;min-width:calc(50% - 8px)}
  .bar .brand{flex-basis:100%}
}
.grp{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1.5px;color:var(--text-faint);margin:12px 6px 5px}
.card{border:1px solid transparent;border-radius:9px;padding:10px 11px;cursor:pointer;margin-bottom:5px}
.card:hover{border-color:var(--border-dim)}
.card.sel{border-color:var(--border-bright);background:rgba(0,230,118,.06)}
.card.child{margin-left:18px}
.card .top{display:flex;align-items:center;gap:8px}
.card .ag{font-weight:600;font-size:12.5px}
.card .br{font-size:11.5px;color:var(--text-muted);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .mt{font-size:10px;color:var(--text-faint);margin-top:4px;display:flex;gap:10px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--text-faint);flex:0 0 auto}
.dot.running{background:var(--amber);box-shadow:0 0 8px var(--amber);animation:pulse 1.1s infinite}
.dot.awaiting_review{background:var(--accent);box-shadow:0 0 8px var(--accent)}
.dot.applied{background:#3aa0ff}
.dot.failed,.dot.timed_out{background:var(--red);box-shadow:0 0 8px var(--red)}
.dot.discarded{background:#555}
.dot.proposed{background:var(--purple);box-shadow:0 0 8px var(--purple)}
.dot.blocked{background:var(--text-faint);border:2px solid var(--amber)}
.dot.orphaned{background:#555;border:2px solid var(--purple)}
@keyframes pulse{50%{opacity:.35}}
.detail{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.dhead{padding:12px 16px;border-bottom:1px solid var(--border-dim);flex:0 0 auto}
.dhead h1{font-size:15px;font-weight:600}
.dhead .sub{font-size:11px;color:var(--text-muted);margin-top:3px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.dscroll{flex:1;overflow-y:auto;padding:16px}
h2{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--text-faint);margin:18px 0 8px}
h2:first-child{margin-top:0}
.files li{font-size:12px;font-family:ui-monospace,Consolas,monospace;padding:5px 8px;border-radius:5px;cursor:pointer;list-style:none}
.files li:hover{background:rgba(0,230,118,.06)}
.badge{display:inline-block;width:16px;text-align:center;color:var(--amber);margin-right:6px}
pre{background:var(--bg);border:1px solid var(--border-dim);border-radius:8px;padding:12px;overflow:auto;
  font-size:11.5px;line-height:1.45;white-space:pre;max-height:44vh}
.diff-add{color:#5dd88a}.diff-del{color:#ff8080}
.feed{background:var(--bg);border:1px solid var(--border-dim);border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;
  font-size:11px;line-height:1.5;max-height:40vh;overflow-y:auto}
.feed .tool{color:var(--blue)}.feed .text{color:var(--text)}.feed .err{color:var(--red)}.feed .step,.feed .reasoning{color:var(--text-faint)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
label{display:block;font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1px;color:var(--text-faint);margin:14px 0 5px}
input[type=text],select,textarea{width:100%;background:var(--bg);border:1px solid var(--border-dim);color:var(--text);
  border-radius:6px;padding:9px 10px;font-size:13px;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
textarea{min-height:120px;resize:vertical}
.hollow{flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:13px}
.note{font-size:11px;color:var(--amber);margin-top:6px}
.pill{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:.5px;padding:2px 7px;border-radius:999px;border:1px solid var(--border-dim);color:var(--text-muted)}
.cklist{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:4px;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:9px 10px}
.ck{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text);margin:0}
.ck input{width:auto}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:4px 8px;margin:3px 4px 0 0;font-size:12px}
.chip button{background:transparent;border:1px solid var(--border-dim);color:var(--text-muted);border-radius:4px;cursor:pointer;font-size:11px;padding:0 5px;line-height:1.6}
.chip button:disabled{opacity:.3;cursor:default}
.btn.sel{border-color:var(--accent);background:rgba(0,230,118,.14);color:var(--accent)}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%) translateY(10px);z-index:99;max-width:min(460px,92vw);
  padding:11px 15px;border-radius:9px;font-size:12px;background:var(--panel);border:1px solid var(--border-bright);
  color:var(--text);box-shadow:0 8px 28px rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:opacity .2s,transform .2s}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast.err{border-color:rgba(255,92,92,.6);color:#ffb3b3}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;z-index:30}
.scrim.open{display:block}
.modal{position:fixed;top:6vh;left:50%;transform:translateX(-50%);width:600px;max-width:94vw;max-height:86vh;overflow-y:auto;
  background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:12px;padding:18px 20px;z-index:31;display:none}
.modal.open{display:block}
.modal h2{font-family:'Orbitron',monospace;font-size:12px;letter-spacing:1.5px;color:var(--accent);margin-bottom:14px}
.flow{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;line-height:1.5}
.flow .st{color:var(--accent);font-weight:700}
.flow .arrow{color:var(--text-faint);text-align:center;margin:1px 0}
.flow .d{color:var(--text-muted);margin:0 0 8px 0}
.flow .you{color:var(--amber);font-weight:700}
.arch-facts{margin-top:16px;border-top:1px solid var(--border-dim);padding-top:12px}
.arch-facts dt{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1px;color:var(--blue);margin-top:10px}
.arch-facts dd{margin:3px 0 0;font-size:12.5px;color:var(--text-muted);line-height:1.5}
</style></head>
<body>
<div id="toast"></div>
<div class="bar">
  <a class="btn" href="/">← HUB</a>
  <span class="brand">MISSIONS</span>
  <button class="btn go" id="btn-new">＋ NEW MISSION</button>
  <span class="spacer"></span>
  <a class="btn" href="/agents">AGENTS</a>
  <a class="btn" href="/graph">GRAPH</a>
  <button class="btn" id="btn-arch">ⓘ HOW THIS WORKS</button>
  <button class="btn" id="btn-reload">↻</button>
</div>
<div class="body">
  <div class="list" id="list"></div>
  <div class="detail" id="detail">
    <div class="hollow" id="hollow">Select a mission, or ＋ NEW MISSION.</div>
    <div id="pane" style="display:none;flex:1;display:none;flex-direction:column;min-height:0"></div>
  </div>
</div>
<div class="scrim" id="arch-scrim"></div>
<div class="modal" id="arch-modal">
  <h2>ONE MISSION, START TO FINISH</h2>
  <div class="flow">
    <div class="d">project + brief + agent/orchestrator + runtime + model</div>
    <div class="st">DISPATCH</div>
    <div class="arrow">↓</div>
    <div class="st">WORKTREE</div>
    <div class="d">git worktree, branch agent/&lt;project&gt;--&lt;id&gt; — a private copy, nothing shared</div>
    <div class="arrow">↓</div>
    <div class="st">PREPARE</div>
    <div class="d">persona written in (.opencode/agent/ or .claude/agents/); model resolved</div>
    <div class="arrow">↓</div>
    <div class="st">RUN</div>
    <div class="d">one subprocess — <code>opencode run</code> or <code>claude -p</code> — same worktree either way</div>
    <div class="arrow">↓</div>
    <div class="st">EVENTS</div>
    <div class="d">streamed live into the feed on the right; teed to mission.jsonl on disk</div>
    <div class="arrow">↓</div>
    <div class="st">FINALIZE</div>
    <div class="d">git diff vs. base branch → awaiting_review</div>
    <div class="arrow">↓</div>
    <div class="st you">YOU — APPLY or DISCARD</div>
    <div class="d">merge into the real project, or delete the worktree. Nothing touches the project before this.</div>
  </div>
  <dl class="arch-facts">
    <dt>RUNTIME</dt>
    <dd>OpenCode or Claude Code, picked per mission. Same worktree/diff/apply either way — only the process that actually runs differs.</dd>
    <dt>MODEL</dt>
    <dd>Policy picks the starting model (auto / free-cloud / local / a pinned id). OpenCode retries a free-tier hiccup down a fallback chain; Claude just retries the same call — no cross-provider chain.</dd>
    <dt>AGENTS</dt>
    <dd><code>team.json</code> is the roster. An orchestrator mission only <b>proposes</b> which agent runs each sub-task — every proposed child still needs your DISPATCH. Nothing runs without a click.</dd>
  </dl>
  <div class="row" style="margin-top:16px"><button class="btn" id="btn-arch-close">close</button></div>
</div>
<script>
const qs = new URLSearchParams(location.search);
let SEL = null, MISSIONS = [], PROJECTS = [], AGENTS = [], MODELS = [], poll = null, es = null;
const $ = (id) => document.getElementById(id);
const esc = (s) => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ago = (t) => { if(!t) return ''; const s=(Date.now()-t*1000)/1000; if(s<60)return Math.round(s)+'s'; if(s<3600)return Math.round(s/60)+'m'; return Math.round(s/3600)+'h'; };
let _tT=null;
function toast(m,k){ const e=$('toast'); if(!e)return; e.textContent=m; e.classList.toggle('err',k==='err'); e.classList.add('show');
  clearTimeout(_tT); _tT=setTimeout(()=>e.classList.remove('show'),4200); }
async function jget(u){ const r=await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(u,b){ const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){j={raw:t}} if(!r.ok) throw new Error(j.raw||t); return j; }

async function boot(){
  try { PROJECTS = (await jget('/api/projects')).projects || []; } catch(e){}
  try { const a = await jget('/api/agents'); AGENTS = a.personas || []; MODELS = a.models || []; } catch(e){}
  await refresh();
  poll = setInterval(refresh, 2500);
  if (qs.get('project')) newMission(qs.get('project'));
}
async function refresh(){
  try { MISSIONS = (await jget('/api/missions')).missions || []; } catch(e){ return; }
  renderList();
  if (SEL && MISSIONS.some(m=>m.id===SEL)) renderDetail(SEL);
}
function renderList(){
  const byProj = {};
  MISSIONS.forEach(m => (byProj[m.project_name] = byProj[m.project_name]||[]).push(m));
  let html = '';
  for (const proj of Object.keys(byProj)){
    html += `<div class="grp">${esc(proj).toUpperCase()}</div>`;
    const roots = byProj[proj].filter(m=>!m.parent_id || !byProj[proj].some(x=>x.id===m.parent_id));
    const kids = (pid) => byProj[proj].filter(m=>m.parent_id===pid);
    for (const m of roots){ html += card(m,false); for (const k of kids(m.id)) html += card(k,true); }
  }
  $('list').innerHTML = html || '<div class="grp">no missions yet</div>';
  document.querySelectorAll('#list .card').forEach(el => el.onclick = () => select(el.dataset.id));
}
function card(m,child){
  const aglabel = (m.kind==='team' && (m.agents||[]).length) ? m.agents.join(' → ') : m.agent;
  return `<div class="card ${child?'child':''} ${m.id===SEL?'sel':''}" data-id="${m.id}">
    <div class="top"><span class="dot ${m.status}"></span><span class="ag">${esc(aglabel)}</span>
      <span class="pill">${esc(m.kind)}</span>${m.runtime==='claude-code'?'<span class="pill">claude</span>':''}${m.group_id?'<span class="pill">⇉ draft</span>':''}<span class="spacer"></span>
      <span style="font-size:10px;color:var(--text-faint)">${ago(m.created)}</span></div>
    <div class="br">${esc(m.brief)}</div>
    <div class="mt"><span>${esc(m.status)}</span>${m.changed?`<span>${m.changed} file${m.changed>1?'s':''}</span>`:''}${m.model_note?`<span class="note">⚠ ${esc(m.model_note)}</span>`:''}</div>
  </div>`;
}
function select(id){ SEL=id; renderList(); renderDetail(id); if(es){es.close();es=null;} const m=MISSIONS.find(x=>x.id===id);
  if(m && m.status==='running'){ es=new EventSource('/api/missions/'+id+'/events'); es.onmessage=()=>renderDetail(id); } }

async function renderDetail(id){
  let d; try { d = await jget('/api/missions/'+id); } catch(e){ return; }
  $('hollow').style.display='none'; $('pane').style.display='flex';
  const running = d.status==='running';
  const failed = d.status==='failed' || d.status==='timed_out';
  const fb = (MODELS.find(x=>x.local)||MODELS.find(x=>/ultra/i.test(x.id))||{}).id || '';
  $('pane').innerHTML = `
    <div class="dhead">
      <h1>${esc((d.kind==='team'&&(d.agents||[]).length)?d.agents.join(' → '):d.agent)} · ${esc(d.project_name)}</h1>
      <div class="sub">
        <span class="pill">${esc(d.status)}</span>
        <span>${esc(d.kind)}</span>${d.runtime==='claude-code'?'<span class="pill">claude</span>':''}${d.exit_code!=null?`<span>exit ${d.exit_code}</span>`:''}
        <span>${ago(d.created)} ago</span>
        <button class="btn" onclick="mTranscript('${d.id}')">OPEN TRANSCRIPT</button>
      </div>
    </div>
    <div class="dscroll">
      <h2>Brief</h2><div style="font-size:13px;color:var(--text-muted);white-space:pre-wrap">${esc(d.brief)}</div>
      ${d.error?`<h2>Error</h2><pre style="max-height:16vh;color:#ff9090">${esc(d.error)}</pre>`:''}
      ${d.kind==='orchestrator' && d.children.length ? planBlock(d) : ''}
      <h2>Working copy</h2>
      <div style="font-size:11px;font-family:ui-monospace,Consolas,monospace;color:var(--text-muted);word-break:break-all;-webkit-user-select:all;user-select:all">${esc(d.worktree||'—')}</div>
      <div class="row" style="margin-top:6px">
        <button class="btn" id="m-folder">OPEN FOLDER</button>
        <button class="btn" onclick="navigator.clipboard.writeText('${esc(d.worktree)}')">COPY PATH</button>
        <span style="font-size:10.5px;color:var(--text-faint)">kept until you APPLY or DISCARD</span>
      </div>
      <h2>Result <span style="color:var(--text-muted)">${d.changed} changed file${d.changed===1?'':'s'}</span></h2>
      <ul class="files" id="mfiles"></ul>
      <pre id="mdiff" style="display:none"></pre>
      <div class="row" style="margin-top:10px">
        <button class="btn go" id="m-apply" ${(d.status==='awaiting_review'||d.status==='orphaned')?'':'disabled'}>${d.kind==='ingest-app'?'WIRE IN':'APPLY TO PROJECT'}</button>
        <button class="btn stop" id="m-discard">DISCARD</button>
        ${running?`<button class="btn stop" id="m-abort">ABORT</button>`:''}
        ${failed?`<button class="btn" id="m-retry">RETRY</button>${fb?`<button class="btn" id="m-retryfb">RETRY ON ${esc(fb)}</button>`:''}`:''}
        ${['applied','discarded','failed','timed_out','orphaned'].includes(d.status)?`<button class="btn" id="m-forget">CLEAR</button>`:''}
        ${d.status==='orphaned'?'':`<button class="btn" id="m-continue">CONTINUE…</button>`}
      </div>
      <h2>Activity</h2>
      <div class="feed" id="mfeed">${(d.events||[]).map(feedRow).join('') || '<span style="color:var(--text-faint)">no events yet</span>'}</div>
    </div>`;
  const f = $('mfeed'); if(f) f.scrollTop = f.scrollHeight;
  renderFiles(d);
  $('m-apply') && ($('m-apply').onclick = async () => {
    try {
      const r = await jpost('/api/missions/'+d.id+'/apply',{});
      toast(r.note || (r.ok ? 'Applied — merged into '+d.project_name
                 : ('Not merged: '+(r.run_this||r.reason||'see server log'))), r.ok?'':'err');
    } catch(e){ toast('Apply failed: '+e.message,'err'); }
    refresh(); });
  $('m-folder') && ($('m-folder').onclick = async () => {
    try { const r = await jpost('/api/missions/'+d.id+'/folder',{}); toast('Opened '+r.path); }
    catch(e){ toast('Could not open folder: '+e.message,'err'); } });
  $('m-discard').onclick = async () => { if(!confirm('Stop this mission and delete its working copy? The row stays as history.'))return;
    await jpost('/api/missions/'+d.id+'/discard',{}); refresh(); };
  $('m-forget') && ($('m-forget').onclick = async () => {
    await jpost('/api/missions/'+d.id+'/forget',{}); SEL=null; $('pane').style.display='none'; $('hollow').style.display='flex'; refresh(); });
  $('m-abort') && ($('m-abort').onclick = () => jpost('/api/missions/'+d.id+'/abort',{}).then(refresh));
  $('m-retry') && ($('m-retry').onclick = async () => { const r=await jpost('/api/missions/'+d.id+'/retry',{}); select(r.id); });
  $('m-retryfb') && ($('m-retryfb').onclick = async () => { const r=await jpost('/api/missions/'+d.id+'/retry',{model:fb}); select(r.id); });
  $('m-continue') && ($('m-continue').onclick = async () => { const msg=prompt('Follow-up instruction for this mission:'); if(!msg)return;
    await jpost('/api/missions/'+d.id+'/continue',{message:msg}); refresh(); });
}
function planBlock(d){
  const props = d.children.filter(c=>c.status==='proposed');
  return `<h2>Plan · ${d.children.length} sub-mission${d.children.length===1?'':'s'}</h2>
    <div>${d.children.map(c=>`<div class="card" style="cursor:default"><div class="top"><span class="dot ${c.status}"></span>
      <span class="ag">${esc(c.agent)}</span><span class="pill">${esc(c.project_name)}</span><span class="spacer"></span><span style="font-size:10px">${esc(c.status)}</span></div>
      <div class="br">${esc(c.brief)}</div>
      ${c.status==='proposed'?`<button class="btn" style="margin-top:6px" onclick="jpost('/api/missions/${c.id}/dispatch',{}).then(refresh)">DISPATCH</button>`:''}</div>`).join('')}</div>
    ${props.length?`<button class="btn go" style="margin-top:8px" onclick="jpost('/api/missions/plan/${d.parent_id||d.id}/dispatch-all',{}).then(refresh)">DISPATCH ALL (${props.length})</button>`:''}`;
}
function feedRow(e){ const k=e.k||'step'; const icon={tool:'🔧',text:'💬',err:'✖',step:'▸',reasoning:'…'}[k]||'·';
  return `<div class="${k==='err'?'err':k}">${icon} ${esc(e.text)}</div>`; }
function renderFiles(d){
  const ul=$('mfiles'); if(!ul)return;
  ul.innerHTML = (d.changed_files||[]).length
    ? '' : '<li style="color:var(--text-faint);cursor:default">no changes'+(d.status==='running'?' yet':'')+'</li>';
  (d.changed_files||[]).forEach(f=>{ const li=document.createElement('li');
    li.innerHTML=`<span class="badge">${esc(f.status)}</span>${esc(f.path)}`;
    li.onclick=()=>showDiff(d.id,f.path); ul.appendChild(li); });
}
async function showDiff(id,path){
  const pre=$('mdiff'); pre.style.display='block'; pre.textContent='loading…';
  const t=await (await fetch('/api/missions/'+id+'/diff?path='+encodeURIComponent(path))).text();
  pre.innerHTML=''; t.split('\n').forEach(l=>{ const s=document.createElement('div');
    if(l.startsWith('+')&&!l.startsWith('+++'))s.className='diff-add';
    else if(l.startsWith('-')&&!l.startsWith('---'))s.className='diff-del';
    s.textContent=l; pre.appendChild(s); });
}
window.mTranscript = async (id) => { try{ const r=await jpost('/api/missions/'+id+'/transcript',{});
  window.open(r.root_url, 'oc-'+id); }catch(e){ toast('transcript failed: '+e.message,'err'); } };
window.jpost = jpost; window.refresh = refresh;

// ── new mission ──────────────────────────────────────────────────────────
function newMission(preProject){
  SEL=null; renderList(); $('hollow').style.display='none'; $('pane').style.display='flex';
  const workers = AGENTS.filter(a=>a.name!=='orchestrator');
  const single1 = (workers.find(a=>a.name==='coder')||workers[0]||{}).name || 'coder';
  let TEAM = [single1];                          // ordered relay for team mode
  let PMODE = 'existing';                        // existing | new

  const projSingle = PROJECTS.map(p=>`<option value="${esc(p.slug)}" ${p.slug===preProject||p.name===preProject?'selected':''}>${esc(p.name)}</option>`).join('')
                   || '<option value="">— no projects —</option>';
  const projChecks = PROJECTS.map(p=>`<label class="ck"><input type="checkbox" class="nm-pcheck" value="${esc(p.slug)}" ${p.slug===preProject||p.name===preProject?'checked':''}> ${esc(p.name)}</label>`).join('')
                   || '<span style="color:var(--text-faint)">no projects</span>';
  const agentSel = workers.map(a=>`<option value="${esc(a.name)}" ${a.name===single1?'selected':''}>${esc(a.name)}</option>`).join('');
  const agentChecks = (pref)=>workers.map(a=>`<label class="ck"><input type="checkbox" class="${pref}" value="${esc(a.name)}" ${['coder','reviewer'].includes(a.name)?'checked':''}> ${esc(a.name)}</label>`).join('');
  const wModel = (MODELS.find(m=>m.workspace_default)||{}).id || '';
  const modelOpts = `<option value="">— workspace default${wModel?' ('+esc(wModel)+')':''} —</option>` +
     MODELS.map(m=>`<option value="${esc(m.id)}">${esc(m.id)}${m.local?' · local':(m.free?' · free':'')}</option>`).join('');

  $('pane').innerHTML = `<div class="dhead"><h1>New mission</h1></div>
    <div class="dscroll">
      <label>Project</label>
      <div class="row" style="gap:6px">
        <button type="button" class="btn nm-pm sel" data-pm="existing">EXISTING</button>
        <button type="button" class="btn nm-pm" data-pm="new">＋ NEW PROJECT</button>
      </div>
      <div id="nm-pex" style="margin-top:8px">
        <select id="nm-proj">${projSingle}</select>
        <div id="nm-pmulti" style="display:none" class="cklist">${projChecks}</div>
        <div id="nm-phint" class="note" style="color:var(--text-faint)"></div>
      </div>
      <div id="nm-pnew" style="display:none;margin-top:8px">
        <input type="text" id="nm-newname" placeholder="my-idea — new git repo under _unsorted projects/">
      </div>
      <div class="note" style="color:var(--text-muted);margin-top:8px">The agent works on a private copy. You review the result as a diff and choose APPLY or DISCARD — nothing touches the repo until you APPLY.</div>

      <label>Brief</label>
      <textarea id="nm-brief" placeholder="Exactly what to do. e.g. Add a --dry-run flag to cli.py that prints planned actions without executing; update the README usage block."></textarea>

      <label>Run as</label>
      <div class="row" style="gap:12px;flex-wrap:wrap">
        ${[['single','Single'],['team','Team (relay)'],['parallel','Parallel drafts'],['orchestrator','Orchestrator']].map(([v,t],i)=>
          `<label style="display:flex;gap:6px;align-items:center;margin:0;color:var(--text)"><input type="radio" name="nm-kind" value="${v}" ${i===0?'checked':''} style="width:auto"> ${t}</label>`).join('')}
      </div>

      <div id="nm-m-single"><label>Agent</label><select id="nm-agent">${agentSel}</select></div>

      <div id="nm-m-team" style="display:none">
        <label>Agents in order — each builds on the last, one combined diff</label>
        <div id="nm-teamlist"></div>
        <div class="row" style="margin-top:6px"><select id="nm-teamadd">${agentSel}</select>
          <button type="button" class="btn" id="nm-teamplus">＋ ADD</button></div>
      </div>

      <div id="nm-m-parallel" style="display:none">
        <label>Agents — each runs the same brief on its own copy; keep the best</label>
        <div class="cklist">${agentChecks('nm-pa')}</div>
      </div>

      <div id="nm-m-orch" style="display:none">
        <label>Worker agents the orchestrator may use</label>
        <div class="cklist">${workers.map(a=>`<label class="ck"><input type="checkbox" class="nm-oa" value="${esc(a.name)}" checked> ${esc(a.name)}</label>`).join('')}</div>
        <div class="note" style="color:var(--text-faint)">Select 2+ projects above and the orchestrator assigns each sub-mission to one of them.</div>
      </div>

      <label>Runtime</label>
      <select id="nm-runtime">
        <option value="opencode">OpenCode</option>
        <option value="claude-code">Claude Code</option>
      </select>
      <div id="nm-model-wrap"><label>Model</label><select id="nm-model">${modelOpts}</select></div>
      <div class="note" id="nm-claude-note" style="display:none;color:var(--text-faint)">Same agent/persona, same worktree/diff/APPLY flow — just runs on the claude CLI instead of opencode. Uses claude's own default model unless you pin one below.</div>
      <div class="row" style="margin-top:16px">
        <button class="btn go" id="nm-go">DISPATCH</button>
        <button class="btn" onclick="$('pane').style.display='none';$('hollow').style.display='flex'">cancel</button>
      </div>
    </div>`;

  const kindNow = () => document.querySelector('input[name=nm-kind]:checked').value;
  function renderTeam(){
    $('nm-teamlist').innerHTML = TEAM.map((a,i)=>`<div class="chip">
      <span>${i+1}. ${esc(a)}</span>
      <button type="button" data-i="${i}" data-op="up" ${i===0?'disabled':''}>↑</button>
      <button type="button" data-i="${i}" data-op="dn" ${i===TEAM.length-1?'disabled':''}>↓</button>
      <button type="button" data-i="${i}" data-op="rm">✕</button></div>`).join('') || '<span style="color:var(--text-faint)">add at least one</span>';
    $('nm-teamlist').querySelectorAll('button').forEach(b=>b.onclick=()=>{
      const i=+b.dataset.i, op=b.dataset.op;
      if(op==='rm') TEAM.splice(i,1);
      else if(op==='up'&&i>0){ [TEAM[i-1],TEAM[i]]=[TEAM[i],TEAM[i-1]]; }
      else if(op==='dn'&&i<TEAM.length-1){ [TEAM[i+1],TEAM[i]]=[TEAM[i],TEAM[i+1]]; }
      renderTeam();
    });
  }
  renderTeam();
  $('nm-teamplus').onclick = () => { TEAM.push($('nm-teamadd').value); renderTeam(); };

  function syncMode(){
    const k = kindNow();
    $('nm-m-single').style.display   = k==='single'?'block':'none';
    $('nm-m-team').style.display     = k==='team'?'block':'none';
    $('nm-m-parallel').style.display = k==='parallel'?'block':'none';
    $('nm-m-orch').style.display     = k==='orchestrator'?'block':'none';
    const multi = k==='orchestrator';
    if(PMODE==='existing'){
      $('nm-proj').style.display   = multi?'none':'block';
      $('nm-pmulti').style.display = multi?'flex':'none';
      $('nm-phint').textContent = multi ? 'tick every project the orchestrator may touch' : '';
    }
  }
  document.querySelectorAll('input[name=nm-kind]').forEach(r=>r.onchange=syncMode);
  $('nm-runtime').onchange = () => {
    const isClaude = $('nm-runtime').value === 'claude-code';
    $('nm-model-wrap').style.display = isClaude ? 'none' : 'block';
    $('nm-claude-note').style.display = isClaude ? 'block' : 'none';
  };
  document.querySelectorAll('.nm-pm').forEach(btn=>btn.onclick=()=>{
    PMODE = btn.dataset.pm;
    document.querySelectorAll('.nm-pm').forEach(b=>b.classList.toggle('sel', b===btn));
    $('nm-pex').style.display  = PMODE==='existing'?'block':'none';
    $('nm-pnew').style.display = PMODE==='new'?'block':'none';
    syncMode();
  });
  syncMode();

  $('nm-go').onclick = async () => {
    const k = kindNow();
    const brief = $('nm-brief').value.trim();
    if(!brief){ $('nm-brief').focus(); return; }

    // projects
    let projects = [];
    if(PMODE==='new'){
      const nn = ($('nm-newname').value||'').trim();
      if(!nn){ $('nm-newname').focus(); return; }
      projects = ['new:'+nn];
    } else if(k==='orchestrator'){
      projects = [...document.querySelectorAll('.nm-pcheck:checked')].map(c=>c.value);
      if(!projects.length){ toast('tick at least one project','err'); return; }
    } else {
      projects = [$('nm-proj').value];
    }

    const runtime = $('nm-runtime').value;
    const body = { brief, kind:k, projects, runtime,
      model: (runtime==='claude-code' ? undefined : ($('nm-model').value||undefined)) };
    if(k==='single')      body.agent  = $('nm-agent').value;
    else if(k==='team')   body.agents = TEAM.slice();
    else if(k==='parallel') body.agents = [...document.querySelectorAll('.nm-pa:checked')].map(c=>c.value);
    else if(k==='orchestrator') body.agents = [...document.querySelectorAll('.nm-oa:checked')].map(c=>c.value);
    if((k==='team'||k==='parallel') && !(body.agents||[]).length){ toast('pick at least one agent','err'); return; }

    $('nm-go').disabled=true;
    try {
      const r = await jpost('/api/missions', body);
      await refresh();
      if(r.id) select(r.id);
      else if(r.missions && r.missions[0]) select(r.missions[0].id);
      else { $('pane').style.display='none'; $('hollow').style.display='flex'; }
    } catch(e){ toast('Dispatch failed: '+e.message,'err'); $('nm-go').disabled=false; }
  };
}
$('btn-new').onclick = () => newMission();
$('btn-reload').onclick = () => location.reload();
$('btn-arch').onclick = () => { $('arch-scrim').classList.add('open'); $('arch-modal').classList.add('open'); };
$('btn-arch-close').onclick = $('arch-scrim').onclick = () => { $('arch-scrim').classList.remove('open'); $('arch-modal').classList.remove('open'); };
boot();
</script>
</body></html>
"""


@routes.get("/missions")
async def missions_page(request: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html", charset="utf-8")
