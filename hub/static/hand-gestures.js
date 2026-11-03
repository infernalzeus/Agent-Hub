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
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.HubHandsGestures=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const BONES=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[9,10],[10,11],[11,12],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];
  const TUNING=Object.freeze({pinchOn:.4,pinchOff:.6,confirmMs:70,settleMs:220,poseHoldMs:200,aimLagMs:190,trailMs:500,clickSlop:20,fitHoldMs:1000,maxJump:.28,idleMs:60000});
  class LowPass{constructor(){this.last=null;}filter(x,a){this.last=this.last===null?x:a*x+(1-a)*this.last;return this.last;}}
  class OneEuro{
    constructor(min=1.1,beta=.012,d=1){this.min=min;this.beta=beta;this.d=d;this.reset();}
    reset(){this.x=new LowPass();this.dx=new LowPass();this.lastAt=null;}
    filter(value,at){const alpha=(c,dt)=>1/(1+1/(2*Math.PI*c*dt));if(this.lastAt===null){this.lastAt=at;this.dx.filter(0,1);return this.x.filter(value,1);}const dt=Math.max(1/240,Math.min(.2,at-this.lastAt));this.lastAt=at;const speed=(value-this.x.last)/dt,dx=this.dx.filter(speed,alpha(this.d,dt));return this.x.filter(value,alpha(this.min+this.beta*Math.abs(dx),dt));}
  }
  class Point{constructor(min=1.1,beta=.012){this.x=new OneEuro(min,beta);this.y=new OneEuro(min,beta);}filter(x,y,at){return{x:this.x.filter(x,at),y:this.y.filter(y,at)};}}
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  function isClick(start,end,maxTravel){return Math.max(distance(start,end),maxTravel||0)<TUNING.clickSlop;}
  function zoomMath(a,b,initial,current){const d=Math.max(1,distance(a,b)),mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};return {ratio:d/Math.max(1,initial.distance),mid,scale:clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6),x:mid.x-initial.world.x*clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6),y:mid.y-initial.world.y*clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6)};}
  class Engine{
    constructor(options={}){this.options=options;this.tuning={...TUNING,...options.tuning};this.reset();}
    reset(){this.hands=new Map();this.last=-Infinity;this.openSince=null;this.fitLatched=false;}
    update(result,now,width,height){
      if(!Number.isFinite(now)||now<=this.last)return {hands:[...this.hands.values()].map(s=>s.out),lost:[],fit:false,stale:true};this.last=now;
      const t=this.tuning,seen=new Set(),out=[],lost=[],marks=result?.landmarks||[],labels=result?.handedness||[],reach=Math.hypot(width,height);
      for(let i=0;i<Math.min(2,marks.length);i++){
        const raw=marks[i];if(!raw||raw.length!==21||raw.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))continue;
        const label=labels[i]?.[0]?.categoryName==='Right'?'right':'left',wrist={x:(1-raw[0].x)*width,y:raw[0].y*height};
        let id=-1,best=Infinity;for(const [key,s]of this.hands){if(seen.has(key))continue;const d=distance(s.wrist,wrist);if(d<best){best=d;id=key;}}
        if(best>reach*t.maxJump)id=-1;
        if(id<0){id=label==='right'?1:0;if(seen.has(id))id=1-id;if(this.hands.has(id)){lost.push(this.hands.get(id).out);this.hands.delete(id);}}
        seen.add(id);let s=this.hands.get(id);
        if(!s){s={cursor:new Point(),joints:Array.from({length:21},()=>new Point(2.4,.02)),trail:[],pinchSince:null,pinched:false,pose:null,poseAt:now,held:'none',changedAt:now,aim:wrist};this.hands.set(id,s);}
        s.wrist=wrist;const points=raw.map((p,j)=>s.joints[j].filter((1-p.x)*width,p.y*height,now/1000));
        const tip=this.options.finger==='middle'?12:8;const span=Math.max(1,distance(points[0],points[9])),gap=distance(points[4],points[tip])/span;const fist=this.options.fistGrab&&s.pinched&&[[8,6],[12,10],[16,14],[20,18]].every(([a,b])=>distance(points[a],points[0])<distance(points[b],points[0])*1.05);const wants=fist||(s.pinched?gap<t.pinchOff:gap<t.pinchOn);
        if(wants&&!s.pinched){if(s.pinchSince===null)s.pinchSince=now;}else if(!wants)s.pinchSince=null;
        const pinched=s.pinched?wants:wants&&s.pinchSince!==null&&now-s.pinchSince>=t.confirmMs&&now-s.changedAt>=t.settleMs;
        if(fist&&!s.grabOffset)s.grabOffset={x:(s.out?.x??points[tip].x)-wrist.x,y:(s.out?.y??points[tip].y)-wrist.y};if(!fist)s.grabOffset=null;const pos=s.cursor.filter(fist?wrist.x+s.grabOffset.x:points[tip].x,fist?wrist.y+s.grabOffset.y:points[tip].y,now/1000);s.trail.push({...pos,at:now});while(s.trail.length>1&&now-s.trail[0].at>t.trailMs)s.trail.shift();
        if(!s.pinched){let aim=s.trail[0];for(const p of s.trail)if(p.at<=now-t.aimLagMs)aim=p;s.aim={x:aim.x,y:aim.y};}
        const ext=(tip,pip)=>distance(points[tip],points[0])>distance(points[pip],points[0])*1.12;
        const fingers={thumb:distance(points[4],points[0])>distance(points[2],points[0])*1.35||distance(points[4],points[6])>span*1.1,index:ext(8,6),middle:ext(12,10),ring:ext(16,14),pinky:ext(20,18)};
        const up=Object.values(fingers).filter(Boolean).length,pose=pinched?'pinch':up>=4?'open':fingers.index&&!fingers.middle&&!fingers.ring&&!fingers.pinky?'point':up===0?'fist':'none';
        if(pinched){s.held='pinch';s.pose='pinch';s.poseAt=now;}else if(s.pose!==pose){s.pose=pose;s.poseAt=now;if(s.held==='pinch')s.held='none';}else if(now-s.poseAt>=t.poseHoldMs){if(s.held!==pose&&s.held!=='pinch')s.changedAt=now;s.held=pose;}
        s.pinched=pinched;s.out={id,...pos,aimX:s.aim.x,aimY:s.aim.y,pinched,gesture:s.held,points,span,fingers,pointerFinger:tip===12?'middle':'index',handedness:label,closeness:clamp(1-(gap-t.pinchOn)/(t.pinchOff-t.pinchOn),0,1),gap};out.push(s.out);
      }
      for(const [id,s]of this.hands)if(!seen.has(id)){lost.push(s.out);this.hands.delete(id);}
      const open=out.length===1&&out[0].gesture==='open'&&!out[0].pinched;let fit=false;
      if(open){if(this.openSince===null)this.openSince=now;if(!this.fitLatched&&now-this.openSince>=t.fitHoldMs){fit=true;this.fitLatched=true;}}else{this.openSince=null;this.fitLatched=false;}
      return {hands:out,lost,fit,zoom:out.length===2&&out.every(h=>h.pinched)?{mid:{x:(out[0].x+out[1].x)/2,y:(out[0].y+out[1].y)/2},distance:distance(out[0],out[1])}:null};
    }
  }
  return {Engine,OneEuro,Point,TUNING,BONES,isClick,zoomMath,distance};
});
