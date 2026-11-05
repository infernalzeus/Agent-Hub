/* Depth Lift site adapter. Renderer/shaders ported from hub/static/depth-lift.js.
 * Free Scatter: 70% spread, two-cell lift, 1500ms; original render-budget guard.
 * Only navigation/lifecycle changes: sibling DOM scenes, no Hub views or state. */
(function(){'use strict';
var pending=null;
function viewport(){return {w:innerWidth,h:innerHeight,dpr:Math.min(devicePixelRatio||1,2)};}
function abort(){if(pending)pending();}
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
   // Keep desktop clipping complexity bounded as the window grows. Phone layout is unchanged.
   var cell=Math.max(17.6,Math.min(32,v.w/22.5),matchMedia('(pointer: coarse)').matches?0:Math.sqrt(v.w*v.h/480)),C=Math.round(v.w/cell),s=v.w/C,R=Math.ceil(v.h/s),count=C*R;
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
var warmRenderer=null,warming=null,busy=false,disposed=false,failed=null,currentFinish=null,warmTimer=0;
var reduce=matchMedia('(prefers-reduced-motion: reduce)');
function releaseWarm(){clearTimeout(warmTimer);warming=null;if(warmRenderer){warmRenderer.destroy();warmRenderer=null;}}
function prepare(){
 if(disposed||document.hidden||reduce.matches||busy||warmRenderer||warming||failed)return warming||Promise.resolve();
 warming=new Promise(function(resolve){
  warmTimer=setTimeout(function(){
   try{warmRenderer=renderer(1);warmRenderer.layer.remove();}
   catch(error){failed=error.message;}
   warming=null;resolve();
  },0);
 });return warming;
}
function go(from,to,reverse){
 if(busy)return Promise.resolve(false);
 busy=true;releaseWarmTimer();
 var r=warmRenderer;warmRenderer=null;
 if(r&&(r.v.w!==innerWidth||r.v.h!==innerHeight)){r.destroy();r=null;}
 if(reduce.matches||document.hidden||failed){if(r)r.destroy();r=null;}
 var shield=document.createElement('div');shield.className='turn-shield';shield.setAttribute('aria-hidden','true');document.body.appendChild(shield);document.body.dataset.turning='';
 from.classList.add('turning');to.classList.add('turning');from.inert=true;to.inert=true;
 return new Promise(function(resolve){
  var raf=0,finished=false,animations=[],deltas=[],prev=0,start=0;
  function finish(){
   if(finished)return;finished=true;cancelAnimationFrame(raf);animations.forEach(function(a){a.cancel();});
   if(r)r.destroy();from.style.opacity='';to.style.opacity='';from.classList.remove('active','turning');to.classList.remove('turning');to.classList.add('active');from.inert=true;to.inert=false;
   shield.remove();delete document.body.dataset.turning;busy=false;pending=null;currentFinish=null;
   var sorted=deltas.slice().sort(function(a,b){return a-b;});
   api.last={kind:r?'multi-cube':'crossfade',reason:r?null:failed|| (reduce.matches?'reduced-motion':document.hidden?'hidden':'not-warm'),p50:sorted[Math.floor(sorted.length*.5)]||0,p95:sorted[Math.floor(sorted.length*.95)]||0,deltas:deltas,cubes:r?r.count:0,cell:r?r.cell:0,reverse:!!reverse};
   resolve(true);
   warmTimer=setTimeout(prepare,200);
  }
  currentFinish=finish;pending=finish;
  if(!r){
   to.style.opacity='0';
   if(document.hidden){finish();return;}
   animations=[from.animate([{opacity:1},{opacity:0}],{duration:180,fill:'forwards'}),to.animate([{opacity:0},{opacity:1}],{duration:180,fill:'forwards'})];
   animations[1].finished.then(finish,finish);return;
  }
  document.documentElement.appendChild(r.layer);r.layer.style.visibility='visible';
  r.randomize(crypto.getRandomValues(new Uint32Array(1))[0]);
  r.attach(reverse?to:from,reverse?from:to);
  function tick(now){
   if(document.hidden||reduce.matches||r.v.w!==innerWidth||r.v.h!==innerHeight){finish();return;}
   if(!start)start=now;if(prev)deltas.push(now-prev);prev=now;
   var p=Math.min(1,(now-start)/1500);
   try{r.draw(reverse?1-p:p);}catch(error){failed=error.message;finish();return;}
   if(p<1)raf=requestAnimationFrame(tick);else finish();
  }
  raf=requestAnimationFrame(tick);
 });
}
function releaseWarmTimer(){clearTimeout(warmTimer);warming=null;}
document.addEventListener('visibilitychange',function(){if(document.hidden){if(currentFinish)currentFinish();releaseWarm();}else prepare();});
addEventListener('resize',function(){if(currentFinish)currentFinish();releaseWarm();failed=null;warmTimer=setTimeout(prepare,200);});
reduce.addEventListener('change',function(){if(reduce.matches){if(currentFinish)currentFinish();releaseWarm();}else prepare();});
addEventListener('pagehide',function(){disposed=true;if(currentFinish)currentFinish();releaseWarm();});
addEventListener('pageshow',function(){disposed=false;prepare();});
var api=window.SiteDepthLift={prepare:prepare,go:go,isBusy:function(){return busy;},isReady:function(){return !!warmRenderer;},last:null};
prepare();
})();
