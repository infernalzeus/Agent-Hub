/* Agent Hub site: scene navigation, auto-playing step lists, the pulsing grid, the fading-in mark, and a tilt that follows the pointer or the phone. */
(()=>{'use strict';
 const scenes=[...document.querySelectorAll('.scene')],reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let active=document.getElementById('landing'),busy=false,mark=null,stopToggle=null,shell=true,permission='unknown',pose=null,hasOrientation=false,pendingRoute=null;
 try{permission=sessionStorage.getItem('site:orientation')||'unknown';}catch(error){}
 const route=()=>document.getElementById(location.hash.slice(1))?.matches('.scene')?location.hash.slice(1):'landing';
 const MAX_TILT=4, REST_X=0, REST_Y=0, MOUSE_DEVICE=matchMedia('(hover:hover) and (pointer:fine)').matches, MOUSE_TILT=1.5, LANDING_MOUSE_TILT=2, PHONE_TILT=4, PERSPECTIVE=1600;
 const STEP=4200;

 /* ---------- auto-playing step lists: they advance by themselves; a tap or hover pins one ---------- */
 const autos=[...document.querySelectorAll('[data-auto]')].map(el=>{
  const a={el,scene:el.closest('.scene'),btns:[...el.querySelectorAll('.st')],detail:el.querySelector('.auto-detail'),i:0,pinned:false,timer:0,resume:0};
  a.kicker=a.detail.querySelector('.kicker');a.h3=a.detail.querySelector('h3');a.d=a.detail.querySelector('.d');a.you=a.detail.querySelector('.you p');a.pic=a.detail.querySelector('.pic');a.chips=a.detail.querySelector('.chips-row');
  a.btns.forEach((b,i)=>{
   b.addEventListener('click',()=>{pin(a,i,8000);});
   b.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')pin(a,i,3500);});
   b.addEventListener('focus',()=>select(a,i));
  });
  return a;
 });
 function select(a,i){
  if(a.i!==(i+a.btns.length)%a.btns.length)a.demoChoice=null;
  a.i=(i+a.btns.length)%a.btns.length;const b=a.btns[a.i];
  a.btns.forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));
  a.detail.dataset.n=a.i+1;a.kicker.textContent=b.dataset.k;a.h3.textContent=b.dataset.t;a.d.textContent=b.dataset.d;a.you.textContent=b.dataset.you||'';a.detail.querySelector('.you').hidden=!b.dataset.you;if(b.dataset.img){a.pic.src=b.dataset.img;a.pic.hidden=false;}else a.pic.hidden=true;a.chips.textContent='';(b.dataset.chips||'').split('|').filter(Boolean).forEach(c=>{const i=document.createElement('span');i.className='chip';i.textContent=c;a.chips.appendChild(i);});
  drawVisual(a);a.el.classList.remove('playing');void a.el.offsetWidth;if(!a.pinned&&!reduced.matches&&a.live)a.el.classList.add('playing');
 }
 function play(a){clearTimeout(a.timer);if(!a.live||a.pinned||reduced.matches)return;a.el.style.setProperty('--step',STEP+'ms');a.el.classList.add('playing');a.timer=setTimeout(()=>{select(a,a.i+1);play(a);},STEP);}
 function pin(a,i,ms){a.pinned=true;clearTimeout(a.timer);clearTimeout(a.resume);select(a,i);a.el.classList.remove('playing');a.resume=setTimeout(()=>{a.pinned=false;play(a);},ms);}
 function startAutos(scene){autos.filter(a=>a.scene===scene).forEach(a=>{a.live=!!a.el.offsetParent||scene.id==='talk';a.pinned=false;clearTimeout(a.resume);if(a.live){select(a,0);play(a);}});}
 function stopAutos(){autos.forEach(a=>{a.live=false;stopDemo(a);clearTimeout(a.timer);clearTimeout(a.resume);a.el.classList.remove('playing');});}
 function stepActive(delta){const a=autos.find(x=>x.scene===active&&x.live);if(a)pin(a,a.i+delta,8000);}

 /* the Agents / Skills tabs */
 document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{const ag=t.closest('.agency');ag.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected',x===t?'true':'false'));ag.querySelectorAll('.tabpanel').forEach(p=>p.hidden=p.dataset.panel!==t.dataset.tab);stopAutos();startAutos(active);}));

 document.querySelectorAll('[data-agent-jump]').forEach(b=>b.addEventListener('click',()=>{const a=autos.find(a=>a.scene.id==='agents'&&a.el.classList.contains('agents-auto'));if(a){const i=a.btns.findIndex(x=>(x.dataset.img||'').endsWith('/'+b.dataset.agentJump+'.png'));if(i>=0)pin(a,i,10000);}}));
 /* small glass blocks open to show more */

 /* the animated machine on the TALK scene is drawn at one size and scaled to the room it has */
 function fit(){const w=active.querySelector('.fit');if(w&&w.offsetParent){const f=w.firstElementChild,s=Math.min(w.clientWidth/1060,w.clientHeight/f.offsetHeight,1.2);f.style.setProperty('--s',s.toFixed(3));}autos.filter(a=>a.live).forEach(drawVisual);drawArchitecture();fitTilt();}
 addEventListener('resize',()=>{fit();sizeGrid();});
 if(document.fonts&&document.fonts.ready)document.fonts.ready.then(()=>{fit();sizeGrid();});

 /* architecture: tap to enlarge */
 const zoom=document.querySelector('#architecture .zoom');if(zoom)document.body.appendChild(zoom);
 const zoomOf=()=>zoom;
 let zoomWidth=1440;
 document.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{zoom.hidden=false;zoomWidth=Math.max(1440,innerWidth);zoom.querySelector('img').style.width=zoomWidth+'px';zoom.querySelector('[data-zoom-close]').focus();}));
 zoom?.querySelector('[data-zoom-close]').addEventListener('click',()=>{zoom.hidden=true;document.querySelector('.enlarge').focus();});
 zoom?.querySelector('[data-zoom-in]').addEventListener('click',()=>{zoomWidth=Math.min(4000,zoomWidth*1.25);zoom.querySelector('img').style.width=zoomWidth+'px';});
 zoom?.querySelector('[data-zoom-out]').addEventListener('click',()=>{zoomWidth=Math.max(600,zoomWidth/1.25);zoom.querySelector('img').style.width=zoomWidth+'px';});
 let pan=null;const scroll=zoom?.querySelector('.zoom-scroll');
 scroll?.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse')return;pan={x:e.clientX,y:e.clientY,left:scroll.scrollLeft,top:scroll.scrollTop};scroll.setPointerCapture(e.pointerId);e.preventDefault();});
 scroll?.addEventListener('pointermove',e=>{if(pan){scroll.scrollLeft=pan.left+pan.x-e.clientX;scroll.scrollTop=pan.top+pan.y-e.clientY;}});
 scroll?.addEventListener('pointerup',()=>{pan=null;});scroll?.addEventListener('pointercancel',()=>{pan=null;});

 /* ---------- the mark: the real animated core fades in once the turn has finished; the picture is only a last resort ---------- */
 const markHost=document.getElementById('hero-mark');
 function mountMark(){
  if(mark||!markHost)return;
  try{if(window.AgentHubMark){mark=AgentHubMark.mount(markHost,{state:'live',mode:'crystal',shell,touchLock:true,reducedMotion:reduced.matches});if(mark)stopToggle=AgentHubMark.tapToToggle(document.getElementById('landing'),mark,markHost,{rippleIn:document.getElementById('landing'),onToggle:value=>{shell=value;}});}}catch(error){mark=null;}
  // Never substitute a stored picture for the live core. GPU failure leaves the title and doors readable.
  requestAnimationFrame(()=>setTimeout(()=>markHost.classList.add('on'),140));
 }
 function unmountMark(){if(!markHost)return;if(stopToggle){stopToggle();stopToggle=null;}if(mark){mark.destroy();mark=null;}markHost.classList.remove('on');markHost.textContent='';}

 /* ---------- the pulsing grid behind the landing page (the original page's grid, one ring every three seconds) ---------- */
 const canvas=document.getElementById('hub-grid'),gx=canvas&&canvas.getContext('2d'),landing=document.getElementById('landing'),doors=[...document.querySelectorAll('.door')];
 let gw=0,gh=0,gclick=0,gpos=[],graf=0,glast=0;
 function sizeGrid(){if(!canvas)return;const r=landing.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);gw=r.width;gh=r.height;canvas.width=gw*d;canvas.height=gh*d;gx.setTransform(d,0,0,d,0,0);
  gpos=doors.map(el=>{const q=el.getBoundingClientRect();return{el,d:Math.hypot(q.left+q.width/2-r.left-gw/2,q.top+q.height/2-r.top-gh/2),v:0};});drawGrid(2000);}
 function drawGrid(n){
  if(!gx||!gw)return;gx.clearRect(0,0,gw,gh);
  const max=Math.hypot(gw,gh)*.5,amb=(n%3000)/3000,ring=amb*max*1.25,fade=1-amb;
  for(let i=0;i<gw;i+=30)for(let j=0;j<gh;j+=30){
   const dist=Math.hypot(i-gw/2,j-gh/2),dA=Math.abs(dist-ring);
   let a=.05+Math.max(0,1-dA/80)*.42*fade+Math.sin(n/1400-dist/190)*.02,tq=0;
   if(gclick){const t=(n-gclick)/1500,r2=t*Math.hypot(gw,gh)*.55;tq=Math.max(0,1-Math.abs(dist-r2)/90)*.45*(1-t)*(1-t);if(t>1)gclick=0;}
   a=Math.max(.03,a);gx.strokeStyle='rgba(0,230,118,'+a+')';gx.lineWidth=a>.3?1.4:1;gx.strokeRect(i+.5,j+.5,30,30);
   if(tq>.01){gx.strokeStyle='rgba(64,224,208,'+tq.toFixed(3)+')';gx.lineWidth=1;gx.strokeRect(i+.5,j+.5,30,30);gx.fillStyle='rgba(64,224,208,'+(tq*.15).toFixed(3)+')';gx.fillRect(i+1,j+1,29,29);}
  }
  for(const o of gpos){const v=Math.max(0,1-Math.abs(o.d-ring)/48)*(1-amb*.5);if(Math.abs(v-o.v)>.04){o.v=v;o.el.style.setProperty('--g',v.toFixed(2));}}
 }
 function gridFrame(n){graf=0;if(document.hidden||active.id!=='landing'||busy||reduced.matches)return;if(n-glast>=33){glast=n;drawGrid(n);}graf=requestAnimationFrame(gridFrame);}
 function startGrid(){if(!graf&&!reduced.matches)graf=requestAnimationFrame(gridFrame);}
 if(markHost)markHost.addEventListener('click',()=>{gclick=performance.now();if(reduced.matches)drawGrid(performance.now());});

/* Explanatory diagrams, not recordings of completed work. All geometry uses the available panel. */
function detailSymbol(a){
 if(!['media','install'].includes(a.scene.id))return;const host=a.detail.querySelector('.detail-copy');if(host.querySelector('.detail-symbol'))return;
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('detail-symbol');svg.setAttribute('viewBox','0 0 64 64');svg.setAttribute('aria-label',a.scene.id==='media'?'Your media folder':'Your PC and phone');svg.setAttribute('role','img');
 svg.innerHTML=a.scene.id==='media'?'<path d="M7 18h19l6 7h25v28H7zM7 18v-7h19l6 7h25v7M26 32l14 8-14 8z"/>':'<rect x="5" y="7" width="42" height="32"/><path d="M18 39v9M11 48h25"/><rect x="43" y="29" width="16" height="28"/><path d="M48 51h6"/>';
 host.append(svg);
}
/* Dashboard-shaped previews. Camera, downloads and PC actions are never invoked here. */
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function stopDemo(a){(a.demoTimers||[]).forEach(clearTimeout);a.demoTimers=[];}
function demoModel(a){const b=a.btns[a.i];return {sid:a.scene.id,title:b.dataset.t,actor:b.dataset.k,ask:b.dataset.you,description:b.dataset.d,image:b.dataset.img,key:(b.dataset.img||'').split('/').pop()?.replace('.png',''),step:a.i};}
function updateInsights(a,m){const f=a.scene.querySelector('.story-foot');if(f){f.querySelector('.try-panel>p').textContent=m.ask||'';f.querySelector('.expect').textContent=m.description||'';f.dataset.step=m.sid+'-'+m.step;}if(m.sid==='talk')a.scene.querySelectorAll('.say-table tbody tr').forEach((r,i)=>r.classList.toggle('example-active',i===a.i));}
function syncTalk(a){if(a.scene.id!=='talk')return;const machine=a.scene.querySelector('.machine');if(!machine)return;const animations=machine.getAnimations({subtree:true});animations.forEach(x=>{x.currentTime=a.i*9000+100;x.playbackRate=2;if(reduced.matches)x.pause();else x.play();});if(!reduced.matches)a.demoTimers.push(setTimeout(()=>animations.forEach(x=>x.pause()),3950));}
function drawVisual(a){
 stopDemo(a);const m=demoModel(a),host=a.detail.querySelector('[data-visual]');updateInsights(a,m);
 if(!host?.offsetParent){syncTalk(a);return;}
 const s=m.step;host.dataset.scenario=m.sid+'-'+(m.key||'step')+'-'+s;host.dataset.phase='ready';
 const button=(text,action,cls='')=>`<button type="button" class="ui-btn ${cls}" data-preview="${action}">${text}</button>`;
 const row=(label,value,cls='')=>`<div class="ui-row ${cls}"><span>${label}</span><strong>${value}</strong></div>`;
 const field=(label,value)=>`<label class="ui-field"><span>${label}</span><input value="${esc(value)}" readonly></label>`;
 let content='',pageTitle=m.sid==='agents'?(m.key?'AGENCY':'SKILLS'):{hands:'DASHBOARD · HAND CONTROL',pc:'PC CONTROL · WINDOWS',media:'MEDIA VAULT',graph:'GIT GRAPH',missions:'MISSIONS',install:'FIRST-RUN SETUP',talk:'AGENT SMITH'}[m.sid];
 if(m.sid==='hands'){
  const names=['start','point','drag','zoom','turn','fit'];content=`<div class="dashboard-capture"><picture><source media="(max-width:650px) and (orientation:portrait)" srcset="assets/previews/hands-phone-${names[s]}.png"><img src="assets/previews/hands-${names[s]}.png" alt="Actual Hub dashboard in GLASS mode: ${esc(m.title)}" draggable="false"></picture><span class="capture-label">${esc(['HANDS · explicit start','POINT · choose a block','PINCH + MOVE · drag the block','TWO PINCHES · zoom the board','FIST · turn the 3D view','OPEN HAND · fit the board'][s])}</span></div>`;
 }else if(m.sid==='pc'){
  content=`<div class="pc-preview"><div class="ui-message"><img src="assets/agents/smith.png" alt="Agent Smith"><div><b>Agent Smith → desktop control</b><p>Play my liked songs in Apple Music.</p></div></div>`;
  if(s===0)content+=field('Goal','Play my liked songs in Apple Music')+button('Show proposed task','next');
  if(s===1)content+=`<div class="ui-section">NAMED CONTROLS</div>`+row('App','Apple Music')+row('Control','Play · button')+row('Next','Request permission');
  if(s===2)content+=`<div class="ui-proposal"><b>Approve this press?</b><p>Press Play in Apple Music.</p><div class="ui-actions">${button('Yes, press Play','approve')}${button('No, leave it','refuse')}</div></div>`;
  if(s===3)content+=`<div class="ui-section">STEP LOG</div>`+row('Permission','Approved')+row('Action','Press Play')+row('Next','Read the window again');
  if(s===4)content+=`<div class="ui-section">RESULT CHECK</div>`+row('Before','Play')+row('After','Pause control visible')+`<p class="ui-note">The agent checks the changed window before reporting success.</p>`;
  if(s===5)content+=`<div class="ui-section">ROUTINES</div><div class="ui-library-row"><b>Play liked songs</b><span>Candidate routine · desktop</span>${button('Read steps','routine')}</div>`;
  content+='</div>';
 }else if(m.sid==='media'){
  if(s<2)content=`<div class="media-preview">${field('YouTube URL','Paste a video link in the Hub')}<label class="ui-field"><span>Format</span><div class="ui-segment">${button('VIDEO','video',s===0?'selected':'')}${button('AUDIO','audio',s===1?'selected':'')}</div></label>${s===0?button('Preview download','next'):field('Output','Audio · converted on this PC')+'<div class="ui-progress"><i></i></div><p class="ui-note">yt-dlp downloads the source; ffmpeg makes the selected format.</p>'}</div>`;
  else content=`<div class="file-preview"><div class="ui-breadcrumb">FILES / ${s===2?'AUDIO':'INBOX'}</div><div class="file-head"><span>NAME</span><span>TYPE</span></div><div class="file-entry"><span>▧ ${s===2?'downloaded-audio.mp3':'received-file'}</span><span>${s===2?'Audio':'From phone'}</span></div><div class="ui-actions">${button(s===2?'Open file':'Receive from phone','file')}${button('Browse folders','browse')}</div><p class="ui-note">${s===2?'The output is a file in the folder you selected.':'Files received from your phone arrive in the PC inbox.'}</p></div>`;
 }else if(m.sid==='graph'){
  content=`<div class="graph-preview"><nav class="ui-segment">${button('Project map','map',s===0?'selected':'')}${button('Changes','changes',s>0?'selected':'')}</nav>`;
  if(s===0)content+=`<div class="project-map"><button type="button" data-preview="changes" class="project-dot"><span></span><b>Agent Hub</b><small>Project on this PC</small></button><div class="graph-key">One project per dot. Open it to inspect its branches and changed files.</div></div>`;
  else content+=`<div class="git-detail"><div class="git-sidebar"><b>AGENT HUB</b><span class="git-branch">⑂ master</span><button type="button" class="file-selected" data-preview="diff">docs/assets/site.js</button><span>docs/index.html</span></div><div class="git-diff"><header>docs/assets/site.js</header><code class="diff-remove">− REST_X=-3, REST_Y=3.5</code><code class="diff-add">+ REST_X=0, REST_Y=0</code><p>${s===1?'Choose a changed file to read the diff.':s===2?'Changes are reviewed inside the selected project.':'Keep reviewing; applying a mission remains your choice.'}</p>${s===3?button('Return to project map','map'):''}</div></div>`;
  content+='</div>';
 }else if(m.sid==='agents'&&m.key){
  const role={orchestrator:['ORCHESTRATION','Plans and delegates','Goal → briefs → named agents','Writes no code; the result returns for review.'],smith:['HUB HELPER','Voice and chat','Your request → router → tool','Routes app, media, mission and conversation requests.'],neo:['AGENT DESIGN','Design an agent','Describe the job → persona draft → save','Hands back instructions you can read and edit.'],doctor:['HUB REPAIR','Diagnose and propose','Hub facts → private repair → your APPLY','You review the diff and decide when to restart.']}[m.key];
  content=`<div class="agency-preview"><div class="agency-profile"><img src="${esc(m.image)}" alt="${esc(m.title)}"><div><span class="ui-section">${role[0]}</span><h4>${esc(m.title)}</h4><p>${role[1]}</p></div></div><div class="agency-about">${esc(role[3])}</div>${row('Handoff',role[2])}<p class="ui-note">${role[3]}</p><div class="ui-actions">${button('Read definition','definition')}${button('Handoffs','handoffs')}</div><div class="ui-inline-detail" hidden></div></div>`;
 }else if(m.sid==='agents'){
  const skills=s===0?[['debugging-methodology','Hub skill','Find the cause, reproduce it, verify the fix.'],['testing-conventions','Hub skill','Choose meaningful checks for the behavior.'],['python-aiohttp-webapp','Hub skill','Conventions for the Hub’s async web services.']]:s===1?[['frontend-design','Anthropic · Apache-2.0','Build distinctive interfaces.'],['mcp-builder','Anthropic · Apache-2.0','Build Model Context Protocol integrations.'],['webapp-testing','Anthropic · Apache-2.0','Inspect and test browser interfaces.']]:[['Launch videos · brag','latent-spaces · MIT','Create a launch video for a finished project.']];
  if(s===3)content=`<div class="skills-preview">${field('Describe a reusable skill','Review interface changes for clarity and consistency')}<div class="skill-file"><b>SKILL.md</b><pre>name: interface-review\ndescription: Review interface changes.\n\nCheck layout, wording and keyboard access.\nReport the issue and its location.</pre></div>${button('Preview saved skill','save')}</div>`;
  else content=`<div class="skills-preview"><div class="ui-section">${s===2?'ADD A SKILL':'SKILL LIBRARY'}</div><div class="ui-segment">${button('Hub skills','hub-skills',s===0?'selected':'')}${button('Open source','open-skills',s===1?'selected':'')}${button('New skill','new-skill')}</div>${skills.map(([name,origin,desc])=>`<button type="button" class="skill-library-row" data-preview="skill"><b>${name}</b><small>${origin}</small><span>${desc}</span></button>`).join('')}<div class="ui-inline-detail" hidden></div></div>`;
 }else if(m.sid==='missions'){
  content=`<div class="mission-preview"><div class="ui-section">MISSION · Add a dark-mode toggle</div><div class="mission-tabs"><span class="${s<3?'selected':''}">PLAN</span><span class="${s===3?'selected':''}">WORK</span><span class="${s>=4?'selected':''}">REVIEW</span></div>`;
  if(s<3)content+=row('Goal','Add a dark-mode toggle to settings')+row('Planner','orchestrator')+row('Briefs','coder → tester → reviewer');
  if(s===3)content+=row('Working copy','Private git worktree')+'<div class="ui-progress"><i></i></div>'+row('Your project','Unchanged');
  if(s===4)content+=`<div class="ui-proposal"><b>Question from the mission</b><p>Should the toggle follow the system theme?</p>${button('Use system theme','answer')}</div>`;
  if(s>=5)content+=`<div class="git-diff"><header>Changed lines · review</header><code class="diff-remove">− color-scheme: light;</code><code class="diff-add">+ color-scheme: light dark;</code></div>${s===6?'<div class="ui-actions">'+button('Preview APPLY','apply')+button('Preview DISCARD','discard')+'</div>':''}`;
  content+='</div>';
 }else if(m.sid==='install'){
  content=`<div class="setup-preview"><div class="ui-section">${['CHOOSE YOUR SYSTEM','FIRST-RUN CHOICES','PRIVATE DEVICE ACCESS','OPEN YOUR HUB'][s]}</div>${s===0?'<div class="setup-os">Windows · macOS · Linux</div>':s===1?['Media tools','PC control · Windows','Speech','File Browser'].map(t=>`<div class="setup-option"><span>${t}</span>${button('Choose','choose')}</div>`).join(''):s===2?row('PC','Hub runs here')+row('Phone / tablet','Same private Tailscale network'):row('Browser','Open your Hub address')+row('Home screen','Save a bookmark')}<p class="ui-note">${s===0?'Choose a download above. macOS builds are unsigned.':'Choose the tools and folders you want during setup.'}</p></div>`;
 }else{
  content=`<div class="talk-preview"><div class="ui-message"><img src="assets/agents/smith.png" alt="Agent Smith"><div><b>Agent Smith</b><p>${esc(a.btns[s].dataset.t)}</p></div></div><div class="ui-proposal"><b>${esc(m.actor)}</b><p>${esc(m.description)}</p>${button('Explore this tool','tool')}</div></div>`;
 }
 host.innerHTML=`<div class="screen-toolbar"><span>${pageTitle}</span><div><button type="button" data-preview="replay" aria-label="Replay this preview">↻</button><button type="button" data-preview="pause" aria-label="Pause this preview">Ⅱ</button><button type="button" data-preview="next" aria-label="Next preview step">›</button></div></div><div class="screen-body">${content}</div>`;
 host.querySelectorAll('[data-preview]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();const action=b.dataset.preview;clearTimeout(a.timer);clearTimeout(a.resume);a.pinned=true;
  const jump=i=>pin(a,i,12000);
  if(action==='next')jump(a.i+1);else if(action==='replay'){a.pinned=false;select(a,a.i);play(a);}else if(action==='pause')host.getAnimations({subtree:true}).forEach(x=>x.pause());
  else if(action==='map')jump(0);else if(action==='changes')jump(1);else if(action==='diff')jump(2);else if(action==='audio')jump(1);else if(action==='video')jump(0);else if(action==='hub-skills')jump(0);else if(action==='open-skills')jump(1);else if(action==='new-skill')jump(3);
  else if(action==='skill'){
   const title=b.querySelector('b').textContent,origin=b.querySelector('small').textContent,description=b.querySelector('span').textContent,pane=host.querySelector('.skills-preview');
   pane.classList.add('skill-reading');pane.innerHTML='<div class="skill-overview"><button type="button" class="ui-btn" data-skill-back>‹ Skill library</button><h4>'+esc(title)+'</h4><p>'+esc(description)+'</p><p class="ui-note">'+esc(origin)+' · SKILL.md</p></div>';pane.querySelector('[data-skill-back]').addEventListener('click',()=>drawVisual(a));
  }else if(action==='approve')jump(3);else if(action==='browse')jump(s===2?3:2);else if(action==='tool')navigate(['talk','missions','pc','media','graph','missions'][s]);
  else {const detail=host.querySelector('.ui-inline-detail'),msg={approve:'Preview: permission granted. The next step presses Play.',refuse:'Preview: declined. No press is sent.',apply:'Preview: the reviewed change is applied.',discard:'Preview: the private copy is discarded.',keep:'Preview: the branch remains separate.',answer:'Preview: your answer returns to the mission.',save:'Preview: the skill is available in the library.',file:'Preview: open the selected file in the Hub.',browse:'Preview: the File Browser opens the selected folder.',routine:'Play liked songs → find Play → ask permission → press → verify.',definition:m.description,handoffs:m.ask,skill:'This skill is in the Hub library. Read its instructions and origin before using it.'}[action]||'Preview selected.';if(detail&&m.sid==='agents'&&m.key){host.querySelector('.agency-about').textContent=msg;}else if(detail){detail.hidden=false;detail.textContent=msg;}else{a.scene.querySelector('.expect').textContent=msg;b.setAttribute('aria-pressed','true');b.textContent={refuse:'Declined · no press',apply:'Applied · preview',discard:'Discarded · preview',keep:'Branch kept separate',answer:'System theme selected',save:'Saved · preview',file:'File selected',routine:'Find Play → ask → press → check'}[action]||'Selected';}}
 }));
 syncTalk(a);
}
document.querySelectorAll('[data-talk-example]').forEach(b=>b.addEventListener('click',()=>{const a=autos.find(x=>x.scene.id==='talk');if(a)pin(a,Number(b.dataset.talkExample),12000);}));
document.querySelectorAll('.machine .lane').forEach((lane,i)=>{lane.tabIndex=0;lane.setAttribute('role','button');lane.setAttribute('aria-label','Follow '+lane.querySelector('strong').textContent);const choose=()=>{const a=autos.find(x=>x.scene.id==='talk');if(a)pin(a,[0,1,2,3,4][i],12000);};lane.addEventListener('click',choose);lane.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});});
document.querySelector('.wishlist-form')?.addEventListener('submit',e=>{e.preventDefault();e.target.querySelector('button').textContent='PREVIEW ONLY';e.target.querySelector('[role=status]').textContent='Interface preview — email signup is not connected yet.';});

function drawArchitecture(){
 const host=document.querySelector('.scene.active [data-architecture]');if(!host)return;
 const model=JSON.parse(host.dataset.architecture),svg=host.querySelector('svg'),W=host.clientWidth,H=host.clientHeight,ns='http://www.w3.org/2000/svg';svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.innerHTML='<defs><marker id="circuit-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L8 4L0 8" fill="#00e676"/></marker></defs>';
 const pos=n=>{let x=0,y=0,e=n;while(e&&e!==host){x+=e.offsetLeft;y+=e.offsetTop;e=e.offsetParent;}return{x,y,w:n.offsetWidth,h:n.offsetHeight};};
 model.edges.forEach(([a,b])=>{const aa=host.querySelector(`[data-arch-node="${a}"]`),bb=host.querySelector(`[data-arch-node="${b}"]`),A=pos(aa),B=pos(bb),p=document.createElementNS(ns,'path');let d;
  if(B.x>A.x+10){const x=A.x+A.w,y=A.y+A.h/2,xx=B.x,yy=B.y+B.h/2,mid=(x+xx)/2;d=`M${x} ${y}H${mid}V${yy}H${xx}`;}
  else{const x=A.x+A.w/2,y=A.y+A.h,xx=B.x+B.w/2,yy=B.y,mid=(y+yy)/2;d=`M${x} ${y}V${mid}H${xx}V${yy}`;}
  p.setAttribute('d',d);p.setAttribute('class','circuit-trace'+((a==='smith'&&b!=='router')||['skills','neo','doctor'].includes(a)?' helper-trace':''));p.dataset.from=a;p.dataset.to=b;svg.append(p);
 });
 host.querySelectorAll('[data-arch-node]').forEach(n=>{if(n.dataset.wired)return;n.dataset.wired='1';n.addEventListener('click',()=>{const id=n.dataset.archNode;host.querySelectorAll('[data-arch-node]').forEach(x=>{x.classList.toggle('selected',x===n);x.setAttribute('aria-pressed',String(x===n));});svg.querySelectorAll('path[data-from]').forEach(p=>p.classList.toggle('selected',p.dataset.from===id||p.dataset.to===id));host.nextElementSibling.querySelector('b').textContent=n.querySelector('b').textContent;host.nextElementSibling.querySelector('p').textContent=model.nodes[id];});});
}


 let settleTimer=0;
 /* ---------- navigation ---------- */
 function enter(scene){
  clearTimeout(settleTimer);scenes.forEach(s=>s.classList.remove('settling'));if(!reduced.matches){scene.classList.add('settling');settleTimer=setTimeout(()=>scene.classList.remove('settling'),1200);}
  active=scene;scenes.forEach(s=>{s.classList.remove('leaving');s.classList.toggle('active',s===active);s.setAttribute('aria-hidden',s===active?'false':'true');s.inert=s!==active;});
  stopAutos();startAutos(active);fit();requestAnimationFrame(fit);if(active.id==='landing'){mountMark();sizeGrid();startGrid();}else unmountMark();
  setTimeout(()=>move(0,0),60);
  const back=document.querySelector('[data-projects]');if(back){const home=scene.id==='landing';back.innerHTML=home?'← PROJECTS':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';back.classList.toggle('close-scene',!home);back.setAttribute('href',home?'https://infernalzeus.github.io/':'#');back.setAttribute('aria-label',home?'Back to the projects page':'Close card and return to Agent Hub');}
 }
 async function navigate(id,push=true){
  if(busy)return;const next=document.getElementById(id)||scenes[0];if(next===active)return;
  busy=true;resetTilt();pose=null;stopAutos();
  if(!reduced.matches&&!document.hidden){active.classList.add('leaving');await new Promise(r=>setTimeout(r,270));}
  if(push)history.pushState(null,'',id==='landing'?location.pathname+location.search:'#'+id);
  next.setAttribute('aria-hidden','false');next.inert=true;
  const previous=active;
  await SiteDepthLift.go(previous,next,next.id==='landing');
  busy=false;enter(next);
  active.querySelector('h1,h2')?.focus({preventScroll:true});
  if(pendingRoute!==null){const p=pendingRoute;pendingRoute=null;navigate(p,false);}
 }
 function askSensor(){
  if(permission!=='unknown')return;
  const Sensor=window.DeviceOrientationEvent;
  if(!Sensor){permission='missing';return;}
  if(typeof Sensor.requestPermission==='function'){
   permission='pending';
   const save=value=>{permission=value;try{sessionStorage.setItem('site:orientation',value);}catch(error){}};
   try{Sensor.requestPermission().then(value=>save(value==='granted'?'granted':'denied'),()=>save('denied'));}catch(error){save('denied');}
  }else permission='granted';
 }
 document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(!a)return;e.preventDefault();if(busy)return;if(a.closest('.landing'))askSensor();navigate(a.hash.slice(1)||'landing');});
 addEventListener('popstate',()=>{if(busy){pendingRoute=route();return;}navigate(route(),false);});
 addEventListener('hashchange',()=>{if(busy){pendingRoute=route();return;}navigate(route(),false);});
 new MutationObserver(()=>{if(!busy&&pendingRoute!==null){const p=pendingRoute;pendingRoute=null;navigate(p,false);}}).observe(document.body,{attributes:true,attributeFilter:['data-turning']});
 document.addEventListener('keydown',e=>{
  if(busy){if(['Escape','ArrowLeft','ArrowRight','Enter',' '].includes(e.key))e.preventDefault();return;}
  const z=zoomOf();if(z&&!z.hidden){if(e.key==='Escape'){e.preventDefault();z.hidden=true;document.querySelector('.enlarge').focus();}if(e.key==='Tab'){const bs=[...z.querySelectorAll('button')],i=bs.indexOf(document.activeElement);e.preventDefault();bs[(i+(e.shiftKey?-1:1)+bs.length)%bs.length].focus();}return;}
  if(active.id==='landing'&&e.key.toLowerCase()==='g'&&!e.ctrlKey&&!e.metaKey&&mark){shell=!mark.isShell();mark.setShell(shell);}
  if(e.key==='Escape'){e.preventDefault();navigate('landing');}
  if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!e.target.matches('input,textarea,select')){e.preventDefault();stepActive(e.key==='ArrowRight'?1:-1);}
 });

 /* ---------- tilt: pointer on a computer, the phone's gravity sensor on a phone, a finger drag as the fallback ---------- */
 let targetX=0,targetY=0,x=0,y=0,raf=0,last=0,lastMove=0,drag=null;
 const tiltEl=()=>active.querySelector('[data-tilt]');
 const maxFor=(el,kind)=>kind==='phone'?PHONE_TILT:el?.classList.contains('tilt-layer')?LANDING_MOUSE_TILT:MOUSE_TILT;

 function fitTilt(){
  const b=tiltEl();if(!b)return;
  // Reserve a safe box below the header, then project its corners at every permitted extreme.
  // A single outer scale accounts for perspective and the shallow child translateZ, without cursor feedback.
  const oldX=b.style.getPropertyValue('--rx'),oldY=b.style.getPropertyValue('--ry');
  b.style.setProperty('--rx','0deg');b.style.setProperty('--ry','0deg');b.style.setProperty('--fit','1');
  const r=b.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
  const top=document.querySelector('.site-header').getBoundingClientRect().bottom+10,inset=12;
  let scale=1;const rad=MAX_TILT*Math.PI/180;
  for(const ax of [-rad,rad])for(const ay of [-rad,rad])for(const px of [-r.width/2,r.width/2])for(const py of [-r.height/2,r.height/2])for(const depth of [0,8,12]){
   const xx=px*Math.cos(ay)+depth*Math.sin(ay),zz=-px*Math.sin(ay)+depth*Math.cos(ay);
   const yy=py*Math.cos(ax)-zz*Math.sin(ax),z=py*Math.sin(ax)+zz*Math.cos(ax),persp=1/(1-z/PERSPECTIVE),dx=xx*persp,dy=yy*persp;
   scale=Math.min(scale,dx>0?(innerWidth-inset-cx)/dx:(cx-inset)/-dx,dy>0?(innerHeight-inset-cy)/dy:(cy-top)/-dy);
  }
  b.style.setProperty('--fit',Math.max(.72,Math.min(1,scale*.995)).toFixed(4));b.style.setProperty('--rx',oldX||'0deg');b.style.setProperty('--ry',oldY||'0deg');
 }
 function animate(now){
  raf=0;if(document.hidden||reduced.matches||busy)return;const b=tiltEl();if(!b)return;
  const dt=last?Math.min(60,now-last):16;last=now;const ease=1-Math.exp(-dt/110);x+=(targetX-x)*ease;y+=(targetY-y)*ease;
  b.style.setProperty('--rx',x.toFixed(3)+'deg');b.style.setProperty('--ry',y.toFixed(3)+'deg');
  if(now-lastMove<2000||Math.abs(x-targetX)+Math.abs(y-targetY)>.01)raf=requestAnimationFrame(animate);
 }
 function move(a,b){if(busy||document.hidden||reduced.matches)return;targetX=Math.max(-MAX_TILT,Math.min(MAX_TILT,a+(MOUSE_DEVICE?REST_X:0)));targetY=Math.max(-MAX_TILT,Math.min(MAX_TILT,b+(MOUSE_DEVICE?REST_Y:0)));lastMove=performance.now();if(!raf){last=0;raf=requestAnimationFrame(animate);}}
 function resetTilt(){cancelAnimationFrame(raf);raf=0;targetX=targetY=x=y=0;document.querySelectorAll('[data-tilt]').forEach(b=>{b.style.setProperty('--rx','0deg');b.style.setProperty('--ry','0deg');});}
 const clamp=(v,m)=>Math.max(-m,Math.min(m,v));
 // The pointer is read against the scene, which never rotates. (Reading it against the board that is turning made the board chase the
 // cursor: as the edge moved away the cursor looked "outside", the tilt reset, and the hover flickered.)
 scenes.forEach(sc=>{
  const el=()=>sc.querySelector('[data-tilt]');
  sc.addEventListener('pointermove',e=>{
   if(busy||sc!==active||!drag||drag.id!==e.pointerId)return;const b=el();if(!b)return;drag.dx=e.clientX-drag.x;drag.dy=e.clientY-drag.y;const p=maxFor(b,'phone');
   if(permission!=='granted'||!hasOrientation)move(clamp(-drag.dy*.14,p),clamp(drag.dx*.14,p));
  });
  sc.addEventListener('pointerdown',e=>{if(busy||sc!==active||e.target.closest('button,a,.zoom,.mark-host'))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,dx:0,dy:0};try{if(e.pointerType!=='mouse')sc.setPointerCapture(e.pointerId);}catch(error){}});
  function end(e){if(!drag||drag.id!==e.pointerId)return;const d=drag;drag=null;if(Math.abs(d.dx)>70&&Math.abs(d.dx)>Math.abs(d.dy)*1.5)stepActive(d.dx<0?1:-1);move(0,0);}
  sc.addEventListener('pointerup',end);sc.addEventListener('pointercancel',()=>{drag=null;move(0,0);});
 });
 // A mouse anywhere in the window steers the tilt (the header is part of the window, so crossing it no longer resets it).
 document.addEventListener('pointermove',e=>{
  if(busy||e.pointerType!=='mouse'||drag||e.buttons)return;if(e.target.closest('a,button')){cancelAnimationFrame(raf);raf=0;targetX=x;targetY=y;return;}const b=tiltEl();if(!b)return;const r=active.getBoundingClientRect(),m=maxFor(b,'mouse');
  move(clamp(-((e.clientY-r.top)/r.height-.5)*2*m,m),clamp(((e.clientX-r.left)/r.width-.5)*2*m,m));
 });
 document.documentElement.addEventListener('mouseleave',()=>{if(!drag)move(0,0);});
 addEventListener('deviceorientation',e=>{
  if(permission!=='granted'||busy||!tiltEl()||e.beta===null||e.gamma===null)return;
  hasOrientation=true;if(!pose){pose={beta:e.beta,gamma:e.gamma};return;}
  // Tilt relative to how the phone was held; turn the sensor axes into screen axes.
  const angle=(screen.orientation?.angle||0)*Math.PI/180,db=e.beta-pose.beta,dg=e.gamma-pose.gamma,m=maxFor(tiltEl(),'phone');
  move(clamp(-(db*Math.cos(angle)+dg*Math.sin(angle))*.9,m),clamp((dg*Math.cos(angle)-db*Math.sin(angle))*.9,m));
 });
 reduced.addEventListener('change',()=>{resetTilt();stopAutos();unmountMark();enter(active);});
 document.addEventListener('visibilitychange',()=>{resetTilt();if(document.hidden){unmountMark();stopAutos();}else enter(active);});
 addEventListener('pagehide',()=>{resetTilt();unmountMark();});
 document.documentElement.classList.add('js');
 enter(document.getElementById(route()));
 window.SiteBoard={get scene(){return active.id;},get permission(){return permission;},get tilt(){return {x,y,targetX,targetY,running:!!raf};}};
})();
