/* Metallic crystal faces with a restrained, frame-capped travelling colour glint. */
(function(root){'use strict';
root.AgentHubCrystalOptimized={mount:function(host,options){
 options=options||{};var doc=host.ownerDocument,c=doc.createElement('canvas'),gpu=root.AgentHubCrystalSurface&&root.AgentHubCrystalSurface.create(c),ctx=gpu?null:c.getContext('2d');if(!gpu&&!ctx)return null;
 c.style.cssText='position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2';host.appendChild(c);
 var image=new Image(),ready=false,alive=true,active=true,q=[0,0,0,1],size=480,scale=1,mode='vertical',drag=-1,lastX=0,lastY=0,total=0,frame=0,returning=false,hasDrag=false,lastMove=0,lastFrame=0,lastPaint=0,coast=2,returnElapsed=0,returnDuration=2,returnAmount=0,returnEase=0,returnSlope=0,returnAxis=[0,1,0],angular=[0,0,0],returnRemaining=0,returnSign=1,initialSpeed=0,cruiseSpeed=0;
 var pulseStarted=-10000;
 var vertices=[0,-1/Math.sqrt(3),-1/Math.sqrt(24),-.5,1/Math.sqrt(12),-1/Math.sqrt(24),.5,1/Math.sqrt(12),-1/Math.sqrt(24),0,0,3/Math.sqrt(24)];
 var uv=[770,98,552,454,982,454,770,332],faces=[0,1,3,1,2,3,2,0,3,0,2,1],points=[],tris=[],order=[];
 var mesh=24,coords=new Float32Array(4*(mesh+1)*(mesh+2)/2*3),screen=new Float32Array(coords.length),src=new Float32Array(coords.length/3*2);
 var depths=new Float32Array(4),count=0,edgeCounts=Object.create(null);
 function edge(a,b){return .42;}
 function point(face,a,b,d){
  var ia=faces[face*3],ib=faces[face*3+1],ic=faces[face*3+2],index=count++;
  for(var component=0;component<3;component++){
   var va=vertices[ia*3+component],vb=vertices[ib*3+component],vc=vertices[ic*3+component];
   // Face geometry and UV use shared bowed edges; the initial face texture
   // keeps the bright PNG's green/cyan shading, instead of dark flat fills.
   coords[index*3+component]=a*a*va+b*b*vb+d*d*vc+edge(ia,ib)*a*b*(va+vb)+edge(ib,ic)*b*d*(vb+vc)+edge(ic,ia)*d*a*(vc+va);var normal=(va+vb+vc)/3;coords[index*3+component]-=normal*Math.sqrt(24)*.035*27*a*b*d;
  }
  // Back face reuses a bright front texture, rather than a blank panel.
  ia=0;ib=1;ic=3;
  // A lensing-style swirl concentrates stars into each concave face.
  // It vanishes on shared edges, so no privileged vertex or seam warp.
  var ca=a-1/3,cb=b-1/3,well=27*a*b*d,phi=well*1.15,cs=Math.cos(phi),sn=Math.sin(phi);
  var la=Math.max(.001,1/3+ca*cs-cb*sn),lb=Math.max(.001,1/3+ca*sn+cb*cs),ld=Math.max(.001,1-la-lb),sum=la+lb+ld;la/=sum;lb/=sum;ld/=sum;
  for(component=0;component<2;component++){
   var origin=component?332:770,va=uv[ia*2+component]-origin,vb=uv[ib*2+component]-origin,vc=uv[ic*2+component]-origin;
   src[index*2+component]=origin+la*la*va+lb*lb*vb+ld*ld*vc+.42*(la*lb*(va+vb)+lb*ld*(vb+vc)+ld*la*(vc+va));
  }
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
 for(var face=0;face<4;face++)for(var t=0;t<tris[face].length;t+=3)for(var e=0;e<3;e++){var u=tris[face][t+e],v=tris[face][t+(e+1)%3],key=Math.min(u,v)*4096+Math.max(u,v);edgeCounts[key]=(edgeCounts[key]||0)+1;}
 function rotate(x,y,z,angle){var n=Math.hypot(x,y,z);if(!n)return;var s=Math.sin(angle/2)/n,w=Math.cos(angle/2),a=q[0],b=q[1],d=q[2],e=q[3];x*=s;y*=s;z*=s;q[0]=w*a+x*e+y*d-z*b;q[1]=w*b-x*d+y*e+z*a;q[2]=w*d+x*b-y*a+z*e;q[3]=w*e-x*a-y*b-z*d;n=Math.hypot.apply(Math,q);for(var k=0;k<4;k++)q[k]/=n;}
 function draw(){
  frame=0;if(!alive||!ready)return;
  if(ctx){ctx.setTransform(scale,0,0,scale,0,0);ctx.clearRect(0,0,size,size);ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';}
  // Fixed crystal orientation survives shared motion transferred by material flips.
  var hs=Math.sqrt(3)/2,x=q[0]*.5-q[1]*hs,y=q[1]*.5+q[0]*hs,z=q[2]*.5-q[3]*hs,w=q[3]*.5+q[2]*hs,a=1-2*(y*y+z*z),b=2*(x*y-z*w),d=2*(x*z+y*w),e=2*(x*y+z*w),g=1-2*(x*x+z*z),h=2*(y*z-x*w),j=2*(x*z-y*w),k=2*(y*z+x*w),l=1-2*(x*x+y*y);
  for(var at=0;at<count;at++){
   var xx=coords[at*3],yy=coords[at*3+1],zz=coords[at*3+2],rz=j*xx+k*yy+l*zz,p=1/(1-rz*.18),r=size*(options.contained?.60:.64);
   screen[at*3]=size/2+(a*xx+b*yy+d*zz)*p*r;screen[at*3+1]=size/2+(e*xx+g*yy+h*zz)*p*r;screen[at*3+2]=rz;
  }
  if(gpu){gpu.draw(screen,coords,tris,edgeCounts,size,[a,b,d,e,g,h,j,k,l],options.freezeTime===undefined?performance.now()/1000:options.freezeTime,options.reducedMotion?-10:(performance.now()-pulseStarted)/1250);return;}
  for(var face=0;face<4;face++){depths[face]=(screen[points[face][0]*3+2]+screen[points[face][1]*3+2]+screen[points[face][2]*3+2])/3;order[face]=face;}
  order.sort(function(a,b){return depths[a]-depths[b];});
  for(var sorted=0;sorted<4;sorted++){
   face=order[sorted];var facePoints=points[face],v0=facePoints[0]*3,v1=facePoints[1]*3,v2=facePoints[2]*3;
   if((screen[v1]-screen[v0])*(screen[v2+1]-screen[v0+1])-(screen[v1+1]-screen[v0+1])*(screen[v2]-screen[v0])>=0)continue;
   var triangles=tris[face],glintTime=performance.now()/1000;
   for(var t=0;t<triangles.length;t+=3){
    var i0=triangles[t],i1=triangles[t+1],i2=triangles[t+2];
    var x0=screen[i0*3],y0=screen[i0*3+1],x1=screen[i1*3],y1=screen[i1*3+1],x2=screen[i2*3],y2=screen[i2*3+1];
    var ux=coords[i1*3]-coords[i0*3],uy=coords[i1*3+1]-coords[i0*3+1],uz=coords[i1*3+2]-coords[i0*3+2];
    var vx=coords[i2*3]-coords[i0*3],vy=coords[i2*3+1]-coords[i0*3+1],vz=coords[i2*3+2]-coords[i0*3+2];
    var nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,n=Math.hypot(nx,ny,nz)||1;
    var rx=(a*nx+b*ny+d*nz)/n,ry=(e*nx+g*ny+h*nz)/n,rz=(j*nx+k*ny+l*nz)/n;
    var diffuse=Math.abs(rx*.35-ry*.5+rz*.7);
    var nxv=Math.abs(rx),nyv=Math.abs(ry),nzv=Math.abs(rz);
    var sweep=Math.pow(Math.max(0,1-Math.abs(rx*.8+ry*.35-rz*.25)),10);
    var spec1=Math.pow(Math.abs(rx*.2-ry*.35+rz*.91),38),spec2=Math.pow(Math.abs(rx*.75+ry*.2+rz*.6),28);
    var spark=Math.min(1,spec1*.9+spec2*.65+sweep*.3),fresnel=Math.pow(1-nzv,3);
    var ox=(coords[i0*3]+coords[i1*3]+coords[i2*3])/3,oy=(coords[i0*3+1]+coords[i1*3+1]+coords[i2*3+1])/3,oz=(coords[i0*3+2]+coords[i1*3+2]+coords[i2*3+2])/3;
    var tint=.5+.5*Math.sin(ox*15+oy*10+oz*13),power=.42+diffuse*.45;
    var red=Math.round(8+spark*220),green=Math.round((140+105*tint)*power+spark*135+fresnel*40),blue=Math.round((245-120*tint)*power+spark*125+fresnel*45);
    // Solid metallic facets. Colour comes from reflected environment bands,
    // never from glowing edge strokes, threads or sparkle cross overlays.
    var reflection=.5+.5*Math.sin(rx*5.4+ry*3.7+rz*4.8);
    var strip=Math.pow(Math.max(0,Math.cos(rx*7.5+ry*3.1-rz*2.4)),18);
    var polish=Math.min(1,strip*.7+spec1*.5+spec2*.35);
    var pulse=Math.pow(Math.max(0,Math.cos(ox*83+oy*71+oz*97+rx*12+ry*9+rz*11)),28);polish=Math.min(1,polish+pulse*.3);var energy=.58+Math.abs(rz)*.16+reflection*.08;
    var emerald=.5+.5*Math.sin(ox*10+oy*6+oz*9);
    var micro=.82+.18*Math.sin(ox*95+oy*73+oz*109);energy*=micro;var rr=Math.round(3+polish*70),gg=Math.round((80+150*emerald)*energy+polish*230),bb=Math.round((205-70*emerald)*energy+polish*230);
    // A travelling face-local wave catches scattered gems in the Star Cloud palette.
    var wave=Math.pow(Math.max(0,Math.cos(ox*9+oy*7+oz*11-glintTime*1.8)),14);
    var catchLight=.35+.65*Math.pow(.5+.5*Math.sin(ox*97+oy*83+oz*71),3);
    var pulseAge=(performance.now()-pulseStarted)/1250;
    var radial=Math.hypot((x0+x1+x2)/3-size/2,(y0+y1+y2)/3-size/2)/size;
    var pulseBand=radial-pulseAge*.48;
    var pulseGlisten=!options.reducedMotion&&pulseAge>=0&&pulseAge<1?Math.exp(-pulseBand*pulseBand/.0025)*Math.sin(Math.PI*pulseAge):0;
    var gleam=wave*catchLight+pulseGlisten*(1.3+.7*catchLight),colour=.5+.5*Math.sin(ox*13+oy*8+glintTime*.45);
    rr+=gleam*18;gg+=gleam*(90+95*colour);bb+=gleam*(185-50*colour);
    var material=ctx.createLinearGradient(x0,y0,x2,y2);
    material.addColorStop(0,'rgb('+Math.min(255,rr)+','+Math.min(255,gg*.7)+','+Math.min(255,bb*.8)+')');
    material.addColorStop(.5,'rgb('+Math.min(255,rr+polish*10)+','+Math.min(255,gg)+','+Math.min(255,bb)+')');
    material.addColorStop(1,'rgb('+Math.min(255,rr*.7)+','+Math.min(255,gg*.5)+','+Math.min(255,bb*.6)+')');ctx.fillStyle=material;
    ctx.beginPath();ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);ctx.lineTo(x2,y2);ctx.closePath();ctx.fill();ctx.save();ctx.beginPath();var rim=[i0,i1,i2];for(var edge=0;edge<3;edge++){var u=rim[edge],v=rim[(edge+1)%3];if(edgeCounts[Math.min(u,v)*4096+Math.max(u,v)]===1){ctx.moveTo(screen[u*3],screen[u*3+1]);ctx.lineTo(screen[v*3],screen[v*3+1]);}}ctx.globalAlpha=1;ctx.lineJoin='miter';ctx.miterLimit=3;ctx.strokeStyle='#025c73';ctx.lineWidth=Math.max(1,size/650);ctx.stroke();ctx.shadowColor='#20e9ff';ctx.shadowBlur=Math.max(2,size*.008);ctx.strokeStyle='rgba(65,235,255,.8)';ctx.lineWidth=Math.max(.35,size/1500);ctx.stroke();ctx.restore();

   }
  }
 }
 function beginReturn(){
  var relative=q;var n=Math.hypot(relative[0],relative[1],relative[2]);if(n<.0001)return;
  var angle=2*Math.acos(Math.max(-1,Math.min(1,relative[3])));
  for(var i=0;i<3;i++)returnAxis[i]=relative[i]/n;
  var speed=Math.hypot.apply(Math,angular),direction=angular[0]*returnAxis[0]+angular[1]*returnAxis[1]+angular[2]*returnAxis[2];
  returnAmount=direction>=0?Math.PI*2-angle:-angle;
  if(mode==='free')returnAmount=-angle;
  returnRemaining=Math.abs(returnAmount);returnSign=Math.sign(returnAmount);initialSpeed=Math.max(.15,Math.min(1.6,speed))*2;cruiseSpeed=Math.min(.5,initialSpeed);
  returnElapsed=returnEase=0;lastFrame=0;returning=true;request();
 }
 function animate(now){
  frame=0;
  if(doc.hidden){return;}if(now-lastPaint<(returning||drag!==-1?16:66)){request();return;}lastPaint=now;
  if(returning){
   var dt=lastFrame?Math.min(.05,(now-lastFrame)/1000):0;lastFrame=now;
   returnElapsed+=dt;
   var velocity=cruiseSpeed+(initialSpeed-cruiseSpeed)*Math.exp(-returnElapsed/Math.max(.12,coast*.2));
   var step=Math.min(returnRemaining,velocity*dt);
   if(returnRemaining<.35)step=Math.min(step,returnRemaining*dt*3);
   rotate(returnAxis[0],returnAxis[1],returnAxis[2],returnSign*step);returnRemaining-=step;
   if(returnRemaining<.003){returning=false;q[0]=q[1]=0;q[2]=0;q[3]=1;}
  }
  draw();if((returning||!options.reducedMotion||performance.now()-pulseStarted<1300)&&alive&&!doc.hidden)request();
 }
 function request(){if(!frame&&alive&&active)frame=root.requestAnimationFrame(animate);}
 function resize(){size=host.clientWidth||480;var zoom=Number(doc.getElementById('zoom')?.value)||1;scale=Math.min(4,(root.devicePixelRatio||1)*zoom,2048/size);c.width=c.height=Math.round(size*scale);request();}
 function down(ev){if(!active)return;if(ev.button!==undefined&&ev.button!==0)return;hasDrag=false;lastMove=performance.now();drag=ev.pointerId;lastX=ev.clientX;lastY=ev.clientY;total=0;ev.preventDefault();ev.stopImmediatePropagation();host.setPointerCapture(drag);}
 function move(ev){if(ev.pointerId!==drag)return;if(ev.pointerType!=="touch"&&ev.buttons!==undefined&&(ev.buttons&1)===0){cancelDrag();return;}var rect=host.getBoundingClientRect(),dx=(ev.clientX-lastX)/rect.width,dy=(ev.clientY-lastY)/rect.height;lastX=ev.clientX;lastY=ev.clientY;total+=Math.abs(dx)+Math.abs(dy);if(total<.01)return;if(!hasDrag){hasDrag=true;returning=false;angular[0]=angular[1]=angular[2]=0;}var now=performance.now(),dt=Math.max(.008,(now-lastMove)/1000);lastMove=now;var vx=mode==='vertical'||mode==='depth'?0:-dy*6/dt,vy=mode==='horizontal'||mode==='depth'?0:dx*6/dt,vz=mode==='depth'?dx*6/dt:0;angular[0]=angular[0]*.35+vx*.65;angular[1]=angular[1]*.35+vy*.65;angular[2]=angular[2]*.35+vz*.65;if(mode==='vertical')rotate(0,1,0,dx*6);else if(mode==='horizontal')rotate(1,0,0,-dy*6);else if(mode==='depth')rotate(0,0,1,dx*6);else rotate(-dy,dx,0,Math.hypot(dx,dy)*6);ev.preventDefault();ev.stopImmediatePropagation();request();}
 function up(ev){if(ev.pointerId!==drag)return;var bounds=host.getBoundingClientRect();if(ev.type==="pointercancel"||(ev.clientX!==undefined&&(ev.clientX<bounds.left||ev.clientX>bounds.right||ev.clientY<bounds.top||ev.clientY>bounds.bottom))){cancelDrag();return;}drag=-1;if(host.hasPointerCapture(ev.pointerId))host.releasePointerCapture(ev.pointerId);ev.stopImmediatePropagation();if(hasDrag&&options.coastOnRelease!==false&&ev.type!=="pointercancel")beginReturn();else if(hasDrag){returning=false;angular[0]=angular[1]=angular[2]=0;request();}}
 function click(ev){if(total>.01){ev.preventDefault();ev.stopImmediatePropagation();total=0;}}
 function cancelDrag(){var id=drag,moved=hasDrag;drag=-1;returning=false;hasDrag=false;if(id!==-1&&host.hasPointerCapture(id))host.releasePointerCapture(id);if(moved&&options.coastOnRelease!==false)beginReturn();else request();}
 function lost(){if(drag!==-1)cancelDrag();}
 function globalUp(ev){if(ev.pointerId===drag)up(ev);}
 function hidden(){if(doc.hidden)lost();}
 root.addEventListener&&root.addEventListener('pointerup',globalUp,true);root.addEventListener&&root.addEventListener('blur',lost);host.addEventListener('lostpointercapture',lost);doc.addEventListener&&doc.addEventListener('visibilitychange',hidden);
 host.addEventListener('pointerdown',down,true);host.addEventListener('pointermove',move,true);host.addEventListener('pointerup',up,true);host.addEventListener('pointercancel',up,true);host.addEventListener('click',click,true);
 function pulse(){pulseStarted=performance.now();request();}host.addEventListener("pulse",pulse);
 function visibility(){if(!doc.hidden)request();}doc.addEventListener&&doc.addEventListener("visibilitychange",visibility);
 ready=true;resize();
 return {setActive:function(value){active=!!value;if(!active&&frame){root.cancelAnimationFrame(frame);frame=0;}lastFrame=0;if(active){request();}},getMotion:function(){return {returning:returning,remaining:returnRemaining,sign:returnSign,initial:initialSpeed,cruise:cruiseSpeed,elapsed:returnElapsed,axis:returnAxis.slice(),angular:angular.slice(),coast:coast,mode:mode};},setMotion:function(value){returning=value.returning;returnRemaining=value.remaining;returnSign=value.sign;initialSpeed=value.initial;cruiseSpeed=value.cruise;returnElapsed=value.elapsed;returnAxis=value.axis.slice();angular=value.angular.slice();coast=value.coast;mode=value.mode;lastFrame=0;if(returning)request();},getCanvas:function(){return c;},renderNow:function(){var pending=frame;draw();frame=pending;if(returning||!options.reducedMotion)request();},setPose:function(value){for(var i=0;i<4;i++)q[i]=value[i];request();},getRenderMesh:function(){return {screen:screen.slice(),triangles:tris};},setResistance:function(value){coast=Math.max(.6,Math.min(10,Number(value)||2));},getSize:function(){return size;},resize:resize,setMode:function(value){mode=value;},reset:function(){returning=false;q[0]=q[1]=0;q[2]=0;q[3]=1;request();},destroy:function(){if(gpu)gpu.destroy();alive=false;root.removeEventListener&&root.removeEventListener("pointerup",globalUp,true);root.removeEventListener&&root.removeEventListener("blur",lost);host.removeEventListener("lostpointercapture",lost);doc.removeEventListener&&doc.removeEventListener("visibilitychange",hidden);host.removeEventListener("pulse",pulse);doc.removeEventListener&&doc.removeEventListener("visibilitychange",visibility);if(frame)root.cancelAnimationFrame(frame);host.removeEventListener('pointerdown',down,true);host.removeEventListener('pointermove',move,true);host.removeEventListener('pointerup',up,true);host.removeEventListener('pointercancel',up,true);host.removeEventListener('click',click,true);c.remove();},getQuaternion:function(){return q.slice();},getGeometry:function(){var orient=function(input){var out=input.slice(),s=Math.sqrt(3)/2;for(var i=0;i<out.length;i+=3){out[i]=-.5*input[i]+s*input[i+1];out[i+1]=-s*input[i]-.5*input[i+1];}return out;};return {vertices:orient(vertices),points:orient(coords)};}};
}};
})(window);















