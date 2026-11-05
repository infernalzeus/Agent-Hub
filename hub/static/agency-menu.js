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
function agCompact(p){
 const id=p.name,open=AG_OPEN.has(id),links=agLinks(id),o=p.settings?.model||{},own=o.source==='override'||o.source==='persona';
 return `<article class="ag-entry" data-agent="${esc(id)}"><div class="ag-summary"><button type="button" class="ag-expand" data-ag-expand="${esc(id)}" aria-expanded="${open}"><img src="/static/agent-icons/${esc(id==='agent-smith'?'neo':id)}.png" alt="" onerror="this.hidden=true"><span class="ag-copy"><b>${esc(id==='agent-smith'?'neo':id)}</b><span class="ag-role" title="${esc(p.description||'')}">${esc(agShort(p.frontmatter?.about||p.description))}</span><span class="ag-chips">${links.html}</span></span></button><div class="ag-model"><label for="model-${esc(id)}">Model</label><select id="model-${esc(id)}" data-agent-model="${esc(id)}" aria-label="Model for ${esc(id)}">${agAgentOptions(p)}</select><span class="ag-source ${own?'own':''}" data-model-source>${own?(o.source==='override'?'Own model':'Persona model'):'Follows all agents'}</span><button type="button" class="btn ag-reset" data-model-reset="${esc(id)}" ${o.source==='override'?'':'hidden'}>RESET</button></div></div><div class="ag-full" ${open?'':'hidden'}>${agRelations(id)}${AG_CARD(p)}</div></article>`;
}
function agHelper(h){const id=h.id||h.icon,key='helper:'+id,open=AG_OPEN.has(key);return `<article class="ag-entry" data-helper="${esc(id)}"><button type="button" class="ag-expand" data-ag-expand="${esc(key)}" aria-expanded="${open}">${helperIcon(h.icon)}<span class="ag-copy"><b>${esc(h.name)}</b><span class="ag-role">${esc(agShort(h.does))}</span><span class="ag-chips">${agLinks(id).html}<span class="tag">${esc(h.state)}</span></span></span></button><div class="ag-full" ${open?'':'hidden'}>${agRelations(id)}${helperCard(h)}</div></article>`;}
function agOverview(){
 const m=AGENTMAP;if(!m)return '<p>Agent relationships could not be read.</p>';
 const name=id=>agNode(id)?.name||id,by={};for(const e of m.edges)(by[e.from]||=[]).push(e);
 return `<h3>WHO CALLS WHOM</h3><div class="ag-table"><table><thead><tr><th>Agent</th><th>Hands work to</th></tr></thead><tbody>${Object.keys(by).map(id=>`<tr><td>${esc(name(id))}</td><td>${by[id].map(e=>esc(name(e.to))).join(', ')}</td></tr>`).join('')}</tbody></table></div><h3>WHAT THE LEARNERS CAN SEE</h3><p>${m.complete?'Every agent has a coverage decision.':'Some agents need a coverage decision.'} Declared learning gaps: ${(m.gaps||[]).length}.</p><div class="ag-table"><table><thead><tr><th>Agent</th><th>State</th><th>Why</th></tr></thead><tbody>${m.nodes.map(n=>{let c=m.coverage[n.id]||{};return `<tr><td>${esc(n.name)}</td><td>${esc(c.state||'not decided')}</td><td>${esc(c.note||'')}</td></tr>`}).join('')}</tbody></table></div>`;
}
function agPaintList(){
 if(!DATA||!AG_CARD)return;
 const q=AG_QUERY.trim().toLowerCase(),persons=DATA.personas||[],has=p=>!q||[p.name,p.description,p.frontmatter?.about].join(' ').toLowerCase().includes(q),used=new Set();
 let html=`<div class="ag-overview"><button type="button" class="btn ${AG_OVERVIEW?'on':''}" data-fam="map" aria-expanded="${AG_OVERVIEW}">HOW THEY WORK TOGETHER</button><div id="agency-overview" ${AG_OVERVIEW?'':'hidden'}>${AG_OVERVIEW?agOverview():''}</div></div>`;
 const section=(name,items,render)=>items.length?`<section class="ag-group"><h2>${esc(name)} <span>${items.length}</span></h2>${items.map(render).join('')}</section>`:'';
 if(AG_SCOPE!=='helpers'&&!AG_WORK){const primary=persons.filter(p=>(p.mode==='primary'||p.name==='orchestrator')&&!p.utility&&p.name!=='neo').filter(has);primary.forEach(p=>used.add(p.name));html+=section('Orchestration',primary,agCompact);}
 if(AG_SCOPE!=='missions'&&!AG_WORK){
  const helpers=HELPERS.filter(h=>!persons.some(p=>p.name===h.id)&&(!q||[h.name,h.does].join(' ').toLowerCase().includes(q)));
  const hp=persons.filter(p=>p.name==='neo'||p.utility).filter(has);hp.forEach(p=>used.add(p.name));
  html+=section('Hub helpers',helpers,agHelper)+section('Agent design',hp,agCompact);
 }
 if(AG_SCOPE!=='helpers'){
  for(const [key,f] of Object.entries(PROFILES)){if(AG_WORK&&AG_WORK!==key)continue;const items=persons.filter(p=>!used.has(p.name)&&(f.roster||[]).includes(p.name)).filter(has);items.forEach(p=>used.add(p.name));html+=section(f.label||key,items,agCompact);}
  if(!AG_WORK){const other=persons.filter(p=>!used.has(p.name)&&!p.utility&&p.name!=='neo').filter(has);html+=section('Hub orchestration and other agents',other,agCompact);}
 }
 $('list').innerHTML=html;
 if(!document.querySelector('.ag-entry'))$('list').insertAdjacentHTML('beforeend','<p class="ag-empty">No agents match these filters.</p>');
}
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
  $('pick').innerHTML=`<div class="ag-filters"><label>Search agents<input type="search" id="agency-search" placeholder="Name, role or work"></label><label>Show<select id="agency-scope"><option value="all">All agents and helpers</option><option value="missions">Mission agents</option><option value="helpers">Hub helpers</option></select></label><label>Work type<select id="agency-work"><option value="">All work types</option>${Object.entries(PROFILES).map(([id,p])=>`<option value="${esc(id)}">${esc(p.label||id)}</option>`).join('')}</select></label></div>`;
  $('agency-search').oninput=e=>{AG_QUERY=e.target.value;agPaintList();};$('agency-scope').value=AG_SCOPE;$('agency-scope').onchange=e=>{AG_SCOPE=e.target.value;agPaintList();};$('agency-work').onchange=e=>{AG_WORK=e.target.value;agPaintList();};
 }
 agPaintList();agPaintModels();agSetTab(AG_TAB);
}
$('tab-agents').onclick=()=>agSetTab('agents');
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-ag-expand]');if(b){const key=b.dataset.agExpand,open=!AG_OPEN.has(key);if(open)AG_OPEN.add(key);else AG_OPEN.delete(key);b.setAttribute('aria-expanded',String(open));b.closest('.ag-entry').querySelector('.ag-full').hidden=!open;}
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
