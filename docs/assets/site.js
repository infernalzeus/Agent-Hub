/* Scene navigation, accessible steppers and a shared, idle-paused board tilt loop. */
(()=>{'use strict';
 const scenes=[...document.querySelectorAll('.scene')],reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let active=document.getElementById('landing'),busy=false,mark=null,stopToggle=null,shell=true,permission='unknown',pose=null,hasOrientation=false;
 try{permission=sessionStorage.getItem('site:orientation')||'unknown';}catch(error){}
 const route=()=>document.getElementById(location.hash.slice(1))?.matches('.scene')?location.hash.slice(1):'landing';
 const pages=new Map();
 scenes.forEach(scene=>{
  const items=[...scene.querySelectorAll('[data-page]')];if(!items.length)return;
  pages.set(scene,{items,index:0});
  scene.querySelector('[data-prev]').addEventListener('click',()=>step(scene,-1));
  scene.querySelector('[data-next]').addEventListener('click',()=>step(scene,1));
  showPage(scene);
 });
 function showPage(scene){const p=pages.get(scene);if(!p)return;p.items.forEach((item,i)=>item.hidden=i!==p.index);scene.querySelector('.page-position').textContent=`${p.index+1} / ${p.items.length}`;scene.querySelector('[data-prev]').disabled=p.index===0;scene.querySelector('[data-next]').disabled=p.index===p.items.length-1;scene.querySelector('.pager').hidden=p.items.length<2;}
 function step(scene,delta){if(busy)return;const p=pages.get(scene);if(!p)return;p.index=Math.max(0,Math.min(p.items.length-1,p.index+delta));showPage(scene);}
 const roles={Smith:'Smith is the helper you talk to; the request goes to the right tool or agent.',Neo:'Neo drafts an agent from a sentence; you review the role and add it to your team.',Planner:'The planner splits a mission into briefs and hands them to agents in private worktrees.',Doctor:'The Doctor proposes a Hub repair and hands the change to you for APPLY.'};
 document.querySelectorAll('[data-role]').forEach(button=>button.addEventListener('click',()=>{button.closest('.agent-grid').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b===button?'true':'false'));button.closest('.page').querySelector('.role').textContent=roles[button.dataset.role];}));
 function mountMark(){if(mark||!window.AgentHubMark)return;try{const host=document.getElementById('hero-mark');mark=AgentHubMark.mount(host,{state:'live',mode:'crystal',shell,touchLock:true,reducedMotion:reduced.matches});if(mark)stopToggle=AgentHubMark.tapToToggle(document.getElementById('landing'),mark,host,{rippleIn:document.getElementById('landing'),onToggle:value=>{shell=value;}});}catch(error){/* The small, existing mark image remains visible. */}}
 function unmountMark(){if(stopToggle){stopToggle();stopToggle=null;}if(mark){mark.destroy();mark=null;}}
 async function navigate(id,push=true){
  if(busy)return;const next=document.getElementById(id)||scenes[0];if(next===active)return;
  busy=true;resetTilt();pose=null;
  if(push)history.pushState(null,'',id==='landing'?location.pathname+location.search:'#'+id);
  next.setAttribute('aria-hidden','false');next.inert=true;
  const previous=active;
  await SiteDepthLift.go(previous,next,next.id==='landing');
  active=next;scenes.forEach(s=>{s.classList.toggle('active',s===active);s.setAttribute('aria-hidden',s===active?'false':'true');s.inert=s!==active;});
  if(active.id==='landing')mountMark();else unmountMark();
  active.querySelector('h1,h2')?.focus({preventScroll:true});busy=false;
  if(pendingRoute!==null){const id=pendingRoute;pendingRoute=null;navigate(id,false);}
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
 let pendingRoute=null;
 addEventListener('hashchange',()=>{if(busy){pendingRoute=route();return;}navigate(route(),false);});
 // A history traversal during a turn is reconciled after its destination settles.
 const historyObserver=new MutationObserver(()=>{if(!busy&&pendingRoute!==null){const id=pendingRoute;pendingRoute=null;navigate(id,false);}});
 historyObserver.observe(document.body,{attributes:true,attributeFilter:['data-turning']});
 document.addEventListener('keydown',e=>{if(busy){if(['Escape','ArrowLeft','ArrowRight','Enter',' '].includes(e.key))e.preventDefault();return;}if(active.id==='landing'&&e.key.toLowerCase()==='g'&&!e.ctrlKey&&!e.metaKey&&mark){shell=!mark.isShell();mark.setShell(shell);}if(e.key==='Escape'){e.preventDefault();navigate('landing');}if(e.key==='ArrowLeft'||e.key==='ArrowRight'){if(e.target.matches('input,textarea,select'))return;e.preventDefault();step(active,e.key==='ArrowRight'?1:-1);}});
 let targetX=0,targetY=0,x=0,y=0,raf=0,last=0,lastMove=0,drag=null;
 function board(){return active.querySelector('[data-tilt]');}
 function animate(now){
  raf=0;if(document.hidden||reduced.matches||busy)return;const b=board();if(!b)return;
  const dt=last?Math.min(60,now-last):16;last=now;const ease=1-Math.exp(-dt/120);x+=(targetX-x)*ease;y+=(targetY-y)*ease;
  b.style.setProperty('--rx',x.toFixed(3)+'deg');b.style.setProperty('--ry',y.toFixed(3)+'deg');
  if(now-lastMove<2000||Math.abs(x-targetX)+Math.abs(y-targetY)>.01)raf=requestAnimationFrame(animate);
 }
 function move(a,b){if(busy||document.hidden||reduced.matches)return;targetX=a;targetY=b;lastMove=performance.now();if(!raf){last=0;raf=requestAnimationFrame(animate);}}
 function resetTilt(){cancelAnimationFrame(raf);raf=0;targetX=targetY=x=y=0;scenes.forEach(s=>{const b=s.querySelector('[data-tilt]');if(b){b.style.setProperty('--rx','0deg');b.style.setProperty('--ry','0deg');}});}
 document.querySelectorAll('[data-tilt]').forEach(b=>{
  b.addEventListener('pointermove',e=>{
   if(busy)return;const r=b.getBoundingClientRect();
   if(e.pointerType==='mouse'&&!drag){move(Math.max(-8,Math.min(8,-((e.clientY-r.top)/r.height-.5)*16)),Math.max(-8,Math.min(8,((e.clientX-r.left)/r.width-.5)*16)));b.style.setProperty('--hx',((e.clientX-r.left)/r.width*100)+'%');b.style.setProperty('--hy',((e.clientY-r.top)/r.height*100)+'%');}
   if(drag&&drag.id===e.pointerId){drag.dx=e.clientX-drag.x;drag.dy=e.clientY-drag.y;if(permission!=='granted'||!hasOrientation)move(Math.max(-10,Math.min(10,-drag.dy*.12)),Math.max(-10,Math.min(10,drag.dx*.12)));}
  });
  b.addEventListener('pointerleave',()=>{if(!drag)move(0,0);});
  b.addEventListener('pointerdown',e=>{if(busy||e.target.closest('button,a'))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,dx:0,dy:0};b.setPointerCapture(e.pointerId);});
  function end(e){if(!drag||drag.id!==e.pointerId)return;const d=drag;drag=null;if(Math.abs(d.dx)>65&&Math.abs(d.dx)>Math.abs(d.dy)*1.5)step(active,d.dx<0?1:-1);move(0,0);}
  b.addEventListener('pointerup',end);b.addEventListener('pointercancel',()=>{drag=null;move(0,0);});
 });
 addEventListener('deviceorientation',e=>{
  if(permission!=='granted'||busy||!board()||e.beta===null||e.gamma===null)return;
  hasOrientation=true;if(!pose){pose={beta:e.beta,gamma:e.gamma};return;}
  // Translate the sensor axes into the current screen orientation.
  const angle=(screen.orientation?.angle||0)*Math.PI/180,db=e.beta-pose.beta,dg=e.gamma-pose.gamma;
  move(Math.max(-10,Math.min(10,-(db*Math.cos(angle)+dg*Math.sin(angle))*.35)),Math.max(-10,Math.min(10,(dg*Math.cos(angle)-db*Math.sin(angle))*.35)));
 });
 reduced.addEventListener('change',()=>{resetTilt();unmountMark();if(active.id==='landing')mountMark();});
 document.addEventListener('visibilitychange',()=>{resetTilt();if(document.hidden)unmountMark();else if(active.id==='landing')mountMark();});
 addEventListener('pagehide',()=>{resetTilt();unmountMark();});
 document.documentElement.classList.add('js');
 active=document.getElementById(route());scenes.forEach(s=>{s.classList.toggle('active',s===active);s.inert=s!==active;s.setAttribute('aria-hidden',s===active?'false':'true');});
 if(active.id==='landing')mountMark();
 // Expose only small diagnostics for reproducible measurements, no private state.
 window.SiteBoard={get scene(){return active.id;},get permission(){return permission;},get tilt(){return {x,y,targetX,targetY,running:!!raf};}};
})();
