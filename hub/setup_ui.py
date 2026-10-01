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
.rt{border:1px solid var(--border-dim);border-radius:9px;padding:9px 11px;margin-top:7px;background:var(--bg)}.rt .h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.rt b{color:var(--ink);font-size:13px;font-weight:600}.rt .meta{font-size:11px;color:var(--text-muted);flex:1;min-width:120px}.rt .steps{font-size:11px;color:var(--text-muted);margin-top:5px;overflow-wrap:anywhere}.tabs{display:flex;gap:7px;margin:10px 0 2px}
.foldh{cursor:pointer;user-select:none}
.tw{transition:transform .15s ease;opacity:.8}.tw.down{transform:rotate(90deg)}
.foldb{margin-top:9px}
.prow{display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:8px 0;border-top:1px solid var(--border-dim)}
.pedit{padding:0 0 10px}
.chip.ok{color:var(--accent);border-color:var(--border-bright)}
.kmask{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--text-muted);letter-spacing:.5px;background:var(--bg-mid);border:1px solid var(--border-dim);border-radius:5px;padding:2px 7px}
.recbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:9px 0;font-size:11px;letter-spacing:1px}
.recbar.live b{color:#ff6b6b}
.recdot{width:9px;height:9px;border-radius:50%;background:#ff6b6b;animation:recpulse 1.1s infinite}
@keyframes recpulse{0%,100%{opacity:1}50%{opacity:.25}}
.reclist{max-height:280px;overflow:auto;margin-top:6px}
.recstep{display:flex;align-items:center;gap:9px;padding:6px 0;border-top:1px solid var(--border-dim);font-size:12px}
.recstep.off{opacity:.4;text-decoration:line-through}
.recnum{min-width:22px;color:var(--text-muted);font-size:10.5px}
.recnote{color:var(--ink)}
.tabs .btn.on{background:rgba(0,230,118,.16);border-color:var(--accent)}.rt-empty{font-size:12px;color:var(--text-muted);padding:10px 2px;line-height:1.6}
.upd{border:1px solid var(--border-bright);border-radius:12px;padding:13px 15px;margin-bottom:16px;background:rgba(0,230,118,.07)}.upd.new{border-color:var(--amber);background:rgba(224,165,60,.09)}.upd b{font:700 10px 'Orbitron',monospace;letter-spacing:1.5px;color:var(--accent)}.upd.new b{color:var(--amber)}.upd p{font-size:12.5px;line-height:1.55;color:var(--ink);margin:7px 0 0}.upd .row{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:10px}.upd pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px ui-monospace,Consolas,monospace;color:var(--text-muted);background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:9px 10px;margin-top:9px;max-height:160px;overflow:auto}
.addr{border:1px solid var(--border-bright);border-radius:12px;padding:13px 15px;margin-bottom:16px;background:rgba(0,230,118,.05)}.addr b{color:var(--accent);font:700 10px 'Orbitron',monospace;letter-spacing:1.5px}.addr .row{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:9px}.addr .lbl{font-size:11px;color:var(--text-muted);flex:0 0 100%}.addr code{flex:1;min-width:180px;font:13px ui-monospace,Consolas,monospace;color:var(--ink);background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:8px 10px;overflow-wrap:anywhere}.addr .warn{font-size:11px;color:var(--amber);flex:0 0 100%;margin-top:2px}
.welcome{border:1px solid var(--amber);border-radius:12px;padding:14px 16px;margin-bottom:16px;background:rgba(224,165,60,.07)}
.welcome b{color:var(--amber);font:700 10px 'Orbitron',monospace;letter-spacing:1.5px}.welcome p{font-size:13px;line-height:1.55;color:var(--ink);margin-top:6px}
h2{font:700 9px 'Orbitron',monospace;letter-spacing:1.6px;color:var(--text-muted);margin:22px 0 8px}
.loc{border:1px solid var(--border-dim);border-radius:11px;padding:12px 13px;margin-bottom:9px;background:var(--panel)}
.lh{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.lh b{color:var(--ink);font-size:14px;font-weight:600}
.req{font:700 8px 'Orbitron',monospace;letter-spacing:1px;color:var(--amber)}
.lp{font-size:12.5px;color:var(--text-muted);margin:6px 0 10px;line-height:1.6;max-width:72ch}
/* A setting's first sentence says what the folder IS; the rest says how it
   behaves. Separating them stops the two reading as one long qualifier. */
.lp .first{display:block;color:var(--ink);margin-bottom:3px}
.lh{row-gap:6px}
@media(max-width:720px){.lp{font-size:13px;line-height:1.65}}
.lin{display:flex;gap:7px;align-items:center}
input[type=text],select{flex:1;min-width:0;background:var(--bg);border:1px solid var(--border-dim);color:var(--ink);border-radius:6px;padding:9px 10px;font-size:13px;outline:none;font-family:ui-monospace,Consolas,monospace}
input[type=text]:focus,select:focus{border-color:var(--accent)}select{flex:0 0 auto;font-family:'Outfit',sans-serif}
.chip{font-size:10.5px;border:1px solid var(--border-dim);border-radius:999px;padding:2px 9px;color:var(--text-muted)}
.chip.warn{color:var(--amber);border-color:var(--amber)}.chip.error{color:var(--red);border-color:var(--red)}
.src{display:grid;grid-template-columns:1fr;gap:7px;padding:10px 0;border-top:1px solid var(--border-dim)}.src:first-of-type{border-top:0;padding-top:2px}
.src .meta{display:flex;gap:9px;align-items:center;flex-wrap:wrap;font-size:12px}
.src .meta .lp{flex:1 1 200px}.ck{display:inline-flex;align-items:center;gap:6px;color:var(--text-muted);font-size:12px}
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
/* Two panes: the sections on the left, one section's settings on the right.
   The list used to be one scroll of every setting the hub has, which meant
   hunting for the one you came to change. */
.pane{display:grid;grid-template-columns:208px minmax(0,1fr);gap:18px;align-items:start}
.nav{position:sticky;top:12px;display:flex;flex-direction:column;gap:2px}
.nav button{display:flex;align-items:center;gap:8px;width:100%;text-align:left;cursor:pointer;
  font:600 12px 'Outfit',sans-serif;letter-spacing:.3px;color:var(--text-muted);
  background:transparent;border:1px solid transparent;border-radius:8px;padding:9px 11px}
.nav button:hover{color:var(--ink);background:rgba(0,230,118,.06)}
.nav button.on{color:var(--accent);border-color:var(--border-bright);background:rgba(0,230,118,.10)}
.nav .nb{margin-left:auto;display:flex;gap:5px;align-items:center}
/* An unsaved edit in a section you are not looking at still saves, so it has to
   be visible from here - otherwise SAVE writes things you cannot see. */
.nav .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 7px var(--accent)}
.nav .dot.need{background:var(--amber);box-shadow:0 0 7px var(--amber)}
.sect h2{margin-top:0}
.themes{display:flex;flex-direction:column;gap:6px;margin:10px 0 2px}
.loc.sub{background:transparent;border-style:dashed}
.src.fixed{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.src.fixed code{font-size:11.5px;color:var(--text-faint);word-break:break-all;flex:1 1 200px}
.src.fixed .btn{flex:0 0 auto;padding:5px 9px}
.src.known{border-top:0;padding:6px 0}
.src.known code{font-size:11px;color:var(--text-faint);word-break:break-all}
.trow{display:flex;align-items:baseline;gap:9px;padding:9px 11px;border:1px solid var(--border-dim);
 border-radius:9px;cursor:pointer;flex-wrap:wrap}
.trow:hover{border-color:var(--border-bright)}
.trow input{width:auto;flex:0 0 auto}
.sws{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:8px}
.sw{display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border-dim);border-radius:9px}
.sw input[type=color]{width:38px;height:38px;padding:0;border-radius:8px;flex:0 0 auto;cursor:pointer;background:transparent}
.sw span{font-size:11.5px;color:var(--text-muted);line-height:1.45}
.sw b{display:block;color:var(--ink);font-size:12.5px;font-weight:600}
@media(max-width:720px){.sws{grid-template-columns:1fr}}
@media (max-width:720px){main{padding:12px}.lin{flex-wrap:wrap}.lin input{flex:1 1 100%}.btn{flex:1 1 auto}.sticky{padding:8px 10px}
  /* No room for a rail: the sections become a row of chips you swipe. */
  .pane{grid-template-columns:minmax(0,1fr);gap:12px}
  .nav{position:static;flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:4px;-webkit-overflow-scrolling:touch}
  .nav button{width:auto;flex:0 0 auto;white-space:nowrap;border-color:var(--border-dim)}}
</style><link rel="stylesheet" href="/theme.css">
</head><body>
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
// The left rail. `group` is the settings group a section shows (null = none of
// the saved locations, just cards). Order is the order you meet them.
const SECTIONS = [
  {id:'hub',       label:'This hub',   group:null},
  {id:'projects',  label:'Projects',   group:'PROJECTS'},
  {id:'missions',  label:'Missions',   group:'MISSIONS'},
  {id:'files',     label:'Files',      group:'FILES'},
  {id:'tools',     label:'Tools',      group:'TOOLS'},
  {id:'appearance',label:'Appearance', group:null},
];
let SEC = (location.hash || '').replace('#','');
if(!SECTIONS.some(x => x.id === SEC)) SEC = '';
let MCPS = [], HTTPS = null, ADDR = null, UPD = null, ROUTINES = null, RTAB = 'mcp';
let KEYS = null, KEYMSG = {}, KEYOPEN = '', FOLD = {};
let YTA = null, YTMSG = '', YTOPEN = false;
let THEME = null, KNOWN = [], MOVE = null;
let REC = null, RECDROP = {}, RECMSG = '', RECTIMER = null;
async function load(){ try{ REC = await jget('/api/pc/record'); }catch(e){ REC = null; } try{ KEYS = await jget('/api/llm/keys'); }catch(e){ KEYS = null; } try{ ROUTINES = (await jget('/api/pc/routines')).routines || []; }catch(e){ ROUTINES = null; } try{ UPD = await jget('/api/update'); }catch(e){ UPD = null; } try{ ADDR = await jget('/api/hub-address'); }catch(e){ ADDR = null; } try{ MCPS = (await jget('/api/mcp')).servers; }catch(e){ MCPS = []; } try{ HTTPS = await jget('/api/phone-https'); }catch(e){ HTTPS = null; } try{ YTA = await jget('/api/youtube/accounts'); }catch(e){ YTA = null; } try{ THEME = await jget('/api/theme'); }catch(e){ THEME = null; } try{ KNOWN = await jget('/api/locations/known'); }catch(e){ KNOWN = []; } try{ MOVE = await jget('/api/install-move'); }catch(e){ MOVE = null; } DATA = await jget('/api/locations'); CUR = {}; ERR = {}; DATA.items.forEach(i => CUR[i.key] = JSON.parse(JSON.stringify(i.value))); render(); }
const chip = (s) => s ? `<span class="chip ${esc(s.level)}">${esc(s.msg)}</span>` : '';

function updateCard(){
  if(!UPD || !UPD.current) return '';
  const when = UPD.checked_at ? new Date(UPD.checked_at*1000).toLocaleString() : 'never';
  if(UPD.newer){
    return `<div class="upd new"><b>AGENT HUB ${esc(UPD.latest)} IS AVAILABLE</b>`
      + `<p>You are on ${esc(UPD.current)}. Updating keeps your locations, ingested apps and your own skills \u2014 `
      + `they live outside the program folder.</p>`
      + (UPD.notes ? `<pre>${esc(UPD.notes)}</pre>` : '')
      + `<div class="row"><button class="btn go" id="do-update">UPDATE NOW</button>`
      + (UPD.page ? `<a class="btn" href="${esc(UPD.page)}" target="_blank" rel="noopener">RELEASE NOTES</a>` : '')
      + `<button class="btn" id="chk-update">CHECK AGAIN</button></div>`
      + `<div class="row" id="upd-msg"></div></div>`;
  }
  const line = UPD.error ? esc(UPD.error)
    : (UPD.latest ? `Version ${esc(UPD.current)} \u2014 up to date. Last checked ${esc(when)}.`
                  : `Version ${esc(UPD.current)}. No published release found yet.`);
  return `<div class="upd"><b>THIS BUILD</b><p>${line}</p>`
    + `<div class="row"><button class="btn" id="chk-update">CHECK FOR UPDATES</button></div>`
    + `<div class="row" id="upd-msg"></div></div>`;
}

function addressCard(){
  if(!ADDR) return '';
  const rows = ADDR.addresses.map(a => `<div class="row"><span class="lbl">${esc(a.label)}</span>`
    + `<code>${esc(a.url)}</code>`
    + `<button class="btn" data-copy="${esc(a.url)}">COPY</button>`
    + (a.hint ? `<span class="warn">${esc(a.hint)}</span>` : '') + '</div>').join('');
  return `<div class="addr"><b>THIS HUB'S ADDRESS</b>${rows}`
    + `<div class="row"><span class="lbl">Open one of these on your phone or tablet and add it to the home screen. `
    + `This card stays here, so you can come back for it any time.</span></div></div>`;
}

function render(){
  const first = !DATA.configured;
  // On a fresh install the required folders are the thing to do first; after
  // that, landing on the hub's own card is the least surprising.
  if(!SEC) SEC = first ? 'projects' : 'hub';
  const cur = SECTIONS.find(x => x.id === SEC) || SECTIONS[0];

  const nav = SECTIONS.map(x => {
    const its = x.group ? DATA.items.filter(i => i.group === x.group) : [];
    const need = its.some(i => i.required && !CUR[i.key] ||
                               (i.kind === 'sources' && i.required && !(CUR[i.key]||[]).length));
    const edited = its.some(i => dirty(i.key));
    const upd = x.id === 'hub' && UPD && UPD.available;
    return `<button data-sec="${x.id}" class="${x.id===SEC?'on':''}">${esc(x.label)}`
      + `<span class="nb">`
      + (need ? `<span class="dot need" title="something required is not set"></span>` : '')
      + (edited ? `<span class="dot" title="unsaved change"></span>` : '')
      + (upd ? `<span class="chip warn">UPDATE</span>` : '')
      + `</span></button>`;
  }).join('');

  let body = '';
  if(cur.id === 'hub') body += updateCard() + addressCard() + moveCard();
  if(first && cur.id === 'projects')
    body += `<div class="welcome"><b>WELCOME — WHERE SHOULD AGENT HUB READ AND WRITE?</b><p>Each section on the left holds one kind of setting, prefilled with what was found on this computer. Project folders are the only ones the hub cannot run without. Change what you like, then press SAVE — it saves every section at once, and nothing is created until you do.</p></div>`;
  if(cur.group){
    const items = DATA.items.filter(i => i.group === cur.group);
    body += `<h2>${cur.group}</h2>` + (cur.group === 'PROJECTS'
      ? projectBoxes(items) : items.map(itemHtml).join(''));
  }
  if(cur.id === 'missions') body += providersCard();
  if(cur.id === 'tools') body += ytCard() + extraTools();
  if(cur.id === 'appearance') body += themeCard();

  $('main').innerHTML = `<div class="pane"><nav class="nav">${nav}</nav><div class="sect">${body}</div></div>`;
  document.querySelectorAll('[data-sec]').forEach(b => b.onclick = () => {
    SEC = b.dataset.sec;
    // A real URL per section, so the back button and a bookmark both work.
    history.replaceState(null, '', '#' + SEC);
    render(); window.scrollTo({top:0});
  });
  saveMsg();
  document.querySelectorAll('[data-fold]').forEach(b => {
    const go = () => { FOLD[b.dataset.fold] = b.dataset.open !== '1'; render(); };
    b.onclick = go;
    b.onkeydown = (e) => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); go(); } };
  });
  const recRefresh = async () => { try{ REC = await jget('/api/pc/record'); }catch(e){} render(); };
  const s1 = $('rec-start'); if(s1) s1.onclick = async () => {
    s1.disabled = true; RECMSG = '';
    try{ REC = await jsend('POST','/api/pc/record/start'); RECDROP = {}; render(); }
    catch(e){ RECMSG = String(e.message||e); render(); }
  };
  const s2 = $('rec-stop'); if(s2) s2.onclick = async () => {
    s2.disabled = true; s2.textContent = 'STOPPING\u2026';
    try{ REC = await jsend('POST','/api/pc/record/stop'); render(); }
    catch(e){ RECMSG = String(e.message||e); render(); }
  };
  document.querySelectorAll('[data-recdrop]').forEach(b => b.onclick = () => {
    const n = b.dataset.recdrop; RECDROP[n] = !RECDROP[n]; render();
  });
  const s3 = $('rec-save'); if(s3) s3.onclick = async () => {
    const intent = ($('rec-name').value||'').trim();
    if(!intent){ RECMSG = 'Give it a name first.'; render(); return; }
    s3.disabled = true; s3.textContent = 'SAVING\u2026';
    try{
      await jsend('POST','/api/pc/record/save', {intent, title: intent,
           profile: $('rec-profile').value, drop: Object.keys(RECDROP).filter(k => RECDROP[k]).map(Number)});
      await jsend('POST','/api/pc/record/discard');
      RECDROP = {}; RECMSG = ''; toast('Routine saved as a candidate');
      ROUTINES = (await jget('/api/pc/routines')).routines || []; await recRefresh();
    }catch(e){ RECMSG = String(e.message||e); render(); }
  };
  const s4 = $('rec-discard'); if(s4) s4.onclick = async () => {
    try{ await jsend('POST','/api/pc/record/discard'); RECDROP = {}; RECMSG = ''; await recRefresh(); }
    catch(e){ RECMSG = String(e.message||e); render(); }
  };
  // While a recording runs the user is in another window, so the panel polls
  // rather than waiting for them to come back and refresh it.
  clearInterval(RECTIMER);
  if(REC && REC.running) RECTIMER = setInterval(recRefresh, 1500);
  document.querySelectorAll('[data-keyopen]').forEach(b => b.onclick = () => {
    KEYOPEN = (KEYOPEN === b.dataset.keyopen) ? '' : b.dataset.keyopen; render();
    const f = $('key-'+KEYOPEN); if(f) f.focus();
  });
  document.querySelectorAll('[data-rtab]').forEach(b => b.onclick = () => { RTAB = b.dataset.rtab; render(); });
  document.querySelectorAll('[data-keysave]').forEach(b => b.onclick = async () => {
    const id = b.dataset.keysave, box = $('key-'+id), key = (box.value||'').trim();
    if(!key){ KEYMSG[id] = 'Paste a key first.'; render(); return; }
    b.disabled = true; b.textContent = 'CHECKING\u2026';
    try{ const r = await jsend('POST','/api/llm/keys',{provider:id, key});
         KEYMSG[id] = r.msg || 'Saved.'; KEYS = await jget('/api/llm/keys'); render(); toast('Connected'); }
    catch(e){ KEYMSG[id] = (e.data && e.data.msg) || String(e.message||e); KEYS = await jget('/api/llm/keys'); render(); }
  });
  document.querySelectorAll('[data-keyrm]').forEach(b => b.onclick = async () => {
    const id = b.dataset.keyrm; b.disabled = true;
    try{ await jsend('DELETE','/api/llm/keys/'+encodeURIComponent(id));
         KEYMSG[id] = 'Removed from this PC.'; KEYS = await jget('/api/llm/keys'); render(); }
    catch(e){ KEYMSG[id] = String(e.message||e); render(); }
  });
  const applyTheme = async (payload) => {
    try{
      THEME = await jsend('PUT','/api/theme',payload);
      // Re-fetch the stylesheet rather than reloading: the page keeps its
      // scroll position and any unsaved folder edits in CUR.
      const link = [...document.querySelectorAll('link[href^="/theme.css"]')][0];
      if(link) link.href = '/theme.css?v=' + Date.now();
      render(); toast('Theme applied');
    }catch(e){ toast(e.message); }
  };
  document.querySelectorAll('input[name="th"]').forEach(r => r.onchange = () => {
    const w = $('custom-wrap'); if(w) w.style.display = r.value === 'custom' ? '' : 'none';
    applyTheme(r.value === 'custom'
      ? {name:'custom', colors:Object.fromEntries([...document.querySelectorAll('[data-col]')].map(i=>[i.dataset.col,i.value]))}
      : {name:r.value});
  });
  document.querySelectorAll('[data-col]').forEach(i => i.onchange = () => applyTheme({
    name:'custom',
    colors:Object.fromEntries([...document.querySelectorAll('[data-col]')].map(x=>[x.dataset.col,x.value]))}));
  const tr = $('th-reset'); if(tr) tr.onclick = () => applyTheme(
    {name:'custom', colors:Object.fromEntries((THEME.tokens||[]).map(t=>[t.key,t.default]))});

  const yo = $('yt-open'); if(yo) yo.onclick = () => { YTOPEN = !YTOPEN; YTMSG = ''; render(); };
  const ys = $('yt-save'); if(ys) ys.onclick = async () => {
    const tag = ($('yt-tag').value || '').trim(), f = $('yt-file').files[0];
    if(!tag){ YTMSG = 'Give the channel a name first.'; render(); return; }
    if(!f){ YTMSG = 'Choose the client_secrets.json you downloaded from Google.'; render(); return; }
    ys.disabled = true; ys.textContent = 'ADDING\u2026';
    try{
      // Read it here rather than asking for a path: the file is the user's own
      // download and the browser will not hand us an absolute path anyway.
      const secrets = await f.text();
      await jsend('POST','/api/youtube/accounts',{tag, secrets});
      YTA = await jget('/api/youtube/accounts'); YTOPEN = false; YTMSG = '';
      render(); toast('Channel added');
    }catch(e){ YTMSG = String(e.message||e); render(); }
  };
  document.querySelectorAll('[data-ytrm]').forEach(b => b.onclick = async () => {
    const tag = b.dataset.ytrm;
    if(!confirm('Forget '+tag+' on this PC? Its Google sign-in is deleted here; nothing changes at Google.')) return;
    b.disabled = true;
    try{ await jsend('DELETE','/api/youtube/accounts/'+encodeURIComponent(tag));
         YTA = await jget('/api/youtube/accounts'); YTMSG = tag+' removed from this PC.'; render(); }
    catch(e){ YTMSG = String(e.message||e); render(); }
  });
  document.querySelectorAll('[data-rstatus]').forEach(b => b.onclick = async () => {
    b.disabled = true;
    try{ await jsend('POST','/api/pc/routines/'+encodeURIComponent(b.dataset.rstatus)+'/status', {status: b.dataset.to});
         ROUTINES = (await jget('/api/pc/routines')).routines || []; render(); }
    catch(e){ b.disabled = false; const m = $('rt-msg-'+b.dataset.rstatus); if(m) m.textContent = String(e.message||e); }
  });
  document.querySelectorAll('[data-run]').forEach(b => b.onclick = async () => {
    const id = b.dataset.run, m = $('rt-msg-'+id);
    b.disabled = true; const was = b.textContent; b.textContent = 'RUNNING\u2026';
    try{ const r = await jsend('POST','/api/pc/routines/'+encodeURIComponent(id)+'/run');
         if(m) m.textContent = r.say || (r.ok ? 'Done.' : 'It refused.');
         ROUTINES = (await jget('/api/pc/routines')).routines || []; render(); }
    catch(e){ b.disabled = false; b.textContent = was; if(m) m.textContent = String(e.message||e); }
  });
  const chk = $('chk-update');
  if(chk) chk.onclick = async () => {
    chk.disabled = true; const was = chk.textContent; chk.textContent = 'CHECKING\u2026';
    try{ UPD = await jget('/api/update?refresh=1'); render(); }
    catch(e){ chk.disabled = false; chk.textContent = was; $('upd-msg').textContent = String(e.message||e); }
  };
  const doUpd = $('do-update');
  if(doUpd) doUpd.onclick = async () => {
    doUpd.disabled = true; doUpd.textContent = 'DOWNLOADING\u2026';
    $('upd-msg').textContent = 'Fetching the installer. This can take a minute on a slow connection.';
    try{
      const r = await jsend('POST','/api/update/install');
      $('upd-msg').textContent = r.message || 'The installer is starting.';
      doUpd.textContent = 'INSTALLER STARTED';
    }catch(e){
      doUpd.disabled = false; doUpd.textContent = 'UPDATE NOW';
      $('upd-msg').textContent = String(e.message||e);
    }
  };
  document.querySelectorAll('[data-copy]').forEach(b => b.onclick = async () => {
    try{ await navigator.clipboard.writeText(b.dataset.copy); }catch(e){ return; }
    const was = b.textContent; b.textContent = 'COPIED'; setTimeout(() => b.textContent = was, 1200);
  });
  bind();
  if(location.hash === '#pc-control') requestAnimationFrame(() => $('pc-control')?.scrollIntoView({block:'start', behavior:'instant'}));
}
function itemHtml(i){
  const k = i.key, e = ERR[k];
  const head = `<div class="lh"><b>${esc(i.label)}</b>${i.required?'<span class="req">REQUIRED</span>':''}${i.restart?'<span class="chip">applies after a hub restart</span>':''}<span id="st-${k}">${i.kind==='sources'?'':chip(i.status)}</span></div><div class="lp">${esc(i.purpose)}</div>`;
  // Project folders are composed by projectBoxes(): two boxes, not one list.
  const st = i.status||{};
  return `<div class="loc">${head}<div class="lin"><input type="text" data-k="${k}" value="${esc(CUR[k]||'')}" placeholder="${i.required?'':'not set'}">${i.kind==='folder'?`<button class="btn" data-browse="${k}">BROWSE</button>`:''}${st.create?`<button class="btn" data-create="${k}">CREATE</button>`:''}${!i.required&&CUR[k]?`<button class="btn" data-clear="${k}">CLEAR</button>`:''}</div>${e?`<div class="err">${esc(e)}</div>`:''}</div>`;
}
function routineRow(r){
  const when = r.updated ? new Date(r.updated*1000).toLocaleString() : '';
  const tone = r.status==='trusted' ? 'ok' : (r.status==='disabled' ? 'error' : 'warn');
  const acted = r.successes + r.failures;
  return `<div class="rt"><div class="h"><b>${esc(r.title)}</b>`
    + `<span class="chip ${tone}">${esc(r.status)}</span>`
    + `<span class="chip">${r.tool==='launch'||r.tool==='App' ? 'launch'
         : r.tool==='recipe' ? 'recipe'
         : esc(r.steps)+' step'+(r.steps===1?'':'s')}</span>`
    + (r.profile ? `<span class="chip">${esc(r.profile)}</span>` : '')
    + (r.lowest_match!=null ? `<span class="chip ${r.lowest_match>=0.9?'ok':(r.lowest_match>=0.8?'warn':'error')}">lowest match ${Math.round(r.lowest_match*100)}%</span>` : '')
    + `<span class="meta">${r.successes} ok \u00b7 ${r.failures} failed${acted?' \u00b7 last used '+esc(when):''}</span>`
    + ((r.tool==='ui'||r.tool==='surface') && r.status!=='disabled' ? `<button class="btn" data-run="${esc(r.id)}">RUN</button>` : '')
    + `<button class="btn ${r.status==='disabled'?'go':'stop'}" data-rstatus="${esc(r.id)}" data-to="${r.status==='disabled'?'candidate':'disabled'}">`
    + `${r.status==='disabled'?'ENABLE':'DISABLE'}</button></div>`
    + `<div class="steps">${esc(r.intent)}</div>`
    + `<div class="steps" id="rt-msg-${esc(r.id)}"></div></div>`;
}

function routinesCard(){
  if(ROUTINES === null) return '';
  const mcp = ROUTINES.filter(r => (r.kind||'mcp')==='mcp');
  const machine = ROUTINES.filter(r => (r.kind||'mcp')==='machine');
  const recipes = ROUTINES.filter(r => r.kind==='ingest');
  const tab = (id, label, n) => `<button class="btn ${RTAB===id?'on':''}" data-rtab="${id}">${label} (${n})</button>`;
  let body;
  if(RTAB === 'mcp'){
    body = mcp.length ? mcp.map(routineRow).join('')
      : `<div class="rt-empty">Nothing learned yet. Ask TALK to open an application and it is saved here as a
         candidate; two clean runs make it trusted.</div>`;
  } else if(RTAB === 'ingest'){
    body = recipes.length ? recipes.map(routineRow).join('')
      : `<div class="rt-empty">Nothing learned yet. The first time you ingest an app, the agent works out
         how to start it; that answer is kept here as a <b>recipe</b> for that shape of project
         (Django with a manage.py, a Node app with a package.json, and so on). The second app of the same
         shape is wired in with <b>no model call at all</b> \u2014 seconds instead of minutes.
         A recipe stores the command, not the port, so two apps of one shape never collide.</div>`;
  } else {
    body = recorderBox() + (machine.length ? machine.map(routineRow).join('')
      : `<div class="rt-empty">Nothing recorded yet. These are sequences you teach by
         <b>doing them once</b> \u2014 for games and anything else with no accessible controls. Each step remembers a
         small picture of what it clicked and finds it again before clicking, so a weak match stops instead of
         guessing. A routine carries a profile: <b>reflex</b> for gameplay (punctual, strict),
         <b>patient</b> for installs and uploads (waits for the screen, not the clock), <b>balanced</b> otherwise.</div>`);
  }
  const inner = `<div class="lp">What the hub has learned to do on this PC. A routine only replays onto the screen it was
       recorded against; if that screen changed it refuses rather than clicking blind.</div>`
    + `<div class="tabs">${tab('mcp','MCP ROUTINES',mcp.length)}${tab('machine','MACHINE ROUTINES',machine.length)}${tab('ingest','APP RECIPES',recipes.length)}</div>`
    + body;
  return fold('routines', 'Learned routines',
              `<span class="chip">${ROUTINES.length} saved</span>`, inner, false);
}

function dirty(k){
  const it = (DATA.items || []).find(i => i.key === k);
  return it ? JSON.stringify(CUR[k]) !== JSON.stringify(it.value) : false;
}

// With sections hidden, SAVE could write edits the user cannot see. Say how many
// and where, so the button never does more than it appears to.
function saveMsg(){
  const keys = (DATA.items || []).map(i => i.key).filter(dirty);
  const el = $('msg'); if(!el) return;
  if(!keys.length){ el.textContent = 'Nothing changes until you press SAVE.'; return; }
  const where = [...new Set(keys.map(k => {
    const g = (DATA.items.find(i => i.key === k) || {}).group;
    return (SECTIONS.find(x => x.group === g) || {}).label || g;
  }))];
  el.textContent = `${keys.length} unsaved change${keys.length>1?'s':''} in ${where.join(', ')}. SAVE applies all of them.`;
}

function fold(id, title, chip, body, openByDefault){
  const open = (FOLD[id] === undefined) ? !!openByDefault : FOLD[id];
  return `<div class="loc" id="${id}">`
    + `<div class="lh foldh" data-fold="${id}" data-open="${open?1:0}" role="button" tabindex="0">`
    + `<svg class="ic tw ${open?'down':''}" viewBox="0 0 24 24" fill="none" stroke="currentColor"`
    + ` stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>`
    + `<b>${title}</b>${chip}</div>`
    + (open ? `<div class="foldb">${body}</div>` : '') + `</div>`;
}

function recorderBox(){
  if(!REC) return '';
  if(!REC.available){
    return `<div class="rt-empty">${esc(REC.why || 'Recording is not available on this machine.')}</div>`;
  }
  if(REC.running){
    return `<div class="recbar live">`
      + `<span class="recdot"></span><b>RECORDING</b>`
      + `<span class="chip">${REC.steps.length} step${REC.steps.length===1?'':'s'}</span>`
      + `<span class="chip">${REC.seconds}s</span>`
      + `<span style="flex:1"></span>`
      + `<button class="btn go" id="rec-stop">STOP</button></div>`
      + `<div class="lp">Do the thing once, then press STOP \u2014 or press <b>Esc</b>, which is not recorded.
         Everything you click and type is captured while this runs, so leave passwords out of it.
         The session stops itself after ${Math.round(REC.max_seconds/60)} minutes.</div>`
      + (REC.steps.length ? `<div class="reclist">${REC.steps.map(recRow).join('')}</div>` : '');
  }
  if(REC.steps && REC.steps.length){
    const kept = REC.steps.filter(s => !RECDROP[s.ordinal]).length;
    return `<div class="recbar"><b>RECORDED</b>`
      + `<span class="chip">${kept} of ${REC.steps.length} step${REC.steps.length===1?'':'s'}</span>`
      + (REC.window ? `<span class="chip">${esc(REC.window)}</span>` : '')
      + (REC.stopped_by ? `<span class="chip">stopped by ${esc(REC.stopped_by)}</span>` : '')
      + `</div>`
      + `<div class="lp">Check it before you keep it. Drop anything you did not mean to do.</div>`
      + `<div class="reclist">${REC.steps.map(recRow).join('')}</div>`
      + `<div class="lin" style="display:flex;gap:7px;flex-wrap:wrap;margin-top:9px">`
      + `<input id="rec-name" style="flex:1 1 220px" placeholder="What does this routine do? e.g. start the daily build">`
      + `<select id="rec-profile" class="btn" style="padding:8px">`
      + `<option value="balanced">balanced \u2014 waits for the screen</option>`
      + `<option value="reflex">reflex \u2014 punctual, strict (gameplay)</option>`
      + `<option value="patient">patient \u2014 waits a long time (installs)</option>`
      + `</select>`
      + `<button class="btn go" id="rec-save">SAVE ROUTINE</button>`
      + `<button class="btn" id="rec-discard">DISCARD</button></div>`
      + (RECMSG ? `<div class="lp" style="color:var(--accent)">${esc(RECMSG)}</div>` : '');
  }
  return `<div class="lin" style="display:flex;gap:9px;align-items:center;flex-wrap:wrap">`
    + `<button class="btn go" id="rec-start">RECORD A ROUTINE</button>`
    + `<span class="lp" style="margin:0;flex:1 1 220px">Press record, do it once, press STOP.
       While it runs it sees everything you click and type, so keep passwords out of the recording.</span></div>`
    + (RECMSG ? `<div class="lp" style="color:#ff6b6b">${esc(RECMSG)}</div>` : '');
}

function recRow(s){
  const dropped = !!RECDROP[s.ordinal];
  return `<div class="recstep${dropped?' off':''}">`
    + `<span class="recnum">${s.ordinal + 1}</span>`
    + `<span class="recnote">${esc(s.note)}</span>`
    + (s.has_anchor ? `<span class="chip" title="a picture of what it clicked, matched again on replay">anchor</span>` : '')
    + (s.delay_ms > 250 ? `<span class="chip">after ${(s.delay_ms/1000).toFixed(1)}s</span>` : '')
    + `<span style="flex:1"></span>`
    + `<button class="btn" data-recdrop="${s.ordinal}">${dropped ? 'KEEP' : 'DROP'}</button></div>`;
}

function providersCard(){
  if(!KEYS) return '';
  const on = KEYS.providers.filter(p => p.configured);
  const row = (p) => {
    const open = KEYOPEN === p.id, msg = KEYMSG[p.id] || '';
    const bad = /reject|not |could not|does not/.test(msg);
    let h = `<div class="prow">`
      + `<b>${esc(p.label)}</b>`
      + (p.configured ? `<span class="chip ok">CONNECTED</span>` : '')
      + (p.hint ? `<code class="kmask">${esc(p.hint)}</code>` : '')
      + (p.checked ? `<span class="chip">checked ${new Date(p.checked*1000)
            .toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'})}</span>` : '')
      + (p.configured && !p.in_hub ? `<span class="chip">via opencode — no key held here</span>` : '')
      + `<span style="flex:1"></span>`
      + `<button class="btn" data-keyopen="${p.id}">${open ? 'CLOSE' : (p.configured ? 'REPLACE' : 'CONNECT')}</button>`
      + `</div>`;
    if(open){
      h += `<div class="pedit">`
        + `<div class="lp" style="margin:0 0 7px">Create a key at`
        + ` <a href="${esc(p.create)}" target="_blank" rel="noopener">${esc(p.create.replace(/^https:\/\//,''))} \u2197</a>,`
        + ` then paste it here.</div>`
        + `<div style="display:flex;gap:7px;flex-wrap:wrap">`
        + `<input type="password" autocomplete="off" spellcheck="false" id="key-${p.id}"`
        + ` style="flex:1 1 220px" placeholder="Paste the key">`
        + `<button class="btn go" data-keysave="${p.id}">CHECK &amp; SAVE</button>`
        + (p.in_hub ? `<button class="btn" data-keyrm="${p.id}">REMOVE</button>` : '')
        + `</div>`
        + (msg ? `<div class="lp" style="margin:7px 0 0;color:${bad?'#ff6b6b':'var(--accent)'}">${esc(msg)}</div>` : '')
        + `</div>`;
    } else if(msg){
      h += `<div class="lp" style="margin:0 0 6px;color:${bad?'#ff6b6b':'var(--accent)'}">${esc(msg)}</div>`;
    }
    return h;
  };
  const chip = on.length
    ? `<span class="chip ok">${on.map(p => esc(p.label)).join(', ')}</span>`
    : `<span class="chip">none connected</span>`;
  const body = `<div class="lp">Where Auto-LLM gets its thinking. The hub asks the provider whether a key works
       before saving it, keeps it on this PC outside your project folders, and never shows it again.
       A Claude or Codex subscription needs no key \u2014 pick that runtime on a mission instead.</div>`
    + KEYS.providers.map(row).join('')
    + (KEYS.other.length ? `<div class="lp">Also connected through opencode: ${esc(KEYS.other.join(', '))}</div>` : '');
  // Open on a machine that cannot run a mission yet; otherwise stay out of the way.
  return fold('providers', 'Model providers', chip, body, on.length === 0);
}

// Two boundaries, drawn as two boxes, because they behave differently: one is
// read for context and never written, the other is what missions copy and can
// publish a diff back into.
// Only on an installed build: from source there is no install folder to move.
function moveCard(){
  if(!MOVE || !MOVE.supported) return '';
  const r = MOVE.result;
  const chip = r === 'queued' ? '<span class="chip warn">moves on next restart</span>'
             : r === 'done'   ? '<span class="chip ok">moved</span>'
             : r === 'failed' ? '<span class="chip error">not moved</span>' : '';
  let body = `<div class="lp">Where Agent Hub itself is installed. Your settings, channels and
      automations are stored elsewhere and do not move.</div>
    <div class="lin"><input type="text" id="mv-to" value="${esc(MOVE.to || MOVE.here || '')}"
        ${r==='queued'?'disabled':''}><button class="btn" id="mv-browse">BROWSE</button></div>`;
  if(r === 'queued'){
    body += `<div class="lp">Queued. It copies, checks the copy, then removes the old folder \u2014
       close the hub to start it.</div>
      <div class="row"><button class="btn stop" id="mv-cancel">CANCEL THE MOVE</button></div>`;
  } else {
    body += `<div class="row"><button class="btn" id="mv-save">MOVE ON NEXT RESTART</button></div>`;
    if(r === 'failed') body += `<div class="err">${esc(MOVE.why||'')}</div>`;
  }
  body += `<div class="lp" id="mv-msg"></div>`;
  return fold('install', 'Install folder', chip, body, r === 'queued' || r === 'failed');
}

function projectBoxes(items){
  const srcItem = items.find(i => i.kind === 'sources');
  const wiki    = items.find(i => i.key === 'wiki_root');
  const k = srcItem ? srcItem.key : 'project_sources';
  const all = CUR[k] || [];
  const ro = all.map((s,n)=>({s,n})).filter(x => x.s.readonly);
  const rw = all.map((s,n)=>({s,n})).filter(x => !x.s.readonly);

  const dupOf = (path) => all.findIndex(s => s.path && isDup(s.path) && covers(path, s.path));
  const known = KNOWN.filter(x => x.exists && x.category === 'The hub itself')
    .map(x => { const n = dupOf(x.path);
      return `<div class="src fixed"><b>${esc(x.name)}</b><span class="chip">always</span>
       <code>${esc(x.path)}</code>
       ${n >= 0 ? `<button class="btn stop" data-rm="${n}" aria-label="Remove the duplicate row">${ic('x')}</button>` : ''}</div>`;
    }).join('');

  const box1 = `<div class="loc"><div class="lh"><b>Read-only</b>
      <span class="chip">never written to</span></div>
    <div class="lp">Read for context. Agents never change anything here.</div>
    ${known}
    ${wiki ? `<div class="src"><div class="meta"><b>${esc(wiki.label)}</b>
        <span class="chip">optional</span>
        <span class="lp" style="margin:0">An Obsidian vault of notes on your projects, read for context.</span>
        ${dupOf(CUR.wiki_root) >= 0 ? `<button class="btn stop" data-rm="${dupOf(CUR.wiki_root)}" aria-label="Remove the duplicate row">${ic('x')}</button>` : ''}</div>
        <div class="lin"><input type="text" data-k="${wiki.key}" value="${esc(CUR[wiki.key]||'')}" placeholder="not set">
          <button class="btn" data-browse="${wiki.key}">BROWSE</button>
          ${CUR[wiki.key]?`<button class="btn" data-clear="${wiki.key}">CLEAR</button>`:''}</div></div>` : ''}
    ${ro.filter(x => !isDup(x.s.path)).map(x => srcRow(k, x.s, x.n)).join('')}
    <div class="row"><button class="btn" id="add-ro">${ic('plus')}ADD A READ-ONLY FOLDER</button></div></div>`;

  const box2 = `<div class="loc" id="loc-${k}"><div class="lh"><b>Project folders</b>
      <span class="req">REQUIRED</span></div>
    <div class="lp">${esc(srcItem ? srcItem.purpose : '')}</div>
    ${rw.length ? rw.map(x => srcRow(k, x.s, x.n)).join('')
                : '<div class="lp">None yet.</div>'}
    <div class="row"><button class="btn go" id="add-col">${ic('plus')}ADD A FOLDER OF PROJECTS</button>
      <button class="btn" id="add-proj">${ic('plus')}ADD ONE PROJECT</button>
      <button class="btn" id="suggest">FIND MY PROJECTS</button></div>
    <div class="sug" id="sug"></div>${ERR[k]?`<div class="err">${esc(ERR[k])}</div>`:''}</div>`;

  return box1 + box2;
}

// A row pointing at a folder the hub already finds by itself, or at the vault's
// own repo. Marked rather than hidden: it is the user's row to remove.
function isDup(path){
  // Separators are normalised to '/' so there is no backslash literal to escape,
  // and a parent folder counts as covering the vault inside it.
  const norm = (x) => String(x||'').split(String.fromCharCode(92)).join('/')
                        .replace(/\/+$/, '').toLowerCase();
  const here = norm(path); if(!here) return false;
  const fixed = (KNOWN||[]).filter(x=>x.exists).map(x=>norm(x.path));
  const vault = norm(CUR.wiki_root);
  return fixed.some(f => covers(f, here)) || (!!vault && covers(vault, here));
}

// Does `a` sit at or inside `b`? Used to tell that a repo row covers the vault
// folder within it, which is the same thing listed at two depths.
function covers(a, b){
  const norm = (x) => String(x||'').split(String.fromCharCode(92)).join('/')
                        .replace(/\/+$/, '').toLowerCase();
  const A = norm(a), B = norm(b);
  return !!A && !!B && (A === B || A.startsWith(B + '/'));
}

function srcRow(k, s, n){
  const item = (DATA.items||[]).find(i => i.key === k) || {};
  return `<div class="src" data-n="${n}">
    <div class="lin"><input type="text" data-src="${n}" data-f="path" value="${esc(s.path)}">
      <button class="btn" data-browse-src="${n}">BROWSE</button>
      <button class="btn stop" data-rm="${n}" aria-label="Remove">${ic('x')}</button></div>
    <div class="meta"><select data-src="${n}" data-f="kind">
        <option value="collection" ${s.kind==='collection'?'selected':''}>a folder full of projects</option>
        <option value="project" ${s.kind==='project'?'selected':''}>one project</option></select>
      <label class="ck"><input type="checkbox" data-src="${n}" data-f="readonly" ${s.readonly?'checked':''}> read-only</label>
      ${isDup(s.path)?'<span class="chip warn">already above</span>':''}
      ${chip((item.sources_status||[])[n])}</div></div>`;
}

function themeCard(){
  if(!THEME) return '<div class="loc"><div class="lp">Could not load the theme.</div></div>';
  const cur = THEME.name, cols = THEME.name==='custom' ? THEME.custom : THEME.colors;
  const pick = THEME.themes.map(t =>
    `<label class="trow"><input type="radio" name="th" value="${t.name}" ${t.name===cur?'checked':''}>`
    + `<b>${esc(t.label)}</b></label>`).join('');
  const swatches = THEME.tokens.map(t =>
    `<label class="sw"><input type="color" data-col="${t.key}" value="${esc(cols[t.key]||t.default)}">`
    + `<b>${esc(t.label)}</b></label>`).join('');
  const body = `<div class="themes">${pick}</div>`
    + `<div id="custom-wrap" style="${cur==='custom'?'':'display:none'}">
         <div class="sws">${swatches}</div>
         <div class="row"><button class="btn" id="th-reset">RESET</button></div></div>`;
  return fold('appearance', 'Theme', `<span class="chip ok">${esc((THEME.themes.find(t=>t.name===cur)||{}).label||cur)}</span>`, body, true);
}

function ytCard(){
  if(!YTA) return '';
  const bad = /not |could not|already|cannot|reserved|use letters|needs a name/i.test(YTMSG);
  const row = (a) => `<div class="prow"><b>${esc(a.tag)}</b>`
    + (a.authorized ? `<span class="chip ok">SIGNED IN</span>`
                    : `<span class="chip">signs in on first upload</span>`)
    + (a.where === 'local_settings.py' ? `<span class="chip">from local_settings.py</span>` : '')
    + `<span style="flex:1"></span>`
    + (a.where === 'folder' ? `<button class="btn" data-ytrm="${esc(a.tag)}">REMOVE</button>` : '')
    + `</div>`;
  let body = `<div class="lp">Channels this PC can upload to. Each one keeps its own Google sign-in,
       stored here and nowhere else \u2014 an update leaves them signed in. Removing a channel forgets it
       on this PC only; it does not touch anything at Google.</div>`;
  body += YTA.length ? YTA.map(row).join('')
                     : `<div class="lp">No channels yet. Add one to turn on uploading.</div>`;
  body += `<div class="prow"><span style="flex:1"></span>`
    + `<button class="btn" id="yt-open">${YTOPEN ? 'CLOSE' : 'ADD A CHANNEL'}</button></div>`;
  if(YTOPEN){
    body += `<div class="pedit">`
      + `<div class="lp" style="margin:0 0 7px">In`
      + ` <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">Google Cloud Console \u2197</a>`
      + ` enable <b>YouTube Data API v3</b>, then create an OAuth client ID of type <b>Desktop app</b>`
      + ` and download its JSON. Name the channel whatever you will recognise on the upload screen.</div>`
      + `<div style="display:flex;gap:7px;flex-wrap:wrap">`
      + `<input type="text" id="yt-tag" style="flex:1 1 160px" placeholder="Channel name, e.g. My Channel"`
      + ` spellcheck="false" autocomplete="off">`
      + `<input type="file" id="yt-file" accept="application/json,.json" style="flex:1 1 200px">`
      + `<button class="btn go" id="yt-save">ADD</button></div>`
      + (YTMSG ? `<div class="lp" style="margin:7px 0 0;color:${bad?'#ff6b6b':'var(--accent)'}">${esc(YTMSG)}</div>` : '')
      + `</div>`;
  } else if(YTMSG){
    body += `<div class="lp" style="margin:0 0 6px;color:${bad?'#ff6b6b':'var(--accent)'}">${esc(YTMSG)}</div>`;
  }
  const chip = YTA.length ? `<span class="chip ok">${YTA.length} channel${YTA.length>1?'s':''}</span>`
                          : `<span class="chip">none added</span>`;
  return fold('ytacc', 'YouTube channels', chip, body, false);
}

function extraTools(){
  let h = '';
  const w = MCPS.find(x => x.name==='windows');
  h += `<div class="loc" id="pc-control"><div class="lh"><b>PC control (Windows MCP)</b>${w ? `<span class="chip ${w.enabled?'warn':'ok'}">${w.enabled?'ON':'off'}</span>${w.installed?'':'<span class="chip error">program missing</span>'}` : '<span class="chip">not set up</span>'}</div>
    <div class="lp">Lets agents click, type and use your desktop. Off by default — switch it on only while you need it.</div>
    ${w && w.excluded_tools && w.excluded_tools.length ? `<div class="lp" style="margin-top:-4px">Excluded: ${esc(w.excluded_tools.join(', '))}.</div>` : ''}
    ${w && w.installed ? `<div class="row"><button class="btn" id="mcp-probe">LIST ITS TOOLS (SAFE TEST)</button><button class="btn ${w.enabled?'stop':'go'}" id="mcp-toggle">${w.enabled?'SWITCH OFF':'SWITCH ON'}</button><span class="lp" style="margin:0">applies to the next step</span></div>` : '<div class="lp">Not installed on this machine.</div>'}</div>`;
  if(HTTPS && HTTPS.available){
    h += `<div class="loc"><div class="lh"><b>Phone microphone and sound (https)</b><span class="chip ${HTTPS.serving?'ok':'warn'}">${HTTPS.serving?'https is on':'not set up'}</span></div>
      <div class="lp">The microphone needs https. Open this on your phone:</div>
      <div class="lin"><input type="text" readonly value="${esc(HTTPS.url)}" id="https-url"><button class="btn" id="https-copy">COPY</button></div>
      ${HTTPS.serving ? '' : `<div class="lp" style="margin-top:8px">Not serving yet. Run this once in a terminal on this PC: <code>${esc(HTTPS.command)}</code></div>`}</div>`;
  }
  h += routinesCard();
  return h;
}
let vt = {};
function bind(){
  document.querySelectorAll('input[data-k]').forEach(inp => inp.oninput = () => { CUR[inp.dataset.k] = inp.value; saveMsg(); clearTimeout(vt[inp.dataset.k]);
    vt[inp.dataset.k] = setTimeout(async () => { try{ const r = await jsend('POST','/api/locations/validate',{key:inp.dataset.k,value:inp.value}); $('st-'+inp.dataset.k).innerHTML = chip(r); }catch(e){} }, 400); });
  document.querySelectorAll('[data-src]').forEach(el => el.onchange = el.oninput = () => { const n = +el.dataset.src, f = el.dataset.f; CUR.project_sources[n][f] = el.type==='checkbox' ? el.checked : el.value; });
  const mvb = $('mv-browse'); if(mvb) mvb.onclick = () => pick($('mv-to').value, p => { $('mv-to').value = p; });
  const mvs = $('mv-save'); if(mvs) mvs.onclick = async () => {
    try{ await jsend('POST','/api/install-move',{to:$('mv-to').value});
         MOVE = await jget('/api/install-move'); render(); toast('Queued for the next restart'); }
    catch(e){ $('mv-msg').innerHTML = '<span style="color:var(--red)">'+esc(e.message)+'</span>'; }
  };
  const mvc = $('mv-cancel'); if(mvc) mvc.onclick = async () => {
    await jsend('POST','/api/install-move',{cancel:true});
    MOVE = await jget('/api/install-move'); render(); };
  const aro = $('add-ro'); if(aro) aro.onclick = () => {
    CUR.project_sources = [...(CUR.project_sources||[]), {path:'', kind:'project', readonly:true}];
    render(); };
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
// The hash names the section, so a bookmark or a typed #files has to move the
// page even though changing it never reloads anything.
window.addEventListener('hashchange', () => {
  const want = (location.hash || '').replace('#','');
  if(want && want !== SEC && SECTIONS.some(x => x.id === want)){ SEC = want; render(); }
});

load().catch(e => { $('main').innerHTML = '<div class="err">Could not load locations: '+esc(e.message)+'</div>'; });
</script></body></html>"""


@routes.get("/setup")
async def setup_page(request: web.Request) -> web.Response:
    return web.Response(text=_HTML, content_type="text/html", headers={"Cache-Control": "no-store"})
