/* Agent Hub site: scene navigation, auto-playing step lists, the pulsing grid, the fading-in mark, and a tilt that follows the pointer or the phone. */
(()=>{'use strict';
 const scenes=[...document.querySelectorAll('.scene')],reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let active=document.getElementById('landing'),busy=false,mark=null,stopToggle=null,shell=true,permission='unknown',pose=null,hasOrientation=false,pendingRoute=null;
 try{permission=sessionStorage.getItem('site:orientation')||'unknown';}catch(error){}
 const route=()=>document.getElementById(location.hash.slice(1))?.matches('.scene')?location.hash.slice(1):'landing';
 const MAX_TILT=10, REST_X=-3, REST_Y=3.5, MOUSE_DEVICE=matchMedia('(hover:hover) and (pointer:fine)').matches, MOUSE_TILT=6, LANDING_MOUSE_TILT=4.5, PHONE_TILT=10, PERSPECTIVE=1600;
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

 document.querySelectorAll('[data-limit]').forEach(b=>b.addEventListener('click',()=>b.setAttribute('aria-expanded',String(b.getAttribute('aria-expanded')!=='true'))));
 document.querySelectorAll('[data-agent-jump]').forEach(b=>b.addEventListener('click',()=>{const a=autos.find(a=>a.scene.id==='agents'&&a.el.classList.contains('agents-auto'));if(a){const i=a.btns.findIndex(x=>(x.dataset.img||'').endsWith('/'+b.dataset.agentJump+'.png'));if(i>=0)pin(a,i,10000);}}));
 /* small glass blocks open to show more */
 document.querySelectorAll('[data-more]').forEach(b=>b.addEventListener('click',()=>b.setAttribute('aria-expanded',b.getAttribute('aria-expanded')==='true'?'false':'true')));

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
/* One scenario model drives the illustration, footer and insight cards on every viewport. */
const DEMO_OUTCOMES={
 missions:['A request enters the mission inbox.','The router chooses a code mission.','Briefs are assigned to the team.','A private worktree changes; main stays still.','The mission waits for your answer.','The changed lines are ready to read.','The private branch waits for your decision.'],
 pc:['Smith hands the goal to desktop control.','The Play control is located by name.','The proposed press waits at the approval gate.','The approved press reaches the app.','The agent checks the changed window.','A successful run becomes a candidate routine.'],
 media:['The example link becomes a PC download.','The source file passes through ffmpeg.','The result appears in the chosen folder.','A phone transfer appears in the PC inbox.'],
 graph:['Demo projects appear with related-project links.','The selected project opens its working branches.','The selected branch opens its changed-file diff.','Merge and leave remain your choices.'],
 install:['The installer opens its first-run choices.','Selected tools enter the setup queue.','PC and phone join the same private network.','The saved bookmark opens the Hub.'],
 hands:['HANDS starts only after you choose it.','The index-finger cursor follows the hand.','A pinch presses; movement drags the block.','Two pinches change the board zoom.','A fist turns the board in its 3D view.','An open hand fits the board; Escape stops the camera.'],
 talk:['Smith returns a routine answer.','Smith sends the code request to a mission.','Smith hands the app task to desktop control.','Smith sends the link to media tools.','Smith opens project status and the diff.','A scheduled mission stops at review.']
};
function demoModel(a){
 const b=a.btns[a.i],sid=a.scene.id,skill=sid==='agents'&&!a.el.classList.contains('agents-auto');
 let key=sid,outcome=(DEMO_OUTCOMES[sid]||[])[a.i]||b.dataset.d,guard=a.scene.querySelector('[data-limit]')?.querySelector('span:not(.limit-title):not(.limit-more)')?.textContent||'Review the result before applying it.';
 if(sid==='agents'){key=skill?'skills':(b.dataset.img||'').split('/').pop().replace('.png','');outcome={smith:'Smith routes the request to the right tool.',neo:'A persona draft is ready for you to read and save.',doctor:'A checked repair diff waits for your APPLY.',orchestrator:'The plan hands one brief to a named worker.',coder:'The change stays in the private working copy.',reviewer:'A verdict returns to the mission review.',tester:'Test results return to the review.',skills:'Instructions become available to the agents.'}[key]||b.dataset.d;}
 if(sid==='graph'&&a.i===3&&a.demoChoice)outcome=a.demoChoice==='merge'?'DEMO: the branch merged after your choice.':'DEMO: the branch stays separate; main is unchanged.';
 if(sid==='missions'&&a.i===6&&a.demoChoice)outcome=a.demoChoice==='apply'?'DEMO: the approved change reached main.':'DEMO: the private copy was discarded.';
 const ask=b.dataset.you||'Choose a step to follow the demonstration.';
 return {sid,key,title:b.dataset.t,actor:b.dataset.k,ask,outcome,guard,image:b.dataset.img||(['talk','missions','pc'].includes(sid)?'assets/agents/smith.png':null),step:a.i};
}
function updateInsights(a,model,phase){
 const sc=a.scene,foot=sc.querySelector('.story-foot');if(foot){const p=foot.querySelector('.try-panel>p');if(p)p.textContent=model.ask;const e=foot.querySelector('.expect');if(e)e.textContent=(phase===2?'RESULT · ':'FOLLOW · ')+model.outcome;foot.dataset.step=model.key+'-'+model.step;}
 const small=sc.querySelectorAll('.small-block');if(small[0]){small[0].dataset.detail=model.actor+' — '+model.title+'. '+model.outcome;small[0].querySelector('.label').textContent='THIS STEP';const line=small[0].querySelector('.line');if(line){line.textContent=model.actor;line.classList.add('context-line');}}
 if(small[1]){small[1].dataset.detail=(model.sid==='hands'?'Camera gestures control the Hub board in your browser. They do not control the operating system.':model.sid==='pc'?'This step uses Windows MCP on the host PC. Approval is required before the press.':'The Hub runs this step on your PC. Your other devices reach its browser interface through your private network.')+' '+model.outcome;const label=small[1].querySelector('.label');label.textContent='WHERE IT RUNS';}
 if(a.scene.id==='talk'){a.scene.querySelectorAll('.say-table tbody tr').forEach((r,i)=>r.classList.toggle('example-active',i===a.i));}
}
function stopDemo(a){(a.demoTimers||[]).forEach(clearTimeout);a.demoTimers=[];}
function animateDemo(a,host,model){
 stopDemo(a);host.dataset.phase=reduced.matches?'2':'0';updateInsights(a,model,reduced.matches?2:0);
 if(!a.live||reduced.matches||document.hidden)return;
 [1,2].forEach((phase,i)=>a.demoTimers.push(setTimeout(()=>{if(a.live){host.dataset.phase=String(phase);updateInsights(a,model,phase);}},850+i*850)));
}
function syncTalk(a){
 if(a.scene.id!=='talk')return;const machine=a.scene.querySelector('.machine');if(!machine)return;
 const animations=machine.getAnimations({subtree:true});animations.forEach(x=>{x.currentTime=a.i*9000+100;x.playbackRate=2;if(reduced.matches)x.pause();else x.play();});
 if(!reduced.matches)a.demoTimers.push(setTimeout(()=>animations.forEach(x=>x.pause()),3950));
}
function drawVisual(a){
 const host=a.detail.querySelector('[data-visual]'),model=demoModel(a);updateInsights(a,model,0);
 if(!host||!host.offsetParent){stopDemo(a);syncTalk(a);return;}
 const w=host.clientWidth,h=host.clientHeight;if(w<70||h<70)return;
 const compact=w<360||h<180||(innerHeight<540&&innerWidth>innerHeight),W=compact?360:720,H=compact?(h<230?Math.max(160,Math.min(220,(h-44)*360/w)):220):320;
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('role','img');svg.setAttribute('aria-label','Illustrative demonstration: '+model.outcome);svg.dataset.scenario=model.key+'-'+model.step;
 const make=(tag,attrs={},text,parent=svg)=>{const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;parent.append(e);return e;};
 const txt=(x,y,t,size=compact?13:16,color='#d9ffe9',parent=svg)=>make('text',{x,y,fill:color,'font-size':size,'font-family':'Outfit,system-ui,sans-serif'},t,parent);
 const path=(d,cls='',color='#41ebff')=>make('path',{d,fill:'none',stroke:color,'stroke-width':2.2,class:cls});
 const box=(x,y,bw,bh,title,note,stage=0)=>{const g=make('g',{class:'demo-node stage-'+stage});make('rect',{x,y,width:bw,height:bh,fill:'#07162c','fill-opacity':'.5',stroke:'#41ebff','stroke-opacity':'.6'},undefined,g);const fs=compact?11:17,limit=Math.floor((bw-16)/(fs*.52)),words=title.split(' '),lines=[''];words.forEach(word=>{let i=lines.length-1;if((lines[i]+' '+word).trim().length>limit&&lines[i])lines.push(word);else lines[i]=(lines[i]+' '+word).trim();});lines.slice(0,2).forEach((t,i)=>txt(x+8,y+20+i*(fs+2),t,fs,'#00e676',g));if(note&&(!compact||lines.length===1)){const n=note.length>limit?note.slice(0,limit-1)+'…':note;txt(x+8,y+bh-10,n,compact?10:14,'#b4d1c4',g);}return g;};
 const packet=(x,y,dx,dy,delay=0)=>make('circle',{cx:x,cy:y,r:5,fill:'#afffe9',class:'demo-packet',style:`--dx:${dx}px;--dy:${dy}px;animation-delay:${delay}s`});
 const branch=(x1,y1,x2,y2)=>path(`M${x1} ${y1}C${x1+35} ${y1} ${x2-35} ${y2} ${x2} ${y2}`,'demo-line');
 const status=(text)=>{if(compact&&text.length>57){const cut=text.lastIndexOf(' ',57);txt(12,H-24,text.slice(0,cut),11,'#a8cbb9');txt(12,H-10,text.slice(cut+1),11,'#a8cbb9');}else txt(12,H-10,text,compact?11:14,'#a8cbb9');};
 if(model.sid==='graph'){
  if(model.step===0){
   const nodes=[['Lantern App',W*.22,H*.36],['Harbor API',W*.75,H*.3],['Field Notes',W*.58,H*.72]];
   [[0,1],[0,2],[1,2]].forEach(([i,j])=>{path(`M${nodes[i][1]} ${nodes[i][2]}L${nodes[j][1]} ${nodes[j][2]}`,'demo-line demo-related','#b590ff');packet(nodes[i][1],nodes[i][2],nodes[j][1]-nodes[i][1],nodes[j][2]-nodes[i][2],i*.2);});
   nodes.forEach(([name,x,y],i)=>{make('circle',{cx:x,cy:y,r:compact?17:24,fill:'#0c2643',stroke:i?'#00e676':'#41ebff','stroke-width':2,class:'demo-orbit'});txt(x-name.length*(compact?3:4),y+43,name);});status('Purple links: related projects from project notes');
  }else{
   const x1=24,x2=W-24,y=H*.3,by=H*.66;path(`M${x1} ${y}H${x2}`,'demo-line','#00e676');txt(x1,y-17,'Lantern App · main',compact?12:16,'#00e676');[.16,.36,.58,.86].forEach(q=>make('circle',{cx:W*q,cy:y,r:6,fill:'#00e676'}));branch(W*.28,y,W*.45,by);path(`M${W*.45} ${by}H${W*.79}`,'demo-line');txt(W*.42,by+27,'feature / night-mode',compact?11:15);make('circle',{cx:W*.77,cy:by,r:7,fill:'#41ebff',class:'demo-orbit'});
   if(model.step===1){box(W*.48,H*.03,W*.45,48,'Private worktree','Agent edits stay here',1);packet(W*.28,y,W*.4,by-y);status('Select a branch to inspect its working copy');}
   if(model.step===2){make('rect',{x:W*.43,y:18,width:W*.54,height:H-48,fill:'#08172e',stroke:'#41ebff'});txt(W*.46,45,'theme.css · demo diff',compact?12:17);txt(W*.46,82,'− color-scheme: light;',compact?11:16,'#ffb0ae');txt(W*.46,117,'+ color-scheme: dark;',compact?11:16,'#00e676');status('Click a project → inspect a branch → read the diff');}
   if(model.step===3){if(a.demoChoice==='merge'){branch(W*.77,by,W*.9,y);packet(W*.77,by,W*.13,y-by);status('DEMO: selected branch merged after your choice');}else if(a.demoChoice==='leave')status('DEMO: branch kept separate; main is unchanged');else status('The branch stays separate until you choose');}
  }
 }else if(model.sid==='missions'){
  const s=model.step;
  if(s<3){const names=['Request inbox','Route: code mission','Planner briefs'];names.forEach((t,i)=>box(12+i*(W/3),H*.32,W/3-22,65,t,['Your sentence','Named worker','Private worktree'][i],i));path(`M${W*.2} ${H*.65}H${W*.82}`,'demo-line');packet(W*.15,H*.65,W*.68,0);status(['A sentence enters the inbox','A code request becomes a mission','The planner assigns the next brief'][s]);}
  else{box(14,H*.1,W*.42,H*.68,'main','Your project stays still');box(W*.55,H*.1,W*.42,H*.68,'private worktree',s===3?'Agent writes the change':s===4?'Question: which theme?':s===5?'Diff ready to review':'Waiting for your choice',1);branch(W*.44,H*.42,W*.55,H*.42);if(s===3){txt(W*.58,H*.48,'+ dark theme',compact?13:21,'#00e676');make('rect',{x:W*.58,y:H*.6,width:W*.32,height:8,fill:'#00e676',class:'demo-progress'});}if(s===5){txt(W*.58,H*.5,'− light',16,'#ffb0ae');txt(W*.58,H*.63,'+ dark',16,'#00e676');}if(s===6&&a.demoChoice==='apply'){branch(W*.55,H*.65,W*.3,H*.65);packet(W*.55,H*.65,-W*.25,0);}status(s===6?(a.demoChoice==='apply'?'DEMO: approved change applied':a.demoChoice==='discard'?'DEMO: private copy discarded':'APPLY and DISCARD are your decisions'):s===4?'A blocked mission waits for your answer':'Review happens before main changes');}
 }else if(model.sid==='pc'){
  const x=W*.12,y=H*.15;box(x,y,W*.76,H*.65,'Demo music player','Windows MCP reads named controls');make('rect',{x:W*.38,y:H*.45,width:W*.24,height:48,fill:'#0e3643',stroke:model.step>=2?'#ffd080':'#41ebff','stroke-width':2,class:model.step>=3?'demo-press':''});txt(W*.43,H*.45+30,model.step>=3?'Playing':'Play',compact?15:20);make('path',{d:`M${W*.24} ${H*.7}l18 -32 9 40-13-6-7 12z`,fill:'#afffe9',class:'demo-cursor'});if(model.step===2)box(W*.52,12,W*.43,60,'ASK FIRST','You approve or refuse',1);if(model.step>=4)txt(W*.19,H*.7,'✓ Window changed',compact?14:20,'#00e676');if(model.step===0){box(12,8,W*.65,62,'You → Smith','Open the player and play liked songs',1);packet(W*.22,72,W*.28,H*.24);}if(model.step===1){make('rect',{x:W*.34,y:H*.4,width:W*.32,height:65,fill:'none',stroke:'#00e676','stroke-width':3,class:'demo-press'});txt(W*.18,H*.88,'Control name: Play',compact?12:17,'#00e676');}if(model.step===5){box(W*.22,H*.25,W*.62,H*.45,'Candidate routine','Checked run → saved for next time',2);make('path',{d:`M${W*.72} ${H*.44}l12 12 22-25`,fill:'none',stroke:'#00e676','stroke-width':4,class:'demo-line'});}status(['Smith hands over the app task','Control found: Play','No press before your approval','The approved press reaches the app','The result is checked, not assumed','A verified run is saved as a candidate'][model.step]);
 }else if(model.sid==='media'){
  const s=model.step,names=s===0?['Video link','yt-dlp','Source file']:s===1?['Source file','ffmpeg','Audio file']:s===2?['Audio file','Save','Chosen folder']:['Phone','Private transfer','PC inbox'];
  names.forEach((t,i)=>box(12+i*(W/3),H*.25,W/3-22,70,t,i===1?'Runs on your PC':i===2?'Your file':'Demo source',i));path(`M${W*.15} ${H*.7}H${W*.85}`,'demo-line');packet(W*.16,H*.7,W*.68,0);make('rect',{x:W*.1,y:H*.82,width:W*.8,height:9,fill:'#00e676',class:'demo-progress'});status(['Download progresses to a local source file','Conversion creates the selected format','The file lands in your chosen folder','A received file appears in the inbox'][s]);
 }else if(model.sid==='hands'){
  const g=make('g',{class:'demo-hand'}),hx=W*.24,hy=H*.53;
  path(`M${hx-18} ${hy+45}L${hx-33} ${hy-5}Q${hx-40} ${hy-24} ${hx-27} ${hy-23}L${hx-14} ${hy-4}V${hy-62}Q${hx-7} ${hy-73} ${hx} ${hy-62}V${hy-7}V${hy-80}Q${hx+8} ${hy-90} ${hx+14} ${hy-78}V${hy-4}V${hy-65}Q${hx+23} ${hy-77} ${hx+27} ${hy-62}V${hy+2}V${hy-42}Q${hx+37} ${hy-50} ${hx+40} ${hy-36}L${hx+36} ${hy+35}L${hx+23} ${hy+52}`,'demo-hand-line');
  const card=box(W*.5,H*.19,W*.44,H*.6,'Hub board','Browser controls only',1);if(model.step===2)card.setAttribute('class','demo-node demo-drag');if(model.step===3)card.setAttribute('class','demo-node demo-zoom');if(model.step===4)card.setAttribute('class','demo-node demo-tilt');
  make('circle',{cx:hx,cy:hy-60,r:13,fill:'none',stroke:'#00e676','stroke-width':2,class:'demo-orbit'});packet(hx+30,hy,W*.28,-H*.1);status(['Camera start is explicit','Point: move the board cursor','Pinch: press; keep pinched to drag','Two pinches: zoom the board','Fist: turn the board in 3D view','Open hand: fit · Escape: camera off'][model.step]);
 }else if(model.sid==='agents'){
  const key=model.key,roles=key==='neo'?['Your job description','Neo drafts a persona','You read and save']:key==='doctor'?['Hub facts','Repair in private copy','Checks → your APPLY']:key==='skills'?['Skill instructions','Agent skill folders','Used by your agents']:key==='desktop-agent'?['Your app task','Windows desktop agent','Approved press + check']:key==='smith'?['Your request','Smith chooses a route','Tool / agent / answer']:['Mission brief',model.title,'Review the result'];
  roles.forEach((t,i)=>box(12+i*(W/3),H*.46,W/3-22,64,t, i===2?'Your decision':'A named handoff',i));
  if(key==='skills'){make('path',{d:`M${W*.5-24} 8h34l14 14v58h-48zM${W*.5+10} 8v16h14M${W*.5-13} 38h26M${W*.5-13} 50h26M${W*.5-13} 62h18`,fill:'none',stroke:'#41ebff','stroke-width':2,class:'demo-avatar'});}else{const image=model.image||'assets/agents/neo.png';make('image',{href:image,x:W*.5-38,y:10,width:76,height:76,preserveAspectRatio:'xMidYMid meet',class:'demo-avatar'});}path(`M${W*.15} ${H*.84}H${W*.85}`,'demo-line');packet(W*.15,H*.84,W*.7,0);status(model.outcome);
 }else if(model.sid==='install'){
  if(model.step===0){['Windows','macOS','Linux'].forEach((t,i)=>{box(12+i*(W/3),H*.22,W/3-22,H*.48,t,i===1?'Unsigned build':'Choose this installer',i);make('path',{d:`M${24+i*(W/3)} ${H*.55}h${W/3-50}`,stroke:'#00e676','stroke-width':4,class:'demo-line'});});}else if(model.step===1){['Media tools','Git tools','Model tools'].forEach((t,i)=>{box(12,H*.06+i*(H*.28),W-24,H*.23,t,'First-run choice',i);txt(W*.83,H*.06+i*(H*.28)+28,'✓',22,'#00e676');});}else{['Your PC','Private network','Your phone'].forEach((t,i)=>box(12+i*(W/3),H*.28,W/3-22,72,t,['Hub runs here','Tailscale',model.step===3?'Saved Hub bookmark':'Join your devices'][i],i));path(`M${W*.16} ${H*.75}H${W*.85}`,'demo-line');packet(W*.16,H*.75,W*.68,0);if(model.step===3)make('rect',{x:W*.68,y:H*.19,width:W*.3,height:H*.48,fill:'none',stroke:'#00e676','stroke-width':3,class:'demo-press'});}status(model.outcome);
 }else{
  const targets=['Saved routine','Mission','Desktop agent','Media tools','Git Graph','Schedule'],target=targets[model.step]||'Router';box(12,H*.4,W*.27,68,'Your request','Speak or type');box(W*.37,H*.4,W*.27,68,'Agent Smith','Routes the request',1);box(W*.72,H*.4,W*.26-10,68,target,'Answer / result',2);make('image',{href:'assets/agents/smith.png',x:W*.5-35,y:10,width:70,height:70,preserveAspectRatio:'xMidYMid meet'});path(`M${W*.15} ${H*.8}H${W*.85}`,'demo-line');packet(W*.15,H*.8,W*.7,0);status(model.outcome);
 }
 const toolbar=document.createElement('div');toolbar.className='demo-toolbar';const label=document.createElement('span');label.textContent='ILLUSTRATED DEMO · '+model.title;toolbar.append(label);
 function control(text,action){const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',action);toolbar.append(b);}
 control('↻',()=>{a.demoChoice=null;drawVisual(a);});toolbar.lastElementChild.setAttribute('aria-label','Replay this demonstration');
 control('Ⅱ',()=>{stopDemo(a);a.pinned=true;clearTimeout(a.timer);clearTimeout(a.resume);host.querySelectorAll('svg').forEach(s=>s.getAnimations({subtree:true}).forEach(x=>x.pause()));});toolbar.lastElementChild.setAttribute('aria-label','Pause this demonstration');
 host.replaceChildren(toolbar,svg);
 if((model.sid==='graph'&&model.step===3)||(model.sid==='missions'&&model.step===6)){const choices=document.createElement('div');choices.className='demo-choices';const items=model.sid==='graph'?[['Preview merge','merge'],['Leave branch','leave']]:[['Preview APPLY','apply'],['Preview DISCARD','discard']];items.forEach(([text,val])=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.addEventListener('click',()=>{a.demoChoice=val;a.pinned=true;clearTimeout(a.timer);drawVisual(a);});choices.append(b);});host.append(choices);}
 animateDemo(a,host,model);syncTalk(a);
}

/* One modal sheet replaces every absolute-positioned insight popup. */
const insight=document.createElement('dialog');insight.className='insight-dialog';insight.innerHTML='<button type="button" class="insight-close" aria-label="Close details">×</button><p class="label"></p><h2></h2><p class="insight-copy"></p>';
document.body.append(insight);let insightOpener=null,insightAuto=null;
function openInsight(button){const sc=button.closest('.scene'),a=autos.find(x=>x.scene===sc&&x.live),model=a?demoModel(a):null;insightOpener=button;insightAuto=a;if(a){a.pinned=true;clearTimeout(a.timer);clearTimeout(a.resume);}insight.querySelector('.label').textContent=sc?.querySelector('.blk-h>.label')?.textContent||'Agent Hub';insight.querySelector('h2').textContent=button.matches('[data-limit]')?'Limits for this tool':button.querySelector('.label')?.textContent||'Step details';insight.querySelector('.insight-copy').textContent=button.dataset.detail||(button.matches('[data-limit]')?(model?.guard||button.querySelector('span:not(.limit-title):not(.limit-more)')?.textContent):(button.querySelector('.more')?.textContent||''));button.setAttribute('aria-expanded','true');insight.showModal();}
insight.querySelector('button').addEventListener('click',()=>insight.close());insight.addEventListener('close',()=>{insightOpener?.setAttribute('aria-expanded','false');insightOpener?.focus();if(insightAuto?.live){insightAuto.pinned=false;play(insightAuto);}});
document.addEventListener('click',e=>{const b=e.target.closest('[data-more],[data-limit]');if(b){e.preventDefault();e.stopImmediatePropagation();openInsight(b);}},true);

function drawArchitecture(){
 const map=document.querySelector('.scene.active .arch-map');if(!map)return;const svg=map.querySelector('.arch-connectors');const r=map.getBoundingClientRect();
 // Offsets avoid feeding the board's current rotation back into diagram layout.
 const w=map.clientWidth,h=map.clientHeight;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.innerHTML='<defs><marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#41ebff"/></marker></defs>';
 const location=e=>{let x=0,y=0,n=e;while(n&&n!==map){x+=n.offsetLeft;y+=n.offsetTop;n=n.offsetParent;}return {x,y,w:e.offsetWidth,h:e.offsetHeight};};
 const connect=(from,to)=>{const a=location(map.querySelector(`[data-node="${from}"]`)),b=location(map.querySelector(`[data-node="${to}"]`));const n=document.createElementNS('http://www.w3.org/2000/svg','path');let d;if(to.startsWith('lane')){const x=a.x+a.w/2,y=a.y+a.h,xx=b.x+b.w/2,yy=b.y;d=`M${x} ${y}L${x} ${y+10}L${xx} ${y+10}L${xx} ${yy}`;}else d=`M${a.x+a.w} ${a.y+a.h/2}L${b.x} ${b.y+b.h/2}`;n.setAttribute('d',d);n.setAttribute('fill','none');n.setAttribute('stroke',from==='smith'?'#00e676':'#41ebff');n.setAttribute('stroke-opacity','.45');n.setAttribute('stroke-width','1.5');n.setAttribute('marker-end','url(#arch-arrow)');svg.append(n);};
 [['devices','network'],['network','smith'],['smith','router']].forEach(([a,b])=>connect(a,b));map.querySelectorAll('[data-from]').forEach(n=>connect(n.dataset.from,n.dataset.node));
}


 let settleTimer=0;
 /* ---------- navigation ---------- */
 function enter(scene){
  clearTimeout(settleTimer);scenes.forEach(s=>s.classList.remove('settling'));if(!reduced.matches){scene.classList.add('settling');settleTimer=setTimeout(()=>scene.classList.remove('settling'),1200);}
  active=scene;scenes.forEach(s=>{s.classList.remove('leaving');s.classList.toggle('active',s===active);s.setAttribute('aria-hidden',s===active?'false':'true');s.inert=s!==active;});
  stopAutos();startAutos(active);fit();requestAnimationFrame(fit);if(active.id==='landing'){mountMark();sizeGrid();startGrid();}else unmountMark();
  setTimeout(()=>move(0,0),60);
  const back=document.querySelector('[data-projects]');if(back){const home=scene.id==='landing';back.textContent=home?'← PROJECTS':'← AGENT HUB';back.setAttribute('href',home?'https://infernalzeus.github.io/':'#');back.setAttribute('aria-label',home?'Back to the projects page':'Back to the Agent Hub landing page');}
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
  if(insight.open){if(e.key==='Escape'){e.preventDefault();insight.close();}return;}
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
  for(const ax of [-rad,rad])for(const ay of [-rad,rad])for(const px of [-r.width/2,r.width/2])for(const py of [-r.height/2,r.height/2])for(const depth of [-72,0,22]){
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
