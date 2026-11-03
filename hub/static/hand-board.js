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
//   thumb + middle  the right button: click opens a context menu, drag tilts the board in VIEW 3D
//   a closed fist   (VIEW 3D) holds the right button too: move and turn the fist to tilt and turn the board
//   two index pinches  zoom;  an open hand held for a second  fits everything
// A press follows the PALM, not the fingertip: the fingertip moves several centimetres while the fingers close, which turned clicks into drags.
(function(root){
  'use strict';
  const G=root.HubHandsGestures,ROLL_PX=320,PROFILE_VERSION=2;
  const ICON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 12V5a1.5 1.5 0 0 1 3 0v6-8a1.5 1.5 0 0 1 3 0v8-6a1.5 1.5 0 0 1 3 0v7-4a1.5 1.5 0 0 1 3 0v6c0 5-3 7-7 7-3 0-5-2-6-4l-3-5a1.5 1.5 0 0 1 2.5-1.6L8 12Z"/></svg>';
  function styles(){if(document.getElementById('hands-style'))return;const s=document.createElement('style');s.id='hands-style';s.textContent='.hb-hands{display:inline-flex;align-items:center;gap:5px}.hb-hands svg{width:17px;height:17px}.hb-hands i{width:6px;height:6px;border-radius:50%;background:var(--text-faint);display:inline-block}.hb-hands.live i{background:var(--accent);box-shadow:0 0 5px var(--accent)}.hb-hands.live{border-color:var(--cyan);color:var(--cyan)}.hands-overlay{position:fixed;inset:0;pointer-events:none;z-index:54}.hands-legend,.hands-status{position:fixed;z-index:55;pointer-events:none;max-width:min(520px,calc(100vw - 32px));padding:10px 14px;border:1px solid var(--border-dim);border-radius:9px;background:rgba(8,12,40,.96);color:var(--text);font:11px/1.8 Orbitron,monospace}.hands-legend{left:16px;bottom:calc(22px + env(safe-area-inset-bottom));transition:opacity .3s}.hands-status{left:16px;top:calc(12px + env(safe-area-inset-top));color:var(--cyan);font-size:10px}.hands-setup{position:fixed;inset:auto;left:50%;top:50%;transform:translate(-50%,-50%);z-index:95;box-sizing:border-box;width:min(460px,calc(100vw - 28px));padding:20px;border:1px solid var(--accent);border-radius:12px;background:#080c28;color:var(--text);font:12px/1.8 Orbitron,monospace;box-shadow:0 14px 50px #0009}.hands-setup button{margin:8px 6px 0 0}.hands-setup p{font-family:Outfit,system-ui,sans-serif;font-size:14px}.hands-legend[hidden],.hands-status[hidden],.hands-setup[hidden]{display:none!important}@media(prefers-reduced-motion:reduce){.hands-legend{transition:none}}';document.head.appendChild(s);}
  function mount({host,bar,fitButton}){
    styles();
    let typedAt=-Infinity,lastAction=-Infinity,alive=true,enabled=false,canvas=null,ctx=null,legend=null,status=null,legendTimer=0,used=false,zooming=false,interlock=false,cooldown=0,diagnostic=false,measurementLabel='MEASURING',hint='',hintAt=0,calibration=null;
    let profile={v:PROFILE_VERSION,fist:false,orbit:true};
    try{const saved=JSON.parse(localStorage.getItem('hub-hands-profile')||'null');if(saved&&saved.v===PROFILE_VERSION)profile={...profile,...saved};}catch(_){}      // an older profile was measured in other units: start again
    const engine=new G.Engine({}),detected=new Set(),presses=new Map(),btn=document.createElement('button');
    btn.type='button';btn.className='hb-btn hb-hands';btn.innerHTML=ICON+'<span>HANDS</span><i aria-hidden="true"></i>';btn.title='Optional local webcam hand control';btn.setAttribute('aria-pressed','false');bar.appendChild(btn);
    const setup=document.createElement('section');setup.className='hands-setup';setup.hidden=true;setup.setAttribute('role','dialog');setup.setAttribute('aria-label','Set up hand control');document.body.appendChild(setup);
    const configure=document.createElement('button');configure.type='button';configure.className='hb-btn';configure.textContent='HAND SETUP';configure.onclick=()=>calibrationPanel();bar.appendChild(configure);
    const fresh=()=>({frames:0,handFrames:0,pinches:0,detectedPinches:0,clicks:0,rclicks:0,orbits:0,zooms:0,fits:0,latencies:[],cameraLatencies:[]});
    let counts=fresh();

    // ---- what a hand is over: the board's own elements, and inside a block's frame when it is one of our own pages
    function resolve(x,y){
      const e=document.elementFromPoint(x,y);if(!e||!host.contains(e))return null;
      const fr=e.tagName==='IFRAME'?e:e.closest('iframe');
      if(!fr)return {el:e,k:1,ox:0,oy:0};
      try{const d=fr.contentDocument;if(!d)return null;const r=fr.getBoundingClientRect(),k=(r.width/(fr.clientWidth||r.width))||1,inner=d.elementFromPoint((x-r.left)/k,(y-r.top)/k);return inner?{el:inner,k,ox:r.left,oy:r.top}:null;}
      catch(_){return null;}                                                  // a page from another origin cannot be reached, and is left alone
    }
    function emit(p,type,id,x,y,pressed){
      const w=p.target.ownerDocument.defaultView||window,b=p.button;
      p.target.dispatchEvent(new w.PointerEvent(type,{bubbles:true,cancelable:true,composed:true,pointerId:9000+id,pointerType:'touch',isPrimary:id===0,clientX:(x-p.ox)/p.k,clientY:(y-p.oy)/p.k,button:type==='pointermove'?-1:b,buttons:pressed?(b===2?2:1):0,pressure:pressed?.5:0}));
    }
    const posOf=(p,hand)=>({x:p.down.x+(hand.palm.x-p.palm0.x)+(p.mode==='orbit'?(hand.roll-p.roll0)*ROLL_PX:0),y:p.down.y+(hand.palm.y-p.palm0.y)});
    function begin(id,hand,mode){
      const from=mode==='zoom'||mode==='orbit'?hand.palm:{x:hand.aimX,y:hand.aimY};
      const r=mode==='zoom'||mode==='orbit'?{el:host,k:1,ox:0,oy:0}:resolve(from.x,from.y);if(!r)return false;
      const p={target:r.el,k:r.k,ox:r.ox,oy:r.oy,mode,button:mode==='right'||mode==='orbit'?2:0,down:{x:from.x,y:from.y},last:{x:from.x,y:from.y},palm0:{...hand.palm},roll0:hand.roll,travel:0};
      presses.set(id,p);emit(p,'pointerdown',id,from.x,from.y,true);counts.pinches++;if(mode==='orbit')counts.orbits++;lastAction=performance.now();firstPinch();return true;
    }
    function release(id,cancel=true,hand){
      const p=presses.get(id);if(!p)return;const at=hand?posOf(p,hand):p.last;
      emit(p,cancel?'pointercancel':'pointerup',id,at.x,at.y,false);
      if(!cancel&&(p.mode==='left'||p.mode==='right')&&G.isClick(p.down,at,p.travel)){
        const now=resolve(at.x,at.y);
        if(now&&now.el===p.target){const w=p.target.ownerDocument.defaultView||window,o={bubbles:true,cancelable:true,composed:true,clientX:(at.x-p.ox)/p.k,clientY:(at.y-p.oy)/p.k};
          if(p.mode==='left'){p.target.dispatchEvent(new w.MouseEvent('click',{...o,detail:1}));counts.clicks++;}
          else{p.target.dispatchEvent(new w.MouseEvent('contextmenu',{...o,button:2}));counts.rclicks++;}}
      }
      presses.delete(id);lastAction=performance.now();
    }
    function cancelAll(){for(const id of [...presses.keys()])release(id,true);zooming=false;}
    const view3d=()=>{try{return root.__hubBoard.active.view().mode()==='3d';}catch(_){return false;}};

    // ---- what is drawn: the skeleton, the three working fingertips, and a line from the thumb that fills as a pinch closes
    function showOverlay(){if(canvas)return;canvas=document.createElement('canvas');canvas.className='hands-overlay';canvas.setAttribute('aria-hidden','true');document.body.appendChild(canvas);ctx=canvas.getContext('2d');
      legend=document.createElement('div');legend.className='hands-legend';legend.textContent='THUMB + INDEX: click, drag a title or the background · THUMB + MIDDLE: right click · FIST in VIEW 3D: tilt and turn · TWO INDEX PINCHES: zoom · OPEN HAND 1s: fit · ESC: camera off';document.body.appendChild(legend);
      status=document.createElement('div');status.className='hands-status';status.setAttribute('role','status');status.textContent='CAMERA ON · LOCAL HAND CONTROL';document.body.appendChild(status);}
    function clearOverlay(){clearTimeout(legendTimer);legendTimer=0;canvas?.remove();legend?.remove();status?.remove();canvas=ctx=legend=status=null;}
    function paint(hands){
      if(!canvas)return;const dpr=Math.min(1.5,devicePixelRatio||1),w=innerWidth,h=innerHeight;
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
      for(const hand of hands){
        ctx.strokeStyle='#41ebff';ctx.lineWidth=1.2;ctx.globalAlpha=.55;ctx.beginPath();for(const [a,b]of G.BONES){ctx.moveTo(hand.points[a].x,hand.points[a].y);ctx.lineTo(hand.points[b].x,hand.points[b].y);}ctx.stroke();ctx.globalAlpha=1;
        const T=hand.points[4],I=hand.points[8],M=hand.points[12];
        for(const [tip,close,on,color,label] of [[I,hand.closeness,hand.pinched,'#00e676','L'],[M,hand.closenessM,hand.rpinched,'#f5c842','R']]){
          ctx.strokeStyle=color;ctx.lineWidth=1+4*close;ctx.globalAlpha=.35+.65*close;ctx.beginPath();ctx.moveTo(T.x,T.y);ctx.lineTo(tip.x,tip.y);ctx.stroke();
          ctx.globalAlpha=1;ctx.fillStyle=on?color:'rgba(8,12,40,.9)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(tip.x,tip.y,on?8:6,0,Math.PI*2);ctx.fill();ctx.stroke();
          ctx.fillStyle=on?'#080c28':color;ctx.font='700 9px Orbitron,monospace';ctx.textAlign='center';ctx.fillText(label,tip.x,tip.y+3);
        }
        ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(T.x,T.y,5,0,Math.PI*2);ctx.fill();
        ctx.strokeStyle=hand.gesture==='fist'?'#ff9d3b':'#41ebff';ctx.lineWidth=1.6;ctx.beginPath();ctx.arc(hand.palm.x,hand.palm.y,hand.gesture==='fist'?16:4,0,Math.PI*2);ctx.stroke();
      }
    }
    function firstPinch(){if(used)return;used=true;legendTimer=setTimeout(()=>{if(legend)legend.style.opacity='0';},4000);}
    const say=(m)=>{hint=m;hintAt=performance.now();};

    // ---- one frame in
    function feed(result,now=performance.now(),meta={}){
      if(!enabled||!alive)return;const processingAt=performance.now();
      const output=engine.update(result,now,innerWidth,innerHeight,meta.cam);if(output.stale)return;counts.frames++;paint(output.hands);
      for(const h of output.hands){const on=h.pinched||h.rpinched;if(on&&!detected.has(h.id)){detected.add(h.id);counts.detectedPinches++;}if(!on)detected.delete(h.id);}
      for(const h of output.lost)detected.delete(h.id);
      counts.latencies.push(performance.now()-(Number.isFinite(meta.inferenceMs)?now:processingAt));if(Number.isFinite(meta.captureTime))counts.cameraLatencies.push(performance.now()-meta.captureTime);
      if(counts.latencies.length>1800)counts.latencies.shift();if(counts.cameraLatencies.length>1800)counts.cameraLatencies.shift();
      if(output.hands.length)counts.handFrames++;
      if(status&&output.hands[0]&&performance.now()-hintAt>2500){const h=output.hands[0];status.textContent=(diagnostic?measurementLabel+' · ACTIONS PAUSED':'CAMERA ON')+' · L '+h.gap.toFixed(2)+' · R '+h.gapM.toFixed(2)+' (press below '+engine.tuning.pinchOn.toFixed(2)+')';}
      else if(status&&hint&&performance.now()-hintAt<=2500)status.textContent=hint;
      for(const lost of output.lost)release(lost.id,true);
      if(calibration){cancelAll();const h=output.hands[0];
        if(h&&output.hands.length===1){calibration.samples.push(h.gap);
          if(now-calibration.at>=2000&&calibration.samples.length>=25){const a=calibration.samples.slice().sort((x,y)=>x-y),v=a[Math.floor(a.length/2)];
            if(calibration.phase==='open'){calibration.open=v;calibration.phase='closed';calibration.samples=[];calibration.at=now;calibration.message.textContent='Now touch your thumb to your index fingertip and hold for two seconds.';}
            else{const open=calibration.open,closed=v;if(open-closed>.2){profile.pinchOn=closed+(open-closed)*.3;profile.pinchOff=closed+(open-closed)*.65;saveProfile();calibration.message.textContent='Calibration saved in this browser. Close this panel to resume.';}else calibration.message.textContent='Samples were too similar. Please restart calibration.';calibration=null;}}
        }else if(calibration){calibration.samples=[];calibration.at=now;}return;}
      if(diagnostic)return;
      if(interlock){if(!output.hands.some(h=>h.pinched||h.rpinched)&&now>=cooldown)interlock=false;else return;}
      if(output.zoom){
        if(!zooming){cancelAll();zooming=true;counts.zooms++;for(const hand of output.hands)begin(hand.id,hand,'zoom');}
        for(const hand of output.hands){const p=presses.get(hand.id);if(p){const at=posOf(p,hand);p.last=at;emit(p,'pointermove',hand.id,at.x,at.y,true);}}
        return;}
      if(zooming){cancelAll();interlock=true;return;}
      if(output.fit&&!presses.size&&now-typedAt>3000&&performance.now()-lastAction>2500){fitButton.click();counts.fits++;}
      for(const hand of output.hands){
        const p=presses.get(hand.id);
        if(p){
          const done=p.mode==='left'?!hand.pinched:p.mode==='right'?!hand.rpinched:hand.gesture!=='fist'&&!hand.pinched&&!hand.rpinched;
          if(done){release(hand.id,false,hand);continue;}
          const at=posOf(p,hand);p.travel=Math.max(p.travel,G.distance(p.down,at));p.last=at;emit(p,'pointermove',hand.id,at.x,at.y,true);
        }else if(hand.pinched)begin(hand.id,hand,'left');
        else if(hand.rpinched)begin(hand.id,hand,'right');
        else if(profile.orbit&&hand.gesture==='fist'){if(view3d())begin(hand.id,hand,'orbit');else say('FIST TILTS THE BOARD IN VIEW 3D: choose VIEW, then 3D');}
        else{const r=resolve(hand.x,hand.y);if(r)emit({target:r.el,k:r.k,ox:r.ox,oy:r.oy,button:0},'pointermove',hand.id,hand.x,hand.y,false);}
      }
    }
    function stopped(reason){enabled=false;btn.classList.remove('live');btn.setAttribute('aria-pressed','false');btn.title='Hand control off: '+reason;cancelAll();calibration=null;diagnostic=false;engine.reset();detected.clear();clearOverlay();}
    const tracker=root.HubHandsTracker.create({onFrame:feed,onStop:stopped,onState(s){if(s.enabled){enabled=true;showOverlay();btn.classList.add('live');btn.setAttribute('aria-pressed','true');}btn.setAttribute('aria-busy',String(s.loading));btn.title=s.error||('Hand control '+s.reason);},...(root.__HUB_HANDS_TEST?.tracker||{})});

    // ---- setup: nothing to save by hand; a choice or a calibration is kept in this browser at once
    function saveProfile(){cancelAll();engine.reset();engine.options.fistGrab=!!profile.fist;engine.tuning.pinchOn=G.TUNING.pinchOn;engine.tuning.pinchOff=G.TUNING.pinchOff;
      if(Number.isFinite(profile.pinchOn)&&profile.pinchOn>.05&&profile.pinchOff>profile.pinchOn&&profile.pinchOff<1.2){engine.tuning.pinchOn=profile.pinchOn;engine.tuning.pinchOff=profile.pinchOff;}
      profile.v=PROFILE_VERSION;try{localStorage.setItem('hub-hands-profile',JSON.stringify(profile));}catch(_){}interlock=true;}
    saveProfile();
    function calibrationPanel(){
      cancelAll();diagnostic=true;setup.replaceChildren();setup.hidden=false;
      const title=document.createElement('strong');title.textContent='HAND CONTROLS';const p=document.createElement('p');
      p.textContent='Thumb to index fingertip: left click, drag. Thumb to middle fingertip: right click. Closed fist in VIEW 3D: tilt and turn. Choices here are saved in this browser the moment you make them, and the defaults need no calibration.';setup.append(title,p);
      const mk=(text,fn)=>{const b=document.createElement('button');b.className='hb-btn';b.type='button';b.textContent=text;b.onclick=fn;setup.append(b);return b;};
      mk('FIST TILTS 3D: '+(profile.orbit?'ON':'OFF'),()=>{profile.orbit=!profile.orbit;saveProfile();calibrationPanel();});
      mk('FIST CONTINUES DRAG: '+(profile.fist?'ON':'OFF'),()=>{profile.fist=!profile.fist;saveProfile();calibrationPanel();});
      mk('CALIBRATE PINCH',()=>{if(!enabled){p.textContent='Close setup, turn HANDS on explicitly, then return here to calibrate.';return;}calibration={phase:'open',at:performance.now(),samples:[],message:p};p.textContent='Hold one hand steady, thumb away from your index fingertip, for two seconds. Board actions are paused.';});
      mk('RESET TO DEFAULTS',()=>{profile={v:PROFILE_VERSION,fist:false,orbit:true};saveProfile();calibrationPanel();});
      mk('CLOSE',()=>{calibration=null;diagnostic=false;engine.reset();interlock=true;setup.hidden=true;});
    }
    function setupPanel(manifest){
      setup.replaceChildren();setup.hidden=false;const title=document.createElement('strong');title.textContent=manifest.ready?'HAND CONTROL READY':'HAND TRACKING NOT INSTALLED';
      const p=document.createElement('p');p.textContent=manifest.ready?'Processing stays on this device. Start only when you want the webcam on.':'Download MediaPipe Tasks Vision 1.2.2 and hand_landmarker.task once (about 18 MB download, 38 MB stored). Files stay in the Hub state folder. No camera opens during download.';setup.append(title,p);
      const action=document.createElement('button'),close=document.createElement('button');action.type=close.type='button';action.className=close.className='hb-btn';close.textContent='CLOSE';close.onclick=()=>setup.hidden=true;
      action.textContent=manifest.ready?'START HAND CONTROL':'DOWNLOAD HAND TRACKING';
      action.onclick=async()=>{if(manifest.ready){setup.hidden=true;await tracker.start();return;}action.disabled=true;action.textContent='DOWNLOADING...';
        try{const r=await fetch('/api/hands/install',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});if(!r.ok)throw Error('Download failed. Try again.');setupPanel(await r.json());}
        catch(e){p.textContent=e.message;action.disabled=false;action.textContent='RETRY DOWNLOAD';}};
      setup.append(action,close);action.focus();
    }
    btn.onclick=async()=>{if(tracker.stats.enabled||tracker.stats.loading){tracker.stop('HANDS off');return;}used=false;engine.reset();interlock=false;
      try{const r=await fetch('/api/hands/status',{cache:'no-store'});if(!r.ok)throw Error('Hand control unavailable');const s=await r.json();if(!alive)return;if(!s.ready)setupPanel(s);else await tracker.start();}
      catch(e){btn.title=e.message;setupPanel({ready:false});}};
    function physical(e){if(!enabled||!e.isTrusted||e.pointerId>=9000)return;cancelAll();engine.reset();interlock=true;cooldown=performance.now()+1000;}
    function escape(e){if(e.key==='Escape'&&(tracker.stats.enabled||tracker.stats.loading)){tracker.stop('Escape');e.preventDefault();}if(e.key==='Escape'){setup.hidden=true;calibration=null;diagnostic=false;}}
    const typing=e=>{if(e.isTrusted&&e.key!=='Escape')typedAt=performance.now();};
    document.addEventListener('pointerdown',physical,true);document.addEventListener('wheel',physical,{capture:true,passive:true});document.addEventListener('keydown',escape,true);document.addEventListener('keydown',typing,true);
    const api={button:btn,tracker,feed,
      stats(){const l=counts.latencies;return {...counts,latencies:l.slice(),cameraLatencies:counts.cameraLatencies.slice(),tracker:{...tracker.stats},presses:presses.size};},
      measure(on,label){diagnostic=!!on;measurementLabel=label||'MEASURING';counts=fresh();cancelAll();},
      destroy(){alive=false;tracker.destroy();cancelAll();clearOverlay();setup.remove();btn.remove();configure.remove();document.removeEventListener('pointerdown',physical,true);document.removeEventListener('wheel',physical,true);document.removeEventListener('keydown',escape,true);document.removeEventListener('keydown',typing,true);if(root.__hubHands===api)root.__hubHands=null;}};
    if(root.__HUB_HANDS_TEST)api.testEnable=()=>{enabled=true;engine.reset();showOverlay();};
    root.__hubHands=api;return api;
  }
  root.HubHandsBoard={mount};
})(window);
