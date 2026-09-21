"""The /setup page: where Agent Hub reads and writes (hub/locations.py), editable any time and shown as the first-run welcome.

Reads / writes through features/locations_api.py. Folder choice uses a server-side picker because a browser cannot give absolute paths.
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#080c28">
<title>AGENT HUB — Locations</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#080c28;--bg-mid:#0d1050;--panel:rgba(8,12,40,0.88);--border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);--red:#ff5c5c;--amber:#e0a53c;--purple:#b07cd6;--ink:#d9ffe9}
html{min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
body{font-family:'Outfit',system-ui,sans-serif;color:var(--text);padding-bottom:90px}
.bar{display:flex;align-items:center;gap:10px;padding:calc(9px + env(safe-area-inset-top)) 14px 9px;border-bottom:1px solid var(--border-dim);flex-wrap:wrap}
.brand{font-family:'Orbitron',monospace;font-weight:900;letter-spacing:3px;font-size:13px;color:var(--accent)}
a{color:var(--accent);text-decoration:none}
.btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1px;padding:9px 12px;min-height:36px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;gap:7px;border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;white-space:nowrap}
.btn:hover{background:rgba(0,230,118,.1)}.btn.go{background:rgba(0,230,118,.14);border-color:var(--accent)}.btn.stop{border-color:rgba(255,92,92,.5);color:var(--red)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.ic{width:15px;height:15px;flex:none}
main{max-width:880px;margin:0 auto;padding:16px}
.welcome{border:1px solid var(--amber);border-radius:12px;padding:14px 16px;margin-bottom:16px;background:rgba(224,165,60,.07)}
.welcome b{color:var(--amber);font:700 10px 'Orbitron',monospace;letter-spacing:1.5px}.welcome p{font-size:13px;line-height:1.55;color:var(--ink);margin-top:6px}
h2{font:700 9px 'Orbitron',monospace;letter-spacing:1.6px;color:var(--text-muted);margin:22px 0 8px}
.loc{border:1px solid var(--border-dim);border-radius:11px;padding:12px 13px;margin-bottom:9px;background:var(--panel)}
.lh{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.lh b{color:var(--ink);font-size:14px;font-weight:600}
.req{font:700 8px 'Orbitron',monospace;letter-spacing:1px;color:var(--amber)}
.lp{font-size:12px;color:var(--text-muted);margin:3px 0 8px;line-height:1.45}
.lin{display:flex;gap:7px;align-items:center}
input[type=text],select{flex:1;min-width:0;background:var(--bg);border:1px solid var(--border-dim);color:var(--ink);border-radius:6px;padding:9px 10px;font-size:13px;outline:none;font-family:ui-monospace,Consolas,monospace}
input[type=text]:focus,select:focus{border-color:var(--accent)}select{flex:0 0 auto;font-family:'Outfit',sans-serif}
.chip{font-size:10.5px;border:1px solid var(--border-dim);border-radius:999px;padding:2px 9px;color:var(--text-muted)}
.chip.ok{color:var(--accent);border-color:var(--border-bright)}.chip.warn{color:var(--amber);border-color:var(--amber)}.chip.error{color:var(--red);border-color:var(--red)}
.src{display:grid;grid-template-columns:1fr;gap:7px;padding:10px 0;border-top:1px solid var(--border-dim)}.src:first-of-type{border-top:0;padding-top:2px}
.src .meta{display:flex;gap:9px;align-items:center;flex-wrap:wrap;font-size:12px}.ck{display:inline-flex;align-items:center;gap:6px;color:var(--text-muted);font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center}
.sug{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.sug .chip{cursor:pointer}
.err{color:var(--red);font-size:12px;margin-top:6px}
.sticky{position:fixed;left:0;right:0;bottom:0;background:var(--panel);border-top:1px solid var(--border-dim);padding:10px 16px;display:flex;gap:10px;align-items:center;justify-content:center;z-index:20}
.sticky .msg{font-size:12px;color:var(--text-muted)}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;z-index:30}.scrim.open{display:block}
.modal{position:fixed;top:6vh;left:50%;transform:translateX(-50%);width:640px;max-width:96vw;max-height:88vh;display:none;flex-direction:column;background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:12px;padding:14px;z-index:31}
.modal.open{display:flex}.modal h3{font:700 11px 'Orbitron',monospace;letter-spacing:1.5px;color:var(--accent);margin-bottom:8px}
.crumbs{display:flex;flex-wrap:wrap;gap:4px;font-size:12px;margin-bottom:8px;color:var(--text-muted)}.crumbs a{cursor:pointer}
.dirs{overflow-y:auto;border:1px solid var(--border-dim);border-radius:8px;background:var(--bg);min-height:180px;max-height:46vh}
.dirs div{display:flex;align-items:center;gap:8px;padding:9px 11px;font-size:13px;color:var(--ink);cursor:pointer;border-bottom:1px solid var(--border-dim)}.dirs div:hover{background:rgba(0,230,118,.08)}
.dirs .git{margin-left:auto;font-size:9.5px;color:var(--accent);border:1px solid var(--border-bright);border-radius:999px;padding:1px 7px}
.toast{position:fixed;left:50%;bottom:76px;transform:translateX(-50%);background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:8px;padding:9px 14px;font-size:12.5px;color:var(--ink);z-index:40;display:none}
@media (max-width:720px){main{padding:12px}.lin{flex-wrap:wrap}.lin input{flex:1 1 100%}.btn{flex:1 1 auto}.sticky{padding:8px 10px}}
</style></head><body>
<div class="bar"><a class="btn" href="/"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>HUB</a>
  <span class="brand">LOCATIONS</span><span style="flex:1"></span><a class="btn" href="/missions">MISSIONS</a></div>
<main id="main"><div style="color:var(--text-muted)">loading…</div></main>
<div class="sticky"><span class="msg" id="msg">Nothing changes until you press SAVE.</span><button class="btn go" id="save"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>SAVE</button></div>
<div class="scrim" id="scrim"></div>
<div class="modal" id="pk"><h3>CHOOSE A FOLDER</h3><div class="crumbs" id="pk-crumbs"></div><div class="dirs" id="pk-dirs"></div>
  <div class="row"><button class="btn" id="pk-up">UP</button><button class="btn" id="pk-new">NEW FOLDER</button><span style="flex:1"></span><button class="btn" id="pk-cancel">CANCEL</button><button class="btn go" id="pk-ok">USE THIS FOLDER</button></div></div>
<div class="toast" id="toast"></div>
<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const IC = {plus:'<path d="M12 5v14M5 12h14"/>', x:'<path d="M6 6l12 12M18 6L6 18"/>', folder:'<path d="M3 7.5A1.5 1.5 0 014.5 6H9l2 2.5h8.5A1.5 1.5 0 0121 10v8a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18z"/>', up:'<path d="M12 19V5M6 11l6-6 6 6"/>'};
const ic = (n) => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${IC[n]||''}</svg>`;
async function jget(u){ const r = await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jsend(m,u,b){ const r = await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}); const t = await r.text(); let j; try{ j=JSON.parse(t); }catch(e){ j={raw:t}; } if(!r.ok){ const e = new Error(j.raw||t); e.data=j; throw e; } return j; }
function toast(t){ const e=$('toast'); e.textContent=t; e.style.display='block'; clearTimeout(toast._t); toast._t=setTimeout(()=>e.style.display='none',3500); }

let DATA = null, CUR = {}, ERR = {};
const GROUPS = ['PROJECTS','MISSIONS','KNOWLEDGE','FILES','TOOLS'];
let MCPS = [], HTTPS = null;
async function load(){ try{ MCPS = (await jget('/api/mcp')).servers; }catch(e){ MCPS = []; } try{ HTTPS = await jget('/api/phone-https'); }catch(e){ HTTPS = null; } DATA = await jget('/api/locations'); CUR = {}; ERR = {}; DATA.items.forEach(i => CUR[i.key] = JSON.parse(JSON.stringify(i.value))); render(); }
const chip = (s) => s ? `<span class="chip ${esc(s.level)}">${esc(s.msg)}</span>` : '';

function render(){
  const first = !DATA.configured;
  let h = first ? `<div class="welcome"><b>WELCOME — WHERE SHOULD AGENT HUB READ AND WRITE?</b><p>Everything below is prefilled with what was found on this computer. Change what you like, then press SAVE. Nothing is created until you save, and you can come back to this page any time (OpenCode card, LOCATIONS).</p></div>` : '';
  for(const g of GROUPS){
    const items = DATA.items.filter(i => i.group===g); if(!items.length) continue;
    h += `<h2>${g}</h2>` + items.map(itemHtml).join('') + (g==='TOOLS' ? extraTools() : '');
  }
  $('main').innerHTML = h;
  bind();
  if(location.hash === '#pc-control') requestAnimationFrame(() => $('pc-control')?.scrollIntoView({block:'start', behavior:'instant'}));
}
function itemHtml(i){
  const k = i.key, e = ERR[k];
  const head = `<div class="lh"><b>${esc(i.label)}</b>${i.required?'<span class="req">REQUIRED</span>':''}${i.restart?'<span class="chip">applies after a hub restart</span>':''}<span id="st-${k}">${i.kind==='sources'?'':chip(i.status)}</span></div><div class="lp">${esc(i.purpose)}</div>`;
  if(i.kind==='sources'){
    const rows = (CUR[k]||[]).map((s,n)=>`<div class="src" data-n="${n}">
      <div class="lin"><input type="text" data-src="${n}" data-f="path" value="${esc(s.path)}"><button class="btn" data-browse-src="${n}">BROWSE</button><button class="btn stop" data-rm="${n}" aria-label="Remove">${ic('x')}</button></div>
      <div class="meta"><select data-src="${n}" data-f="kind"><option value="collection" ${s.kind==='collection'?'selected':''}>a folder full of projects</option><option value="project" ${s.kind==='project'?'selected':''}>one project</option></select>
        <label class="ck"><input type="checkbox" data-src="${n}" data-f="readonly" ${s.readonly?'checked':''}> read-only (agents never write here)</label>${chip((i.sources_status||[])[n])}</div></div>`).join('') || '<div class="lp">No project folders yet. Add one, or pick from the suggestions.</div>';
    return `<div class="loc" id="loc-${k}">${head}${rows}<div class="row"><button class="btn go" id="add-col">${ic('plus')}ADD A FOLDER OF PROJECTS</button><button class="btn" id="add-proj">${ic('plus')}ADD ONE PROJECT</button><button class="btn" id="suggest">FIND MY PROJECTS</button></div><div class="sug" id="sug"></div>${e?`<div class="err">${esc(e)}</div>`:''}</div>`;
  }
  const st = i.status||{};
  return `<div class="loc">${head}<div class="lin"><input type="text" data-k="${k}" value="${esc(CUR[k]||'')}" placeholder="${i.required?'':'not set'}">${i.kind==='folder'?`<button class="btn" data-browse="${k}">BROWSE</button>`:''}${st.create?`<button class="btn" data-create="${k}">CREATE</button>`:''}${!i.required&&CUR[k]?`<button class="btn" data-clear="${k}">CLEAR</button>`:''}</div>${e?`<div class="err">${esc(e)}</div>`:''}</div>`;
}
function extraTools(){
  let h = '';
  const w = MCPS.find(x => x.name==='windows');
  h += `<div class="loc" id="pc-control"><div class="lh"><b>PC control (Windows MCP)</b>${w ? `<span class="chip ${w.enabled?'warn':'ok'}">${w.enabled?'ON':'off'}</span>${w.installed?'':'<span class="chip error">program missing</span>'}` : '<span class="chip">not set up</span>'}</div>
    <div class="lp">Lets OpenCode agents click, type, take screenshots, open apps and use the clipboard. ${w ? 'PowerShell, registry, file and process control are excluded ('+esc(w.excluded_tools.join(', '))+'). ' : ''}It is off by default: while ON, the agents in any ask can use it, so switch it on only while you need it.</div>
    ${w && w.installed ? `<div class="row"><button class="btn" id="mcp-probe">LIST ITS TOOLS (SAFE TEST)</button><button class="btn ${w.enabled?'stop':'go'}" id="mcp-toggle">${w.enabled?'SWITCH OFF':'SWITCH ON'}</button><span class="lp" style="margin:0">applies to the next ask step; restart the OpenCode workspace to apply it there</span></div>` : '<div class="lp">Not installed on this machine.</div>'}</div>`;
  if(HTTPS && HTTPS.available){
    h += `<div class="loc"><div class="lh"><b>Phone microphone and sound (https)</b><span class="chip ${HTTPS.serving?'ok':'warn'}">${HTTPS.serving?'https is on':'not set up'}</span></div>
      <div class="lp">Browsers only allow the microphone (and reliable sound) on https. On your phone open the hub at:</div>
      <div class="lin"><input type="text" readonly value="${esc(HTTPS.url)}" id="https-url"><button class="btn" id="https-copy">COPY</button></div>
      ${HTTPS.serving ? '' : `<div class="lp" style="margin-top:8px">Not serving yet. Run this once in a terminal on this PC: <code>${esc(HTTPS.command)}</code></div>`}</div>`;
  }
  return h;
}
let vt = {};
function bind(){
  document.querySelectorAll('input[data-k]').forEach(inp => inp.oninput = () => { CUR[inp.dataset.k] = inp.value; clearTimeout(vt[inp.dataset.k]);
    vt[inp.dataset.k] = setTimeout(async () => { try{ const r = await jsend('POST','/api/locations/validate',{key:inp.dataset.k,value:inp.value}); $('st-'+inp.dataset.k).innerHTML = chip(r); }catch(e){} }, 400); });
  document.querySelectorAll('[data-src]').forEach(el => el.onchange = el.oninput = () => { const n = +el.dataset.src, f = el.dataset.f; CUR.project_sources[n][f] = el.type==='checkbox' ? el.checked : el.value; });
  document.querySelectorAll('[data-browse]').forEach(b => b.onclick = () => pick(CUR[b.dataset.browse], p => { CUR[b.dataset.browse] = p; render(); }));
  document.querySelectorAll('[data-browse-src]').forEach(b => b.onclick = () => { const n = +b.dataset.browseSrc; pick(CUR.project_sources[n].path, p => { CUR.project_sources[n].path = p; render(); }); });
  document.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { CUR.project_sources.splice(+b.dataset.rm,1); render(); });
  document.querySelectorAll('[data-clear]').forEach(b => b.onclick = () => { CUR[b.dataset.clear] = ''; render(); });
  document.querySelectorAll('[data-create]').forEach(b => b.onclick = async () => { try{ await jsend('POST','/api/fs/mkdir',{path:CUR[b.dataset.create]}); toast('Folder created'); const r = await jget('/api/locations'); DATA = r; render(); }catch(e){ toast(e.message); } });
  const mt = $('mcp-toggle'); if(mt) mt.onclick = async () => { const w = MCPS.find(x=>x.name==='windows'), on = !w.enabled;
    if(on && !confirm('Switch PC control ON? Agents in any ask will be able to click, type and open apps until you switch it off.')) return;
    try{ const r = await jsend('POST','/api/mcp/windows/enabled',{enabled:on}); MCPS = r.servers; render(); toast(on?'PC control is ON':'PC control is off'); }catch(e){ toast(e.message); } };
  const mp = $('mcp-probe'); if(mp) mp.onclick = async () => { mp.disabled = true; mp.textContent = 'STARTING IT…'; try{ const r = await jsend('POST','/api/mcp/windows/probe'); toast('It answered: '+r.tools.length+' tools (' + r.tools.join(', ') + ')'); }catch(e){ toast('Test failed: '+e.message); } mp.disabled = false; mp.textContent = 'LIST ITS TOOLS (SAFE TEST)'; };
  const hc = $('https-copy'); if(hc) hc.onclick = () => { $('https-url').select(); try{ navigator.clipboard.writeText($('https-url').value); toast('Copied'); }catch(e){} };
  const addc = $('add-col'); if(addc) addc.onclick = () => pick('', p => { CUR.project_sources.push({kind:'collection', path:p}); render(); });
  const addp = $('add-proj'); if(addp) addp.onclick = () => pick('', p => { CUR.project_sources.push({kind:'project', path:p}); render(); });
  const sg = $('suggest'); if(sg) sg.onclick = async () => { sg.disabled = true; try{ const r = await jsend('POST','/api/locations/suggest');
      $('sug').innerHTML = r.folders.length ? r.folders.map(f=>`<span class="chip ok" data-sug="${esc(f.path)}">${ic('plus')} ${esc(f.path)} · ${f.repos} repos</span>`).join('') : '<span class="lp">No usual place holds git repos. Use ADD instead.</span>';
      document.querySelectorAll('[data-sug]').forEach(c => c.onclick = () => { if(!CUR.project_sources.some(s=>s.path===c.dataset.sug)) CUR.project_sources.push({kind:'collection', path:c.dataset.sug}); render(); });
    }catch(e){ toast(e.message); } sg.disabled = false; };
}
// ---- folder picker (server side: a browser cannot give absolute paths)
let PK = {path:'', cb:null};
async function pkLoad(path){
  let d; try{ d = await jget('/api/fs/list?path='+encodeURIComponent(path||'')); }catch(e){ toast(e.message); return; }
  PK.path = d.path || ''; PK.parent = d.parent;
  const parts = PK.path ? PK.path.split(/[\\/]+/).filter(Boolean) : [];
  let acc = '';
  $('pk-crumbs').innerHTML = `<a data-p="">this computer</a>` + parts.map((p,i)=>{ acc = i===0 ? p+'\\' : acc.replace(/\\$/,'')+'\\'+p; return ` / <a data-p="${esc(acc)}">${esc(p)}</a>`; }).join('');
  document.querySelectorAll('#pk-crumbs a').forEach(a => a.onclick = () => pkLoad(a.dataset.p));
  const items = !PK.path ? [...(d.drives||[]).map(x=>({name:x,full:x})), ...(d.places||[]).map(x=>({name:x,full:x}))] : d.dirs.map(x=>({name:x.name,full:PK.path.replace(/[\\/]+$/,'')+'\\'+x.name,git:x.git}));
  $('pk-dirs').innerHTML = items.map(x=>`<div data-full="${esc(x.full)}">${ic('folder')}${esc(x.name)}${x.git?'<span class="git">git repo</span>':''}</div>`).join('') || '<div style="color:var(--text-faint)">no sub-folders</div>';
  document.querySelectorAll('#pk-dirs [data-full]').forEach(r => r.onclick = () => pkLoad(r.dataset.full));
  $('pk-ok').disabled = !PK.path;
}
function pick(start, cb){ PK.cb = cb; $('scrim').classList.add('open'); $('pk').classList.add('open'); pkLoad(start && /^[A-Za-z]:/.test(start) ? start : ''); }
function pkClose(){ $('scrim').classList.remove('open'); $('pk').classList.remove('open'); }
$('pk-cancel').onclick = pkClose; $('scrim').onclick = pkClose;
$('pk-up').onclick = () => pkLoad(PK.parent || '');
$('pk-ok').onclick = () => { const cb = PK.cb, p = PK.path; pkClose(); if(cb && p) cb(p); };
$('pk-new').onclick = async () => { if(!PK.path) return; const n = prompt('New folder name'); if(!n) return; try{ const r = await jsend('POST','/api/fs/mkdir',{path:PK.path.replace(/[\\/]+$/,'')+'\\'+n}); pkLoad(r.path); }catch(e){ toast(e.message); } };

$('save').onclick = async () => {
  $('save').disabled = true; $('msg').textContent = 'Saving…';
  try{
    const r = await jsend('PUT','/api/locations',{values:CUR});
    DATA = r; ERR = {}; CUR = {}; DATA.items.forEach(i => CUR[i.key] = JSON.parse(JSON.stringify(i.value))); render();
    $('msg').textContent = r.restart && r.restart.length ? 'Saved. Restart the hub for: ' + r.restart.join(', ') + '. Project folders apply at once.' : 'Saved.';
    toast('Saved');
  }catch(e){ ERR = (e.data && e.data.errors) || {}; render(); $('msg').textContent = 'Not saved: fix the marked rows.'; }
  $('save').disabled = false;
};
load().catch(e => { $('main').innerHTML = '<div class="err">Could not load locations: '+esc(e.message)+'</div>'; });
</script></body></html>"""


@routes.get("/setup")
async def setup_page(request: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html", headers={"Cache-Control": "no-store"})
