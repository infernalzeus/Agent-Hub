/* Isolated prototype: per-projected-facet screen-space flip, 30 fps, finite. */
(function(){'use strict';
var host=document.getElementById('demo-1'),active=false,overlay=null,frame=0,last=0;
window.stopFacetFlip=function(){if(frame)cancelAnimationFrame(frame);frame=0;if(overlay)overlay.remove();overlay=null;active=false;};
function snapshot(core){core.renderNow();var source=core.getCanvas(),copy=document.createElement('canvas');copy.width=source.width;copy.height=source.height;copy.getContext('2d').drawImage(source,0,0);return copy;}
host.addEventListener('click',function(event){
 if(active||!window.CoreFlipControls)return;
 var state=CoreFlipControls.get();if(!state.core)return;
 var motion=state.core.getMotion(),points=state.core.getGeometry().points,pose=state.core.getQuaternion(),mesh=state.core.getRenderMesh(),before=snapshot(state.core),size=host.clientWidth;mesh=state.core.getRenderMesh();
 var rect=host.getBoundingClientRect(),clickX=(event.clientX-rect.left)/rect.width*size,clickY=(event.clientY-rect.top)/rect.height*size;
 var next=CoreFlipControls.switch(state.mode==='star'?'crystal':'star');if(!next)return;
 next.setPose(pose);next.setMotion(motion);next.renderNow();var target=next.getCanvas();target.style.visibility='hidden';
 overlay=document.createElement('canvas');overlay.width=before.width;overlay.height=before.height;overlay.style.cssText='position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2';host.appendChild(overlay);
 var ctx=overlay.getContext('2d'),ratio=overlay.width/size,facets=[],screen=mesh.screen;
 for(var face=0;face<mesh.triangles.length;face++)for(var at=0;at<mesh.triangles[face].length;at+=3){
  var indices=mesh.triangles[face],i=indices[at]*3,j=indices[at+1]*3,k=indices[at+2]*3;
  var x0=screen[i],y0=screen[i+1],x1=screen[j],y1=screen[j+1],x2=screen[k],y2=screen[k+1];
  if((x1-x0)*(y2-y0)-(y1-y0)*(x2-x0)>=0)continue;
  var cx=(x0+x1+x2)/3,cy=(y0+y1+y2)/3;
  facets.push({indices:[i,j,k],source:[x0,y0,x1,y1,x2,y2],p:[x0,y0,x1,y1,x2,y2],x:cx,y:cy,z:(screen[i+2]+screen[j+2]+screen[k+2])/3,delay:Math.hypot(cx-clickX,cy-clickY)/size*.55});
 }
 facets.sort(function(a,b){return a.z-b.z;});active=true;last=0;var start=performance.now();
 if(state.globe)CoreFlipControls.get().globe?.pulse();
 function tick(now){
  frame=0;if(now-last<32){frame=requestAnimationFrame(tick);return;}last=now;
  var elapsed=(now-start)/1000;ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,size,size);
  next.renderNow();var pose=next.getQuaternion(),qx=pose[0],qy=pose[1],qz=pose[2],qw=pose[3],a=1-2*(qy*qy+qz*qz),b=2*(qx*qy-qz*qw),d=2*(qx*qz+qy*qw),e=2*(qx*qy+qz*qw),g=1-2*(qx*qx+qz*qz),h=2*(qy*qz-qx*qw),j=2*(qx*qz-qy*qw),k=2*(qy*qz+qx*qw),l=1-2*(qx*qx+qy*qy);
  var r=size*(CoreFlipControls.get().globe?.60:.64);
  for(var n=0;n<facets.length;n++){var f=facets[n];for(var corner=0;corner<3;corner++){var at=f.indices[corner],x=points[at],y=points[at+1],z=points[at+2],zz=j*x+k*y+l*z,projection=1/(1-zz*.18);f.p[corner*2]=size/2+(a*x+b*y+d*z)*r*projection;f.p[corner*2+1]=size/2+(e*x+g*y+h*z)*r*projection;}f.x=(f.p[0]+f.p[2]+f.p[4])/3;f.y=(f.p[1]+f.p[3]+f.p[5])/3;}
  for(var n=0;n<facets.length;n++){
   var f=facets[n],t=Math.max(0,Math.min(1,(elapsed-f.delay)/.38)),angle=t*Math.PI,thin=Math.max(.015,Math.abs(Math.cos(angle))),p=f.p;
   if((p[2]-p[0])*(p[5]-p[1])-(p[3]-p[1])*(p[4]-p[0])>=0)continue;
   ctx.save();ctx.translate(f.x,f.y);ctx.scale(thin,1);ctx.translate(-f.x,-f.y);ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(p[2],p[3]);ctx.lineTo(p[4],p[5]);ctx.closePath();ctx.clip();
   if(t<.5){var s=f.source,D=s[0]*(s[3]-s[5])+s[2]*(s[5]-s[1])+s[4]*(s[1]-s[3]);if(Math.abs(D)>.00001){var aa=(p[0]*(s[3]-s[5])+p[2]*(s[5]-s[1])+p[4]*(s[1]-s[3]))/D,bb=(p[1]*(s[3]-s[5])+p[3]*(s[5]-s[1])+p[5]*(s[1]-s[3]))/D,cc=(p[0]*(s[4]-s[2])+p[2]*(s[0]-s[4])+p[4]*(s[2]-s[0]))/D,dd=(p[1]*(s[4]-s[2])+p[3]*(s[0]-s[4])+p[5]*(s[2]-s[0]))/D;ctx.transform(aa,bb,cc,dd,p[0]-aa*s[0]-cc*s[1],p[1]-bb*s[0]-dd*s[1]);ctx.drawImage(before,0,0,size,size);}}
   else ctx.drawImage(target,0,0,size,size);
   if(t>.06&&t<.94){ctx.globalCompositeOperation='lighter';ctx.globalAlpha=Math.sin(t*Math.PI)*.24;ctx.fillStyle='#4eefff';ctx.fillRect(0,0,size,size);}ctx.restore();
  }
  if(elapsed>1){target.style.visibility='';window.stopFacetFlip();}else frame=requestAnimationFrame(tick);
 }
 frame=requestAnimationFrame(tick);
});
})();


