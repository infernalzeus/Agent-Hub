/* Native-page Depth Lift: one renderer and clock for the complete turn.
 * A prepared same-origin destination is revealed through matching cube-face clips.
 * A confirmed destination is retained after the turn; no second page load.
 * Free Scatter: independent cell timing, 70% spread, two-cell lift, 2000ms.
 * No DOM painter, JPEG, stored poster or project state is used.
 */
(function(){'use strict';
 if(window.DepthLift&&DepthLift.build==='__DL_BUILD__'&&!DepthLift.disposed)return;
 if(window.DepthLift&&DepthLift.dispose)DepthLift.dispose();
 var hostTasks=window.__hubNativeTasks;var nativeRAF=(hostTasks?hostTasks.raf:window.requestAnimationFrame).bind(window),nativeCancel=(hostTasks?hostTasks.cancel:window.cancelAnimationFrame).bind(window),hostTimeout=(hostTasks?hostTasks.timeout:window.setTimeout).bind(window),hostClear=(hostTasks?hostTasks.clearT:window.clearTimeout).bind(window);
 var BUILD='__DL_BUILD__',FLAG='agenthub:depth-lift:v2',DURATION=2000,PREP_MS=3500;
 var warmTimer=0,warmPending=false,warmEpoch=0,cancelWarm=null;var tapShield=null,tapAnimation=null,tapElement=null;var views={home:null,landing:null};var activeView=null,cancelPreparation=null,destinationFrame=null;var ready=null,busy=false,raf=0,timers=[],pending=null,closed=false,activeFrom=0,resizeObserver=null;
 var DL={settings:{timing:'free-scatter',spread:.7,liftCells:2},durationMs:DURATION,last:null,build:BUILD,disposed:false};
 function trace(name,data){if(window.__hubTrace)window.__hubTrace(name,data);if(name==='prep-timeout'||name==='transition-abort'||name==='fallback'){try{sessionStorage.setItem('agenthub:transition-exit',JSON.stringify({at:Date.now(),name:name,data:data||{},build:BUILD}));}catch(e){}}}
 DL.debugLine=function(){var child=null;try{child=activeView&&activeView.contentWindow.DepthLift&&activeView.contentWindow.DepthLift.build;}catch(e){}var ring=window.__hubTiming||[];return 'host '+BUILD+' active-child '+(child||'root')+' build-fallback '+!!window.__hubLastBuildFallback+(window.__hubPreviousTransitionExit?'\nprevious-exit '+JSON.stringify(window.__hubPreviousTransitionExit):'')+'\n'+ring.slice(-16).map(function(e){return Math.round(e.at-performance.timeOrigin)+'ms '+e.name+' '+JSON.stringify(e.data);}).join('\n');};
 function reduced(){return matchMedia('(prefers-reduced-motion: reduce)').matches;}
 function viewport(){
  // Mobile toolbar expansion is not a change of the crystal field's geometry.
  // Draw a full-screen-height field and clip it to the current viewport, never scale its pixels.
  var h=matchMedia('(pointer: coarse)').matches?Math.max(innerHeight,screen.height):innerHeight;
  return {w:innerWidth,h:h,dpr:Math.min(devicePixelRatio||1,2),vw:visualViewport?visualViewport.width:innerWidth,vh:h};
 }
 function equal(a,b){return a&&b&&a.w===b.w&&a.h===b.h&&a.dpr===b.dpr&&(matchMedia('(pointer: coarse)').matches||Math.abs(a.vw-b.vw)<1)&&Math.abs(a.vh-b.vh)<.01;}
 function later(fn,ms){var id=hostTimeout(fn,ms);timers.push(id);return id;}
 function cleanCover(){var e=document.getElementById('dl-arrive');if(e)e.remove();}
 try{localStorage.removeItem('agenthub:poster:home');localStorage.removeItem('agenthub:poster:landing');sessionStorage.removeItem('agenthub:xfade');}catch(e){}
  var VERTEX = '#version 300 es\nprecision highp float;\n' +
    'in vec3 p;in vec3 n;in vec2 uv;in float face;in vec4 inst;in vec4 mat;\n' +
    'uniform float progress;uniform float staggerSpan;uniform float lift;uniform vec2 grid;uniform float ry;\n' +
    'out vec3 normal;out vec3 position;out vec2 tex;out vec2 local;out float kind;out float tint;out float shine;out float motion;\n' +
    'vec3 rot(vec3 v,float a,float axis){float c=cos(a),s=sin(a);return axis<.5?vec3(v.x,c*v.y-s*v.z,s*v.y+c*v.z):vec3(c*v.x+s*v.z,v.y,-s*v.x+c*v.z);}\n' +
    'void main(){float start=inst.z*staggerSpan*.55;float finish=1.-mat.w*staggerSpan*.45;float u=clamp((progress-start)/(finish-start),0.,1.);float t=u*u*(3.-2.*u);' +
    'float a=3.14159265359*t*inst.w;' +
    'float energy=sin(t*3.14159265);' +
    'vec3 v=rot(p,a,mat.x);v.z-=.5;v.z+=lift*energy*2.0;' +
    'vec3 world=vec3(inst.x,inst.y,0.)+v;' +
    'vec2 xy=vec2((world.x/grid.x-.5)*2.,(.5-world.y*ry)*2.);' +
    'float perspective=1./(1.-world.z/70.);gl_Position=vec4(xy*perspective,-world.z/40.,1.);' +
    'normal=rot(n,a,mat.x);position=world;local=uv;kind=face;tint=mat.y;shine=mat.z;motion=energy;' +
    'vec2 sampleUV=face>.5&&face<1.5&&mat.x<.5?1.-uv:uv;' +
    'tex=vec2((inst.x-.5+sampleUV.x)/grid.x,(inst.y-.5+sampleUV.y)*ry);}\n';
  var FRAGMENT = '#version 300 es\nprecision highp float;\n' +
    'in vec3 normal;in vec3 position;in vec2 tex;in vec2 local;in float kind;in float tint;in float shine;in float motion;\n' +
    'uniform vec3 palette;uniform vec4 finish;uniform float colourMix;uniform vec2 centre;uniform sampler2D beforeScreen;uniform sampler2D afterScreen;\n' +
    'out vec4 color;\n' +
    'vec3 hsv(vec3 c){vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.);return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y);}\n' +
    'vec3 env(vec3 r){vec3 e=vec3(.014,.021,.065);float bar=pow(max(0.,1.-abs(dot(r,normalize(vec3(.7,.8,1.)))-.35)*7.),5.);' +
    'float cyan=pow(max(0.,dot(r,normalize(vec3(-.8,.3,1.)))),24.);float green=pow(max(0.,dot(r,normalize(vec3(.6,-.5,1.)))),18.);' +
    'e+=vec3(.72,1.,.94)*bar*2.2+vec3(.06,.8,1.)*cyan*1.7+vec3(.0,.9,.47)*green*1.4;' +
    'float horizon=exp(-pow((r.y+.22)*28.,2.));e+=vec3(.16,.33,.55)*horizon;return e;}\n' +
    'void main(){vec3 N=normalize(normal);vec3 V=normalize(vec3((centre.x-position.x)*.012,(centre.y-position.y)*.012,1.));vec3 col;\n' +
    'if(kind<1.5){color=vec4(0.);return;}else{' +
    'float edge=min(min(local.x,1.-local.x),min(local.y,1.-local.y));float bevel=1.-smoothstep(.0,.065,edge);' +
    'vec2 ed=local-.5;N=normalize(N+vec3(ed*.38*bevel,0.));' +
    'vec3 base=hsv(vec3(tint<colourMix?palette.y:palette.x,palette.z,mix(.09,.24,shine)))*finish.x;' +
    'vec3 reflection=env(reflect(-V,N));float fres=pow(1.-max(0.,dot(N,V)),5.);' +
    'float spec=pow(max(0.,dot(reflect(-normalize(vec3(-.4,-.7,1.)),N),V)),180.);float facet=local.x+local.y*.63>1.?1.:.78;' +
    'col=base*facet+reflection*(.5+fres*.6)*finish.y+vec3(.65,1.,.91)*spec*.8*finish.y;col+=bevel*vec3(.025,.18,.14);}\n' +
    'float edge=min(min(local.x,1.-local.x),min(local.y,1.-local.y));float rim=(1.-smoothstep(.006,.036,edge))*motion;' +
    'col+=vec3(0.,.55,.24)*rim*.6*finish.z;col=col/(vec3(1.)+max(vec3(0.),col-1.));color=vec4(col,1.);}\n';

 function renderer(seed,options){
  options=options||{};var v=options.viewport||viewport();if(v.w*v.h*v.dpr*v.dpr>9000000)throw Error('render budget exceeded');
  var layer=document.createElement('div');layer.id='dl-overlay';layer.style.cssText='position:'+(options.parent?'absolute':'fixed')+';inset:0;z-index:2147483001;pointer-events:none;visibility:hidden;contain:strict';

  var cvs=document.createElement('canvas');cvs.style.cssText='position:absolute;left:0;top:0;pointer-events:none';cvs.style.width=v.w+'px';cvs.style.height=v.h+'px';cvs.width=Math.round(v.w*v.dpr);cvs.height=Math.round(v.h*v.dpr);layer.appendChild(cvs);
  var gl=cvs.getContext('webgl2',{alpha:true,antialias:false,premultipliedAlpha:true,powerPreference:'default'});if(!gl)throw Error('WebGL2 unavailable');
  var objects=[],lost=false,cleanupMasks=function(){};function sh(type,src){var o=gl.createShader(type);objects.push(function(){gl.deleteShader(o)});gl.shaderSource(o,src);gl.compileShader(o);if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(o));return o;}
  function destroy(){cleanupMasks();layer.remove();objects.forEach(function(fn){try{fn()}catch(e){}});var ext=gl.getExtension('WEBGL_lose_context');if(ext)ext.loseContext();}
  try{
   var prog=gl.createProgram();objects.push(function(){gl.deleteProgram(prog)});gl.attachShader(prog,sh(gl.VERTEX_SHADER,VERTEX));gl.attachShader(prog,sh(gl.FRAGMENT_SHADER,FRAGMENT));gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(prog));gl.useProgram(prog);
   var cell=Math.max(17.6,Math.min(32,v.w/22.5)),C=Math.round(v.w/cell),s=v.w/C,R=Math.ceil(v.h/s),count=C*R;
   var data=[];function face(v,n,id){[0,1,2,0,2,3].forEach(function(i){data.push.apply(data,v[i].concat(n,[[0,0],[1,0],[1,1],[0,1]][i],[id]));});}
   face([[-.5,-.5,.5],[.5,-.5,.5],[.5,.5,.5],[-.5,.5,.5]],[0,0,1],0);
   face([[.5,-.5,-.5],[-.5,-.5,-.5],[-.5,.5,-.5],[.5,.5,-.5]],[0,0,-1],1);
   face([[.5,-.5,.5],[.5,-.5,-.5],[.5,.5,-.5],[.5,.5,.5]],[1,0,0],2);
   face([[-.5,-.5,-.5],[-.5,-.5,.5],[-.5,.5,.5],[-.5,.5,-.5]],[-1,0,0],2);
   face([[-.5,-.5,-.5],[.5,-.5,-.5],[.5,-.5,.5],[-.5,-.5,.5]],[0,-1,0],2);
   face([[-.5,.5,.5],[.5,.5,.5],[.5,.5,-.5],[-.5,.5,-.5]],[0,1,0],2);
   function attr(n,size,stride,offset,d){var a=gl.getAttribLocation(prog,n);if(a<0)return;gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,size,gl.FLOAT,false,stride,offset);if(d)gl.vertexAttribDivisor(a,d);}
   var vao=gl.createVertexArray();gl.bindVertexArray(vao);objects.push(function(){gl.deleteVertexArray(vao)});
   var mesh=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,mesh);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);objects.push(function(){gl.deleteBuffer(mesh)});attr('p',3,36,0);attr('n',3,36,12);attr('uv',2,36,24);attr('face',1,36,32);
   var buffer=gl.createBuffer();objects.push(function(){gl.deleteBuffer(buffer)});gl.bindBuffer(gl.ARRAY_BUFFER,buffer);var values=new Float32Array(count*8);gl.bufferData(gl.ARRAY_BUFFER,values.byteLength,gl.DYNAMIC_DRAW);attr('inst',4,32,0,1);attr('mat',4,32,16,1);
   var U={};['progress','lift','grid','ry','palette','finish','colourMix','centre','staggerSpan'].forEach(function(k){U[k]=gl.getUniformLocation(prog,k);});
   gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.disable(gl.CULL_FACE);gl.clearColor(0,0,0,0);gl.viewport(0,0,cvs.width,cvs.height);
   function randomize(seed){var z=seed>>>0;function rnd(){z=(1664525*z+1013904223)>>>0;return z/4294967296;}
    var mix=.1+rnd()*.8;for(var i=0;i<count;i++)values.set([i%C+.5,Math.floor(i/C)+.5,rnd(),rnd()<.5?-1:1,rnd()<.5?0:1,rnd(),rnd(),rnd()],i*8);
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,values);gl.uniform1f(U.colourMix,mix);return mix;
   }
   gl.uniform1f(U.lift,1);gl.uniform2f(U.grid,C,R);gl.uniform1f(U.ry,s/v.h);gl.uniform3f(U.palette,215/360,180/360,1);gl.uniform4f(U.finish,2,1.75,1.55,0);gl.uniform2f(U.centre,C/2,R/2);
   var from=null,to=null,oldClips=[],spread=.7,lift=1;
   function clearMasks(){oldClips.forEach(function(x){x[0].style.clipPath=x[1];x[0].style.webkitClipPath=x[2];x[0].style.opacity=x[3]});oldClips=[];from=to=null;}
   cleanupMasks=clearMasks;
   function attach(a,b){clearMasks();from=a;to=b;[a,b].forEach(function(e){oldClips.push([e,e.style.clipPath,e.style.webkitClipPath,e.style.opacity]);});}
   function pose(p,start,end){var a=start*spread*.55,b=1-end*spread*.45;var u=Math.max(0,Math.min(1,(p-a)/(b-a)));return u*u*(3-2*u);}
   function mask(node,p,back){if(!node)return;
    // Free Scatter can show front and back page regions simultaneously.
    if((!back&&p===0)||(back&&p===1)){node.style.clipPath='none';node.style.webkitClipPath='none';return;}
    var bounds=node.getBoundingClientRect(),origin=options.parent?options.parent.getBoundingClientRect():{left:0,top:0};var ox=origin.left-bounds.left,oy=origin.top-bounds.top,paths=[];
    for(var i=0;i<count;i++){
     var k=i*8,t=pose(p,values[k+2],values[k+7]),angle=Math.PI*t*values[k+3],c=Math.cos(angle),sn=Math.sin(angle),axis=values[k+4],z0=back?-.5:.5;
     if((back&&t<=.5)||(!back&&t>=.5))continue;
     var points=[[-.5,-.5],[.5,-.5],[.5,.5],[-.5,.5]],part=[];
     for(var j=0;j<4;j++){var x=points[j][0],y=points[j][1],z=z0;
      if(axis<.5){var yy=c*y-sn*z;z=sn*y+c*z;y=yy;}else{var xx=c*x+sn*z;z=-sn*x+c*z;x=xx;}
      z+=-.5+lift*Math.sin(t*Math.PI)*2;var perspective=1/(1-z/70);
      var px=((values[k]+x-C/2)*s*perspective+v.w/2)+ox,py=((values[k+1]+y-v.h/s/2)*s*perspective+v.h/2)+oy;
      part.push((j?'L':'M')+px.toFixed(2)+' '+py.toFixed(2));
     }paths.push(part.join('')+'Z');
    }
    var path=paths.length?'path("'+paths.join('')+'")':'inset(100%)';node.style.clipPath=path;node.style.webkitClipPath=path;
   }
   function draw(p){if(lost)throw Error('context lost');gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.uniform1f(U.progress,p);gl.uniform1f(U.staggerSpan,spread);gl.uniform1f(U.lift,lift);gl.drawArraysInstanced(gl.TRIANGLES,0,36,count);mask(from,p,false);mask(to,p,true);}
   cvs.addEventListener('webglcontextlost',function(e){e.preventDefault();lost=true;if(pending)abort();});
   randomize(seed||1);draw(.5);gl.finish();draw(0);gl.finish();if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL warmup failed');(options.parent||document.documentElement).appendChild(layer);
   return {v:v,layer:layer,cvs:cvs,draw:draw,randomize:randomize,destroy:destroy,count:count,cell:s,attach:attach,finish:function(){oldClips=[];from=to=null;},configure:function(o){spread=Math.max(0,Math.min(.9,o.spread===undefined?.7:o.spread));lift=(o.lift===undefined?2:o.lift)/2;},clearMasks:clearMasks};
  }catch(e){destroy();throw e;}
 }
 function release(){warmEpoch++;if(warmTimer)hostClear(warmTimer);warmTimer=0;if(cancelWarm)cancelWarm();cancelWarm=null;warmPending=false;if(raf)nativeCancel(raf);raf=0;if(ready){ready.destroy();ready=null;}cleanCover();busy=false;}
 function abort(reason){trace('transition-abort',{reason:reason||'context',viewport:viewport(),prepared:ready&&ready.v});if(cancelPreparation){var cancel=cancelPreparation;cancelPreparation=null;cancel();return;}var fn=pending;pending=null;release();if(fn)fn(true);}
 // Compile off the label-change path. Adopt the prepared program without touching
 // the approved renderer or shader sources; the GL instance is scoped to this call.
 function adoptWarm(canvas,gl,vs,fs,program){
  var create=document.createElement,originals={};
  var replacements={createShader:function(type){return type===gl.VERTEX_SHADER?vs:fs;},shaderSource:function(){},compileShader:function(){},createProgram:function(){return program;},attachShader:function(){},linkProgram:function(){}};
  try{if(canvas){document.createElement=function(name){return name.toLowerCase()==='canvas'?canvas:create.apply(document,arguments);};Object.keys(replacements).forEach(function(k){originals[k]=gl[k];gl[k]=replacements[k];});}
   try{ready=renderer(1);}catch(e){DL.last={skipped:String(e.message||e)};}
  }finally{document.createElement=create;Object.keys(originals).forEach(function(k){gl[k]=originals[k];});}
 }
 function startWarm(){
  warmTimer=0;if(ready||warmPending||closed||document.hidden||reduced())return;warmPending=true;var epoch=++warmEpoch;
  var canvas=document.createElement('canvas'),gl=null,vs=null,fs=null,program=null,owned=false;
  function clean(){if(gl&&!owned){if(program)gl.deleteProgram(program);if(vs)gl.deleteShader(vs);if(fs)gl.deleteShader(fs);var lose=gl.getExtension('WEBGL_lose_context');if(lose)lose.loseContext();}gl=null;}
  cancelWarm=clean;
  try{
   gl=canvas.getContext('webgl2',{alpha:true,antialias:false,premultipliedAlpha:true,powerPreference:'default'});if(!gl)throw Error('WebGL2 unavailable');var parallel=gl.getExtension('KHR_parallel_shader_compile');
   if(!parallel){clean();cancelWarm=null;warmPending=false;adoptWarm();return;}
   vs=gl.createShader(gl.VERTEX_SHADER);fs=gl.createShader(gl.FRAGMENT_SHADER);gl.shaderSource(vs,VERTEX);gl.shaderSource(fs,FRAGMENT);gl.compileShader(vs);gl.compileShader(fs);program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
   function poll(){if(epoch!==warmEpoch||closed)return;if(!gl.getProgramParameter(program,parallel.COMPLETION_STATUS_KHR)){later(poll,8);return;}
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)){DL.last={skipped:gl.getProgramInfoLog(program)};clean();}else{adoptWarm(canvas,gl,vs,fs,program);owned=!!ready;if(!owned)clean();}
    warmPending=false;cancelWarm=null;
   }later(poll,0);
  }catch(e){clean();cancelWarm=null;warmPending=false;DL.last={skipped:String(e.message||e)};}
 }
 function warm(interaction){
  if(closed||ready||warmPending||document.hidden||reduced()||(!interaction&&document.getElementById('wake-btn')&&!document.documentElement.classList.contains('hub-up')&&!activeView))return;
  if(warmTimer){if(!interaction)return;hostClear(warmTimer);warmTimer=0;}
  if(interaction){var ticket=warmEpoch;nativeRAF(function(){nativeRAF(function(){if(ticket===warmEpoch)startWarm();});});return;}
  warmTimer=later(function(){warmTimer=0;var ticket=warmEpoch;var begin=function(){if(ticket===warmEpoch)startWarm();};if(window.requestIdleCallback)window.requestIdleCallback(begin,{timeout:1000});else later(begin,0);},350);
 }
 function run(from,to,done){var r=ready;if(!r){done();return;}busy=true;activeFrom=from;r.layer.style.visibility='visible';trace('first-frame',{build:BUILD});r.draw(from);cleanCover();var start=0,prev=0,elapsed=0,deltas=[];pending=done;
  function tick(now){if(!equal(r.v,viewport())||document.hidden||reduced()){abort(document.hidden?'hidden':reduced()?'reduced-motion':'drawing-viewport');return;}if(!start)start=now;
   if(prev){var dt=now-prev;deltas.push(dt);elapsed+=dt;}prev=now;
   // Once visible, complete the reveal; a few slow frames must not dismiss it mid-turn.
   var p=Math.min(1,elapsed/(DURATION*(to-from)));try{r.draw(from+(to-from)*p);}catch(e){abort();return;}
   if(p<1){raf=nativeRAF(tick);return;}raf=0;var sorted=deltas.slice().sort(function(a,b){return a-b});DL.last={deltas:deltas,p50:sorted[Math.floor(sorted.length*.5)]||0,p95:sorted[Math.floor(sorted.length*.95)]||0,over25:deltas.filter(function(x){return x>25}).length,cubes:r.count,cell:r.cell,phase:to===1&&from===0?'complete':from===0?'cover':'reveal'};pending=null;done();
  }raf=nativeRAF(tick);
 }
 // Keep the confirmed live destination rather than reloading it after the turn.
 function tapFeedback(element){
  if(!element)return;if(tapElement===element&&tapAnimation)return;clearFeedback();tapElement=element;tapShield=document.createElement('div');tapShield.id='dl-tap-shield';tapShield.style.cssText='position:fixed;inset:0;z-index:2147483002;background:transparent';tapShield.onclick=function(){trace('ignored',{reason:'busy'});};document.documentElement.appendChild(tapShield);element.setAttribute('aria-busy','true');element.setAttribute('data-dl-pending','');
  if(element.animate&&!reduced())tapAnimation=element.animate([{opacity:1},{opacity:.45},{opacity:1}],{duration:650,iterations:Infinity});
 }
 function clearFeedback(){if(tapShield)tapShield.remove();tapShield=null;if(tapAnimation)tapAnimation.cancel();if(tapElement){tapElement.removeAttribute('aria-busy');tapElement.removeAttribute('data-dl-pending');}tapAnimation=tapElement=null;}
 // A cached view can stop being what it is named after: when the hub drops, the Home view is rewritten into the
 // dormant landing page (and the reverse). Such a view must be replaced, never resumed as the other page.
 function staleView(f,dest){try{var d=f.contentDocument;if(!d||!d.documentElement)return true;var landing=!!d.getElementById('wake-btn');return dest==='home'?landing:!landing;}catch(e){return true;}}
 function suspendView(frame){frame.removeAttribute('data-dl-view');frame.setAttribute('data-dl-cached','');frame.style.visibility='hidden';frame.style.pointerEvents='none';try{frame.contentWindow.__hubSuspendView(false);}catch(e){}}
 function routeFor(destination){return (destination==='home'?'/?enter=1':'/offline.html')+(/debug/.test(location.hash)?'#debug':'');}
 function syncAddress(frame,replace){try{var win=frame.contentWindow;if(win.location.origin!==location.origin)return;var url=win.location.pathname+win.location.search+win.location.hash;history[replace?'replaceState':'pushState']({agentHubView:true},'',url);document.title=win.document.title;}catch(e){}}
 function backToDocument(){if(activeView)location.reload();}
 function retireOriginalView(){
  window.__hubViewSuspended=true;
  try{if(window.__hubSuspendView)window.__hubSuspendView(true);if(window.dormantGlobe)window.dormantGlobe.destroy();}catch(e){}
  if(window.__hubPageTasks)window.__hubPageTasks.stop();
  try{(window.__socks||[]).forEach(function(sock){sock.onclose=sock.onerror=sock.onmessage=null;sock.close();});}catch(e){}
  if(stateObserver)stateObserver.disconnect();document.body.style.display='none';
 }
 DL.viewStatus=function(win,status){if(activeView&&activeView.contentWindow===win&&!busy){if(status.page==='landing'&&status.state!=='up')release();else later(warm,0);}};
 DL.go=function(destination,navigate,element){
  trace(destination==='home'?'enter-tap':'orb-tap',{host:BUILD});tapFeedback(element);if(busy){trace('ignored',{reason:'busy'});return;}trace('accepted',{destination:destination});
  if(closed||document.hidden||reduced()||(ready&&!equal(ready.v,viewport()))){release();clearFeedback();navigate();return;}
  busy=true;DL.last={phase:'preparing'};if(!ready)warm(true);
  var existing=views[destination],discard=null;if(existing&&staleView(existing,destination)){discard=existing;trace('stale-view-replaced',{page:destination});if(existing!==activeView)existing.remove();views[destination]=null;existing=null;}var created=!existing,frame=existing||document.createElement('iframe');destinationFrame=frame;frame.removeAttribute('data-dl-view');frame.removeAttribute('data-dl-cached');frame.setAttribute('data-dl-destination','');frame.title=destination==='home'?'Agent Hub Home':'Agent Hub landing';
  if(created)frame.style.cssText='position:fixed;inset:0;border:0;width:100%;height:100%;z-index:2147482999;background:#080c28;visibility:hidden;clip-path:inset(100%)';
  var timer=later(function(){trace('prep-timeout',{ms:PREP_MS});fail();},PREP_MS),started=false,confirmed=null,readySeen=false;cancelPreparation=fail;
  function fail(){if(started)return;started=true;cancelPreparation=null;hostClear(timer);if(created)frame.remove();else{frame.removeAttribute('data-dl-destination');frame.setAttribute('data-dl-cached','');suspendView(frame);}destinationFrame=null;busy=false;release();clearFeedback();if(!closed)navigate();}
  frame.onerror=fail;
  var waitForStatus=function(){if(started||closed)return;try{
   var doc=frame.contentDocument,win=frame.contentWindow,status=win.__hubViewStatus;
   if(destination==='home'&&doc&&doc.getElementById('wake-btn')){trace('fallback',{reason:'non-home-answer'});fail();return;}
   if(!doc||!status){later(waitForStatus,50);return;}
   var button=doc.getElementById('wake-btn');
   if(button){var expected=status.state==='up'?'enter':'start';var line=doc.querySelector('.status');if(status.page!=='landing'||button.dataset.s!==expected){later(waitForStatus,50);return;}}
   else if(status.page!=='home'||status.state!=='up'||!doc.getElementById('orb-home')){later(waitForStatus,50);return;}
   if(!readySeen){readySeen=true;trace('ready',{page:status.page,state:status.state});}if(!ready){later(waitForStatus,8);return;}confirmed=status;nativeRAF(begin);
  }catch(e){fail();}};
  function begin(){if(started||closed)return;started=true;cancelPreparation=null;hostClear(timer);if(document.hidden||!ready||!equal(ready.v,viewport())){frame.remove();destinationFrame=null;busy=false;release();clearFeedback();navigate();return;}
   var previous=activeView,source=previous||document.body;
   var seed=new Uint32Array(1);crypto.getRandomValues(seed);ready.randomize(seed[0]);ready.attach(source,frame);ready.draw(0);frame.style.visibility='visible';frame.style.pointerEvents='auto';
   run(0,1,function(skipped){if(skipped){frame.remove();destinationFrame=null;clearFeedback();navigate();return;}ready.finish();ready.layer.style.visibility='hidden';
    frame.removeAttribute('data-dl-destination');frame.setAttribute('data-dl-view','');activeView=frame;destinationFrame=null;busy=false;clearFeedback();
    views[confirmed.page]=frame;if(previous){suspendView(previous);if(previous===discard)previous.remove();}else retireOriginalView();
    try{if(confirmed.page==='home')sessionStorage.setItem('agenthub:entered','1');sessionStorage.removeItem(FLAG);}catch(e){}
    trace('done',{page:confirmed.page,build:BUILD});DL.last.phase='complete';DL.last.destination=confirmed;DL.last.retained=true;
    syncAddress(frame,destination==='home');frame.onload=function(){if(frame===activeView)syncAddress(frame,true);};
    later(warm,150);
   });
  }
  if(created){frame.onload=function(){trace('iframe-load',{page:destination});waitForStatus();};frame.src=routeFor(destination);document.documentElement.appendChild(frame);later(waitForStatus,0);}else{try{frame.contentWindow.__hubViewStatus=null;frame.contentWindow.__hubResumeView();}catch(e){fail();return;}waitForStatus();}
 };
 DL.prepare=function(){warm(true);};
 function onIntent(e){var target=e.target&&e.target.closest&&e.target.closest('#wake-btn,#orb-home');if(target)DL.prepare();}
 document.addEventListener('pointerdown',onIntent,true);
 DL.createPreview=function(parent,source,target,options){var box=parent.getBoundingClientRect();var r=renderer(1,{parent:parent,viewport:{w:box.width,h:box.height,dpr:Math.min(devicePixelRatio||1,2)}});r.configure(options||{});r.attach(source,target);return r;};
 // Compatibility for callers: capture no longer paints, caches or stores any UI.
 DL.capture=function(){return Promise.resolve(false)};
 function onHide(){if(document.hidden&&busy)abort('hidden');else if(document.hidden)release();else later(warm,150);}
 function onResize(){if(ready&&equal(ready.v,viewport()))return;if(busy)abort('resize');else{release();later(warm,150);}}
 function onShow(e){if(e.persisted){release();later(warm,150);}}
 DL.dispose=function(){DL.disposed=true;closed=true;document.removeEventListener('pointerdown',onIntent,true);clearFeedback();cancelPreparation=null;if(destinationFrame){destinationFrame.remove();destinationFrame=null;}if(stateObserver)stateObserver.disconnect();window.removeEventListener('popstate',backToDocument);pending=null;timers.forEach(hostClear);document.removeEventListener('visibilitychange',onHide);window.removeEventListener('resize',onResize);window.removeEventListener('pageshow',onShow);if(visualViewport)visualViewport.removeEventListener('resize',onResize);release();};
 DL.isBusy=function(){return busy||warmPending;};
 DL.isTransitioning=function(){return !!warmTimer||warmPending||!!(busy&&ready&&ready.layer.style.visibility==='visible')||!!window.__depthLiftArrival;};
 window.DepthLift=DL;
 if(document.documentElement.hasAttribute('data-depth-lift-demo'))return;
 if(window.frameElement&&(window.frameElement.hasAttribute('data-dl-destination')||window.frameElement.hasAttribute('data-dl-view')||window.frameElement.hasAttribute('data-dl-cached'))){
  DL.prepare=function(){try{if(parent.DepthLift&&parent.DepthLift.prepare)parent.DepthLift.prepare();}catch(e){}};
  DL.go=function(d,n,element){try{if(parent.DepthLift&&!parent.DepthLift.disposed){if(parent.DepthLift.build!==BUILD){trace('build-mismatch-fallback',{host:parent.DepthLift.build,child:BUILD});try{sessionStorage.setItem('agenthub:dl-upgrade',JSON.stringify({at:Date.now(),host:parent.DepthLift.build,child:BUILD}));}catch(e){}parent.location.replace(routeFor(d));return;}parent.DepthLift.go(d,function(){parent.location.replace(routeFor(d));},element);return;}}catch(e){}n();};
  DL.isBusy=function(){try{return parent.DepthLift.isBusy()}catch(e){return false}};
  DL.isTransitioning=function(){try{return parent.DepthLift.isTransitioning()}catch(e){return false}};return;
 }
 window.addEventListener('popstate',backToDocument);
 document.addEventListener('visibilitychange',onHide);window.addEventListener('resize',onResize);window.addEventListener('pageshow',onShow);if(visualViewport)visualViewport.addEventListener('resize',onResize);
 var stateObserver=new MutationObserver(function(){if(document.documentElement.classList.contains('hub-up'))later(warm,0);else if(document.getElementById('wake-btn')&&!busy&&!window.__depthLiftArrival)release();});stateObserver.observe(document.documentElement,{attributes:true,attributeFilter:['class']});
 function arrive(){cleanCover();later(warm,250);}
 if(document.readyState!=='loading')arrive();else document.addEventListener('DOMContentLoaded',arrive,{once:true});
})();
