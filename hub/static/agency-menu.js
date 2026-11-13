/* Agency presentation. Existing persona/skill actions remain in agents_ui.py. */
let AG_CARD=null,AG_FAMS=[],AG_POLICY={policy:'auto',resolved:''};
let AG_TAB=location.hash==='#skills'?'skills':'agents',AG_QUERY='',AG_SCOPE=location.hash==='#helpers'?'helpers':'all',AG_WORK='',AG_SKILL_QUERY='';
let AG_OPEN=new Set(),AG_OVERVIEW=location.hash==='#map';
function agShort(s,n=110){s=String(s||'').replace(/\s+/g,' ').trim();return s.length>n?s.slice(0,n-1)+'…':s;}
function agNode(id){return (AGENTMAP?.nodes||[]).find(n=>n.id===id);}
function agLinks(id){
 const edges=AGENTMAP?.edges||[],name=i=>agNode(i)?.name||i;
 const to=[...new Set(edges.filter(e=>e.from===id).map(e=>e.to))],from=[...new Set(edges.filter(e=>e.to===id).map(e=>e.from))];
 return {to,from,html:to.slice(0,3).map(i=>`<span class="tag" title="Hands work to ${esc(name(i))}">To ${esc(name(i))}</span>`).join('')+from.slice(0,2).map(i=>`<span class="tag" title="Receives work from ${esc(name(i))}">From ${esc(name(i))}</span>`).join('')};
}
function agRelations(id){const x=agLinks(id),name=i=>agNode(i)?.name||i,c=AGENTMAP?.coverage?.[id];return `<section class="ag-relationships"><h3>Works with</h3><p><b>Hands work to:</b> ${x.to.map(name).map(esc).join(', ')||'No callers declared'}</p><p><b>Receives work from:</b> ${x.from.map(name).map(esc).join(', ')||'No callers declared'}</p>${c?`<p><b>Learning:</b> ${esc(c.state)} — ${esc(c.note||'')}</p>`:''}</section>`;}
function agModelChoices(){const a=[{id:'auto',name:'Auto'},{id:'free-cloud',name:'Free cloud'},{id:'local',name:'Local'}],seen=new Set(a.map(x=>x.id));for(const m of DATA?.models||[])if(!seen.has(m.id)){a.push(m);seen.add(m.id);}return a;}
function agAgentOptions(p){
 const o=p.settings?.model||{},own=o.source==='override'||o.source==='persona',resolved=AG_POLICY.resolved||DATA.workspace_model||'default';
 let html=`<option value="">Follows all agents (${esc(resolved)})</option>`;
 const models=(DATA.models||[]).slice();if(own&&o.value&&!models.some(m=>m.id===o.value))models.push({id:o.value,name:o.value});
 html+=models.map(m=>`<option value="${esc(m.id)}" ${own&&m.id===o.value?'selected':''}>${esc(m.name||m.id)}</option>`).join('');return html;
}
// Victor is the name, Orchestrator the designation; the id stays 'orchestrator' (files, missions, settings).
const AG_ICON={'agent-smith':'neo'};
function agCompact(p){
 const id=p.name,open=AG_OPEN.has(id),links=agLinks(id),o=p.settings?.model||{},own=o.source==='override'||o.source==='persona';
 return `<article class="ag-entry" data-agent="${esc(id)}"><div class="ag-summary"><button type="button" class="ag-expand" data-ag-expand="${esc(id)}" aria-expanded="${open}"><img src="/static/agent-icons/${esc(AG_ICON[id]||id)}.png" alt="" onerror="this.hidden=true"><span class="ag-copy"><b>${esc((p.display||AG_ICON[id]||id).toLowerCase())}</b><span class="ag-role" title="${esc(p.description||'')}">${esc((p.designation?p.designation+'. ':'')+agShort(p.frontmatter?.about||p.description))}</span><span class="ag-chips">${links.html}</span></span></button><div class="ag-model"><label for="model-${esc(id)}">Model</label><select id="model-${esc(id)}" data-agent-model="${esc(id)}" aria-label="Model for ${esc(id)}">${agAgentOptions(p)}</select><span class="ag-source ${own?'own':''}" data-model-source>${own?(o.source==='override'?'Own model':'Persona model'):'Follows all agents'}</span><button type="button" class="btn ag-reset" data-model-reset="${esc(id)}" ${o.source==='override'?'':'hidden'}>RESET</button></div></div><div class="ag-full" ${open?'':'hidden'}>${agRelations(id)}${AG_CARD(p)}</div></article>`;
}
function agHelperModel(h){
 if(!h.model)return '<div class="ag-model"><label>Model</label><span class="ag-source">none of its own</span></div>';
 const m=h.model;return `<div class="ag-model"><label for="hm-${esc(h.id)}">Model</label><select id="hm-${esc(h.id)}" data-helper-model="${esc(h.id)}" aria-label="Model for ${esc(h.name)}"><option value="">Follows the Hub order (${esc(m.effective||'default')})</option>${m.options.map(o=>`<option value="${esc(o)}" ${o===m.current?'selected':''}>${esc(o)}</option>`).join('')}</select><span class="ag-source ${m.current?'own':''}">${m.current?'Own model':'Follows the Hub order'}</span></div>`;
}
document.addEventListener('change',async e=>{const s=e.target.closest&&e.target.closest('[data-helper-model]');if(!s)return;const err=document.getElementById('agency-model-error');try{await jpost('/api/hub/helpers/'+encodeURIComponent(s.dataset.helperModel)+'/model',{model:s.value});HELPERS=(await jget('/api/hub/helpers')).helpers||[];agPaintList();}catch(x){if(err)err.textContent='Model not saved: '+x.message;}});
function agHelper(h){const id=h.id||h.icon,key='helper:'+id,open=AG_OPEN.has(key);return `<article class="ag-entry" data-helper="${esc(id)}"><div class="ag-summary"><button type="button" class="ag-expand" data-ag-expand="${esc(key)}" aria-expanded="${open}">${helperIcon(h.icon)}<span class="ag-copy"><b>${esc(h.name)}</b><span class="ag-role">${esc(agShort(h.does))}</span><span class="ag-chips">${agLinks(id).html}<span class="tag">${esc(h.state)}</span></span></span></button>${agHelperModel(h)}</div><div class="ag-full" ${open?'':'hidden'}>${agRelations(id)}${helperCard(h)}</div></article>`;}
function agOverview(){
 const m=AGENTMAP;if(!m)return '<p>Agent relationships could not be read.</p>';
 const name=id=>agNode(id)?.name||id,by={};for(const e of m.edges)(by[e.from]||=[]).push(e);
 return `<h3>WHO CALLS WHOM</h3><div class="ag-table"><table><thead><tr><th>Agent</th><th>Hands work to</th></tr></thead><tbody>${Object.keys(by).map(id=>`<tr><td>${esc(name(id))}</td><td>${by[id].map(e=>esc(name(e.to))).join(', ')}</td></tr>`).join('')}</tbody></table></div><h3>WHAT THE LEARNERS CAN SEE</h3><p>${m.complete?'Every agent has a coverage decision.':'Some agents need a coverage decision.'} Declared learning gaps: ${(m.gaps||[]).length}.</p><div class="ag-table"><table><thead><tr><th>Agent</th><th>State</th><th>Why</th></tr></thead><tbody>${m.nodes.map(n=>{let c=m.coverage[n.id]||{};return `<tr><td>${esc(n.name)}</td><td>${esc(c.state||'not decided')}</td><td>${esc(c.note||'')}</td></tr>`}).join('')}</tbody></table></div>`;
}
// An opened agent shows its editable controls (model, temperature, top_p, max steps, reasoning) at once, not behind a second SETTINGS press.
function agOpenEditor(key){
 if(String(key).startsWith('helper:')||!window.editAgent)return;
 const box=document.getElementById('edit-'+key);if(!box)return;
 if(box.style.display!=='block')window.editAgent(key);
 return;        // the controls are on the card now (agControls); the editor keeps the persona text
 // Sliders with a live value beside each, and every change saved at once with a visible SAVED / ERROR mark (no second SAVE press, nothing to double-click).
 const $e=id=>document.getElementById(id),temp=$e('e-temp-'+key),topp=$e('e-topp-'+key),steps=$e('e-steps-'+key),vari=$e('e-var-'+key),model=$e('e-model-'+key),row=box.querySelector('.editrow');
 const p=(DATA.personas||[]).find(x=>x.name===key),eff=k=>{const o=(p&&p.settings&&p.settings[k])||{};return o.value;};
 const wrap=document.createElement('div');wrap.className='ag-sliders';
 const mk=(label,input,min,max,step,fallback,hint)=>{const d=document.createElement('div'),out=document.createElement('output'),r=document.createElement('input');r.type='range';r.min=min;r.max=max;r.step=step;
   const start=input.value!==''?input.value:(fallback!=null?fallback:min);r.value=start;out.textContent=input.value!==''?input.value:(fallback!=null?fallback+' (default)':'default');
   r.oninput=()=>{out.textContent=r.value;input.value=r.value;};r.onchange=()=>{input.value=r.value;save();};
   const l=document.createElement('label');l.append(label,out);d.append(l,r);if(hint){const h=document.createElement('small');h.textContent=hint;d.append(h);}return d;};
 wrap.append(mk('TEMPERATURE',temp,0,2,.05,eff('temperature'),'low = repeatable, high = varied'),mk('TOP_P',topp,0,1,.05,eff('top_p'),'how much of the likely words it may pick from'),mk('MAX STEPS',steps,1,60,1,eff('steps'),'tool calls per run'));
 const status=document.createElement('div');status.className='ag-saved';status.textContent='CHANGES SAVE AT ONCE';wrap.append(status);
 row.parentNode.insertBefore(wrap,row);row.style.display='none';
 // model and reasoning stay as dropdowns, visible beside the sliders
 const sel=document.createElement('div');sel.className='ag-sliders';[['MODEL',model],['REASONING',vari]].forEach(([t,el])=>{const d=document.createElement('div'),l=document.createElement('label');l.textContent=t;el.remove();d.append(l,el);sel.append(d);});
 wrap.parentNode.insertBefore(sel,wrap);
 let timer=0;const save=()=>{clearTimeout(timer);status.className='ag-saved';status.textContent='SAVING...';timer=setTimeout(async()=>{
   try{await jpost('/api/opencode/agents/'+encodeURIComponent(key)+'/settings',{model:model.value||null,temperature:temp.value||null,top_p:topp.value||null,steps:steps.value||null,variant:vari.value||null});
     DATA=await jget('/api/agents');agPaintModels();status.className='ag-saved ok';status.textContent='SAVED';}catch(e){status.className='ag-saved bad';status.textContent='NOT SAVED: '+e.message;}},350);};
 model.onchange=save;vari.onchange=save;
}
// The team: the four core agents first (the ones that form the agentic team), then the operatives the orchestrator calls on, grouped by the work they do, then the other helpers of the Hub.
// Every agent that has a model of its own carries its controls on the card itself: temperature and output size at once, every other setting one press away. Nothing is removed from the card.
const AG_CORE=['orchestrator','neo','smith','doctor'],AG_CORE_NAMES={orchestrator:'orchestrator',neo:'neo',smith:'agent-smith',doctor:'doctor'};
function agPaintList(){
 if(!DATA||!AG_CARD)return;
 const q=AG_QUERY.trim().toLowerCase(),persons=DATA.personas||[],has=p=>!q||[p.name,p.description,p.frontmatter?.about].join(' ').toLowerCase().includes(q),used=new Set();
 const hasH=h=>!q||[h.name,h.does].join(' ').toLowerCase().includes(q);
 let html=`<div class="ag-overview"><button type="button" class="btn ${AG_OVERVIEW?'on':''}" data-fam="map" aria-expanded="${AG_OVERVIEW}">HOW THEY WORK TOGETHER</button><div id="agency-overview" ${AG_OVERVIEW?'':'hidden'}>${AG_OVERVIEW?agOverview():''}</div></div>`;
 const section=(name,note,items,render)=>items.length?`<section class="ag-group"><h2>${esc(name)} <span>${items.length}</span></h2>${note?`<p class="ag-note">${esc(note)}</p>`:''}<div class="ag-grid">${items.map(render).join('')}</div></section>`:'';
 if(!AG_WORK){
  // 1. the core team, in the order they work: the orchestrator splits the ask, Neo designs agents, Smith is the voice, the Doctor fixes the Hub
  const core=[];
  for(const key of AG_CORE){
   const p=persons.find(x=>x.name===(AG_CORE_NAMES[key]||key)||x.name===key),h=HELPERS.find(x=>x.id===key||x.icon===key);
   if(p){used.add(p.name);if(AG_SCOPE!=='helpers'&&has(p))core.push({kind:'persona',p});}
   else if(h&&AG_SCOPE!=='missions'&&hasH(h))core.push({kind:'helper',h});
  }
  html+=section('Core team','The four agents that form the agentic team: Victor (the orchestrator), Neo, Smith and the Doctor. Everything below is an operative they call on.',core,x=>x.kind==='persona'?agCompact(x.p):agHelper(x.h));
 }
 if(AG_SCOPE!=='helpers'){
  // 2. operatives, grouped by the work they do
  for(const [key,f] of Object.entries(PROFILES)){if(AG_WORK&&AG_WORK!==key)continue;const items=persons.filter(p=>!used.has(p.name)&&(f.roster||[]).includes(p.name)&&!p.utility).filter(has);items.forEach(p=>used.add(p.name));html+=section('Operatives: '+(f.label||key),'',items,agCompact);}
  if(!AG_WORK){const other=persons.filter(p=>!used.has(p.name)&&!p.utility).filter(has);other.forEach(p=>used.add(p.name));html+=section('Operatives: other','',other,agCompact);}
 }
 if(AG_SCOPE!=='missions'&&!AG_WORK){
  // 3. the Hub's own helpers that are not part of the core team
  const helpers=HELPERS.filter(h=>!AG_CORE.includes(h.id)&&!persons.some(p=>p.name===h.id)&&hasH(h)),util=persons.filter(p=>!used.has(p.name)&&p.utility).filter(has);
  html+=section('Hub helpers','Parts of the Hub that act for you. They are not called by Victor.',helpers,agHelper)+section('Agent design','',util,agCompact);
 }
 $('list').innerHTML=html;
 agDecorate();
 AG_OPEN.forEach(agOpenEditor);
 if(!document.querySelector('.ag-entry'))$('list').insertAdjacentHTML('beforeend','<p class="ag-empty">No agents match these filters.</p>');
}
// ---- the controls on each card
const AG_VARIANTS=['','minimal','low','medium','high','max'];
function agCtlFields(){return [
 ['temperature','TEMPERATURE','range',0,2,.05,'low = repeatable, high = varied'],
 ['num_predict','MAX OUTPUT TOKENS','number',16,32768,64,'the longest answer it may write (blank: the model\'s own limit)',true],
 ['steps','MAX STEPS','number',1,200,1,'tool calls in one run (blank: unbounded)'],
 ['top_p','TOP P','range',0,1,.05,'how much of the likely words it may pick from'],
 ['top_k','TOP K','number',1,200,1,'only the K likeliest words (blank: model default)',true],
 ['min_p','MIN P','range',0,1,.01,'drop words less likely than this share of the best one',true],
 ['num_ctx','CONTEXT WINDOW','number',1024,262144,1024,'how much text it can hold in mind at once',true],
 ['presence_penalty','PRESENCE PENALTY','range',-2,2,.1,'push it towards new topics',true],
 ['frequency_penalty','FREQUENCY PENALTY','range',-2,2,.1,'push it away from repeating itself',true],
];}
function agCtlValue(p,f){const s=p.settings||{};if(f[7])return (s.options?.value||{})[f[0]];return s[f[0]]?.value;}
function agCtlSource(p,f){const s=p.settings||{};if(f[7])return (s.options?.value||{})[f[0]]!=null?'override':'default';return s[f[0]]?.source||'default';}
function agCtlInput(p,f){
 const [key,label,kind,min,max,step,hint]=f,v=agCtlValue(p,f),src=agCtlSource(p,f),has=v!==undefined&&v!==null&&v!=='';
 if(kind==='range')return `<div class="ag-c"><label>${label} <output data-out="${key}">${has?esc(v):'default'}</output><span class="ag-src ${src}">${esc(src)}</span></label><input type="range" data-k="${key}" ${f[7]?'data-opt="1"':''} min="${min}" max="${max}" step="${step}" value="${has?esc(v):min}" data-set="${has?1:0}"><small>${esc(hint)}</small></div>`;
 return `<div class="ag-c"><label>${label}<span class="ag-src ${src}">${esc(src)}</span></label><input type="number" data-k="${key}" ${f[7]?'data-opt="1"':''} min="${min}" max="${max}" step="${step}" value="${has?esc(v):''}" placeholder="default"><small>${esc(hint)}</small></div>`;
}
function agControls(p){
 const f=agCtlFields(),quick=f.slice(0,3),more=f.slice(3),s=p.settings||{},stop=((s.options?.value||{}).stop||[]).join(', '),variant=s.variant?.value||'';
 return `<div class="ag-controls" data-ctl="${esc(p.name)}"><div class="ag-ctl-row">${quick.map(x=>agCtlInput(p,x)).join('')}<div class="ag-btns"><button type="button" class="btn" data-ctl-more aria-expanded="false">ALL SETTINGS</button><button type="button" class="btn" data-ctl-reset title="Back to the persona's own settings">RESET</button></div></div>
  <div class="ag-more" hidden><div class="ag-ctl-row">${more.map(x=>agCtlInput(p,x)).join('')}
   <div class="ag-c"><label>REASONING<span class="ag-src ${s.variant?.source||'default'}">${esc(s.variant?.source||'default')}</span></label><select data-k="variant">${AG_VARIANTS.map(v=>`<option value="${v}" ${v===variant?'selected':''}>${v||'model default'}</option>`).join('')}</select><small>how hard it thinks before answering</small></div>
   <div class="ag-c"><label>STOP SEQUENCES</label><input type="text" data-k="stop" data-opt="1" value="${esc(stop)}" placeholder="comma separated"><small>text that ends its answer</small></div></div>
   <p class="ag-fine">Settings are saved as you change them and used the next time this agent starts. Options the chosen model does not know are ignored by it.</p></div><span class="ag-saved" data-ctl-status></span></div>`;
}
function agDecorate(){
 document.querySelectorAll('.ag-entry[data-agent]').forEach(card=>{
  const p=(DATA.personas||[]).find(x=>x.name===card.dataset.agent);if(!p||card.querySelector('.ag-controls'))return;
  card.querySelector('.ag-summary').insertAdjacentHTML('afterend',agControls(p));
 });
}
const agTimers={};
function agCollect(box){
 const out={temperature:null,steps:null,top_p:null,variant:null,options:{}};
 box.querySelectorAll('[data-k]').forEach(el=>{
  const k=el.dataset.k;let v=el.value;
  if(el.type==='range'&&el.dataset.set!=='1')v='';
  if(k==='stop'){const l=v.split(',').map(x=>x.trim()).filter(Boolean);if(l.length)out.options.stop=l;return;}
  if(v===''||v==null)return;
  const val=(el.type==='range'||el.type==='number')?Number(v):v;
  if(el.dataset.opt)out.options[k]=val;else out[k]=(k==='variant')?val:val;
 });
 return out;
}
async function agSaveControls(box,reset){
 const name=box.dataset.ctl,status=box.querySelector('[data-ctl-status]');
 status.className='ag-saved';status.textContent='SAVING...';
 try{
  const body=reset?{temperature:null,steps:null,top_p:null,variant:null,options:{}}:agCollect(box);
  await jpost('/api/opencode/agents/'+encodeURIComponent(name)+'/settings',body);
  DATA=await jget('/api/agents');
  if(reset){const card=box.closest('.ag-entry'),open=!box.querySelector('.ag-more').hidden;box.remove();agDecorate();if(open){const nb=card.querySelector('.ag-controls');nb.querySelector('.ag-more').hidden=false;}}
  const st=(reset?document.querySelector(`.ag-controls[data-ctl="${CSS.escape(name)}"] [data-ctl-status]`):status);
  if(st){st.className='ag-saved ok';st.textContent=reset?'BACK TO DEFAULTS':'SAVED';}
 }catch(e){status.className='ag-saved bad';status.textContent='NOT SAVED: '+e.message;}
}
document.addEventListener('input',e=>{
 const el=e.target.closest&&e.target.closest('.ag-controls [data-k]');if(!el)return;const box=el.closest('.ag-controls');
 if(el.type==='range'){el.dataset.set='1';const o=box.querySelector(`[data-out="${el.dataset.k}"]`);if(o)o.textContent=el.value;}
 clearTimeout(agTimers[box.dataset.ctl]);agTimers[box.dataset.ctl]=setTimeout(()=>agSaveControls(box,false),450);
});
document.addEventListener('change',e=>{const el=e.target.closest&&e.target.closest('.ag-controls select[data-k]');if(el){const box=el.closest('.ag-controls');clearTimeout(agTimers[box.dataset.ctl]);agSaveControls(box,false);}});
document.addEventListener('click',e=>{
 const more=e.target.closest&&e.target.closest('[data-ctl-more]');
 if(more){const box=more.closest('.ag-controls'),m=box.querySelector('.ag-more');m.hidden=!m.hidden;more.setAttribute('aria-expanded',String(!m.hidden));more.textContent=m.hidden?'ALL SETTINGS':'FEWER SETTINGS';return;}
 const reset=e.target.closest&&e.target.closest('[data-ctl-reset]');
 if(reset){const box=reset.closest('.ag-controls');if(confirm('Put every setting of '+box.dataset.ctl+' back to what its persona says?'))agSaveControls(box,true);}
});

function agPaintModels(){
 const all=$('agency-all-model');if(all){all.innerHTML=agModelChoices().map(m=>`<option value="${esc(m.id)}" ${m.id===AG_POLICY.policy?'selected':''}>${esc(m.name||m.id)}</option>`).join('');all.value=AG_POLICY.policy||'auto';}
 const resolved=$('agency-resolved');if(resolved)resolved.textContent='Currently: '+(AG_POLICY.resolved||DATA.workspace_model||'default');
 document.querySelectorAll('[data-agent-model]').forEach(select=>{const p=DATA.personas.find(p=>p.name===select.dataset.agentModel);if(!p)return;const o=p.settings?.model||{},box=select.closest('.ag-model');select.innerHTML=agAgentOptions(p);box.querySelector('[data-model-source]').textContent=o.source==='override'?'Own model':o.source==='persona'?'Persona model':'Follows all agents';box.querySelector('[data-model-source]').classList.toggle('own',o.source==='override'||o.source==='persona');box.querySelector('[data-model-reset]').hidden=o.source!=='override';let row=select.closest('.ag-entry').querySelector('.settings .s');if(row){row.querySelector('.v').textContent=o.value||AG_POLICY.resolved;row.querySelector('.src').textContent=o.source||'all';}});
}
async function agRefreshModels(){AG_POLICY=await jget('/api/model-policy');DATA=await jget('/api/agents');agPaintModels();}
async function agModelChange(name,value){const err=$('agency-model-error');err.textContent='';try{await jpost('/api/opencode/agents/'+encodeURIComponent(name)+'/settings',{model:value});await agRefreshModels();}catch(e){err.textContent='Model choice was not saved: '+e.message;agPaintModels();}}
function agSetTab(tab){AG_TAB=tab==='skills'?'skills':'agents';$('agents-view').hidden=AG_TAB!=='agents';$('skl-modal').classList.toggle('open',AG_TAB==='skills');$('skl-scrim').classList.remove('open');$('tab-agents').setAttribute('aria-selected',String(AG_TAB==='agents'));$('btn-skills').setAttribute('aria-selected',String(AG_TAB==='skills'));$('btn-create').hidden=AG_TAB==='skills';history.replaceState(null,'','#'+AG_TAB);}
function agRender(){
 if(!$('agency-search')){
  $('pick').innerHTML=`<div class="ag-filters"><label>Search agents<input type="search" id="agency-search" placeholder="Name, role or work"></label></div><div class="agency-tabs ag-subtabs" id="agency-subtabs" role="tablist" aria-label="Agents by group"></div>`;
  const paintTabs=()=>{const T=[['all','','ALL'],['missions','','MISSION AGENTS'],['helpers','','HUB HELPERS']].concat(Object.entries(PROFILES).map(([id,p])=>['missions',id,String(p.label||id).toUpperCase()]));
   $('agency-subtabs').innerHTML=T.map(([sc,wk,lab])=>`<button type="button" role="tab" data-sc="${sc}" data-wk="${wk}" aria-selected="${sc===AG_SCOPE&&wk===AG_WORK}">${esc(lab)}</button>`).join('');
   $('agency-subtabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{AG_SCOPE=b.dataset.sc;AG_WORK=b.dataset.wk;paintTabs();agPaintList();});};
  paintTabs();
  $('agency-search').oninput=e=>{AG_QUERY=e.target.value;agPaintList();};
 }
 agPaintList();agPaintModels();agSetTab(AG_TAB);
}
$('tab-agents').onclick=()=>agSetTab('agents');
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-ag-expand]');if(b){const key=b.dataset.agExpand,open=!AG_OPEN.has(key);if(open)AG_OPEN.add(key);else AG_OPEN.delete(key);b.setAttribute('aria-expanded',String(open));b.closest('.ag-entry').querySelector('.ag-full').hidden=!open;if(open)agOpenEditor(key);}
 const reset=e.target.closest('[data-model-reset]');if(reset)agModelChange(reset.dataset.modelReset,'');
 const overview=e.target.closest('[data-fam=map]');if(overview){AG_OVERVIEW=!AG_OVERVIEW;agPaintList();}
});
document.addEventListener('change',e=>{if(e.target.matches('[data-agent-model]'))agModelChange(e.target.dataset.agentModel,e.target.value);});
$('agency-all-model').onchange=async e=>{const select=e.target,old=AG_POLICY.policy;select.disabled=true;$('agency-model-error').textContent='';try{await jpost('/api/model-policy',{policy:select.value});await agRefreshModels();}catch(err){$('agency-model-error').textContent='Default model was not saved: '+err.message;select.value=old;}finally{select.disabled=false;}};
function agSkillUsers(s){
 const match=(name,pattern)=>{const re='^'+String(pattern).split('*').map(x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$';try{return new RegExp(re).test(name)}catch(_){return false}};
 const names=(DATA?.personas||[]).filter(p=>{const rules=p.frontmatter?.skills||p.skills||'*';return (Array.isArray(rules)?rules:String(rules).split(',')).some(r=>match(s.name,String(r).trim()))}).map(p=>p.name);
 return `<div class="ag-skill-users">Available to: ${names.map(esc).join(', ')||'agents that request this skill'}</div>`;
}
function agSkillMatches(s,q){return [s.name,s.description,s.topic,agSkillUsers(s).replace(/<[^>]*>/g,' ')].join(' ').toLowerCase().includes(q.toLowerCase());}
function agFilterSkills(){const q=AG_SKILL_QUERY.toLowerCase();document.querySelectorAll('#skills .skl').forEach(e=>{e.hidden=!e.querySelector('#sk-desc')&&!!q&&!e.textContent.toLowerCase().includes(q);});}
$('skill-search').oninput=e=>{AG_SKILL_QUERY=e.target.value;loadSkills();};

document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-skl-all]');if(!b)return;const open=b.dataset.sklAll==='open';document.querySelectorAll('#skills details.skl:not(.add)').forEach(d=>{d.open=open;});});
