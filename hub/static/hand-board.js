/* Plain-JavaScript port/adaptation of https://github.com/adewaskar/jarvis
Sources: src/lib/hands.ts, src/lib/oneEuro.ts, src/lib/camera.ts, src/ui/GestureGuide.tsx

MIT License

Copyright (c) 2026 Aditya Dewaskar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
 */
// The board adapter: turns what the engine sees (hands, pinches, a fist) into the ordinary pointer events the board already understands.
//   thumb + index   the left button: press, drag, click
//   thumb + middle  the right button: a click opens a context menu (it never turns the board)
//   thumb + index + middle together, hand moved up or down   zoom, one hand
//   a closed fist   (VIEW 3D) move and turn the fist to tilt and turn the board, through the board's own orbit, not a faked button
//   two index pinches  zoom;  an open hand held for a second  fits everything
// A press follows the PALM, not the fingertip: the fingertip moves several centimetres while the fingers close, which turned clicks into drags.
(function(root){
  'use strict';
  const G=root.HubHandsGestures,ROLL_PX=320,PROFILE_VERSION=2;
  // the camera picture is about a quarter of the screen's width, so a hand that shakes by a few camera pixels moves the cursor by tens of screen pixels:
  // the distance a click may wander scales with the screen
  const slop=()=>Math.max(40,Math.round(innerWidth*.05));      // measured: a hand drifts 20 to 45 px in the first third of a second of a pinch at 1280 px wide
  const boardView=()=>{try{return root.__hubBoard.active.view();}catch(_){return null;}};
  const ICON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 12V5a1.5 1.5 0 0 1 3 0v6-8a1.5 1.5 0 0 1 3 0v8-6a1.5 1.5 0 0 1 3 0v7-4a1.5 1.5 0 0 1 3 0v6c0 5-3 7-7 7-3 0-5-2-6-4l-3-5a1.5 1.5 0 0 1 2.5-1.6L8 12Z"/></svg>';
  function styles(){if(document.getElementById('hands-style'))return;const s=document.createElement('style');s.id='hands-style';s.textContent='.hands-log{position:fixed;left:0;right:0;bottom:0;z-index:46;height:calc(var(--hb-log,24px) + env(safe-area-inset-bottom));font:12px Outfit,system-ui,sans-serif;color:#d6f5e6;pointer-events:none}.hl-head{pointer-events:auto;display:flex;position:absolute;left:0;right:0;bottom:0;height:calc(var(--hb-log,24px) + env(safe-area-inset-bottom));box-sizing:border-box;align-items:center;gap:8px;text-align:left;background:rgba(6,10,36,.94);border:0;border-top:1px solid rgba(0,230,118,.22);padding:0 12px env(safe-area-inset-bottom);color:#00e676;font:700 8px Orbitron,monospace;letter-spacing:1.2px;cursor:pointer}.hl-head:hover{background:rgba(10,16,52,.96)}.hl-arrow{flex:none;width:22px;height:18px;display:inline-flex;align-items:center;justify-content:center;border:1px solid rgba(0,230,118,.45);border-radius:5px;color:#00e676}.hl-arrow svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;transition:transform .18s}.hands-log.open .hl-arrow svg{transform:rotate(180deg)}.hl-head:hover .hl-arrow{border-color:#00e676;background:rgba(0,230,118,.12)}.hl-status{flex:1;min-width:0;font:600 11px Outfit,system-ui,sans-serif;letter-spacing:0;color:#d6f5e6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hl-body{pointer-events:auto;display:none;position:absolute;bottom:calc(var(--hb-log,24px) + env(safe-area-inset-bottom) + 6px);right:164px;left:auto;width:min(560px,calc(100vw - 188px));box-sizing:border-box;max-height:min(46vh,360px);overflow:auto;background:linear-gradient(145deg,#131b45ee,#080c28f2);border:1px solid #6576b755;border-radius:10px;padding:8px 10px;box-shadow:0 12px 30px #0008;animation:hlfade .18s ease}.hands-log.open .hl-body{display:block}@keyframes hlfade{from{opacity:0}to{opacity:1}}@media (prefers-reduced-motion:reduce){.hl-body{animation:none}}.hl-rows div{padding:2px 0;border-bottom:1px solid rgba(0,230,118,.08);font-size:12px}.hl-rows time{color:#8fcfb2;margin-right:8px;font-variant-numeric:tabular-nums}.hl-rows b{display:inline-block;min-width:44px;margin-right:8px;font:700 8px Orbitron,monospace;letter-spacing:1px;color:#41ebff}.hl-rows .k-chat b{color:#00e676}.hl-rows .hl-err{color:#ff9d9d}.hl-empty{color:#8fcfb2}.hl-top{display:flex;flex-wrap:wrap;gap:6px;justify-content:space-between;margin-bottom:6px}.hl-filters,.hl-tools{display:flex;flex-wrap:wrap;gap:4px}.hl-top button{font:700 8px Orbitron,monospace;letter-spacing:1px;color:#00e676;background:rgba(6,10,36,.78);border:1px solid rgba(0,230,118,.28);border-radius:6px;padding:5px 8px;min-height:26px;cursor:pointer}.hl-tools button[hidden]{display:none!important}.hl-top button.on,.hl-top button:hover{border-color:#00e676;background:rgba(0,230,118,.12)}.hl-legend{margin-top:8px;color:#8fcfb2;font-size:12px;line-height:1.55}html.hub-hide-hand-legend .hl-legend{display:none}@media(max-width:720px){.hl-body{position:fixed;left:8px;right:8px;width:auto;bottom:calc(var(--hb-log,24px) + env(safe-area-inset-bottom) + 6px);max-height:50vh}}.hands-target{position:fixed;z-index:2147483000;pointer-events:none;border:2px solid #00e676;border-radius:8px;box-shadow:0 0 14px rgba(0,230,118,.55)}html.hands-live,html.hands-live body{cursor:none}.hb-hands{display:inline-flex;align-items:center;gap:5px}.hb-hands svg{width:17px;height:17px}.hb-hands i{width:6px;height:6px;border-radius:50%;background:var(--text-faint);display:inline-block}.hb-hands.live i{background:var(--accent);box-shadow:0 0 5px var(--accent)}.hb-hands.live{border-color:var(--cyan);color:var(--cyan)}.hands-overlay{position:fixed;inset:0;pointer-events:none;z-index:54}.hands-legend,.hands-status{position:fixed;z-index:55;pointer-events:none;max-width:min(520px,calc(100vw - 32px));padding:10px 14px;border:1px solid var(--border-dim);border-radius:9px;background:rgba(8,12,40,.96);color:var(--text);font:11px/1.8 Orbitron,monospace}.hands-legend{left:16px;bottom:calc(22px + env(safe-area-inset-bottom));transition:opacity .3s}.hands-status{left:16px;top:calc(12px + env(safe-area-inset-top));color:var(--cyan);font-size:10px}.hands-setup{position:fixed;inset:auto;left:50%;top:50%;transform:translate(-50%,-50%);z-index:95;box-sizing:border-box;width:min(460px,calc(100vw - 28px));padding:20px;border:1px solid var(--accent);border-radius:12px;background:#080c28;color:var(--text);font:12px/1.8 Orbitron,monospace;box-shadow:0 14px 50px #0009}.hands-setup button{margin:8px 6px 0 0}.hands-setup p{font-family:Outfit,system-ui,sans-serif;font-size:14px}.hands-legend[hidden],.hands-status[hidden],.hands-setup[hidden]{display:none!important}@media(prefers-reduced-motion:reduce){.hands-legend{transition:none}}';document.head.appendChild(s);}
  function mount({host,bar,fitButton}){
    styles();
    let typedAt=-Infinity,lastAction=-Infinity,alive=true,enabled=false,canvas=null,ctx=null,legend=null,status=null,legendTimer=0,used=false,zooming=false,interlock=false,cooldown=0,diagnostic=false,measurementLabel='MEASURING',hint='',hintAt=0,calibration=null;
    let confLive=[];
    // GESTURES ARE RULES. Each rule: first (the pose), when / then (for a fist: what follows it), does (the action). The ones below are what ships; the menu edits, adds and deletes them.
    const DEFAULT_RULES=[
      {id:'r1',on:true,first:'point',when:'',then:'',does:'left'},{id:'r2',on:true,first:'middle',when:'',then:'',does:'right'},
      {id:'r3',on:true,first:'pinch',when:'',then:'',does:'left'},{id:'r4',on:true,first:'mpinch',when:'',then:'',does:'back'},
      {id:'r5',on:true,first:'triple',when:'',then:'',does:'left'},{id:'r6',on:true,first:'open',when:'',then:'',does:'none'},
      {id:'r7',on:true,first:'twohand',when:'',then:'',does:'zoom'},{id:'r8',on:true,first:'fist',when:'',then:'',does:'control'},
      {id:'r9',on:true,first:'fist',when:'while',then:'wrist',does:'rotate'},{id:'r10',on:true,first:'fist',when:'while',then:'palm',does:'rotate'},
      {id:'r11',on:true,first:'fist',when:'after',then:'palm',does:'pan'},{id:'r12',on:true,first:'fist',when:'after',then:'depth',does:'zoom'}];
    const rules=()=>Array.isArray(profile.rules)?profile.rules:DEFAULT_RULES,hasRule=f=>rules().some(r=>r.on&&f(r));
    const single=k=>rules().find(r=>r.on&&r.first===k&&!r.then&&r.does!=='control');
    const isOff=k=>k==='hand'?!!(profile.dis&&profile.dis.hand):k==='twohand'?!hasRule(r=>r.first==='twohand'&&r.does==='zoom'):!single(k);
    const fistRule=(when,then,does)=>hasRule(r=>r.first==='fist'&&r.when===when&&r.then===then&&r.does===does);
    const ctlEnabled=()=>hasRule(r=>r.first==='fist'&&r.does==='control')&&hasRule(r=>r.first==='fist'&&r.when==='after'&&r.does!=='none');
    const canPan=()=>fistRule('after','palm','pan'),canZoom=()=>fistRule('after','depth','zoom'),rotWrist=()=>fistRule('while','wrist','rotate'),rotMove=()=>fistRule('while','palm','rotate'),fistRotate=()=>rotWrist()||rotMove();
const ctl={on:false,sawRelease:false,fistSince:null,fistLatched:false,lock:null,ref:null,sm:null,d0:0,still:null,lostAt:null,pp:null,t:0,id:0,zref:0,zlast:0},ctlInfo={travel:0,dchange:0,lock:''};let profile={v:PROFILE_VERSION,fist:false,orbit:true,palm:false};
    try{const saved=JSON.parse(localStorage.getItem('hub-hands-profile')||'null');if(saved&&saved.v===PROFILE_VERSION)profile={...profile,...saved};}catch(_){}      if(profile.tuning){const stale={pinchOn:.1,pinchOff:.4,pinchOnM:.16,tripleOn:.1};for(const k in stale)if(profile.tuning[k]===stale[k])delete profile.tuning[k];}      // an older profile was measured in other units: start again
    // what each pointing / pinching gesture does can be chosen in the hands menu; these are the defaults
    const ACTIONS=[['left','Left click and drag'],['right','Right click'],['back','Back: close the open menu, else fit'],['fit','Fit the board'],['tidy','Tidy'],['view','Switch 2D / 3D'],['none','Nothing'],['zoom','Zoom (hand up / down)']];
    const act=()=>{const o={};for(const k of ['pinch','mpinch','triple','point','middle','open']){const r=single(k);o[k]=r?r.does:'none';}return o;},actName=k=>(ACTIONS.find(a=>a[0]===k)||ACTIONS[6])[1],rWas=new Set(),lWas=new Set(),tWas=new Set();
    const engine=new G.Engine({tripleZoom:!isOff('triple'),tuning:profile.tuning||{}}),detected=new Set(),presses=new Map(),btn=document.createElement('button');
    btn.type='button';btn.className='hb-btn hb-hands';btn.innerHTML=ICON+'<span>HANDS</span><i aria-hidden="true"></i>';btn.title='Optional local webcam hand control';btn.setAttribute('aria-pressed','false');bar.appendChild(btn);
    const setup=document.createElement('section');setup.className='hands-setup';setup.hidden=true;setup.setAttribute('role','dialog');setup.setAttribute('aria-label','Set up hand control');document.body.appendChild(setup);
    const configure=document.createElement('button');configure.type='button';configure.className='hb-btn';configure.textContent='HAND SETUP';configure.onclick=()=>calibrationPanel();bar.appendChild(configure);
    const saveBtn=document.createElement('button');saveBtn.type='button';saveBtn.className='hb-btn';saveBtn.textContent='SAVE TRACE';saveBtn.hidden=true;saveBtn.title='Save the last minute of hand numbers (no pictures) so Claude can look at what happened';saveBtn.onclick=()=>saveTrace('free',null);bar.appendChild(saveBtn);
    const fresh=()=>({frames:0,handFrames:0,pinches:0,detectedPinches:0,clicks:0,rclicks:0,orbits:0,zooms:0,zoom1:0,fits:0,dwells:0,pans:0,taps:0,latencies:[],cameraLatencies:[]});
    let counts=fresh();

    // ---- what a hand is over: the board's own elements, and inside a block's frame when it is one of our own pages
    const dead=()=>Math.max(10,Math.round(innerWidth*.012));      // a drag ignores the first few pixels of hand tremor
    function resolve(x,y){
      const e=document.elementFromPoint(x,y);if(!e||!host.contains(e))return null;
      const fr=e.tagName==='IFRAME'?e:e.closest('iframe');
      if(!fr)return {el:e,k:1,ox:0,oy:0};
      try{const d=fr.contentDocument;if(!d)return null;const r=fr.getBoundingClientRect(),k=(r.width/(fr.clientWidth||r.width))||1,inner=d.elementFromPoint((x-r.left)/k,(y-r.top)/k);return inner?{el:inner,k,ox:r.left,oy:r.top}:null;}
      catch(_){return null;}                                                  // a page from another origin cannot be reached, and is left alone
    }
    // A script-made click is untrusted: browsers refuse file pickers and media play for it. For those targets the click goes through the Hub as a real mouse click.
    const needsReal=el=>{try{if(!el||!el.closest)return false;if(el.closest('input[type=file],video,audio,[data-real-click]'))return true;const l=el.closest('label');return !!(l&&l.control&&l.control.type==='file');}catch(_){return false;}};
    async function realClick(x,y){const dpr=devicePixelRatio||1,bw=(outerWidth-innerWidth)/2,left=screenX+bw,top=screenY+(outerHeight-innerHeight)-bw;
      try{const r=await fetch('/api/hands/os-click',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({x:Math.round((left+x)*dpr),y:Math.round((top+y)*dpr)})});const j=await r.json().catch(()=>({}));mark('real-click',{ok:!!j.ok,why:j.why||''});return !!j.ok;}catch(e){mark('real-click',{ok:false,why:String(e)});return false;}}
    // Right click inside an app window (a page of its own): the Hub's page menu, because the page has none.
    function pageMenu(x,y,fw){document.querySelectorAll('.hb-pagemenu').forEach(n=>n.remove());const m=document.createElement('div');m.className='hb-pagemenu';m.style.cssText='position:fixed;z-index:2147483001;left:'+Math.min(x,innerWidth-170)+'px;top:'+Math.min(y,innerHeight-130)+'px;background:#080c28;border:1px solid #00e676;border-radius:6px;padding:4px;display:grid;gap:2px;min-width:150px;box-shadow:0 8px 24px #000a';
      [['BACK',()=>fw.history.back()],['RELOAD',()=>fw.location.reload()],['OPEN IN TAB',()=>window.open(fw.location.href,'_blank')]].forEach(([t,fn])=>{const b=document.createElement('button');b.type='button';b.textContent=t;b.style.cssText='font:700 10px Orbitron,monospace;letter-spacing:1px;color:#00e676;background:transparent;border:0;padding:9px 10px;text-align:left;cursor:pointer';b.onclick=()=>{m.remove();try{fn();}catch(_){}};m.appendChild(b);});
      document.body.appendChild(m);setTimeout(()=>document.addEventListener('pointerdown',()=>m.remove(),{once:true,capture:true}),50);}
    function emit(p,type,id,x,y,pressed){
      const w=p.target.ownerDocument.defaultView||window,b=p.button;
      p.target.dispatchEvent(new w.PointerEvent(type,{bubbles:true,cancelable:true,composed:true,pointerId:9000+id,pointerType:'touch',isPrimary:id===0,clientX:(x-p.ox)/p.k,clientY:(y-p.oy)/p.k,button:type==='pointermove'?-1:b,buttons:pressed?(b===2?2:1):0,pressure:pressed?.5:0}));
    }
    const posOf=(p,hand)=>({x:p.down.x+(hand.palm.x-p.palm0.x)+(p.mode==='orbit'?(hand.roll-p.roll0)*ROLL_PX:0),y:p.down.y+(hand.palm.y-p.palm0.y)});
    // the nearest panel under the pointer that can scroll (inside a block's own page too); null for the board itself, which pans by pointer events
    function scrollerOf(el){
      if(!el||!el.ownerDocument)return null;const w=el.ownerDocument.defaultView||window;
      for(let e=el;e&&e.nodeType===1;e=e.parentElement){
        if(e===el.ownerDocument.body||e===el.ownerDocument.documentElement)break;
        if(e.classList&&e.classList.contains('hk-h'))return null;                                   // a title bar is for dragging the block
        const cs=w.getComputedStyle(e);
        if(/(auto|scroll|overlay)/.test(cs.overflowY)&&e.scrollHeight>e.clientHeight+2)return e;
        if(/(auto|scroll|overlay)/.test(cs.overflowX)&&e.scrollWidth>e.clientWidth+2)return e;
      }
      const d=el.ownerDocument;if(d!==document&&d.scrollingElement&&d.scrollingElement.scrollHeight>d.scrollingElement.clientHeight+2)return d.scrollingElement;   // a block's own page scrolls as a document
      return null;
    }
    function begin(id,hand,mode){
      if(mode==='orbit'||mode==='zoom1'){presses.set(id,{mode,prev:{...hand.palm},roll:hand.roll,twist:hand.twist,pitch:hand.pitch,at:{x:hand.x,y:hand.y},travel:0});if(mode==='orbit')counts.orbits++;else counts.zoom1++;mark('begin-'+mode);lastAction=performance.now();firstPinch();return true;}
      const from=mode==='zoom'?hand.palm:{x:hand.aimX,y:hand.aimY};
      const r=mode==='zoom'?{el:host,k:1,ox:0,oy:0}:resolve(from.x,from.y);if(!r){mark('no-target',{mode});return false;}
      const p={target:r.el,k:r.k,ox:r.ox,oy:r.oy,mode,button:mode==='right'?2:0,down:{x:from.x,y:from.y},last:{x:from.x,y:from.y},palm0:{...hand.palm},roll0:hand.roll,travel:0,t0:performance.now(),scroller:mode==='left'?scrollerOf(r.el):null,sy:from.y,sx:from.x,scrolled:false};
      presses.set(id,p);emit(p,'pointerdown',id,from.x,from.y,true);counts.pinches++;mark('begin-'+mode,{x:Math.round(from.x),y:Math.round(from.y),target:String(r.el.className||r.el.tagName).slice(0,30)});lastAction=performance.now();firstPinch();return true;
    }
    function beginPan(id,hand){
      const from={x:hand.palm.x,y:hand.palm.y},p={target:host,k:1,ox:0,oy:0,mode:'pan',button:0,down:{...from},last:{...from},palm0:{...hand.palm},roll0:hand.roll,travel:0,size:hand.depth,sm:hand.depth,moved:false};
      presses.set(id,p);emit(p,'pointerdown',id,from.x,from.y,true);counts.pans++;mark('begin-pan');firstPinch();
    }
    function release(id,cancel=true,hand){
      const p=presses.get(id);if(!p)return;
      if(p.mode==='orbit'||p.mode==='zoom1'){presses.delete(id);mark('end-'+p.mode);lastAction=performance.now();return;}
      const at=hand?posOf(p,hand):p.last;
      const tap=!cancel&&p.mode==='left'&&!p.scrolled&&p.travel<dead()&&performance.now()-p.t0<700;
      emit(p,(cancel||p.scrolled)?'pointercancel':'pointerup',id,at.x,at.y,false);
      if(tap&&needsReal(p.target)){realClick(at.x,at.y);counts.clicks++;counts.taps++;}else if(tap){const w=p.target.ownerDocument.defaultView||window;p.target.dispatchEvent(new w.MouseEvent('click',{bubbles:true,cancelable:true,composed:true,clientX:(p.down.x-p.ox)/p.k,clientY:(p.down.y-p.oy)/p.k,detail:1}));counts.clicks++;counts.taps++;}
      if(p.mode==='pan'){presses.delete(id);mark('end-pan',{travel:Math.round(p.travel)});return;}
      let how=cancel?'cancelled':tap?'tap':p.scrolled?'scroll':'drag';
      if(!cancel&&p.mode==='right'&&G.isClick(p.down,at,p.travel,slop())){
        const now=resolve(at.x,at.y);how='click-missed';
        if(now&&now.el===p.target){const w=p.target.ownerDocument.defaultView||window,o={bubbles:true,cancelable:true,composed:true,clientX:(at.x-p.ox)/p.k,clientY:(at.y-p.oy)/p.k};
          if(p.mode==='left'){p.target.dispatchEvent(new w.MouseEvent('click',{...o,detail:1}));counts.clicks++;how='click';}
          else{p.target.dispatchEvent(new w.MouseEvent('contextmenu',{...o,button:2}));counts.rclicks++;how='contextmenu';}}
      }
      mark('end-'+p.mode,{how,travel:Math.round(p.travel),slop:slop()});
      presses.delete(id);lastAction=performance.now();
    }
    function cancelAll(){for(const id of [...presses.keys()])release(id,true);zooming=false;ctl.on=false;ctl.lock=null;ctl.ref=null;ctl.sm=null;ctl.still=null;ctl.sawRelease=false;ctl.fistLatched=false;ctl.fistSince=null;}

    // ---- what is drawn: the skeleton, the three working fingertips, and a line from the thumb that fills as a pinch closes
    function showOverlay(){if(canvas)return;canvas=document.createElement('canvas');canvas.className='hands-overlay';canvas.setAttribute('aria-hidden','true');document.body.appendChild(canvas);ctx=canvas.getContext('2d');
      ensureLog();legend.textContent='POINT: the ring is your cursor; hold it still on a button: click · THUMB + INDEX: a quick pinch taps, a pinch that moves scrolls a panel or drags a block · THUMB + MIDDLE (index away): right click menu · FIST: take control, then open palm to move or push / pull to zoom, fist again to finish · THUMB + INDEX + MIDDLE together, hand up or down: zoom · FIST in VIEW 3D: turn your wrist to turn the board · OPEN HAND 1s: fit · ESC: camera off';
      status.textContent='CAMERA ON · LOCAL HAND CONTROL';}
    function clearOverlay(){clearTimeout(legendTimer);legendTimer=0;canvas?.remove();canvas=ctx=null;updateHead();}
    // ---- LOG: one small tab at the bottom, always there. Everything that happens lands here, newest first: your chat with Smith (also what was said on
    // the landing page), hand gestures and their errors, and the Hub's own messages. Pull it up to read, filter, open the chat, or set up the hands.
    const LOGKEY='agenthub:log',KINDS=[['all','ALL'],['chat','CHAT'],['hands','HANDS'],['hub','HUB']];
    let logBox=null,rowsEl=null,toolsEl=null,headEl=null,logFilter='all',logUnhook=null;
    function logOff(){if(logUnhook){logUnhook();logUnhook=null;}}
    const loadLog=()=>{try{const a=JSON.parse(sessionStorage.getItem(LOGKEY)||'[]');return Array.isArray(a)?a:[];}catch(_){return [];}};
    let logRows=loadLog();
    const LEGEND='POINT: the ring is your cursor; hold it still on a button: click · THUMB + INDEX: a quick pinch taps, a pinch that moves scrolls a panel or drags a block · THUMB + MIDDLE (index away): right click menu · THUMB + INDEX + MIDDLE together, hand up or down: zoom · FIST in VIEW 3D: tilt and turn · OPEN HAND 1 s: fit · ESC: camera off. (Flat-palm pan and zoom: switch on in HAND SETUP.)';
    function ensureLog(){
      if(logBox)return;
      document.querySelectorAll('.hands-log').forEach(n=>n.remove());                          // one only, even when the board is mounted again
      logRows=loadLog();
      logBox=document.createElement('div');logBox.className='hands-log';
      headEl=document.createElement('button');headEl.type='button';headEl.className='hl-head';headEl.setAttribute('aria-expanded','false');
      const lab=document.createElement('span');lab.textContent='LOG';status=document.createElement('span');status.className='hl-status';status.setAttribute('role','status');
      const arrow=document.createElement('span');arrow.className='hl-arrow';arrow.setAttribute('aria-hidden','true');arrow.innerHTML='<svg viewBox="0 0 24 24"><path d="M6 15l6-6 6 6"/></svg>';headEl.title='Open the log (the arrow, or anywhere on this line)';headEl.setAttribute('aria-label','Log. Open or close');headEl.append(lab,status,arrow);
      const body=document.createElement('div');body.className='hl-body';
      const top=document.createElement('div');top.className='hl-top';
      const chips=document.createElement('div');chips.className='hl-filters';
      KINDS.forEach(([k,t])=>{const b=document.createElement('button');b.type='button';b.textContent=t;b.dataset.kind=k;b.className=k===logFilter?'on':'';b.onclick=()=>{logFilter=k;chips.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.kind===k));paintLog();};chips.append(b);});
      toolsEl=document.createElement('div');toolsEl.className='hl-tools';
      
      top.append(chips,toolsEl);
      rowsEl=document.createElement('div');rowsEl.className='hl-rows';legend=document.createElement('div');legend.className='hl-legend';legend.textContent=LEGEND;
      body.append(top,rowsEl,legend);logBox.append(body,headEl);document.body.appendChild(logBox);
      const toggle=(open)=>{logBox.classList.toggle('open',open);headEl.setAttribute('aria-expanded',String(open));try{localStorage.setItem('agenthub:hands:log',open?'1':'0');}catch(_){}if(open)paintLog();};
      headEl.onclick=()=>toggle(!logBox.classList.contains('open'));
      logOff();const open1=()=>toggle(true),onLog=(e)=>{const d=e.detail||{};if(d.kind&&d.text)logAdd(d.kind,String(d.text),!!d.err);};
      window.addEventListener('hub-hands-log-open',open1);window.addEventListener('hub-log-open',open1);window.addEventListener('hub-log',onLog);
      logUnhook=()=>{window.removeEventListener('hub-hands-log-open',open1);window.removeEventListener('hub-log-open',open1);window.removeEventListener('hub-log',onLog);if(window.__hubLogAdd===logAdd)window.__hubLogAdd=null;};
      window.__hubLogAdd=logAdd;                                                              // voice.js and other pages write through this when it exists
      try{if(localStorage.getItem('agenthub:hands:log')==='1')toggle(true);}catch(_){}
      updateHead();paintLog();
      window.dispatchEvent(new CustomEvent('hub-log-ready'));
    }
    function updateHead(){if(!status||enabled)return;const r=logRows[0];status.textContent=r?r.t:'nothing yet';}
    function paintLog(){
      if(!rowsEl||!logBox||!logBox.classList.contains('open'))return;
      rowsEl.replaceChildren();
      if(logFilter==='chat'){const open=document.createElement('button');open.type='button';open.className='hb-btn hl-smith';open.textContent='CHAT WITH AGENT SMITH';open.onclick=()=>{try{window.HubVoice&&window.HubVoice.open&&window.HubVoice.open(false);}catch(_){}};rowsEl.append(open);}
      const rows=logRows.filter(r=>logFilter==='all'||r.kind===logFilter).slice(0,30);
      if(!rows.length){const d=document.createElement('div');d.className='hl-empty';d.textContent=logFilter==='hands'?'Nothing yet. Turn HANDS on and use a gesture; each press, tap, scroll and error appears here.':'Nothing yet. Your chat with Smith, hand gestures and Hub messages appear here.';rowsEl.append(d);return;}
      rows.forEach(r=>{const d=document.createElement('div');d.className='hl-row k-'+r.kind+(r.err?' hl-err':'');const tx=document.createElement('span');tx.className='hl-text';tx.textContent=r.t;const meta=document.createElement('span');meta.className='hl-meta';meta.title=new Date(r.at).toLocaleString([],{dateStyle:'full',timeStyle:'medium'});const tm=document.createElement('time');tm.dateTime=new Date(r.at).toISOString();tm.textContent=new Date(r.at).toLocaleTimeString([],{hour12:false});const kd=document.createElement('b');kd.textContent=(r.kind||'').toUpperCase();meta.append(tm,kd);d.append(tx,meta);rowsEl.append(d);});
    }
    function logAdd(kind,t,err){if(logRows.length&&logRows[0].t===t&&logRows[0].kind===kind)return;logRows.unshift({at:Date.now(),kind,t,err:!!err});if(logRows.length>80)logRows.pop();try{sessionStorage.setItem(LOGKEY,JSON.stringify(logRows.slice(0,80)));}catch(_){}paintLog();updateHead();}
    function logLine(t,err){logAdd('hands',t,err);}
    function clickByText(t){const b=[...document.querySelectorAll('.hb-viewbar button,.hb-right-panel button')].find(n=>n.textContent.trim().toUpperCase().startsWith(t));if(b)b.click();}
    function backAction(){
      if(!setup.hidden){setup.hidden=true;calibration=null;diagnostic=false;engine.reset();interlock=true;return true;}
      for(const s of ['.hb-session-detail','.hb-glass-panel','.hb-context-panel']){const n=document.querySelector(s);if(n&&!n.hidden){n.remove();return true;}}
      const m=document.querySelector('.hb-layer-menu:not([hidden]),.hb-more-menu:not([hidden]),.hb-tray-list:not([hidden]),.hb-jump:not([hidden]),.hb-ctx:not([hidden])');if(m){m.hidden=true;return true;}
      const v=document.getElementById('voice'),c=document.getElementById('v-close');if(v&&!v.hidden&&c){c.click();return true;}
      return false;}
    function doAction(a){if(a==='back'){if(!backAction())fitButton.click();}else if(a==='fit')fitButton.click();else if(a==='tidy')clickByText('TIDY');else if(a==='view')clickByText('VIEW:');}
    function friendly(ev,x){
      if(ev==='dwell-right')return 'MIDDLE-FINGER POINT: right click on '+(x.target||'a control');
      if(ev==='dwell-action')return 'POINT HOLD: '+actName(x.action);if(ev==='mpinch-action')return 'THUMB + MIDDLE: '+actName(x.action);
      if(ev==='end-left')return x.how==='tap'?'TAP: click':x.how==='scroll'?'SCROLL: a panel followed your hand':x.how==='drag'?'DRAG ('+x.travel+' px)':null;
      if(ev==='dwell-click')return 'POINT CLICK on '+(x.target||'a control');
      if(ev==='real-click')return x.ok?'REAL CLICK sent (file picker / media needs a real one)':'real click refused: '+(x.why||'error');
      if(ev==='end-right')return x.how==='contextmenu'?'RIGHT CLICK: menu':'right press ended ('+x.how+')';
      if(ev==='begin-orbit')return 'FIST: tilting the board';if(ev==='begin-zoom1')return 'ZOOM hold';if(ev==='begin-pan')return 'PALM: panning';
      if(ev==='no-target'||ev==='tap-no-target')return 'press found nothing under the pointer';
      return null;
    }
    // ---- POINT: a ring that follows the index fingertip (it is the cursor), the control under it outlined, and a click when it is held still on one
    function clickableOf(el){
      for(let e=el,d=0;e&&e.nodeType===1&&d<6;e=e.parentElement,d++){
        if(e.classList&&e.classList.contains('hk-h'))return null;
        if(e.matches&&e.matches(CLICKABLE)&&!e.disabled)return e;
        const w=e.ownerDocument.defaultView||window;if(w.getComputedStyle(e).cursor==='pointer')return e;                // anything that shows a pointing cursor is clickable
      }
      return null;
    }
    const DWELL_MS=800,RING_FROM_MS=250,CLICKABLE='button,a[href],[role=button],[role=menuitem],[role=tab],input:not([type=hidden]),select,textarea,summary,label,[data-a],[data-restore],[onclick]';
    let cursorInfo=null,dw={x:0,y:0,since:0,fired:false},targetBox=null,realMouseAt=-Infinity,handsLive=false,lastEl=null,lastRes=null,lastAt=-Infinity,lastX=-1e9,lastY=-1e9,lastRect='';
    function hideTarget(){if(targetBox){targetBox.remove();targetBox=null;lastRect='';}}
    function pointerUi(hands,now){
      const h=hands[0],pointing=h&&(h.gesture==='point'||h.gesture==='middle')&&!h.pinched&&!h.rpinched&&!h.triple&&!diagnostic&&!interlock&&!presses.size;
      if(!pointing){cursorInfo=null;dw.since=0;hideTarget();if(handsLive){handsLive=false;document.documentElement.classList.remove('hands-live');}return;}
      const x=h.x,y=h.y;
      if(!dw.since||Math.hypot(x-dw.x,y-dw.y)>Math.max(22,innerWidth*.017)){dw={x,y,since:now,fired:false};}
      if(Math.hypot(x-lastX,y-lastY)>4||now-lastAt>150){lastRes=resolve(x,y);lastX=x;lastY=y;lastAt=now;}         // the element under the pointer is looked up when the pointer moved, not every frame
      const mode=h.gesture==='middle'?act().middle:act().point,r=lastRes,el=r&&r.el?clickableOf(r.el):null,any=r&&r.el?r.el:null,usable=!isOff(h.gesture==='middle'?'middle':'point')&&!h.near&&mode==='none'?false:mode==='left'?!!el:mode==='right'?!!any:true;
      const live=now-realMouseAt>2500;if(live!==handsLive){handsLive=live;document.documentElement.classList.toggle('hands-live',live);}
      const held=now-dw.since;
      cursorInfo={x,y,progress:usable&&!dw.fired?Math.max(0,Math.min(1,(held-RING_FROM_MS)/(DWELL_MS-RING_FROM_MS))):0,usable};
      if(usable&&(el||any)&&(mode==='left'||mode==='right')){
        const tg=el||any,b=tg.getBoundingClientRect(),k=r.k||1;if(!targetBox){targetBox=document.createElement('div');targetBox.className='hands-target';targetBox.setAttribute('aria-hidden','true');document.body.appendChild(targetBox);}
        const key=Math.round(r.ox+b.left*k)+','+Math.round(r.oy+b.top*k)+','+Math.round(b.width*k)+','+Math.round(b.height*k);
        if(key!==lastRect){lastRect=key;Object.assign(targetBox.style,{left:(r.ox+b.left*k-3)+'px',top:(r.oy+b.top*k-3)+'px',width:(b.width*k+6)+'px',height:(b.height*k+6)+'px'});}
      }else hideTarget();
      if(usable&&!dw.fired&&held>=DWELL_MS&&h.sincePinch>600&&now-typedAt>1500&&mode!=='left'){
        dw.fired=true;lastAction=performance.now();
        if(mode==='right'&&r.el.ownerDocument!==document&&!r.el.closest('.hk-h')){pageMenu(x,y,r.el.ownerDocument.defaultView);counts.rclicks++;mark('dwell-right',{target:'page menu'});}else if(mode==='right'){const w=r.el.ownerDocument.defaultView||window;r.el.dispatchEvent(new w.MouseEvent('contextmenu',{bubbles:true,cancelable:true,composed:true,clientX:(x-r.ox)/r.k,clientY:(y-r.oy)/r.k,button:2}));counts.rclicks++;mark('dwell-right',{target:String(any.className||any.tagName).slice(0,30)});}
        else{doAction(mode);mark('dwell-action',{action:mode});}
      }
      if(usable&&!dw.fired&&held>=DWELL_MS&&h.sincePinch>600&&now-typedAt>1500&&mode==='left'){
        dw.fired=true;const q={target:r.el,k:r.k,ox:r.ox,oy:r.oy,button:0},w=r.el.ownerDocument.defaultView||window,o={bubbles:true,cancelable:true,composed:true,clientX:(x-r.ox)/r.k,clientY:(y-r.oy)/r.k};
        emit(q,'pointermove',h.id,x,y,false);if(needsReal(r.el)){realClick(x,y);}else{emit(q,'pointerdown',h.id,x,y,true);emit(q,'pointerup',h.id,x,y,false);r.el.dispatchEvent(new w.MouseEvent('click',{...o,detail:1}));}
        counts.clicks++;counts.dwells++;counts.pinches++;mark('dwell-click',{x:Math.round(x),y:Math.round(y),target:String(el.className||el.tagName).slice(0,30)});lastAction=performance.now();firstPinch();
      }
    }
    // What this hand is doing right now, or what a pose would do if held: shown as a coloured ring and a label at the palm
    function modeLabel(hand){
      const pr=presses.get(hand.id),v=boardView();
      if(ctl.on&&ctl.id===hand.id){
        if(hand.gesture==='fist')return {t:v&&v.mode()==='3d'?'ROTATE BOARD AND PANELS':'CONTROL ON',c:'#ff9d3b'};
        if(ctl.lock==='pan')return {t:'PAN',c:'#41ebff'};
        if(ctl.lock==='zoom')return {t:'ZOOM',c:'#00e676'};
        return {t:'CONTROL · MOVE OR PUSH / PULL',c:'#ff9d3b',soft:true};}
      if(pr){
        if(pr.mode==='orbit')return {t:'ROTATE BOARD AND PANELS',c:'#ff9d3b'};
        if(pr.mode==='zoom1')return {t:'ZOOM',c:'#00e676'};
        if(pr.mode==='left')return {t:pr.scrolled?'SCROLL':pr.travel>=dead()?'DRAG':'CLICK OR DRAG',c:'#00e676'};
        if(pr.mode==='right')return {t:'RIGHT CLICK',c:'#f5c842'};}
      if(output0&&output0.zoom)return {t:'ZOOM',c:'#00e676'};
      if(hand.closeness>.5&&!isOff('pinch')&&act().pinch!=='none')return {t:'PINCH · '+actName(act().pinch).toUpperCase(),c:'#00e676',soft:true};
      if(hand.closenessM>.5&&!isOff('mpinch')&&act().mpinch!=='none')return {t:'MIDDLE PINCH · '+actName(act().mpinch).toUpperCase(),c:'#f5c842',soft:true};
      if(hand.gesture==='fist'&&ctlEnabled())return {t:'HOLD FIST · TAKE CONTROL',c:'#ff9d3b',soft:true};
      return null;
    }
    let output0=null;
    function paint(hands){
      if(!canvas)return;const dpr=Math.min(1.5,devicePixelRatio||1),w=innerWidth,h=innerHeight;
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
      if(cursorInfo){const c=cursorInfo;ctx.strokeStyle=c.usable?'#00e676':'#41ebff';ctx.lineWidth=2.4;ctx.beginPath();ctx.arc(c.x,c.y,14,0,Math.PI*2);ctx.stroke();ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(c.x,c.y,3,0,Math.PI*2);ctx.fill();
        if(c.progress>0){ctx.strokeStyle='#00e676';ctx.lineWidth=5;ctx.beginPath();ctx.arc(c.x,c.y,20,-Math.PI/2,-Math.PI/2+c.progress*Math.PI*2);ctx.stroke();}}
      for(const hand of hands){
        const ml=modeLabel(hand);
        ctx.strokeStyle='#41ebff';ctx.lineWidth=1.2;ctx.globalAlpha=.55;ctx.beginPath();for(const [a,b]of G.BONES){ctx.moveTo(hand.points[a].x,hand.points[a].y);ctx.lineTo(hand.points[b].x,hand.points[b].y);}ctx.stroke();ctx.globalAlpha=1;
        const T=hand.points[4],I=hand.points[8],M=hand.points[12];
        for(const [tip,close,on,color,label] of [[I,hand.closeness,hand.pinched,'#00e676','L'],[M,hand.closenessM,hand.rpinched,'#f5c842','R']]){
          ctx.strokeStyle=color;ctx.lineWidth=1+4*close;ctx.globalAlpha=.35+.65*close;ctx.beginPath();ctx.moveTo(T.x,T.y);ctx.lineTo(tip.x,tip.y);ctx.stroke();
          ctx.globalAlpha=1;ctx.fillStyle=on?color:'rgba(8,12,40,.9)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(tip.x,tip.y,on?8:6,0,Math.PI*2);ctx.fill();ctx.stroke();
          ctx.fillStyle=on?'#080c28':color;ctx.font='700 9px Orbitron,monospace';ctx.textAlign='center';ctx.fillText(label,tip.x,tip.y+3);
        }
        ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(T.x,T.y,5,0,Math.PI*2);ctx.fill();
        ctx.strokeStyle=hand.gesture==='fist'?'#ff9d3b':'#41ebff';ctx.lineWidth=1.6;ctx.beginPath();ctx.arc(hand.palm.x,hand.palm.y,hand.gesture==='fist'?16:4,0,Math.PI*2);ctx.stroke();
        if(ml){ctx.save();ctx.strokeStyle=ml.c;ctx.lineWidth=ml.soft?1.5:3;ctx.globalAlpha=ml.soft?.7:1;ctx.setLineDash(ml.soft?[5,4]:[]);ctx.beginPath();ctx.arc(hand.palm.x,hand.palm.y,30,0,Math.PI*2);ctx.stroke();ctx.setLineDash([]);
          ctx.font='700 10px Orbitron,monospace';ctx.textAlign='center';const tw=ctx.measureText(ml.t).width+14,ty=hand.palm.y+52;ctx.globalAlpha=.9;ctx.fillStyle='rgba(8,12,40,.88)';ctx.fillRect(hand.palm.x-tw/2,ty-12,tw,18);ctx.strokeRect(hand.palm.x-tw/2,ty-12,tw,18);ctx.globalAlpha=1;ctx.fillStyle=ml.c;ctx.fillText(ml.t,hand.palm.x,ty+1);ctx.restore();}
      }
    }
    function firstPinch(){if(used)return;used=true;legendTimer=setTimeout(()=>{if(legend)legend.style.opacity='0';},4000);}
    const say=(m)=>{hint=m;hintAt=performance.now();logLine(m);};

    // ---- one frame in
    // One action for a pinch gesture: a press (left / right: click, drag, scroll) or a one-shot command (back, fit, tidy, view)
    function pressOrAct(hand,key,was){
      const a=act()[key];
      if(a==='left'||a==='right'){if(begin(hand.id,hand,a)){const pp=presses.get(hand.id);if(pp)pp.src=key;}return;}
      if(!was.has(hand.id)){was.add(hand.id);if(a!=='none'){doAction(a);mark('gesture-action',{key,action:a});}lastAction=performance.now();}
    }
    // FIST CONTROL. A held fist takes control of the screen. Open the hand and the palm moves the board OR zooms it, never both at once: the first
    // one to move far enough locks, and it stays locked until the hand rests. A fist again, or a point or a pinch, hands the screen back.
    function ctlEnd(hand,why){
      const pr=presses.get(ctl.id);if(pr&&pr.mode==='pan')release(ctl.id,false,hand);
      ctl.on=false;ctl.lock=null;ctl.ref=null;ctl.sm=null;ctl.still=null;ctl.sawRelease=false;ctl.fistLatched=false;ctlInfo.lock='';ctlInfo.travel=0;ctlInfo.dchange=0;
      say('CONTROL DONE'+(why?': '+why:''));mark('control-off',{why:why||''});
    }
    function controlStep(hand,now){
      const T=engine.tuning;
      if(!hand){if(ctl.on){ctl.lostAt=ctl.lostAt||now;if(now-ctl.lostAt>1500)ctlEnd(null,'hand lost');}return false;}
      ctl.lostAt=null;ctl.id=hand.id;
      if(!ctlEnabled()){if(ctl.on)ctlEnd(hand,'turned off');return false;}
      const fist=hand.gesture==='fist'&&!hand.pinched&&!hand.rpinched&&!hand.triple;
      if(fist){
        ctl.fistSince=ctl.fistSince==null?now:ctl.fistSince;
        if(now-ctl.fistSince>=300&&!ctl.fistLatched){ctl.fistLatched=true;
          if(!ctl.on){ctl.on=true;ctl.sawRelease=false;ctl.lock=null;ctl.ref=null;ctl.sm=null;say('CONTROL ON: OPEN YOUR PALM TO MOVE OR ZOOM. FIST AGAIN TO FINISH');mark('control-on');}
          else if(ctl.sawRelease){ctlEnd(hand,'fist');return false;}}
        return false;      // the fist itself: the 3D rotation below
      }
      ctl.fistSince=null;ctl.fistLatched=false;if(ctl.on)ctl.sawRelease=true;
      if(!ctl.on)return false;
      if(hand.pinched||hand.rpinched||hand.triple||hand.gesture==='point'||hand.gesture==='middle'){ctlEnd(hand,hand.gesture==='point'||hand.gesture==='middle'?'pointer':'pinch');return false;}
      const gx=hand.palm;ctl.sm=ctl.sm==null?hand.depth:ctl.sm*.5+hand.depth*.5;
      if(!ctl.ref){ctl.ref={...gx};ctl.d0=ctl.sm;ctl.pp=null;}
      const dt=Math.max(16,now-(ctl.t||now)),sp=ctl.pp?G.distance(ctl.pp,gx)/dt*1000:0;ctl.t=now;ctl.pp={...gx};
      const dd=Math.log(ctl.sm/ctl.d0),travel=G.distance(ctl.ref,gx),cp=canPan(),cz=canZoom();
      ctlInfo.travel=travel;ctlInfo.dchange=Math.abs(dd);ctlInfo.lock=ctl.lock||'';
      if(!ctl.lock){
        const pr=travel/T.panStart,zr=Math.abs(dd)/T.depthStep;
        if(cp&&pr>=1&&(!cz||pr>=zr)){ctl.lock='pan';ctl.still=null;beginPan(hand.id,hand);say('PAN: REST YOUR HAND TO FINISH THIS MOVE');}
        else if(cz&&zr>=1&&(!cp||zr>pr)){ctl.lock='zoom';ctl.zref=ctl.sm;ctl.zlast=now;say('ZOOM: HOLD STILL TO FINISH THIS ZOOM');}
        return true;
      }
      if(ctl.lock==='pan'){
        const pr=presses.get(hand.id);if(!pr||pr.mode!=='pan'){ctl.lock=null;ctl.ref=null;ctl.sm=null;return true;}
        const at=posOf(pr,hand);pr.travel=Math.max(pr.travel,G.distance(pr.down,at));pr.last=at;emit(pr,'pointermove',hand.id,at.x,at.y,true);
        if(sp<T.depthStill){if(ctl.still==null)ctl.still=now;else if(now-ctl.still>=T.ctlStillMs){release(hand.id,false,hand);ctl.lock=null;ctl.ref=null;ctl.sm=null;ctl.still=null;}}else ctl.still=null;
        return true;
      }
      const r=Math.log(ctl.sm/ctl.zref);
      if(Math.abs(r)>.02){ctl.zref=ctl.sm;ctl.zlast=now;host.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,ctrlKey:true,deltaY:Math.max(-180,Math.min(180,-r*1100)),deltaMode:0,clientX:ctl.ref.x,clientY:ctl.ref.y}));}      // toward the camera = bigger hand = zoom in
      else if(now-ctl.zlast>=T.ctlStillMs){ctl.lock=null;ctl.ref=null;ctl.sm=null;}
      return true;
    }
    function feed(result,now=performance.now(),meta={}){
      if(!enabled||!alive)return;
      if(!document.hasFocus()||document.hidden){if(presses.size)cancelAll();if(status&&!hint)status.textContent='CLICK THE HUB WINDOW ONCE SO HANDS CAN ACT ON IT';else if(status)say('CLICK THE HUB WINDOW ONCE SO HANDS CAN ACT ON IT');return;}
      const processingAt=performance.now();
      const output=engine.update(result,now,innerWidth,innerHeight,meta.cam);if(output.stale)return;output0=output;counts.frames++;if(isOff('hand')){output.hands=[];output.zoom=null;output.fit=false;}else if(isOff('twohand'))output.zoom=null;pointerUi(output.hands,now);paint(output.hands);
      if(confLive.length&&now-(feed.cl||0)>150){feed.cl=now;const h=output.hands[0];for(const c of confLive){if(!c.cell.isConnected)continue;try{c.cell.textContent=h?c.fn(h,output):'no hand';c.fill.style.width=h?Math.round(c.v(h,output)*100)+'%':'0';}catch(_){}}}
      for(const h of output.hands){if(!h.rpinched)rWas.delete(h.id);if(!h.pinched)lWas.delete(h.id);if(!h.triple)tWas.delete(h.id);}
      for(const h of output.hands){const on=h.pinched||h.rpinched||h.triple;if(on&&!detected.has(h.id)){detected.add(h.id);counts.detectedPinches++;}if(!on)detected.delete(h.id);}
      for(const h of output.lost)detected.delete(h.id);
      counts.latencies.push(performance.now()-(Number.isFinite(meta.inferenceMs)?now:processingAt));if(Number.isFinite(meta.captureTime))counts.cameraLatencies.push(performance.now()-meta.captureTime);
      if(counts.latencies.length>1800)counts.latencies.shift();if(counts.cameraLatencies.length>1800)counts.cameraLatencies.shift();
      if(output.hands.length)counts.handFrames++;
      if(status&&output.hands[0]&&performance.now()-hintAt>2500){const h=output.hands[0];status.textContent=(diagnostic?measurementLabel+' · ACTIONS PAUSED':'CAMERA ON')+' · L '+h.gap.toFixed(2)+' · R '+h.gapM.toFixed(2)+' (press below '+engine.tuning.pinchOn.toFixed(2)+' / '+engine.tuning.pinchOnM.toFixed(2)+') · '+(h.triple?'ZOOM HOLD':h.pinched?'LEFT PRESS':h.rpinched?'RIGHT PRESS':String(h.gesture).toUpperCase());}
      else if(status&&hint&&performance.now()-hintAt<=2500)status.textContent=hint;
      for(const lost of output.lost)release(lost.id,true);
      ringFrame(output,result,now);
      if(calibration){cancelAll();const h=output.hands[0];
        if(h&&output.hands.length===1){calibration.samples.push(h.gap);
          if(now-calibration.at>=2000&&calibration.samples.length>=25){const a=calibration.samples.slice().sort((x,y)=>x-y),v=a[Math.floor(a.length/2)];
            if(calibration.phase==='open'){calibration.open=v;calibration.phase='closed';calibration.samples=[];calibration.at=now;calibration.message.textContent='Now touch your thumb to your index fingertip and hold for two seconds.';}
            else{const open=calibration.open,closed=v;if(open-closed>.2){profile.pinchOn=closed+(open-closed)*.3;profile.pinchOff=closed+(open-closed)*.65;saveProfile();calibration.message.textContent='Calibration saved in this browser. Close this panel to resume.';}else calibration.message.textContent='Samples were too similar. Please restart calibration.';calibration=null;}}
        }else if(calibration){calibration.samples=[];calibration.at=now;}return;}
      if(diagnostic)return;
      if(interlock){if(!output.hands.some(h=>h.pinched||h.rpinched||h.triple)&&now>=cooldown)interlock=false;else return;}
      if(output.zoom){
        if(!zooming){cancelAll();zooming=true;counts.zooms++;for(const hand of output.hands)begin(hand.id,hand,'zoom');}
        for(const hand of output.hands){const p=presses.get(hand.id);if(p){const at=posOf(p,hand);p.last=at;emit(p,'pointermove',hand.id,at.x,at.y,true);}}
        return;}
      if(zooming){cancelAll();interlock=true;return;}
      if(output.fit&&![...presses.values()].some(p=>p.mode!=='pan')&&now-typedAt>3000&&performance.now()-lastAction>2500&&!ctl.on&&!isOff('open')){if(act().open!=='none')doAction(act().open);counts.fits++;}
      const h0=output.hands[0],owns=controlStep(h0,now);
      for(const hand of output.hands){
        if(owns&&hand===h0)continue;
        let p=presses.get(hand.id);
        // thumb, index and middle together: one-hand zoom. A press that began on the way there is cancelled, never completed as a click.
        if(hand.triple&&!isOff('triple')&&act().triple==='zoom'&&(!p||p.mode!=='zoom1')){if(p)release(hand.id,true);begin(hand.id,hand,'zoom1');continue;}
        if(p){
          if(p.mode==='zoom1'){
            if(!hand.triple){release(hand.id,false);continue;}
            const dy=hand.palm.y-p.prev.y;p.prev={...hand.palm};
            if(dy)host.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:dy*2.2,deltaMode:0,clientX:p.at.x,clientY:p.at.y}));      // hand up zooms in, down zooms out
            continue;
          }
          if(p.mode==='orbit'){
            if(!(hand.gesture==='fist'||hand.fistRatio<engine.tuning.fistDist*1.2)||hand.pinched||hand.rpinched||hand.triple){release(hand.id,false);continue;}      // a fist that flickers to another label for a frame does not end the turn
            const Tn=engine.tuning,v=boardView(),sg=profile.twistSign===-1?-1:1;      // rotation only: turning the wrist turns the board, moving the hand does nothing
            const step=(cur,key)=>{const ref=p[key]==null?cur:p[key],d=cur-ref;if(Math.abs(d)<Tn.rotDead)return 0;p[key]=cur;return d;};      // slow turns add up until they pass the dead band: a trembling hand turns nothing
            const dT=step(hand.twist||0,'twist')*sg,dR=step(hand.roll,'roll'),dP=step(hand.pitch||0,'pitch');
            const ww=rotWrist()?1:0,mm=rotMove()?1:0,ox=(dT*Tn.rotGain+dR*Tn.rollGain)*ROLL_PX*ww+(hand.palm.x-p.prev.x)*Tn.moveGain*mm,oy=(dP*Tn.tiltGain+dR*Tn.rollTilt)*ROLL_PX*ww+(hand.palm.y-p.prev.y)*Tn.moveGain*mm;
            p.sx=(p.sx||0)*Tn.rotSmooth+ox*(1-Tn.rotSmooth);p.sy=(p.sy||0)*Tn.rotSmooth+oy*(1-Tn.rotSmooth);      // and the board eases toward it instead of following every wobble
            if(v)v.orbitBy(p.sx,p.sy);p.prev={...hand.palm};continue;
          }
          if(p.mode==='pan'){release(hand.id,false,hand);continue;}      // pan belongs to the fist-control mode below
          const trp=act().triple!=='zoom'&&hand.triple,done=p.src==='pinch'?!(hand.pinched||trp):p.src==='triple'?!(hand.triple||hand.pinched):p.src==='mpinch'?!hand.rpinched:(p.mode==='left'?!hand.pinched:!hand.rpinched);
          if(done){release(hand.id,false,hand);continue;}
          const at=posOf(p,hand);p.travel=Math.max(p.travel,G.distance(p.down,at));
          if(p.mode==='left'&&p.scroller&&p.travel>=dead()){const k=p.k||1;p.scroller.scrollTop-=(at.y-p.sy)/k;p.scroller.scrollLeft-=(at.x-p.sx)/k;p.sy=at.y;p.sx=at.x;p.scrolled=true;p.last=at;continue;}      // touch-style scrolling
          p.last=p.travel<(p.mode==='left'?dead():slop())?p.down:at;emit(p,'pointermove',hand.id,p.last.x,p.last.y,true);
        }
        else if(hand.pinched&&!isOff('pinch')){pressOrAct(hand,'pinch',lWas);}
        else if(hand.rpinched&&!isOff('mpinch')){pressOrAct(hand,'mpinch',rWas);}
        else if(hand.triple&&!isOff('triple')&&act().triple!=='zoom'){pressOrAct(hand,'triple',tWas);}
        else if(fistRotate()&&hand.gesture==='fist'&&hand.sincePinch>700){const v=boardView();if(v&&v.mode()==='3d')begin(hand.id,hand,'orbit');else say('FIST TILTS THE BOARD IN VIEW 3D: choose VIEW, then 3D');}
        else{const r=resolve(hand.x,hand.y);if(r)emit({target:r.el,k:r.k,ox:r.ox,oy:r.oy,button:0},'pointermove',hand.id,hand.x,hand.y,false);}
      }
    }
    function stopped(reason){logLine('HANDS OFF: '+reason,/fail|error|denied|blocked/i.test(String(reason)));enabled=false;cursorInfo=null;hideTarget();document.documentElement.classList.remove('hands-live');saveBtn.hidden=true;btn.classList.remove('live');btn.setAttribute('aria-pressed','false');btn.title='Hand control off: '+reason;cancelAll();calibration=null;diagnostic=false;engine.reset();detected.clear();clearOverlay();}
    const tracker=root.HubHandsTracker.create({onFrame:feed,onStop:stopped,onState(s){if(s.error)logLine('ERROR: '+s.error+' - tell the Doctor it is there',true);saveBtn.hidden=!s.enabled;if(s.enabled){enabled=true;showOverlay();btn.classList.add('live');btn.setAttribute('aria-pressed','true');}btn.setAttribute('aria-busy',String(s.loading));btn.title=s.error||('Hand control '+s.reason);},...(root.__HUB_HANDS_TEST?.tracker||{})});

    // ---- numbers only: the last minute of what the camera saw and what the engine and the board did, kept in memory while HANDS is on and saved when asked
    const STEPS=[['relaxed','Rest your hand, relaxed, fingers loose'],['point','Point at the screen with your index finger, other fingers curled'],['open','Open hand, fingers spread'],
      ['pinch_index','Pinch thumb to INDEX fingertip, hold a second, release: three times'],['pinch_middle','Pinch thumb to MIDDLE fingertip, hold, release: three times'],
      ['fist','Make a FIST, hold, then open: twice'],['three_together','Bring thumb, index and middle together, then spread them: three times'],['rest','Rest your hand again, relaxed']];
    const ring=[],events=[],rd=v=>Math.round(v*1000)/1000;let guided=null,lastRingAt=-1e9;
    function mark(ev,extra){events.push({t:Math.round(performance.now()),ev,...(extra||{})});if(events.length>500)events.shift();const f=friendly(ev,extra||{});if(f)logLine(f);}
    function ringFrame(output,result,now){
      if(now-lastRingAt<66)return;lastRingAt=now;
      ring.push({t:Math.round(performance.now()),step:guided?guided.step():'',hands:output.hands.map((h,k)=>({gesture:h.gesture,pinched:h.pinched,rpinched:h.rpinched,triple:h.triple,flat:h.flat?1:0,gap:rd(h.gap),gapM:rd(h.gapM),roll:rd(h.roll),
        sincePinch:Math.min(99999,Math.round(h.sincePinch)),lm:(result.landmarks[k]||[]).map(q=>[rd(q.x),rd(q.y),rd(q.z||0)])}))});
      if(ring.length>900)ring.shift();
    }
    async function saveTrace(kind,message){
      const v=boardView();
      try{const x=await fetch('/api/hands/trace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,trace:{version:3,kind,screen:[innerWidth,innerHeight],view:v?v.mode():'',
          tuning:{on:engine.tuning.pinchOn,off:engine.tuning.pinchOff},steps:STEPS.map(z=>z[0]),frames:ring.slice(),events:events.slice()}})});
        if(!x.ok)throw Error('not saved');const j=await x.json();say('TRACE SAVED: '+j.saved+' ('+Math.round(j.bytes/1024)+' KB). Tell the Doctor it is there.');if(message)message.textContent='Saved '+j.saved+' in the Hub data folder: only numbers, no pictures. Tell the Doctor it is there.';}
      catch(e){say('TRACE NOT SAVED: '+e.message);if(message)message.textContent='The trace could not be saved: '+e.message;}
    }
    function startTrace(message){
      const stepMs=(root.__HUB_HANDS_TEST&&root.__HUB_HANDS_TEST.traceStepMs)||4000,t0=performance.now();cancelAll();diagnostic=true;
      guided={step:()=>STEPS[Math.min(STEPS.length-1,Math.floor((performance.now()-t0)/stepMs))][0]};
      const tick=()=>{if(!guided||!alive)return;const i=Math.floor((performance.now()-t0)/stepMs);
        if(i>=STEPS.length){guided=null;diagnostic=false;engine.reset();interlock=true;saveTrace('guided',message);return;}
        if(status)status.textContent='RECORDING '+(i+1)+'/'+STEPS.length+' · '+STEPS[i][1].toUpperCase();setTimeout(tick,120);};tick();
    }

    // ---- setup: nothing to save by hand; a choice or a calibration is kept in this browser at once
    function saveProfile(){cancelAll();engine.reset();engine.options.fistGrab=!!profile.fist;engine.options.tripleZoom=!isOff('triple');engine.tuning.pinchOn=G.TUNING.pinchOn;engine.tuning.pinchOff=G.TUNING.pinchOff;
      if(Number.isFinite(profile.pinchOn)&&profile.pinchOn>.05&&profile.pinchOff>profile.pinchOn&&profile.pinchOff<1.2){engine.tuning.pinchOn=profile.pinchOn;engine.tuning.pinchOff=profile.pinchOff;}
      Object.assign(engine.tuning,profile.tuning||{});profile.v=PROFILE_VERSION;try{localStorage.setItem('hub-hands-profile',JSON.stringify(profile));}catch(_){}interlock=true;}
    saveProfile();
    function closeX(onclose){const b=document.createElement('button');b.type='button';b.className='hb-btn hs-x';b.setAttribute('aria-label','Close');b.title='Close';b.innerHTML='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';b.onclick=onclose;return b;}
    function tableOf(caption,heads,rows,cls){const tb=document.createElement('table');tb.className='hs-table '+(cls||'');tb.createCaption().textContent=caption;const hr=tb.insertRow();heads.forEach(x=>{const th=document.createElement('th');th.textContent=x;hr.appendChild(th);});
      rows.forEach(r=>{const tr=tb.insertRow();r.cells.forEach(c=>{tr.insertCell().textContent=c;});if(r.fn){tr.className='hs-act';tr.tabIndex=0;tr.setAttribute('role','button');tr.onclick=r.fn;tr.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();r.fn();}};}});return tb;}
    // The two tables of the hands menu. The same ones are in the dialog and under HANDS in the log; `repaint` redraws whichever is showing.
    function handsTables(repaint,p){
      // TWO TABLES. DETECTORS: what the camera can tell about the hand, each with a live meter and its thresholds.
      // GESTURES: what you want done when detectors line up (a pose, a hold, a combo of two), each with ON / OFF and, where it can change, its action.
      const D=G.TUNING,T=engine.tuning,save=()=>{try{localStorage.setItem('hub-hands-profile',JSON.stringify(profile));}catch(_){}};
      const tog=(key,on)=>()=>{profile[key]=!on();saveProfile();repaint();},dis=key=>({on:()=>!isOff(key),flip:()=>{profile.dis={...(profile.dis||{}),[key]:!isOff(key)};saveProfile();repaint();}});
      const el=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;};
      const cnt=o=>o.hands.filter(x=>x.pinched).length;
      confLive=[];
      // ---------------- detectors
      const det=[
        {n:'Hand seen',tip:'The camera model must be at least this sure it is a hand, for this many frames in a row.',m:{v:h=>h.conf,max:1,tk:[['minScore','min']],f:h=>Math.round(h.conf*100)+'%'},k:[['minScore','min score',.05,0,1],['presentFrames','frames',1,1,10]]},
        {n:'Index finger out',tip:'Fingertip distance from the wrist divided by its middle knuckle distance. Above the mark the finger counts as out.',m:{v:h=>h.idxRatio,max:2,tk:[['extendRatio','out']],f:h=>h.idxRatio.toFixed(2)+(h.idxRatio>T.extendRatio?' out':' curled')},k:[['extendRatio','out at',.02,1,1.6]]},
        {n:'Middle finger out',tip:'Same measure for the middle finger.',m:{v:h=>h.midRatio,max:2,tk:[['extendRatio','out']],f:h=>h.midRatio.toFixed(2)+(h.midRatio>T.extendRatio?' out':' curled')},k:[['extendRatio','out at',.02,1,1.6]]},
        {n:'Thumb to index',tip:'Distance between the two fingertips as a fraction of your hand size. Under ON it becomes a pinch; it stays one until it passes OFF.',m:{v:h=>h.gap,max:.8,tk:[['pinchOn','ON'],['pinchOff','OFF']],f:h=>h.gap.toFixed(2)+(h.pinched?' PINCH':'')},k:[['pinchOn','ON',.01,.05,.6],['pinchOff','OFF',.01,.1,.9],['confirmMs','hold ms',10,0,400]]},
        {n:'Thumb to middle',tip:'Same, thumb to middle fingertip, with the index finger kept away by at least the third number.',m:{v:h=>h.gapM,max:.8,tk:[['pinchOnM','ON'],['pinchOffM','OFF']],f:h=>h.gapM.toFixed(2)+(h.rpinched?' PINCH':'')},k:[['pinchOnM','ON',.01,.05,.6],['pinchOffM','OFF',.01,.1,.9],['rightIndexAway','index away',.01,.1,.9]]},
        {n:'Thumb to index and middle',tip:'Thumb touching both fingertips; must be held for the last number.',m:{v:h=>Math.max(h.gap,h.gapM),max:.8,tk:[['tripleOn','ON'],['tripleOff','OFF']],f:h=>Math.max(h.gap,h.gapM).toFixed(2)+(h.triple?' PINCH':'')},k:[['tripleOn','ON',.01,.05,.6],['tripleOff','OFF',.01,.1,.9],['tripleHoldMs','hold ms',20,0,800]]},
        {n:'Two hands pinching',tip:'Both hands in a thumb and index pinch at once; the distance between them is the zoom.',m:{v:(h,o)=>cnt(o),max:2,tk:[],f:(h,o)=>cnt(o)+' of 2'+(o.zoom?' · '+Math.round(o.zoom.distance)+' px apart':'')},k:[]},
        {n:'Fist',tip:'Average fingertip distance from the palm as a fraction of hand size. Under the mark it is a fist.',m:{v:h=>h.fistRatio,max:1.2,tk:[['fistDist','max']],f:h=>h.fistRatio.toFixed(2)},k:[['fistDist','fist under',.01,.3,1.2]]},
        {n:'Open fingers',tip:'How many of the five fingers are out, and how long a pose must hold before it counts.',m:{v:h=>h.openScore,max:1,tk:[],f:h=>Math.round(h.openScore*5)+' of 5'},k:[['poseHoldMs','hold ms',20,0,800]]},
        {n:'Wrist rotation',tip:'Twist = forearm turning. Roll = fist tilting like a steering wheel. Pitch = fist tipping toward the camera. The numbers say how far the board turns for each, a minus flips the direction; "hand moves" adds the fist travelling through space; smooth and ignore-under steady it.',m:{v:h=>Math.abs(h.twist)+Math.abs(h.roll)+Math.abs(h.pitch),max:1,tk:[],f:h=>'twist '+h.twist.toFixed(2)+' roll '+h.roll.toFixed(2)+' pitch '+h.pitch.toFixed(2)},k:[['rotGain','twist · left/right',.25,-6,6],['rollGain','roll · left/right',.25,-6,6],['tiltGain','pitch · up/down',.5,-12,12],['rollTilt','roll · up/down',.25,-6,6],['moveGain','hand moves',.1,-3,3],['rotSmooth','smooth',.05,0,.95],['rotDead','ignore under',.002,0,.05]]},
        {n:'Palm travel',tip:'How far the open palm has moved since the combo started. Past the start mark it locks to PAN. Resting for the rest time ends it.',m:{v:()=>ctlInfo.travel,max:150,tk:[['panStart','start']],f:()=>Math.round(ctlInfo.travel)+' px '+(ctlInfo.lock||'')},k:[['panStart','start px',5,10,200],['ctlStillMs','rest ms',50,100,2000],['depthStill','still under px/s',25,25,1000]]},
        {n:'Palm push / pull',tip:'Change of hand size in the picture (toward or away from the camera). Past the start mark it locks to ZOOM.',m:{v:()=>ctlInfo.dchange,max:.3,tk:[['depthStep','start']],f:()=>Math.round(ctlInfo.dchange*100)+'% '+(ctlInfo.lock||'')},k:[['depthStep','start change',.01,.01,.3]]}];
      const dt=el('table','hs-table hs-det');dt.createCaption().textContent='DETECTORS · what the camera can tell (live)';
      const dh=dt.insertRow();['Detector','Live','Thresholds'].forEach(x=>dh.appendChild(el('th',null,x)));
      for(const r of det){
        const tr=dt.insertRow(),c=[tr.insertCell(),tr.insertCell(),tr.insertCell()];
        c[0].append(el('b',null,r.n));c[0].title=r.tip;
        const m=el('div','hs-meter'),fill=document.createElement('i'),num=el('span',null,'no hand');m.append(fill);
        const ticks=r.m.tk.map(([key,lab])=>{const u=document.createElement('u');u.dataset.l=lab;m.append(u);return {u,key};});
        const place=()=>ticks.forEach(({u,key})=>{u.style.left=Math.min(100,T[key]/r.m.max*100)+'%';});place();c[1].append(num,m);
        confLive.push({cell:num,fill,fn:r.m.f,v:(h,o)=>Math.max(0,Math.min(1,r.m.v(h,o)/r.m.max))});
        const wrap=el('div','hs-fields');
        for(const [key,label,step,lo,hi] of r.k){
          const w=el('label','hs-field');w.append(el('span',null,label));
          const inp=document.createElement('input');inp.type='number';inp.step=step;inp.min=lo;inp.max=hi;inp.value=+(+T[key]).toFixed(3);
          inp.onchange=()=>{let v=parseFloat(inp.value);if(!Number.isFinite(v))v=D[key];v=Math.max(lo,Math.min(hi,v));inp.value=v;T[key]=v;profile.tuning={...(profile.tuning||{}),[key]:v};save();place();p.textContent=r.n+': '+label+' = '+v+' (saved)';};
          inp.onkeydown=e=>e.stopPropagation();w.append(inp);wrap.append(w);
        }
        if(r.k.length){const rs=el('button','hb-btn hs-reset','DEFAULT');rs.type='button';rs.onclick=()=>{for(const [key] of r.k){T[key]=D[key];if(profile.tuning)delete profile.tuning[key];}save();repaint();};wrap.append(rs);}
        c[2].append(wrap);
      }
      // ---------------- gestures
      const FIRSTS=[['point','Point, index finger'],['middle','Point, middle finger'],['pinch','Thumb + index pinch'],['mpinch','Thumb + middle pinch'],['triple','Thumb + index + middle pinch'],['open','Open hand held'],['twohand','Two hands pinching'],['fist','Fist']];
      const FOLLOW=[['','held'],['while:wrist','while held, wrist turns'],['while:palm','while held, hand moves'],['after:palm','then open palm moves'],['after:depth','then open palm push / pull']];
      const lab=(f,k,t)=>k==='left'?(f==='point'||f==='middle'?'Click':'Click, drag and scroll'):k==='zoom'?'Zoom (hand up / down)':t;
      const doesOf=r=>{const f=r.first;
        if(f==='fist'){if(!r.then)return [['control','Take control of the screen']];if(r.when==='while')return [['rotate','Rotate board and panels (VIEW 3D)'],['none','Nothing']];return r.then==='palm'?[['pan','Pan the board'],['none','Nothing']]:[['zoom','Zoom the board'],['none','Nothing']];}
        if(f==='twohand')return [['zoom','Zoom the board'],['none','Nothing']];
        return ACTIONS.filter(([k])=>k!=='zoom'||f==='triple').map(([k,t])=>[k,lab(f,k,t)]);};
      const fname=r=>(FIRSTS.find(x=>x[0]===r.first)||[0,r.first])[1]+(r.first==='fist'&&r.then?' · '+(FOLLOW.find(x=>x[0]===r.when+':'+r.then)||[0,''])[1]:'');
      const setRules=fn=>{profile.rules=fn(rules().map(r=>({...r})));saveProfile();repaint();};
      const edit=(id,fn)=>setRules(a=>{const x=a.find(y=>y.id===id);if(x)fn(x);return a;});
      const fix=x=>{if(x.first!=='fist'){x.when='';x.then='';}const ok=doesOf(x).map(d=>d[0]);if(!ok.includes(x.does))x.does=ok[0];};
      const gt=el('table','hs-table hs-gest');gt.createCaption().textContent='GESTURES · rules you can change, add and delete';
      const gh=gt.insertRow();['Gesture','On','Built from','Does',''].forEach(x=>gh.appendChild(el('th',null,x)));
      const selectOf=(opts,val,fn,title)=>{const sel=el('select','hs-sel');sel.title=title||'';opts.forEach(([k,t])=>{const o=el('option',null,t);o.value=k;if(k===val)o.selected=true;sel.append(o);});sel.onchange=()=>fn(sel.value);sel.onkeydown=e=>e.stopPropagation();return sel;};
      for(const r of rules()){
        const tr=gt.insertRow(),c=[0,1,2,3,4].map(()=>tr.insertCell());
        c[0].append(el('b',null,fname(r)));
        if(r.on&&!r.then&&r.does!=='control'&&single(r.first)!==r)c[0].append(el('small',null,'not used: an earlier rule with the same pose is active'));
        const bt=el('button','hb-btn hs-tog'+(r.on?' on':''),r.on?'ON':'OFF');bt.type='button';bt.onclick=()=>edit(r.id,x=>{x.on=!x.on;});c[1].append(bt);
        c[2].append(selectOf(FIRSTS,r.first,v=>edit(r.id,x=>{x.first=v;fix(x);}),'The pose that starts it'));
        if(r.first==='fist')c[2].append(selectOf(FOLLOW,r.then?r.when+':'+r.then:'',v=>edit(r.id,x=>{const [w,t]=v.split(':');x.when=w||'';x.then=t||'';fix(x);}),'What follows the fist'));
        c[3].append(selectOf(doesOf(r),r.does,v=>edit(r.id,x=>{x.does=v;}),'What it does'));
        const del=el('button','hb-btn hs-reset','X');del.type='button';del.title='Delete this gesture';del.onclick=()=>setRules(a=>a.filter(y=>y.id!==r.id));c[4].append(del);
      }
      const tools=el('div','hs-tools');
      const tb2=(t,fn)=>{const x=el('button','hb-btn',t);x.type='button';x.onclick=fn;tools.append(x);};
      tb2(enabled?'CAMERA: ON (turn off)':'CAMERA: OFF (turn on)',()=>{btn.onclick();setTimeout(repaint,900);});
      tb2('SAVE LAST MINUTE',()=>{if(!enabled){p.textContent='Turn the camera on, use your hands for a minute, then come back here.';return;}saveTrace('free',p);});
      tb2('RECORD A TRACE (32 s)',()=>{if(!enabled){p.textContent='Turn the camera on first.';return;}p.textContent='Recording about 32 seconds. Follow the prompts at the top left.';setup.hidden=true;startTrace(p);});
      tb2('ADD A GESTURE',()=>setRules(a=>{a.push({id:'u'+Date.now(),on:true,first:'pinch',when:'',then:'',does:'left'});return a;}));
      tb2('RESET EVERYTHING',()=>{profile={v:PROFILE_VERSION,fist:false,orbit:true,palm:false};saveProfile();for(const k of Object.keys(D))engine.tuning[k]=D[k];repaint();});
      const grid=el('div','hs-grid');grid.append(gt,dt);
      return [tools,grid];
    }
    // ONE hands menu (right-click on the hand; also under HANDS in the log): the controls and the gestures, as tables
    function closeMenu(){if(setup.hidden||!setup.querySelector('.hs-table'))return;calibration=null;diagnostic=false;engine.reset();interlock=true;setup.hidden=true;}
    let menuOpenedAt=0;
    const outside=e=>{if(setup.hidden||!setup.querySelector('.hs-table'))return;if(performance.now()-menuOpenedAt<500)return;const t=e.target;if(t&&(setup.contains(t)||btn.contains(t)||configure.contains(t)))return;closeMenu();};
    document.addEventListener('pointerdown',outside,true);
    function calibrationPanel(){menuOpenedAt=performance.now();
      cancelAll();diagnostic=true;setup.replaceChildren();setup.hidden=false;
      const head=document.createElement('div');head.className='hb-glass-head';const h2=document.createElement('h2');h2.textContent='HANDS';
      head.append(h2,closeX(()=>{calibration=null;diagnostic=false;engine.reset();interlock=true;setup.hidden=true;}));
      const p=document.createElement('p');p.className='hs-note';p.textContent=enabled?'Camera on. Tracking stays on this device.':'Camera off. Nothing watches until you turn it on. Choices save here at once; the defaults need no calibration.';
      setup.append(head,p,...handsTables(()=>{if(!setup.hidden&&setup.querySelector('.hs-table'))calibrationPanel();},p));
    }
    function setupPanel(manifest){
      setup.replaceChildren();setup.hidden=false;const title=document.createElement('strong');title.textContent=manifest.ready?'HAND CONTROL READY':'HAND TRACKING NOT INSTALLED';
      const p=document.createElement('p');p.textContent=manifest.ready?'Processing stays on this device. Start only when you want the webcam on.':'Download MediaPipe Tasks Vision 1.2.2 and hand_landmarker.task once (about 18 MB download, 38 MB stored). Files stay in the Hub state folder. No camera opens during download.';const action=document.createElement('button');action.type='button';action.className='hb-btn';const close=closeX(()=>{setup.hidden=true;});const head=document.createElement('div');head.className='hb-glass-head';const h2=document.createElement('h2');h2.textContent=title.textContent;head.append(h2,close);setup.append(head,p);
      action.textContent=manifest.ready?'START HAND CONTROL':'DOWNLOAD HAND TRACKING';
      action.onclick=async()=>{if(manifest.ready){setup.hidden=true;await tracker.start();return;}action.disabled=true;action.textContent='DOWNLOADING...';
        try{const r=await fetch('/api/hands/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});if(!r.ok)throw Error('Download failed. Try again.');setupPanel(await r.json());}
        catch(e){p.textContent=e.message;action.disabled=false;action.textContent='RETRY DOWNLOAD';}};
      setup.append(action);action.focus();
    }
    btn.onclick=async()=>{if(tracker.stats.enabled||tracker.stats.loading){tracker.stop('HANDS off');return;}used=false;engine.reset();interlock=false;
      try{const r=await fetch('/api/hands/status',{cache:'no-store'});if(!r.ok)throw Error('Hand control unavailable');const s=await r.json();if(!alive)return;if(!s.ready)setupPanel(s);else await tracker.start();}
      catch(e){btn.title=e.message;setupPanel({ready:false});}};
    const mouseSeen=e=>{if(e.isTrusted)realMouseAt=performance.now();};addEventListener('mousemove',mouseSeen,true);
    function physical(e){if(!enabled||!e.isTrusted||e.pointerId>=9000)return;cancelAll();engine.reset();interlock=true;cooldown=performance.now()+1000;}
    function escape(e){if(e.key==='Escape'&&(tracker.stats.enabled||tracker.stats.loading)){tracker.stop('Escape');e.preventDefault();}if(e.key==='Escape'){setup.hidden=true;calibration=null;diagnostic=false;}}
    const typing=e=>{if(e.isTrusted&&e.key!=='Escape')typedAt=performance.now();};
    document.addEventListener('pointerdown',physical,true);document.addEventListener('wheel',physical,{capture:true,passive:true});document.addEventListener('keydown',escape,true);document.addEventListener('keydown',typing,true);
    const api={button:btn,tracker,feed,
      startTrace,stats(){const l=counts.latencies;return {...counts,latencies:l.slice(),cameraLatencies:counts.cameraLatencies.slice(),tracker:{...tracker.stats},presses:presses.size};},
      measure(on,label){diagnostic=!!on;measurementLabel=label||'MEASURING';counts=fresh();cancelAll();},
      destroy(){alive=false;tracker.destroy();cancelAll();clearOverlay();logOff();if(logBox){logBox.remove();logBox=null;}hideTarget();document.documentElement.classList.remove('hands-live');removeEventListener('mousemove',mouseSeen,true);setup.remove();btn.remove();configure.remove();saveBtn.remove();document.removeEventListener('pointerdown',physical,true);document.removeEventListener('wheel',physical,true);document.removeEventListener('keydown',escape,true);document.removeEventListener('keydown',typing,true);if(root.__hubHands===api)root.__hubHands=null;}};
    ensureLog();
    if(root.__HUB_HANDS_TEST)api.testEnable=(opts)=>{enabled=true;if(opts&&opts.triple)engine.options.tripleZoom=true;engine.reset();showOverlay();};
    if(root.__HUB_HANDS_TEST)api.testOption=(k,v)=>{profile[k]=v;};
    root.__hubHands=api;return api;
  }
  root.HubHandsBoard={mount};
})(window);
