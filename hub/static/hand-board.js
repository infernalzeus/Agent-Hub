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
    const saveBtn=document.createElement('button');saveBtn.type='button';saveBtn.className='hb-btn';saveBtn.textContent='SAVE TRACE';saveBtn.hidden=true;saveBtn.title='Save the last minute of hand numbers (no pictures) so Claude can look at what happened';saveBtn.onclick=()=>saveTrace('free',null);bar.appendChild(saveBtn);
    const fresh=()=>({frames:0,handFrames:0,pinches:0,detectedPinches:0,clicks:0,rclicks:0,orbits:0,zooms:0,zoom1:0,fits:0,latencies:[],cameraLatencies:[]});
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
      if(mode==='orbit'||mode==='zoom1'){presses.set(id,{mode,prev:{...hand.palm},roll:hand.roll,at:{x:hand.x,y:hand.y},travel:0});if(mode==='orbit')counts.orbits++;else counts.zoom1++;mark('begin-'+mode);lastAction=performance.now();firstPinch();return true;}
      const from=mode==='zoom'?hand.palm:{x:hand.aimX,y:hand.aimY};
      const r=mode==='zoom'?{el:host,k:1,ox:0,oy:0}:resolve(from.x,from.y);if(!r){mark('no-target',{mode});return false;}
      const p={target:r.el,k:r.k,ox:r.ox,oy:r.oy,mode,button:mode==='right'?2:0,down:{x:from.x,y:from.y},last:{x:from.x,y:from.y},palm0:{...hand.palm},roll0:hand.roll,travel:0};
      presses.set(id,p);emit(p,'pointerdown',id,from.x,from.y,true);counts.pinches++;mark('begin-'+mode,{x:Math.round(from.x),y:Math.round(from.y),target:String(r.el.className||r.el.tagName).slice(0,30)});lastAction=performance.now();firstPinch();return true;
    }
    function release(id,cancel=true,hand){
      const p=presses.get(id);if(!p)return;
      if(p.mode==='orbit'||p.mode==='zoom1'){presses.delete(id);mark('end-'+p.mode);lastAction=performance.now();return;}
      const at=hand?posOf(p,hand):p.last;
      emit(p,cancel?'pointercancel':'pointerup',id,at.x,at.y,false);
      let how=cancel?'cancelled':'drag';
      if(!cancel&&(p.mode==='left'||p.mode==='right')&&G.isClick(p.down,at,p.travel,slop())){
        const now=resolve(at.x,at.y);how='click-missed';
        if(now&&now.el===p.target){const w=p.target.ownerDocument.defaultView||window,o={bubbles:true,cancelable:true,composed:true,clientX:(at.x-p.ox)/p.k,clientY:(at.y-p.oy)/p.k};
          if(p.mode==='left'){p.target.dispatchEvent(new w.MouseEvent('click',{...o,detail:1}));counts.clicks++;how='click';}
          else{p.target.dispatchEvent(new w.MouseEvent('contextmenu',{...o,button:2}));counts.rclicks++;how='contextmenu';}}
      }
      mark('end-'+p.mode,{how,travel:Math.round(p.travel),slop:slop()});
      presses.delete(id);lastAction=performance.now();
    }
    function cancelAll(){for(const id of [...presses.keys()])release(id,true);zooming=false;}

    // ---- what is drawn: the skeleton, the three working fingertips, and a line from the thumb that fills as a pinch closes
    function showOverlay(){if(canvas)return;canvas=document.createElement('canvas');canvas.className='hands-overlay';canvas.setAttribute('aria-hidden','true');document.body.appendChild(canvas);ctx=canvas.getContext('2d');
      legend=document.createElement('div');legend.className='hands-legend';legend.textContent='THUMB + INDEX: left click, drag · THUMB + MIDDLE: right click · THUMB + INDEX + MIDDLE together, hand up or down: zoom · FIST in VIEW 3D: tilt and turn · OPEN HAND 1s: fit · ESC: camera off';document.body.appendChild(legend);
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
      if(!enabled||!alive)return;
      if(!document.hasFocus()||document.hidden){if(presses.size)cancelAll();if(status&&!hint)status.textContent='CLICK THE HUB WINDOW ONCE SO HANDS CAN ACT ON IT';else if(status)say('CLICK THE HUB WINDOW ONCE SO HANDS CAN ACT ON IT');return;}
      const processingAt=performance.now();
      const output=engine.update(result,now,innerWidth,innerHeight,meta.cam);if(output.stale)return;counts.frames++;paint(output.hands);
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
      if(output.fit&&!presses.size&&now-typedAt>3000&&performance.now()-lastAction>2500){fitButton.click();counts.fits++;}
      for(const hand of output.hands){
        let p=presses.get(hand.id);
        // thumb, index and middle together: one-hand zoom. A press that began on the way there is cancelled, never completed as a click.
        if(hand.triple&&(!p||p.mode!=='zoom1')){if(p)release(hand.id,true);begin(hand.id,hand,'zoom1');continue;}
        if(p){
          if(p.mode==='zoom1'){
            if(!hand.triple){release(hand.id,false);continue;}
            const dy=hand.palm.y-p.prev.y;p.prev={...hand.palm};
            if(dy)host.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:dy*2.2,deltaMode:0,clientX:p.at.x,clientY:p.at.y}));      // hand up zooms in, down zooms out
            continue;
          }
          if(p.mode==='orbit'){
            if(hand.gesture!=='fist'||hand.pinched||hand.rpinched||hand.triple){release(hand.id,false);continue;}
            const v=boardView();if(v)v.orbitBy((hand.palm.x-p.prev.x)+(hand.roll-p.roll)*ROLL_PX,hand.palm.y-p.prev.y);p.prev={...hand.palm};p.roll=hand.roll;continue;
          }
          const done=p.mode==='left'?!hand.pinched:!hand.rpinched;
          if(done){release(hand.id,false,hand);continue;}
          const at=posOf(p,hand);p.travel=Math.max(p.travel,G.distance(p.down,at));p.last=p.travel<slop()?p.down:at;emit(p,'pointermove',hand.id,p.last.x,p.last.y,true);
        }else if(hand.pinched)begin(hand.id,hand,'left');
        else if(hand.rpinched)begin(hand.id,hand,'right');
        else if(profile.orbit&&hand.gesture==='fist'&&hand.sincePinch>700){const v=boardView();if(v&&v.mode()==='3d')begin(hand.id,hand,'orbit');else say('FIST TILTS THE BOARD IN VIEW 3D: choose VIEW, then 3D');}
        else{const r=resolve(hand.x,hand.y);if(r)emit({target:r.el,k:r.k,ox:r.ox,oy:r.oy,button:0},'pointermove',hand.id,hand.x,hand.y,false);}
      }
    }
    function stopped(reason){enabled=false;saveBtn.hidden=true;btn.classList.remove('live');btn.setAttribute('aria-pressed','false');btn.title='Hand control off: '+reason;cancelAll();calibration=null;diagnostic=false;engine.reset();detected.clear();clearOverlay();}
    const tracker=root.HubHandsTracker.create({onFrame:feed,onStop:stopped,onState(s){saveBtn.hidden=!s.enabled;if(s.enabled){enabled=true;showOverlay();btn.classList.add('live');btn.setAttribute('aria-pressed','true');}btn.setAttribute('aria-busy',String(s.loading));btn.title=s.error||('Hand control '+s.reason);},...(root.__HUB_HANDS_TEST?.tracker||{})});

    // ---- numbers only: the last minute of what the camera saw and what the engine and the board did, kept in memory while HANDS is on and saved when asked
    const STEPS=[['relaxed','Rest your hand, relaxed, fingers loose'],['point','Point at the screen with your index finger, other fingers curled'],['open','Open hand, fingers spread'],
      ['pinch_index','Pinch thumb to INDEX fingertip, hold a second, release: three times'],['pinch_middle','Pinch thumb to MIDDLE fingertip, hold, release: three times'],
      ['fist','Make a FIST, hold, then open: twice'],['three_together','Bring thumb, index and middle together, then spread them: three times'],['rest','Rest your hand again, relaxed']];
    const ring=[],events=[],rd=v=>Math.round(v*1000)/1000;let guided=null,lastRingAt=-1e9;
    function mark(ev,extra){events.push({t:Math.round(performance.now()),ev,...(extra||{})});if(events.length>500)events.shift();}
    function ringFrame(output,result,now){
      if(now-lastRingAt<66)return;lastRingAt=now;
      ring.push({t:Math.round(performance.now()),step:guided?guided.step():'',hands:output.hands.map((h,k)=>({gesture:h.gesture,pinched:h.pinched,rpinched:h.rpinched,triple:h.triple,gap:rd(h.gap),gapM:rd(h.gapM),roll:rd(h.roll),
        sincePinch:Math.min(99999,Math.round(h.sincePinch)),lm:(result.landmarks[k]||[]).map(q=>[rd(q.x),rd(q.y),rd(q.z||0)])}))});
      if(ring.length>900)ring.shift();
    }
    async function saveTrace(kind,message){
      const v=boardView();
      try{const x=await fetch('/api/hands/trace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,trace:{version:3,kind,screen:[innerWidth,innerHeight],view:v?v.mode():'',
          tuning:{on:engine.tuning.pinchOn,off:engine.tuning.pinchOff},steps:STEPS.map(z=>z[0]),frames:ring.slice(),events:events.slice()}})});
        if(!x.ok)throw Error('not saved');const j=await x.json();say('TRACE SAVED: '+j.saved+' ('+Math.round(j.bytes/1024)+' KB). Tell Claude it is there.');if(message)message.textContent='Saved '+j.saved+' in the Hub data folder: only numbers, no pictures. Tell Claude it is there.';}
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
    function saveProfile(){cancelAll();engine.reset();engine.options.fistGrab=!!profile.fist;engine.tuning.pinchOn=G.TUNING.pinchOn;engine.tuning.pinchOff=G.TUNING.pinchOff;
      if(Number.isFinite(profile.pinchOn)&&profile.pinchOn>.05&&profile.pinchOff>profile.pinchOn&&profile.pinchOff<1.2){engine.tuning.pinchOn=profile.pinchOn;engine.tuning.pinchOff=profile.pinchOff;}
      profile.v=PROFILE_VERSION;try{localStorage.setItem('hub-hands-profile',JSON.stringify(profile));}catch(_){}interlock=true;}
    saveProfile();
    function calibrationPanel(){
      cancelAll();diagnostic=true;setup.replaceChildren();setup.hidden=false;
      const title=document.createElement('strong');title.textContent='HAND CONTROLS';const p=document.createElement('p');
      p.textContent='Thumb + index: left click, drag. Thumb + middle: right click. Thumb + index + middle together, hand up or down: zoom. Fist in VIEW 3D: tilt and turn. Choices save here at once; the defaults need no calibration.';setup.append(title,p);
      const mk=(text,fn)=>{const b=document.createElement('button');b.className='hb-btn';b.type='button';b.textContent=text;b.onclick=fn;setup.append(b);return b;};
      mk('FIST TILTS 3D: '+(profile.orbit?'ON':'OFF'),()=>{profile.orbit=!profile.orbit;saveProfile();calibrationPanel();});
      mk('SAVE LAST MINUTE',()=>{if(!enabled){p.textContent='Turn HANDS on, use your hands for a minute, then come back here (or press SAVE TRACE in the bar).';return;}saveTrace('free',p);});
      mk('RECORD HAND TRACE',()=>{if(!enabled){p.textContent='Close setup, turn HANDS on explicitly, then return here to record.';return;}p.textContent='Recording about 32 seconds. Follow the prompts at the top left; this panel closes so you can see them.';setup.hidden=true;startTrace(p);});
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
      startTrace,stats(){const l=counts.latencies;return {...counts,latencies:l.slice(),cameraLatencies:counts.cameraLatencies.slice(),tracker:{...tracker.stats},presses:presses.size};},
      measure(on,label){diagnostic=!!on;measurementLabel=label||'MEASURING';counts=fresh();cancelAll();},
      destroy(){alive=false;tracker.destroy();cancelAll();clearOverlay();setup.remove();btn.remove();configure.remove();saveBtn.remove();document.removeEventListener('pointerdown',physical,true);document.removeEventListener('wheel',physical,true);document.removeEventListener('keydown',escape,true);document.removeEventListener('keydown',typing,true);if(root.__hubHands===api)root.__hubHands=null;}};
    if(root.__HUB_HANDS_TEST)api.testEnable=()=>{enabled=true;engine.reset();showOverlay();};
    root.__hubHands=api;return api;
  }
  root.HubHandsBoard={mount};
})(window);
