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
(function(root){
  'use strict';
  function create(options={}){
    const clock=options.clock||(()=>performance.now()),idleMs=options.idleMs||60000;
    let generation=0,model=null,video=null,stream=null,callback=0,callbackKind='',watchdog=0,pending=null,lastHand=0,lastFrame=-1,stamp=0;
    const stats={enabled:false,loading:false,frames:0,handCount:0,inferenceMs:0,callbackToPointerMs:0,captureToPointerMs:null,delegate:'',error:'',reason:'off',callbacks:0};
    const stopHooks=root.__hubMediaStops||(root.__hubMediaStops=new Set());
    const report=()=>options.onState?.({...stats});
    function stop(reason='off'){
      ++generation;stats.enabled=stats.loading=false;stats.reason=reason;
      if(callback&&video&&callbackKind==='video')video.cancelVideoFrameCallback(callback);else if(callback)cancelAnimationFrame(callback);
      callback=0;stats.callbacks=0;clearTimeout(watchdog);watchdog=0;
      if(video){video.pause();video.srcObject=null;video.remove();video=null;}
      if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
      if(model){try{model.close();}catch(e){}model=null;}
      pending=null;lastFrame=-1;options.onStop?.(reason);report();
    }
    const release=()=>stop('view released');stopHooks.add(release);
    function idleCheck(mine){if(mine!==generation||!stats.enabled)return;const remaining=idleMs-(clock()-lastHand);if(remaining<=0){stop('No hand for 60 seconds');return;}watchdog=setTimeout(()=>idleCheck(mine),remaining);}
    async function makeModel(manifest){
      if(options.factory)return options.factory(manifest);
      const runtime=await import(manifest.runtime_url),files=await runtime.FilesetResolver.forVisionTasks(manifest.wasm_url);
      const config={runningMode:'VIDEO',numHands:2,minHandDetectionConfidence:.5,minHandPresenceConfidence:.5,minTrackingConfidence:.5};
      try{const m=await runtime.HandLandmarker.createFromOptions(files,{...config,baseOptions:{modelAssetPath:manifest.model_url,delegate:'GPU'}});stats.delegate='GPU';return m;}
      catch(error){stats.delegate='CPU';return runtime.HandLandmarker.createFromOptions(files,{...config,baseOptions:{modelAssetPath:manifest.model_url,delegate:'CPU'}});}
    }
    function schedule(mine){if(mine!==generation||!video||!stats.enabled)return;stats.callbacks=1;if(video.requestVideoFrameCallback){callbackKind='video';callback=video.requestVideoFrameCallback((now,meta)=>tick(mine,now,meta));}else{callbackKind='raf';callback=requestAnimationFrame(now=>tick(mine,now,{}));}}
    function tick(mine,now,meta){
      callback=0;stats.callbacks=0;if(mine!==generation||!stats.enabled||!video)return;
      if(document.hidden){stop('page hidden');return;}
      if(video.readyState<2||video.currentTime===lastFrame){schedule(mine);return;}lastFrame=video.currentTime;
      const begun=clock();stamp=Math.max(stamp+1,begun);
      try{
        const result=model.detectForVideo(video,stamp);stats.inferenceMs=clock()-begun;stats.frames++;
        stats.handCount=result.landmarks?.length||0;if(stats.handCount)lastHand=clock();
        options.onFrame?.(result,begun,{captureTime:meta.captureTime,mediaTime:meta.mediaTime,inferenceMs:stats.inferenceMs});
        stats.callbackToPointerMs=clock()-begun;stats.captureToPointerMs=Number.isFinite(meta.captureTime)?clock()-meta.captureTime:null;
        if(stats.frames%15===0)report();
      }catch(error){stats.error=String(error.message||error);stop('tracking failed');return;}
      if(clock()-lastHand>=idleMs){stop('No hand for 60 seconds');return;}schedule(mine);
    }
    function start(){
      if(stats.enabled)return Promise.resolve(true);if(pending)return pending;
      const mine=++generation;stats.loading=true;stats.error='';stats.reason='loading';report();
      pending=(async()=>{
        let acquired=null,built=null;
        try{
          const manifest=options.manifest||await(await fetch('/api/hands/status',{cache:'no-store'})).json();
          if(!manifest.ready)throw Error('Download hand tracking first');
          built=await makeModel(manifest);if(mine!==generation){built.close();return false;}model=built;
          acquired=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:30,max:30},facingMode:'user'},audio:false});
          if(mine!==generation){acquired.getTracks().forEach(t=>t.stop());return false;}
          stream=acquired;video=document.createElement('video');video.muted=true;video.autoplay=true;video.playsInline=true;video.style.cssText='position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;left:0;top:0';document.body.appendChild(video);video.srcObject=stream;await video.play();
          if(mine!==generation)return false;
          stats.enabled=true;stats.loading=false;stats.reason='on';lastHand=clock();watchdog=setTimeout(()=>idleCheck(mine),idleMs);report();schedule(mine);return true;
        }catch(error){if(mine===generation){stats.error=String(error.message||error);stop('could not start');}else acquired?.getTracks().forEach(t=>t.stop());return false;}
        finally{if(mine===generation)pending=null;}
      })();return pending;
    }
    const hidden=()=>{if(document.hidden)stop('page hidden');};const pagehide=()=>stop('page left');document.addEventListener('visibilitychange',hidden);addEventListener('pagehide',pagehide);
    return {start,stop,stats,tracks:()=>stream?.getTracks()||[],destroy(){stop('board removed');stopHooks.delete(release);document.removeEventListener('visibilitychange',hidden);removeEventListener('pagehide',pagehide);}};
  }
  root.HubHandsTracker={create};
})(window);
