"""Agents — persona management (a real page, one top bar).

Lists the baseline + user personas with their **effective** LLM settings (never
blank), lets you edit those, and has a dedicated Create-Agent flow where
`agent-smith` drafts the persona prompt from a plain-language description.

Reads:
  GET    /api/agents                       personas (+ settings) + models
  POST   /api/opencode/agents/{name}/settings   {model,temperature,top_p,variant,steps}
  POST   /api/opencode/agents              {name, text}    save a user persona
  DELETE /api/opencode/agents/{name}
  POST   /api/agents/draft                 {description} -> {markdown}
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

# Agent Smith icon — cyan neon line-art bust, matted to transparency from the user's
# reference photo (background removed by isolating the cyan glow channel).
_SMITH_B64 = (
    "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"
)

_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#080c28">
<title>AGENT HUB — Agents</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c28;--bg-mid:#0d1050;--panel:rgba(8,12,40,0.88);
  --border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);
  --red:#ff5c5c;--amber:#e0a53c;--blue:#3ba7ff;
}
html{min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
html,body{min-height:100%;font-family:'Outfit',system-ui,sans-serif;color:var(--text)}
body{max-width:900px;margin:0 auto;padding:0 16px 60px}
a{color:var(--accent);text-decoration:none}
button,input,select,textarea{font-family:'Outfit',inherit}
.bar{display:flex;align-items:center;gap:10px;padding:14px 0;border-bottom:1px solid var(--border-dim);flex-wrap:wrap;position:sticky;top:0;background:linear-gradient(#080c28,#080c28ee);z-index:5}
.brand{font-family:'Orbitron',monospace;font-weight:900;letter-spacing:3px;font-size:13px;color:var(--accent)}
.spacer{flex:1}
.btn{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1px;padding:9px 13px;min-height:36px;border-radius:6px;
  display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;white-space:nowrap;transition:all .15s}
.btn:hover:not(:disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn.stop{border-color:rgba(255,92,92,.5);color:var(--red)}
.btn.go{border-color:var(--accent);background:rgba(0,230,118,.12)}
.persona{background:var(--panel);border:1px solid var(--border-dim);border-radius:10px;padding:14px;margin:12px 0}
.pn{font-weight:600;font-size:14px;display:flex;align-items:center;gap:8px}
.pd{font-size:12px;color:var(--text-muted);margin-top:4px}
.tag{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:.5px;padding:2px 7px;border-radius:999px;border:1px solid var(--border-dim);color:var(--text-muted)}
.tag.primary{border-color:var(--amber);color:var(--amber)}
.tag.user{border-color:var(--blue);color:var(--blue)}
.settings{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:10px;font-size:12px}
.settings .s{border:1px solid var(--border-dim);border-radius:7px;padding:7px 9px}
.settings .s .k{font-family:'Orbitron',monospace;font-size:7.5px;letter-spacing:1px;color:var(--text-faint)}
.settings .s .v{margin-top:2px}
.settings .s .src{font-size:9px;color:var(--text-faint)}
.src.override{color:var(--accent)}
pre.def{background:var(--bg);border:1px solid var(--border-dim);border-radius:7px;padding:10px;margin-top:9px;
  font-size:11px;white-space:pre-wrap;max-height:280px;overflow:auto;display:none}
label{display:block;font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1px;color:var(--text-faint);margin:12px 0 5px}
input[type=text],input[type=number],select,textarea{width:100%;background:var(--bg);border:1px solid var(--border-dim);color:var(--text);
  border-radius:6px;padding:8px 9px;font-size:13px;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
textarea{min-height:200px;resize:vertical;font-family:ui-monospace,Consolas,monospace}
.editrow{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;z-index:20}
.scrim.open{display:block}
.modal{position:fixed;top:5vh;left:50%;transform:translateX(-50%);width:640px;max-width:94vw;max-height:88vh;overflow-y:auto;
  background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:12px;padding:18px;z-index:21;display:none}
.modal.open{display:block}
.modal h2{font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1.5px;color:var(--accent);margin-bottom:6px}
.note{font-size:11px;color:var(--amber);margin-top:8px}
.smith{width:22px;height:22px;vertical-align:-6px;margin-right:7px;flex:none}
.btn-icon{display:inline-flex;align-items:center;justify-content:center;position:relative;
  width:52px;height:52px;min-height:52px;border-radius:14px;flex:none;padding:0;
  border:1px solid var(--border-bright);background:rgba(0,230,118,.1);cursor:pointer;transition:all .15s}
.btn-icon:hover{background:rgba(0,230,118,.18);box-shadow:0 0 14px rgba(0,230,118,.28)}
.btn-icon .smith-lg{width:38px;height:38px;display:block}
.btn-icon .plus-badge{position:absolute;right:-5px;bottom:-5px;width:22px;height:22px;border-radius:50%;
  background:var(--accent);border:2px solid var(--bg-mid);display:flex;align-items:center;justify-content:center;
  color:#04160c;font-weight:900;font-size:15px;line-height:1;font-family:'Outfit',sans-serif}
.explain{background:var(--panel);border:1px solid var(--border-dim);border-radius:10px;margin:12px 0;overflow:hidden}
.explain summary{cursor:pointer;padding:11px 14px;font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--text-muted);list-style:none}
.explain summary::-webkit-details-marker{display:none}
.explain summary::before{content:'▸ ';color:var(--text-faint)}
.explain[open] summary::before{content:'▾ '}
.explain .body{padding:2px 16px 14px;font-size:12px;line-height:1.65;color:var(--text-muted)}
.explain .body b{color:var(--text);font-weight:600}
.explain ol{margin:6px 0 6px 18px}
.explain code{background:var(--bg);border:1px solid var(--border-dim);border-radius:4px;padding:1px 5px;font-size:11px}
.ck input{min-width:20px;min-height:20px}
@media (max-width:720px){
  .bar{gap:8px}
  .bar .btn{flex:1 1 auto;min-width:calc(50% - 8px)}
  .bar .brand{flex-basis:100%}
  .pn{flex-wrap:wrap}
  .pn .btn{flex:1 1 auto}
  .editrow{grid-template-columns:1fr 1fr}
}
</style></head>
<body>
<div class="bar">
  <a class="btn" href="/">← HUB</a>
  <span class="brand">AGENTS</span>
  <button class="btn-icon" id="btn-create" title="Create agent" aria-label="Create agent">__SMITH_ICON_BIG__<span class="plus-badge">+</span></button>
  <span class="spacer"></span>
  <a class="btn" href="/missions">MISSIONS</a>
  <a class="btn" href="/graph">GRAPH</a>
</div>
<div style="font-size:11px;color:var(--text-muted);margin:12px 0">
  Personas ship in the repo (<code>hub/agent_knowledge/agents/</code>) and are copied into every
  mission's private working copy. Yours (blue) live in <code>agents_user/</code>. LLM settings save to
  <code>agent_overrides.json</code> and apply on the next mission dispatch.
</div>

<details class="explain">
  <summary>How these values are chosen</summary>
  <div class="body">
    Value in effect = your <b>override</b> (set below) → the agent's <b>persona</b> default →
    the model's own default. <b>temperature</b>: low = repeatable, higher = more varied.
    <b>steps</b> caps tool calls per run. Each agent's own reason for its numbers is on its card.
    <div id="mpol" style="margin-top:8px"></div>
  </div>
</details>

<div id="list"></div>

<div class="scrim" id="scrim"></div>
<div class="modal" id="modal">
  <h2 id="modal-title">CREATE AGENT</h2>
  <label>Name</label><input type="text" id="c-name" placeholder="sql-migration-reviewer">
  <label>When to use it (one line)</label><input type="text" id="c-desc" placeholder="Reviews SQL migrations for backwards-incompatible changes.">
  <div class="editrow">
    <div><label>Mode</label><select id="c-mode"><option value="all">all (usable solo + as subagent)</option><option value="subagent">subagent</option><option value="primary">primary</option></select></div>
    <div><label>bash</label><select id="c-bash"><option>ask</option><option>allow</option><option>deny</option></select></div>
    <div><label>skills (comma patterns)</label><input type="text" id="c-skills" placeholder="sql-*, *" value="*"></div>
  </div>
  <label>Prompt body</label>
  <textarea id="c-body" placeholder="Who this agent is, its method step by step, what &quot;done&quot; looks like, hard rules…"></textarea>
  <div class="row"><button class="btn" id="c-draft">✨ DRAFT WITH AGENT-SMITH</button><span class="note" id="c-drafting" style="display:none">agent-smith is drafting… (up to a couple of minutes on a free model)</span></div>
  <div class="row" style="margin-top:14px;display:flex;gap:8px">
    <button class="btn go" id="c-save">SAVE</button>
    <button class="btn" id="c-cancel">cancel</button>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function jget(u){ const r=await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(u,b){ const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){j={raw:t}} if(!r.ok) throw new Error(j.raw||t); return j; }
let DATA = null;

async function load(){
  DATA = await jget('/api/agents');
  try {
    const mp = await jget('/api/model-policy');
    $('mpol').innerHTML = `<b>Model:</b> policy <code>${esc(mp.policy)}</code> → runs use `
      + `<code>${esc(mp.resolved)}</code>. Free-cloud (<code>opencode/*</code>) is slow and has no `
      + `SLA; a run that hits a 502 auto-retries then falls back to <code>${esc(mp.fast_free)}</code> `
      + `→ <code>${esc(mp.local)}</code>. <code>ollama/*</code> runs on this machine. `
      + (mp.has_paid_key ? `A paid provider key is configured — <code>auto</code> uses it.`
                         : `Add a provider key (<code>opencode auth login</code>) and set policy <code>auto</code> for fast, reliable runs.`);
  } catch(e){ $('mpol').textContent=''; }
  const prim = (DATA.team||{}).primary;
  $('list').innerHTML = (DATA.personas||[]).map(p => {
    const isP = p.name===prim || p.mode==='primary';
    const s = p.settings || {};
    const cell = (k,label) => { const o=s[k]||{}; return `<div class="s" title="${esc(o.note||o.source||'')}"><div class="k">${label}</div>
      <div class="v">${esc(o.value!=null?o.value:(o.note||'default'))}</div>
      <div class="src ${o.source==='override'?'override':''}">${esc(o.source||'')}</div></div>`; };
    return `<div class="persona">
      <div class="pn">${esc(p.name)}
        <span class="tag ${isP?'primary':''}">${esc(p.mode)}</span>
        ${p.origin==='user'?'<span class="tag user">yours</span>':''}
        <span style="flex:1"></span>
        <button class="btn" onclick="editAgent('${esc(p.name)}')">EDIT SETTINGS</button>
        <button class="btn" onclick="editWithAI('${esc(p.name)}')">__SMITH_ICON__EDIT WITH AI</button>
        <button class="btn" onclick="toggleDef('${esc(p.name)}')">DEFINITION</button>
        ${p.origin==='user'?`<button class="btn stop" onclick="delAgent('${esc(p.name)}')">DELETE</button>`:''}
      </div>
      <div class="pd">${esc(p.description||'')}</div>
      <div class="settings">
        ${cell('model','MODEL')}${cell('temperature','TEMPERATURE')}${cell('top_p','TOP_P')}${cell('steps','MAX STEPS')}${cell('variant','REASONING')}
      </div>
      ${p.rationale?`<div style="font-size:11px;color:var(--text-faint);margin-top:7px">↳ ${esc(p.rationale)}</div>`:''}
      <div id="edit-${esc(p.name)}" style="display:none;margin-top:10px">
        <div class="editrow">
          <div><label>model</label><select id="e-model-${esc(p.name)}"></select></div>
          <div><label>temperature</label><input type="number" step="0.05" id="e-temp-${esc(p.name)}"></div>
          <div><label>top_p</label><input type="number" step="0.05" id="e-topp-${esc(p.name)}"></div>
          <div><label>max steps</label><input type="number" id="e-steps-${esc(p.name)}"></div>
          <div><label>reasoning</label><select id="e-var-${esc(p.name)}"><option value="">default</option><option>low</option><option>medium</option><option>high</option></select></div>
        </div>
        <button class="btn go" style="margin-top:8px" onclick="saveAgent('${esc(p.name)}')">SAVE SETTINGS</button>
        <span class="note">Applies on the next mission dispatch.</span>
      </div>
      <pre class="def" id="def-${esc(p.name)}">${esc(p.body||'')}</pre>
    </div>`;
  }).join('');
}
window.toggleDef = (n) => { const e=$('def-'+n); e.style.display = e.style.display==='block'?'none':'block'; };
window.delAgent = async (n) => { if(!confirm('Delete your agent "'+n+'"?'))return;
  await fetch('/api/opencode/agents/'+encodeURIComponent(n),{method:'DELETE'}); load(); };
window.editAgent = (n) => {
  const box=$('edit-'+n); const open = box.style.display!=='block'; box.style.display = open?'block':'none';
  if(!open) return;
  const p = DATA.personas.find(x=>x.name===n); const ov = p.frontmatter||{}; const s=p.settings||{};
  const cur = (k)=> (s[k]&&s[k].source==='override') ? s[k].value : '';
  const sel = $('e-model-'+n);
  sel.innerHTML = '<option value="">— default —</option>' + (DATA.models||[]).map(m=>`<option value="${esc(m.id)}">${esc(m.id)}${m.local?' · local':''}</option>`).join('');
  sel.value = cur('model'); $('e-temp-'+n).value = cur('temperature'); $('e-topp-'+n).value = cur('top_p');
  $('e-steps-'+n).value = cur('steps'); $('e-var-'+n).value = cur('variant');
};
window.saveAgent = async (n) => {
  const patch = { model:$('e-model-'+n).value||null, temperature:$('e-temp-'+n).value||null,
    top_p:$('e-topp-'+n).value||null, steps:$('e-steps-'+n).value||null, variant:$('e-var-'+n).value||null };
  await jpost('/api/opencode/agents/'+encodeURIComponent(n)+'/settings', patch);
  await load();
};

// ── create / edit with agent-smith ───────────────────────────────────────
let EDIT_BASE = null;   // when editing an existing persona: its current .md text
function openModal(title){ $('modal-title').textContent = title || 'CREATE AGENT';
  $('scrim').classList.add('open'); $('modal').classList.add('open'); }
function closeModal(){ $('scrim').classList.remove('open'); $('modal').classList.remove('open'); EDIT_BASE=null; }
$('btn-create').onclick = () => { EDIT_BASE=null; $('c-name').disabled=false;
  $('c-name').value=$('c-desc').value=$('c-body').value=''; $('c-desc').placeholder='Reviews SQL migrations for backwards-incompatible changes.';
  openModal('CREATE AGENT'); };
$('c-cancel').onclick = closeModal; $('scrim').onclick = closeModal;
window.editWithAI = (n) => {
  const p = DATA.personas.find(x=>x.name===n); if(!p) return;
  const fm = p.frontmatter || {};
  const full = '---\n' + Object.entries(fm).map(([k,v])=>`${k}: ${typeof v==='string'?JSON.stringify(v):JSON.stringify(v)}`).join('\n')
             + '\n---\n\n' + (p.body||'');
  EDIT_BASE = full;
  $('c-name').value = n; $('c-name').disabled = true;
  $('c-desc').value = ''; $('c-desc').placeholder = 'What to change — e.g. "also flag missing DOWN migrations" / "be terser"';
  $('c-body').value = full;
  openModal('EDIT ' + n.toUpperCase() + ' WITH AGENT-SMITH');
};
$('c-draft').onclick = async () => {
  const desc = $('c-desc').value.trim() || (EDIT_BASE ? '' : $('c-name').value.trim());
  if(!desc){ $('c-desc').focus(); return; }
  $('c-draft').disabled = true; $('c-drafting').style.display='inline';
  try {
    const r = await jpost('/api/agents/draft', {description: desc, base: EDIT_BASE || undefined});
    if (r.markdown) $('c-body').value = r.markdown;
    else alert('agent-smith did not produce a clean draft:\n\n'+(r.raw||'').slice(0,600));
  } catch(e){ alert('Draft failed: '+e.message); }
  $('c-draft').disabled = false; $('c-drafting').style.display='none';
};
$('c-save').onclick = async () => {
  const name = $('c-name').value.trim();
  if(!name){ $('c-name').focus(); return; }
  let body = $('c-body').value.trim();
  let text;
  if (body.startsWith('---')) {           // agent-smith gave a full file
    text = body;
  } else {
    const fm = ['---',
      'description: ' + JSON.stringify($('c-desc').value.trim() || name),
      'mode: ' + $('c-mode').value,
      'bash: ' + $('c-bash').value,
      'skills: ' + JSON.stringify($('c-skills').value.trim() || '*'),
      'steps: 15', '---', '', body || ('You are ' + name + '.')].join('\n');
    text = fm;
  }
  try {
    await jpost('/api/opencode/agents', {name, text});
    closeModal(); $('c-name').value=$('c-desc').value=$('c-body').value='';
    await load();
  } catch(e){ alert('Save failed: '+e.message); }
};
load();
</script>
</body></html>
"""

_HTML = (_HTML
    .replace("__SMITH_ICON__", f'<img class="smith" src="data:image/png;base64,{_SMITH_B64}" alt="">')
    .replace("__SMITH_ICON_BIG__", f'<img class="smith-lg" src="data:image/png;base64,{_SMITH_B64}" alt="">')
)


@routes.get("/agents")
async def agents_page(request: web.Request) -> web.Response:
    # old workspace-chat deep links (`/agents?slug=`) now just land on management
    return web.Response(text=_HTML, content_type="text/html", charset="utf-8")
