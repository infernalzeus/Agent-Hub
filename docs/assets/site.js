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
  a.i=(i+a.btns.length)%a.btns.length;const b=a.btns[a.i];
  a.btns.forEach(x=>x.setAttribute('aria-pressed',x===b?'true':'false'));
  a.detail.dataset.n=a.i+1;a.kicker.textContent=b.dataset.k;a.h3.textContent=b.dataset.t;a.d.textContent=b.dataset.d;a.you.textContent=b.dataset.you||'';a.detail.querySelector('.you').hidden=!b.dataset.you;if(b.dataset.img){a.pic.src=b.dataset.img;a.pic.hidden=false;}else a.pic.hidden=true;a.chips.textContent='';(b.dataset.chips||'').split('|').filter(Boolean).forEach(c=>{const i=document.createElement('span');i.className='chip';i.textContent=c;a.chips.appendChild(i);});
  detailSymbol(a);drawVisual(a);a.el.classList.remove('playing');void a.el.offsetWidth;if(!a.pinned&&!reduced.matches&&a.live)a.el.classList.add('playing');
 }
 function play(a){clearTimeout(a.timer);if(!a.live||a.pinned||reduced.matches)return;a.el.style.setProperty('--step',STEP+'ms');a.el.classList.add('playing');a.timer=setTimeout(()=>{select(a,a.i+1);play(a);},STEP);}
 function pin(a,i,ms){a.pinned=true;clearTimeout(a.timer);clearTimeout(a.resume);select(a,i);a.el.classList.remove('playing');a.resume=setTimeout(()=>{a.pinned=false;play(a);},ms);}
 function startAutos(scene){autos.filter(a=>a.scene===scene).forEach(a=>{a.live=!!a.el.offsetParent;a.pinned=false;clearTimeout(a.resume);if(a.live){select(a,0);play(a);}});}
 function stopAutos(){autos.forEach(a=>{a.live=false;clearTimeout(a.timer);clearTimeout(a.resume);a.el.classList.remove('playing');});}
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
function drawVisual(a){
 const host=a.detail.querySelector('[data-visual]');if(!host||!host.offsetParent)return;
 const w=host.clientWidth,h=host.clientHeight;if(w<80||h<60)return;
 const sid=a.scene.id,svgNS='http://www.w3.org/2000/svg',svg=document.createElementNS(svgNS,'svg');
 svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',`${sid}: an illustration of the handoff and the decision you make`);
 function node(tag,attrs,text){const n=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text)n.textContent=text;svg.append(n);return n;}
 const text=(x,y,t,size=13,color='#d9ffe9')=>node('text',{x,y,fill:color,'font-size':size,'font-family':'Outfit,system-ui,sans-serif'},t);
 const line=(x,y,xx,yy)=>node('path',{d:`M${x} ${y}L${xx} ${yy}`,stroke:'#41ebff','stroke-opacity':'.65','stroke-width':1.5,fill:'none','marker-end':'url(#arrow-'+sid+')'});
 const defs=node('defs',{});const marker=document.createElementNS(svgNS,'marker');marker.setAttribute('id','arrow-'+sid);marker.setAttribute('viewBox','0 0 10 10');marker.setAttribute('refX','9');marker.setAttribute('refY','5');marker.setAttribute('markerWidth','5');marker.setAttribute('markerHeight','5');marker.setAttribute('orient','auto');const tip=document.createElementNS(svgNS,'path');tip.setAttribute('d','M0 0L10 5L0 10');tip.setAttribute('fill','#41ebff');marker.append(tip);defs.append(marker);
 const box=(x,y,bw,bh,title,note,color='#00e676')=>{node('rect',{x,y,width:bw,height:bh,fill:'#080c28','fill-opacity':'.36',stroke:color,'stroke-opacity':'.45'});text(x+12,y+24,title,Math.max(11,Math.min(15,w/30)),color);if(note)text(x+12,y+45,note,Math.max(10,Math.min(13,w/36)));};
 text(10,18,'ILLUSTRATION · '+({missions:'PRIVATE COPY → YOUR REVIEW',pc:'YOUR APPROVAL COMES FIRST',media:'FROM LINK TO YOUR FILE',graph:'PROJECT → BRANCH → DIFF',agents:'A HANDOFF YOU CAN READ',install:'YOUR DEVICES, YOUR PC',talk:'SMITH HANDS THE REQUEST ON'}[sid]||'HOW IT WORKS'),Math.min(11,w/37),'#9dcbb7');
 if(w<220){
  svg.replaceChildren();const titles={pc:['YOU approve','MCP acts'],media:['YOU choose','PC saves'],graph:['YOU inspect','YOU decide'],missions:['Agent copy','YOU review'],talk:['YOU ask','Smith routes'],install:['YOU install','YOU connect'],agents:['Neo drafts','YOU save']}[sid]||['YOU ask','HUB acts'];
  const bh=Math.max(24,(h-16)/2-6);titles.forEach((t,i)=>{node('rect',{x:4,y:4+i*(bh+12),width:w-8,height:bh,fill:'#0a1632',stroke:'#41ebff','stroke-opacity':'.45'});text(10,4+i*(bh+12)+bh/2+4,t,11,i?'#00e676':'#d9ffe9');});line(w/2,bh+4,w/2,bh+15);host.replaceChildren(svg);return;
 }
 if(['missions','pc','talk'].includes(sid))node('image',{href:'assets/agents/smith.png',x:w-36,y:0,width:30,height:30});
 const top=34,gap=18,third=(w-20-gap*2)/3;
 if(sid==='graph'){
  const step=a.i||0,fs=Math.max(10,Math.min(13,w/44)),G='#00e676',C='#41ebff',R='#ff8f8f';
  const at=(tag,attrs,text,delay,cls)=>{const n=node(tag,attrs,text);n.setAttribute('class',cls||'gv-fade');n.style.animationDelay=(delay||0)+'s';return n;};
  const draw=(d,delay,col,wd)=>at('path',{d,pathLength:1,stroke:col||C,'stroke-width':wd||2,fill:'none','stroke-linecap':'round'},'',delay,'gv-draw');
  const dot=(x,y,r,delay,col,fill)=>at('circle',{cx:x,cy:y,r,fill:fill||'#0d2040',stroke:col||G,'stroke-width':2},'',delay,'gv-pop');
  const mx=w*.08,mxe=w*.92,my=h*.38,fx=w*.3,by=h*.7,bxe=w*.7;
  if(step===0){
   const names=[['agent-hub',.5,.34],['wiki',.22,.58],['clipper',.74,.6],['cadenza',.3,.28],['mri-sim',.82,.3]];
   names.forEach(([n,px,py],i)=>{const x=w*px,y=h*py+8;dot(x,y,Math.min(15,h*.055),i*.22,i===0?C:G);at('text',{x:x-n.length*3.2,y:y+Math.min(34,h*.12),fill:'#d9ffe9','font-size':fs,'font-family':'Outfit,system-ui,sans-serif'},n,i*.22+.2);});
   const x0=w*.5,y0=h*.34+8;[0,1].forEach(k=>{const c=at('circle',{cx:x0,cy:y0,r:Math.min(15,h*.055),fill:'none',stroke:C,'stroke-width':2},'',k*.9+1.1,'gv-ring');});
   text(10,h-14,'YOU: choose a project dot — one dot per repo, found in your folders',Math.min(13,w/42),'#d9ffe9');
  }else if(step===1){
   draw(`M${mx} ${my}L${mxe} ${my}`,0,G,3);[.12,.3,.5,.72,.92].forEach((q,i)=>dot(w*q,my,5,.25+i*.18,G,G));
   draw(`M${fx} ${my}C${fx+30} ${my} ${fx+24} ${by} ${fx+60} ${by}L${bxe} ${by}`,1,C,3);[.46,.58,.7].forEach((q,i)=>dot(w*q,by,5,1.5+i*.2,C,C));
   at('text',{x:mx,y:my-14,fill:G,'font-size':fs,'font-family':'Outfit,system-ui,sans-serif'},'main · your code, untouched',.4);
   at('text',{x:fx+60,y:by+24,fill:C,'font-size':fs,'font-family':'Outfit,system-ui,sans-serif'},'agent copy · 3 files changed',2.1);
   at('text',{x:mx,y:h-14,fill:'#d9ffe9','font-size':Math.min(13,w/42),'font-family':'Outfit,system-ui,sans-serif'},'HUB reads this straight from git — nothing is stored elsewhere',2.6);
  }else if(step===2){
   const lw=w*.4;draw(`M${mx} ${my}L${lw} ${my}`,0,G,3);draw(`M${w*.2} ${my}C${w*.22} ${my} ${w*.2} ${by} ${w*.26} ${by}L${lw} ${by}`,.2,C,3);[.14,.3].forEach((q,i)=>dot(w*q,my,5,.2,G,G));[.3,.38].forEach((q,i)=>dot(w*q,by,5,.4,C,C));
   const px=w*.46,pw=w*.5,py=18,ph=h-44;node('rect',{x:px,y:py,width:pw,height:ph,fill:'#050a20','fill-opacity':'.6',stroke:C,'stroke-opacity':'.4'});
   at('text',{x:px+12,y:py+22,fill:C,'font-size':fs,'font-family':'Outfit,system-ui,sans-serif'},'settings.css  +1 −1',.2);
   [['  .page {',null],['−   color-scheme: light;',R],['+   color-scheme: dark;',G],['    background: #070a25;',null],['  }',null]].forEach(([t,c],i)=>at('text',{x:px+14,y:py+50+i*Math.max(18,ph*.11),fill:c||'#a8cbb9','font-size':fs,'font-family':'Consolas,monospace'},t,.7+i*.45));
   at('text',{x:mx,y:h-14,fill:'#d9ffe9','font-size':Math.min(13,w/42),'font-family':'Outfit,system-ui,sans-serif'},'YOU: read every changed line before deciding',1.5);
  }else{
   draw(`M${mx} ${my}L${mxe} ${my}`,0,G,3);[.12,.3,.5,.72].forEach(q=>dot(w*q,my,5,0,G,G));
   draw(`M${fx} ${my}C${fx+30} ${my} ${fx+24} ${by} ${fx+60} ${by}L${bxe} ${by}`,0,C,3);[.46,.58,.7].forEach(q=>dot(w*q,by,5,0,C,C));
   const m=at('path',{d:`M${bxe} ${by}C${bxe+50} ${by} ${bxe+60} ${my} ${w*.86} ${my}`,pathLength:1,stroke:'#ffd36a','stroke-width':3,fill:'none','stroke-linecap':'round'},'',.3,'gv-merge');
   dot(w*.86,my,6,2.2,'#ffd36a','#ffd36a');
   const bw=Math.min(120,w*.26),bh=34,bx=w*.18,byb=h-bh-34;
   [['MERGE',G,0],['LEAVE IT',C,bw+16]].forEach(([t,c,o],i)=>{const r=at('rect',{x:bx+o,y:byb,width:bw,height:bh,fill:'#0a1632',stroke:c,'stroke-width':2},'',.2,i?'gv-fade':'gv-press');at('text',{x:bx+o+bw/2,y:byb+22,'text-anchor':'middle',fill:c,'font-size':fs+1,'font-family':'Orbitron,Outfit,sans-serif'},t,.3);});
   at('text',{x:mx,y:h-12,fill:'#d9ffe9','font-size':Math.min(13,w/42),'font-family':'Outfit,system-ui,sans-serif'},'Nothing merges until YOU press MERGE. LEAVE IT keeps it separate.',.6);
  }
 }else{
  let rows={missions:[['Your project','Untouched'],['Agent copy','Code changes'],['Your review','APPLY / DISCARD']],pc:[['Agent looks','Finds Play'],['YOU APPROVE','Yes or no'],['MCP acts','Checks the window']],media:[['Your link','yt-dlp'],['Your format','ffmpeg'],['Your folder','Browse / receive']],agents:[['YOU describe','One job'],['Neo designs','One persona file'],['YOU save','Agent can be picked']],install:[['Your PC','Install the Hub'],['Private network','Tailscale'],['Your phone','Open the address']],talk:[['YOU ask','Speak or type'],['Smith routes','Tool or agent'],['YOU receive','Answer / review']]}[sid]||[];
  if(sid==='agents'){
   const name=a.btns[a.i].dataset.t;
   if(!a.el.classList.contains('agents-auto'))rows=[['YOU choose','Skill instructions'],['HUB adds','Agent skill folders'],['Agents use','OpenCode / Claude']];
   else if(name==='The Doctor')rows=[['YOU ask','Hub facts'],['Doctor mission','Private Hub copy'],['YOU APPLY','Restart is yours']];
   else if(name==='Agent Smith')rows=[['YOU ask','Speak or type'],['Smith routes','Tool or agent'],['YOU receive','Answer / review']];
   else if(name!=='Neo')rows=[['Planner briefs','One role'],['Agent delivers','Private copy'],['YOU review','Apply or discard']];
  }
  const bh=Math.max(54,Math.min(76,h*.29));rows.forEach(([t,n],i)=>{const xx=10+i*(third+gap);box(xx,top,third,bh,t,n,i===2?'#41ebff':'#00e676');if(i<2)line(xx+third,top+bh/2,xx+third+gap,top+bh/2);});
  const y=top+bh+18,remaining=h-y-8;
  if(remaining>50){
   node('rect',{x:10,y,width:w-20,height:remaining,fill:'#050a20','fill-opacity':'.5',stroke:'#41ebff','stroke-opacity':'.2'});
   if(sid==='missions'){
    text(24,y+23,'settings.css · example diff',13,'#a8cbb9');text(24,y+Math.min(52,remaining*.48),'− color-scheme: light;',14,'#ffb0ae');text(24,y+Math.min(80,remaining*.75),'+ color-scheme: dark;',14,'#00e676');
   }else{
    const notes={pc:['ASK FIRST is the gate.','Shell · registry · file · process tools are off.'],media:['The PC downloads and converts.','The saved result is yours to browse or copy.'],agents:['Neo: describe → design → read → save.','Doctor: ask → facts → mission → checks → YOU apply.'],install:['First run: choose the optional tools to prepare.','Then bookmark the private address on your device.'],talk:['Smith can hand work to the router and desktop agent.','Neo designs agents; the Doctor proposes Hub repairs.']}[sid]||[];
    notes.forEach((t,i)=>text(24,y+Math.min(28+i*26,remaining-10),t,Math.min(14,w/41)));
   }
  }
 }
 host.replaceChildren(svg);
}

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
