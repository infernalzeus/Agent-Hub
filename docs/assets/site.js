/* Agent Hub site: scene navigation, auto-playing step lists, the pulsing grid, the fading-in mark, and a tilt that follows the pointer or the phone. */
(()=>{'use strict';
 const scenes=[...document.querySelectorAll('.scene')],reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let active=document.getElementById('landing'),busy=false,mark=null,stopToggle=null,shell=true,permission='unknown',pose=null,hasOrientation=false,pendingRoute=null;
 try{permission=sessionStorage.getItem('site:orientation')||'unknown';}catch(error){}
 const route=()=>document.getElementById(location.hash.slice(1))?.matches('.scene')?location.hash.slice(1):'landing';
 const STEP=4200;

 /* ---------- auto-playing step lists: they advance by themselves; a tap or hover pins one ---------- */
 const autos=[...document.querySelectorAll('[data-auto]')].map(el=>{
  const a={el,scene:el.closest('.scene'),btns:[...el.querySelectorAll('.st')],detail:el.querySelector('.auto-detail'),i:0,pinned:false,timer:0,resume:0};
  a.kicker=a.detail.querySelector('.kicker');a.h3=a.detail.querySelector('h3');a.d=a.detail.querySelector('.d');
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
  a.kicker.textContent=b.dataset.k;a.h3.textContent=b.dataset.t;a.d.textContent=b.dataset.d;
  a.el.classList.remove('playing');void a.el.offsetWidth;if(!a.pinned&&!reduced.matches&&a.live)a.el.classList.add('playing');
 }
 function play(a){clearTimeout(a.timer);if(!a.live||a.pinned||reduced.matches)return;a.el.style.setProperty('--step',STEP+'ms');a.el.classList.add('playing');a.timer=setTimeout(()=>{select(a,a.i+1);play(a);},STEP);}
 function pin(a,i,ms){a.pinned=true;clearTimeout(a.timer);clearTimeout(a.resume);select(a,i);a.el.classList.remove('playing');a.resume=setTimeout(()=>{a.pinned=false;play(a);},ms);}
 function startAutos(scene){autos.filter(a=>a.scene===scene).forEach(a=>{a.live=!!a.el.offsetParent;a.pinned=false;clearTimeout(a.resume);if(a.live){select(a,0);play(a);}});}
 function stopAutos(){autos.forEach(a=>{a.live=false;clearTimeout(a.timer);clearTimeout(a.resume);a.el.classList.remove('playing');});}
 function stepActive(delta){const a=autos.find(x=>x.scene===active&&x.live);if(a)pin(a,a.i+delta,8000);}

 /* small glass blocks open to show more */
 document.querySelectorAll('[data-more]').forEach(b=>b.addEventListener('click',()=>b.setAttribute('aria-expanded',b.getAttribute('aria-expanded')==='true'?'false':'true')));

 /* the animated machine on the TALK scene is drawn at one size and scaled to the room it has */
 function fit(){const w=active.querySelector('.fit');if(!w||!w.offsetParent)return;const f=w.firstElementChild,s=Math.min(w.clientWidth/1060,w.clientHeight/f.offsetHeight,1.05);f.style.setProperty('--s',s.toFixed(3));}
 addEventListener('resize',()=>{fit();sizeGrid();});
 if(document.fonts&&document.fonts.ready)document.fonts.ready.then(()=>{fit();sizeGrid();});

 /* architecture: tap to enlarge */
 const zoomOf=()=>active.querySelector('.zoom');
 document.querySelectorAll('[data-zoom]').forEach(b=>b.addEventListener('click',()=>{const z=b.closest('.scene').querySelector('.zoom');z.hidden=false;z.querySelector('[data-zoom-close]').focus();}));
 document.querySelectorAll('[data-zoom-close]').forEach(b=>b.addEventListener('click',()=>{b.closest('.zoom').hidden=true;}));

 /* ---------- the mark: the real animated core fades in once the turn has finished; the picture is only a last resort ---------- */
 const markHost=document.getElementById('hero-mark');
 function mountMark(){
  if(mark||!markHost)return;
  try{if(window.AgentHubMark){mark=AgentHubMark.mount(markHost,{state:'live',mode:'crystal',shell,touchLock:true,reducedMotion:reduced.matches});if(mark)stopToggle=AgentHubMark.tapToToggle(document.getElementById('landing'),mark,markHost,{rippleIn:document.getElementById('landing'),onToggle:value=>{shell=value;}});}}catch(error){mark=null;}
  if(!mark&&!markHost.firstElementChild){const img=new Image();img.src='assets/agent-hub-mark.png';img.alt='';img.width=img.height=256;markHost.appendChild(img);}
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

 /* ---------- navigation ---------- */
 function enter(scene){
  active=scene;scenes.forEach(s=>{s.classList.toggle('active',s===active);s.setAttribute('aria-hidden',s===active?'false':'true');s.inert=s!==active;});
  stopAutos();fit();startAutos(active);if(active.id==='landing'){mountMark();sizeGrid();startGrid();}else unmountMark();
 }
 async function navigate(id,push=true){
  if(busy)return;const next=document.getElementById(id)||scenes[0];if(next===active)return;
  busy=true;resetTilt();pose=null;stopAutos();
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
  const z=zoomOf();if(e.key==='Escape'&&z&&!z.hidden){e.preventDefault();z.hidden=true;return;}
  if(active.id==='landing'&&e.key.toLowerCase()==='g'&&!e.ctrlKey&&!e.metaKey&&mark){shell=!mark.isShell();mark.setShell(shell);}
  if(e.key==='Escape'){e.preventDefault();navigate('landing');}
  if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&!e.target.matches('input,textarea,select')){e.preventDefault();stepActive(e.key==='ArrowRight'?1:-1);}
 });

 /* ---------- tilt: pointer on a computer, the phone's gravity sensor on a phone, a finger drag as the fallback ---------- */
 let targetX=0,targetY=0,x=0,y=0,raf=0,last=0,lastMove=0,drag=null;
 const tiltEl=()=>active.querySelector('[data-tilt]');
 const maxFor=(el,kind)=>el&&el.classList.contains('tilt-layer')?(kind==='phone'?13:7):(kind==='phone'?18:9);
 function animate(now){
  raf=0;if(document.hidden||reduced.matches||busy)return;const b=tiltEl();if(!b)return;
  const dt=last?Math.min(60,now-last):16;last=now;const ease=1-Math.exp(-dt/110);x+=(targetX-x)*ease;y+=(targetY-y)*ease;
  b.style.setProperty('--rx',x.toFixed(3)+'deg');b.style.setProperty('--ry',y.toFixed(3)+'deg');
  if(now-lastMove<2000||Math.abs(x-targetX)+Math.abs(y-targetY)>.01)raf=requestAnimationFrame(animate);
 }
 function move(a,b){if(busy||document.hidden||reduced.matches)return;targetX=a;targetY=b;lastMove=performance.now();if(!raf){last=0;raf=requestAnimationFrame(animate);}}
 function resetTilt(){cancelAnimationFrame(raf);raf=0;targetX=targetY=x=y=0;document.querySelectorAll('[data-tilt]').forEach(b=>{b.style.setProperty('--rx','0deg');b.style.setProperty('--ry','0deg');});}
 const clamp=(v,m)=>Math.max(-m,Math.min(m,v));
 document.querySelectorAll('[data-tilt]').forEach(b=>{
  b.addEventListener('pointermove',e=>{
   if(busy)return;const r=b.getBoundingClientRect(),m=maxFor(b,'mouse');
   if(e.pointerType==='mouse'&&!drag)move(clamp(-((e.clientY-r.top)/r.height-.5)*2*m,m),clamp(((e.clientX-r.left)/r.width-.5)*2*m,m));
   if(drag&&drag.id===e.pointerId){drag.dx=e.clientX-drag.x;drag.dy=e.clientY-drag.y;const p=maxFor(b,'phone');if(permission!=='granted'||!hasOrientation)move(clamp(-drag.dy*.14,p),clamp(drag.dx*.14,p));}
  });
  b.addEventListener('pointerleave',()=>{if(!drag)move(0,0);});
  b.addEventListener('pointerdown',e=>{if(busy||e.target.closest('button,a'))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,dx:0,dy:0};try{b.setPointerCapture(e.pointerId);}catch(error){}});
  function end(e){if(!drag||drag.id!==e.pointerId)return;const d=drag;drag=null;if(Math.abs(d.dx)>70&&Math.abs(d.dx)>Math.abs(d.dy)*1.5)stepActive(d.dx<0?1:-1);move(0,0);}
  b.addEventListener('pointerup',end);b.addEventListener('pointercancel',()=>{drag=null;move(0,0);});
 });
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
