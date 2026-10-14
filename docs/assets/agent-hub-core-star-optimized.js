/* Star Cloud textured curved faces. Only redraws on input/resize, no idle loop. */
(function(root){'use strict';
root.AgentHubStarOptimized={mount:function(host,options){
 options=options||{};var doc=host.ownerDocument,c=doc.createElement('canvas'),ctx=null,depth=root.AgentHubDepthSurface.create(c);if(!depth)return null;
 c.style.cssText='position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2';host.appendChild(c);
 var image=new Image(),ready=false,alive=true,active=true,q=[0,0,0,1],size=480,scale=1,mode='vertical',drag=-1,lastX=0,lastY=0,total=0,frame=0,returning=false,hasDrag=false,lastMove=0,lastFrame=0,lastPaint=0,coast=2,returnElapsed=0,returnDuration=2,returnAmount=0,returnEase=0,returnSlope=0,returnAxis=[0,1,0],angular=[0,0,0],returnRemaining=0,returnSign=1,initialSpeed=0,cruiseSpeed=0;
 var vertices=[0,-1/Math.sqrt(3),-1/Math.sqrt(24),-.5,1/Math.sqrt(12),-1/Math.sqrt(24),.5,1/Math.sqrt(12),-1/Math.sqrt(24),0,0,3/Math.sqrt(24)];
 var uv=[770,98,552,454,982,454,770,332],faces=[0,1,3,1,2,3,2,0,3,0,2,1],points=[],tris=[],order=[];
 var mesh=22,coords=new Float32Array(4*(mesh+1)*(mesh+2)/2*3),screen=new Float32Array(coords.length),src=new Float32Array(coords.length/3*2),bary=new Float32Array(coords.length);
 var depths=new Float32Array(4),count=0;
 function edge(a,b){return .42;}
 function point(face,a,b,d){
  var ia=faces[face*3],ib=faces[face*3+1],ic=faces[face*3+2],index=count++;
  for(var component=0;component<3;component++){
   var va=vertices[ia*3+component],vb=vertices[ib*3+component],vc=vertices[ic*3+component];
   // Face geometry and UV use shared bowed edges; the initial face texture
   // keeps the bright PNG's green/cyan shading, instead of dark flat fills.
   coords[index*3+component]=a*a*va+b*b*vb+d*d*vc+edge(ia,ib)*a*b*(va+vb)+edge(ib,ic)*b*d*(vb+vc)+edge(ic,ia)*d*a*(vc+va);var normal=(va+vb+vc)/3;coords[index*3+component]-=normal*Math.sqrt(24)*.035*27*a*b*d;
  }
  // Bijective face UVs: no swirl, clamping or folded texture coordinates.
  bary[index*3]=a;bary[index*3+1]=b;bary[index*3+2]=d;
  src[index*2]=(a*.5+b*.06+d*.94)*2048;src[index*2+1]=(a*.04+(b+d)*.96)*2048;
  return index;
 }
 for(var f=0;f<4;f++){
  var grid=[];for(var row=0;row<=mesh;row++){grid[row]=[];for(var col=0;col<=mesh-row;col++)grid[row][col]=point(f,row/mesh,col/mesh,1-(row+col)/mesh);}
  var list=[];
  for(row=0;row<mesh;row++)for(col=0;col<mesh-row;col++){
   list.push(grid[row][col],grid[row+1][col],grid[row][col+1]);
   if(col<mesh-row-1)list.push(grid[row+1][col],grid[row+1][col+1],grid[row][col+1]);
  }
  tris[f]=new Uint16Array(list);points[f]=[grid[mesh][0],grid[0][mesh],grid[0][0]];order[f]=f;
 }
 function rotate(x,y,z,angle){var n=Math.hypot(x,y,z);if(!n)return;var s=Math.sin(angle/2)/n,w=Math.cos(angle/2),a=q[0],b=q[1],d=q[2],e=q[3];x*=s;y*=s;z*=s;q[0]=w*a+x*e+y*d-z*b;q[1]=w*b-x*d+y*e+z*a;q[2]=w*d+x*b-y*a+z*e;q[3]=w*e-x*a-y*b-z*d;n=Math.hypot.apply(Math,q);for(var k=0;k<4;k++)q[k]/=n;}
 function draw(){
  frame=0;if(!alive||!ready)return;

  var x=q[0],y=q[1],z=q[2],w=q[3],a=1-2*(y*y+z*z),b=2*(x*y-z*w),d=2*(x*z+y*w),e=2*(x*y+z*w),g=1-2*(x*x+z*z),h=2*(y*z-x*w),j=2*(x*z-y*w),k=2*(y*z+x*w),l=1-2*(x*x+y*y);
  for(var at=0;at<count;at++){
   var xx=coords[at*3],yy=coords[at*3+1],zz=coords[at*3+2],rz=j*xx+k*yy+l*zz,p=1/(1-rz*.18),r=size*(options.contained?.60:.64);
   screen[at*3]=size/2+(a*xx+b*yy+d*zz)*p*r;screen[at*3+1]=size/2+(e*xx+g*yy+h*zz)*p*r;screen[at*3+2]=rz;
  }
  depth.draw(screen,src,tris,size,bary,q,coords);
 }
 function cloudTexture(){
  var tile=doc.createElement('canvas');tile.width=tile.height=2048;var cc=tile.getContext('2d');cc.scale(2,2);
  // Transparent star-cloud membrane: no opaque solid face interior.
  var seed=73129;function rng(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;}
  cc.globalCompositeOperation='lighter';
  for(var pocket=0;pocket<120;pocket++){
   var px=rng()*1024,py=rng()*1024,radius=55+rng()*150;
   var glow=cc.createRadialGradient(px,py,0,px,py,radius);
   glow.addColorStop(0,pocket%2?'rgba(35,150,255,.48)':'rgba(0,255,155,.48)');
   glow.addColorStop(.4,pocket%2?'rgba(35,150,255,.16)':'rgba(0,255,155,.16)');glow.addColorStop(1,'transparent');
   cc.fillStyle=glow;cc.fillRect(px-radius,py-radius,radius*2,radius*2);
  }
  // Fine stars plus unequal luminous clusters, with no graph lines.
  for(var star=0;star<16000;star++){
   var px=rng()*1024,py=rng()*1024,w=rng(),r=.25+w*w*1.05;
   cc.globalAlpha=.4+w*.6;cc.fillStyle=w>.97?'#e3fff4':star%2?'#62c5ff':'#31ffb0';cc.beginPath();cc.arc(px,py,r,0,Math.PI*2);cc.fill();
   if(w>.975){var glow=cc.createRadialGradient(px,py,0,px,py,8);glow.addColorStop(0,star%2?'rgba(100,200,255,.5)':'rgba(65,255,175,.5)');glow.addColorStop(1,'transparent');cc.fillStyle=glow;cc.fillRect(px-8,py-8,16,16);}
  }
  // Curved star streams and caustic-like arcs suggest a deep, lensed sky.
  // These are part of the continuous texture, not disconnected mesh shards.
  for(var stream=0;stream<44;stream++){
   var angle=rng()*Math.PI*2,rad=90+rng()*380,blue=stream%2===0;
   cc.lineWidth=.35+rng()*1.25;cc.strokeStyle=blue?'rgba(75,165,255,.22)':'rgba(25,255,163,.22)';cc.beginPath();
   for(var sample=0;sample<60;sample++){
    var t=sample/59,phi=angle+t*2.2,rr=rad*(.65+.35*t),px=512+Math.cos(phi)*rr,py=512+Math.sin(phi)*rr*.73;
    if(sample===0)cc.moveTo(px,py);else cc.lineTo(px,py);
    if(sample%5===0){cc.fillStyle=blue?'#84cfff':'#7affc5';cc.fillRect(px,py,.8,.8);}
   }cc.stroke();
  }
  // Bright compact formations, with fine filaments inspired by the original mark.
  for(var cluster=0;cluster<36;cluster++){
   var px=140+rng()*744,py=100+rng()*824,blue=cluster%2===0;
   for(var dust=0;dust<260;dust++){
    var angle=rng()*Math.PI*2,rr=Math.pow(rng(),1.7)*65;
    cc.globalAlpha=.25+rng()*.7;cc.fillStyle=blue?'#52bdff':'#40ffb0';cc.fillRect(px+Math.cos(angle)*rr,py+Math.sin(angle)*rr*.65,.5+rng(),.5+rng());
   }
   cc.globalAlpha=1;var glow=cc.createRadialGradient(px,py,0,px,py,18);glow.addColorStop(0,'#effff7');glow.addColorStop(.08,blue?'#6cceff':'#6effb8');glow.addColorStop(.3,blue?'rgba(35,160,255,.4)':'rgba(0,255,130,.4)');glow.addColorStop(1,'transparent');cc.fillStyle=glow;cc.fillRect(px-18,py-18,36,36);
   cc.strokeStyle='rgba(220,255,246,.6)';cc.lineWidth=.55;cc.beginPath();cc.moveTo(px-5,py);cc.lineTo(px+5,py);cc.moveTo(px,py-5);cc.lineTo(px,py+5);cc.stroke();
  }
  cc.globalAlpha=1;return tile;
 }
 function beginReturn(){
  var n=Math.hypot(q[0],q[1],q[2]);if(n<.0001)return;
  var angle=2*Math.acos(Math.max(-1,Math.min(1,q[3])));
  for(var i=0;i<3;i++)returnAxis[i]=q[i]/n;
  var speed=Math.hypot.apply(Math,angular),direction=angular[0]*returnAxis[0]+angular[1]*returnAxis[1]+angular[2]*returnAxis[2];
  returnAmount=direction>=0?Math.PI*2-angle:-angle;
  if(mode==='free')returnAmount=-angle;
  returnRemaining=Math.abs(returnAmount);returnSign=Math.sign(returnAmount);initialSpeed=Math.max(.15,Math.min(1.6,speed));cruiseSpeed=Math.min(.25,initialSpeed);
  returnElapsed=returnEase=0;lastFrame=0;returning=true;request();
 }
 function animate(now){
  frame=0;
  if(now-lastPaint<16){request();return;}lastPaint=now;
  if(returning){
   var dt=lastFrame?Math.min(.05,(now-lastFrame)/1000):0;lastFrame=now;
   returnElapsed+=dt;
   var velocity=cruiseSpeed+(initialSpeed-cruiseSpeed)*Math.exp(-returnElapsed/Math.max(.12,coast*.2));
   var step=Math.min(returnRemaining,velocity*dt);
   if(returnRemaining<.35)step=Math.min(step,returnRemaining*dt*3);
   rotate(returnAxis[0],returnAxis[1],returnAxis[2],returnSign*step);returnRemaining-=step;
   if(returnRemaining<.003){returning=false;q[0]=q[1]=q[2]=0;q[3]=1;}
  }
  draw();if(returning&&alive&&!doc.hidden)request();
 }
 function request(){if(!frame&&alive&&active)frame=root.requestAnimationFrame(animate);}
 function resize(){size=host.clientWidth||480;var zoom=Number(doc.getElementById('zoom')?.value)||1;scale=Math.min(4,(root.devicePixelRatio||1)*zoom,2048/size);c.width=c.height=Math.round(size*scale);request();}
 function down(ev){if(!active)return;if(ev.button!==undefined&&ev.button!==0)return;hasDrag=false;lastMove=performance.now();drag=ev.pointerId;lastX=ev.clientX;lastY=ev.clientY;total=0;ev.preventDefault();ev.stopImmediatePropagation();host.setPointerCapture(drag);}
 function move(ev){if(ev.pointerId!==drag)return;if(ev.pointerType!=="touch"&&ev.buttons!==undefined&&(ev.buttons&1)===0){cancelDrag();return;}var rect=host.getBoundingClientRect(),dx=(ev.clientX-lastX)/rect.width,dy=(ev.clientY-lastY)/rect.height;lastX=ev.clientX;lastY=ev.clientY;total+=Math.abs(dx)+Math.abs(dy);if(total<.01)return;if(!hasDrag){hasDrag=true;returning=false;angular[0]=angular[1]=angular[2]=0;}var now=performance.now(),dt=Math.max(.008,(now-lastMove)/1000);lastMove=now;var vx=mode==='vertical'||mode==='depth'?0:-dy*6/dt,vy=mode==='horizontal'||mode==='depth'?0:dx*6/dt,vz=mode==='depth'?dx*6/dt:0;angular[0]=angular[0]*.35+vx*.65;angular[1]=angular[1]*.35+vy*.65;angular[2]=angular[2]*.35+vz*.65;if(mode==='vertical')rotate(0,1,0,dx*6);else if(mode==='horizontal')rotate(1,0,0,-dy*6);else if(mode==='depth')rotate(0,0,1,dx*6);else rotate(-dy,dx,0,Math.hypot(dx,dy)*6);ev.preventDefault();ev.stopImmediatePropagation();request();}
 function up(ev){if(ev.pointerId!==drag)return;var bounds=host.getBoundingClientRect();if(ev.type==="pointercancel"||(ev.clientX!==undefined&&(ev.clientX<bounds.left||ev.clientX>bounds.right||ev.clientY<bounds.top||ev.clientY>bounds.bottom))){cancelDrag();return;}drag=-1;if(host.hasPointerCapture(ev.pointerId))host.releasePointerCapture(ev.pointerId);ev.stopImmediatePropagation();if(hasDrag)beginReturn();}
 function click(ev){if(total>.01){ev.preventDefault();ev.stopImmediatePropagation();total=0;}}
 function cancelDrag(){var id=drag,moved=hasDrag;drag=-1;returning=false;hasDrag=false;if(id!==-1&&host.hasPointerCapture(id))host.releasePointerCapture(id);if(moved&&options.coastOnRelease!==false)beginReturn();else request();}
 function lost(){if(drag!==-1)cancelDrag();}
 function globalUp(ev){if(ev.pointerId===drag)up(ev);}
 function hidden(){if(doc.hidden)lost();}
 root.addEventListener&&root.addEventListener('pointerup',globalUp,true);root.addEventListener&&root.addEventListener('blur',lost);host.addEventListener('lostpointercapture',lost);doc.addEventListener&&doc.addEventListener('visibilitychange',hidden);
 host.addEventListener('pointerdown',down,true);host.addEventListener('pointermove',move,true);host.addEventListener('pointerup',up,true);host.addEventListener('pointercancel',up,true);host.addEventListener('click',click,true);
 if(depth.setBrightness)depth.setBrightness(options.brightness||1);image=cloudTexture();depth.setTexture(image);ready=true;resize();
 return {setActive:function(value){active=!!value;if(!active&&frame){root.cancelAnimationFrame(frame);frame=0;}lastFrame=0;if(active){request();}},getMotion:function(){return {returning:returning,remaining:returnRemaining,sign:returnSign,initial:initialSpeed,cruise:cruiseSpeed,elapsed:returnElapsed,axis:returnAxis.slice(),angular:angular.slice(),coast:coast,mode:mode};},setMotion:function(value){returning=value.returning;returnRemaining=value.remaining;returnSign=value.sign;initialSpeed=value.initial;cruiseSpeed=value.cruise;returnElapsed=value.elapsed;returnAxis=value.axis.slice();angular=value.angular.slice();coast=value.coast;mode=value.mode;lastFrame=0;if(returning)request();},getCanvas:function(){return c;},renderNow:function(){var pending=frame;draw();frame=pending;if(returning)request();},setPose:function(value){for(var i=0;i<4;i++)q[i]=value[i];request();},getRenderMesh:function(){return {screen:screen.slice(),triangles:tris};},setResistance:function(value){coast=Math.max(.6,Math.min(10,Number(value)||2));},setParallax:function(value){depth.setParallax(value);request();},resize:resize,setMode:function(value){mode=value;},reset:function(){returning=false;q[0]=q[1]=q[2]=0;q[3]=1;request();},destroy:function(){depth.destroy();alive=false;root.removeEventListener&&root.removeEventListener("pointerup",globalUp,true);root.removeEventListener&&root.removeEventListener("blur",lost);host.removeEventListener("lostpointercapture",lost);doc.removeEventListener&&doc.removeEventListener("visibilitychange",hidden);if(frame)root.cancelAnimationFrame(frame);host.removeEventListener('pointerdown',down,true);host.removeEventListener('pointermove',move,true);host.removeEventListener('pointerup',up,true);host.removeEventListener('pointercancel',up,true);host.removeEventListener('click',click,true);c.remove();},getQuaternion:function(){return q.slice();},getGeometry:function(){return {vertices:vertices.slice(),points:coords.slice()};}};
}};
})(window);














