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
  // pinchOn / pinchOff are fractions of the hand's own size (wrist to the middle finger's knuckle), measured in the camera's own space and
  // including depth, so two fingertips that merely overlap in the picture but sit at different depths are not a pinch. 0.22 is about 2 cm on an
  // adult hand and 0.34 about 3.5 cm: a pinch starts below the first and ends above the second.
  const TUNING=Object.freeze({pinchOn:.22,pinchOff:.40,pinchOnM:.28,pinchOffM:.42,tripleOn:.28,tripleOff:.40,tripleHoldMs:260,tripleTips:.30,rightIndexAway:.30,flatOn:1.45,flatOff:1.7,flatHoldMs:400,confirmMs:60,settleMs:140,poseHoldMs:200,aimLagMs:190,trailMs:500,clickSlop:20,fitHoldMs:1000,maxJump:.28,idleMs:60000,minScore:.6,minSize:.05,maxSize:.5,presentFrames:3,fistDist:.75,depthStep:.05,depthStill:250,panStart:40,ctlStillMs:500,rotGain:1,rollGain:1,tiltGain:-4,rollTilt:0,moveGain:.5,rotSmooth:.5,rotDead:.008,extendRatio:1.12});
  const CAMERA={w:640,h:480};
  const PALM=[0,5,9,13,17];
  class LowPass{constructor(){this.last=null;}filter(x,a){this.last=this.last===null?x:a*x+(1-a)*this.last;return this.last;}}
  class OneEuro{
    constructor(min=1.1,beta=.012,d=1){this.min=min;this.beta=beta;this.d=d;this.reset();}
    reset(){this.x=new LowPass();this.dx=new LowPass();this.lastAt=null;}
    filter(value,at){const alpha=(c,dt)=>1/(1+1/(2*Math.PI*c*dt));if(this.lastAt===null){this.lastAt=at;this.dx.filter(0,1);return this.x.filter(value,1);}const dt=Math.max(1/240,Math.min(.2,at-this.lastAt));this.lastAt=at;const speed=(value-this.x.last)/dt,dx=this.dx.filter(speed,alpha(this.d,dt));return this.x.filter(value,alpha(this.min+this.beta*Math.abs(dx),dt));}
  }
  class Point{constructor(min=1.1,beta=.012){this.x=new OneEuro(min,beta);this.y=new OneEuro(min,beta);}filter(x,y,at){return{x:this.x.filter(x,at),y:this.y.filter(y,at)};}}
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
  function isClick(start,end,maxTravel,slop){return Math.max(distance(start,end),maxTravel||0)<(slop||TUNING.clickSlop);}
  function zoomMath(a,b,initial,current){const d=Math.max(1,distance(a,b)),mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};return {ratio:d/Math.max(1,initial.distance),mid,scale:clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6),x:mid.x-initial.world.x*clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6),y:mid.y-initial.world.y*clamp(initial.scale*d/Math.max(1,initial.distance),.3,2.6)};}
  class Engine{
    constructor(options={}){this.options=options;this.tuning={...TUNING,...options.tuning};this.reset();}
    reset(){this.hands=new Map();this.last=-Infinity;this.openSince=null;this.fitLatched=false;}
    // result: MediaPipe's {landmarks, handedness}; width/height: the screen the cursor lives on; cam: the camera picture's size, for true distances
    update(result,now,width,height,cam){
      if(!Number.isFinite(now)||now<=this.last)return {hands:[...this.hands.values()].map(s=>s.out),lost:[],fit:false,stale:true};this.last=now;
      const t=this.tuning,seen=new Set(),out=[],lost=[],marks=result?.landmarks||[],labels=result?.handedness||[],reach=Math.hypot(width,height),cw=cam?.w||CAMERA.w,ch=cam?.h||CAMERA.h;
      for(let i=0;i<Math.min(2,marks.length);i++){
        const raw=marks[i];if(!raw||raw.length!==21||raw.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))continue;
        // A hand the model is unsure of, or one far too small or large to be a hand at this camera, is background (a face, a poster): ignored.
        const conf=labels[i]?.[0]?.score;if(typeof conf==='number'&&conf<t.minScore)continue;
        {const sz=Math.hypot(raw[0].x-raw[9].x,raw[0].y-raw[9].y);if(sz<t.minSize||sz>t.maxSize)continue;}
        const label=labels[i]?.[0]?.categoryName==='Right'?'right':'left',wrist={x:(1-raw[0].x)*width,y:raw[0].y*height};
        let id=-1,best=Infinity;for(const [key,s]of this.hands){if(seen.has(key))continue;const d=distance(s.wrist,wrist);if(d<best){best=d;id=key;}}
        if(best>reach*t.maxJump)id=-1;
        if(id<0){id=label==='right'?1:0;if(seen.has(id))id=1-id;if(this.hands.has(id)){if(this.hands.get(id).out)lost.push(this.hands.get(id).out);this.hands.delete(id);}}
        seen.add(id);let s=this.hands.get(id);
        if(!s){s={cursor:new Point(),palmF:new Point(1.1,.012),rollF:new OneEuro(.8,.01),rollU:null,rollRaw:null,joints:Array.from({length:21},()=>new Point(2.4,.02)),trail:[],pinchSince:null,rSince:null,pinched:false,rpinched:false,pose:null,poseAt:now,held:'none',changedAt:now,aim:wrist};this.hands.set(id,s);}
        // Present for a few frames before it counts, so a one-frame false detection never reaches the board.
        if(!s.confirmed){s.frames=(s.frames||0)+1;s.wrist=wrist;if(s.frames<t.presentFrames)continue;s.confirmed=true;}
        s.wrist=wrist;const points=raw.map((p,j)=>s.joints[j].filter((1-p.x)*width,p.y*height,now/1000));
        // true distances: the camera's own pixels plus its depth estimate (same scale as x), so the picture's shape and overlap cannot fake a pinch
        const P=raw.map(p=>[p.x*cw,p.y*ch,(p.z||0)*cw]),d3=(a,b)=>Math.hypot(P[a][0]-P[b][0],P[a][1]-P[b][1],P[a][2]-P[b][2]);
        const rawSize=d3(0,9),size=Math.max(1e-6,rawSize),gap=d3(4,8)/size,gapM=d3(4,12)/size,tips=d3(8,12)/size,spread=(d3(8,12)+d3(12,16)+d3(16,20))/size,span=Math.max(1,distance(points[0],points[9]));
        // a fist is four fingertips pulled in to the palm; a pinch with the other fingers curled is NOT one (the index fingertip stays about a hand-size from the palm)
        const pc=[0,1,2].map(k=>PALM.reduce((a,j)=>a+P[j][k],0)/PALM.length),dp=i=>Math.hypot(P[i][0]-pc[0],P[i][1]-pc[1],P[i][2]-pc[2]);
        const fistShape=[8,12,16,20].every(i=>dp(i)<t.fistDist*size);
        const fist=this.options.fistGrab&&s.pinched&&[[8,6],[12,10],[16,14],[20,18]].every(([a,b])=>d3(a,0)<d3(b,0)*1.05);
        let wantsI=fist||(s.pinched?gap<t.pinchOff:gap<t.pinchOn),wantsM=(s.rpinched?gapM<t.pinchOffM:gapM<t.pinchOnM)&&(s.rpinched||(gap>=t.rightIndexAway&&(d3(16,0)>d3(14,0)*.95||d3(20,0)>d3(18,0)*.95)));      // a right press is the thumb on the middle fingertip with the index finger away; with the index finger touching too it is the zoom hold
        // pointing with the MIDDLE finger (index, ring and little finger curled in) tucks the thumb against the curled index finger, which measures
        // as a thumb-to-index pinch. Traced 5 Nov: 44 frames of it read as left presses. That posture (middle clearly out, the other three clearly in)
        // is never a pinch; a pinch already held keeps going.
        const mx=(a,b)=>d3(a,0)/Math.max(1e-6,d3(b,0)),midStrict=mx(12,10)>1.25&&mx(8,6)<1&&mx(16,14)<1&&mx(20,18)<1;
        if(midStrict&&!s.pinched&&!s.rpinched){wantsI=false;wantsM=false;}
        // thumb, index and middle fingertips all together is a third thing, the zoom hold: it is neither of the two single pinches
        // (stricter than a single pinch: with the index finger resting beside the middle one, a thumb-to-middle pinch is also fairly close to the index tip)
        let wantsT=this.options.tripleZoom===true&&(s.triple?(gap<t.tripleOff&&gapM<t.tripleOff):(gap<t.tripleOn&&gapM<t.tripleOn))&&(s.triple||tips<t.tripleTips);
        // the zoom hold takes over only after it has been held a moment: a quick left pinch made with the middle finger resting beside the index finger must stay a click
        if(wantsT&&!s.triple){if(s.tSince==null)s.tSince=now;}else if(!wantsT)s.tSince=null;
        if(s.triple?wantsT:wantsT&&now-s.tSince>=t.tripleHoldMs){wantsI=false;wantsM=false;}
        else if(wantsI&&wantsM){if(s.pinched||(!s.rpinched&&gapM>=gap*.75))wantsM=false;else wantsI=false;}      // one pinch at a time: the one already held, else the left click unless the middle finger is clearly (a quarter) nearer the thumb. The middle finger's wider threshold must never turn an ordinary left pinch into a right press
        if(wantsI&&!s.pinched){if(s.pinchSince===null)s.pinchSince=now;}else if(!wantsI)s.pinchSince=null;
        if(wantsM&&!s.rpinched){if(s.rSince===null)s.rSince=now;}else if(!wantsM)s.rSince=null;
        wantsT=wantsT&&(s.triple||now-s.tSince>=t.tripleHoldMs);
        if(fistShape&&!fist&&!wantsT){wantsI=false;wantsM=false;}
        const settled=now-s.changedAt>=t.settleMs;
        const pinched=s.pinched?wantsI:wantsI&&s.pinchSince!==null&&now-s.pinchSince>=t.confirmMs&&settled;
        const rpinched=s.rpinched?wantsM:wantsM&&s.rSince!==null&&now-s.rSince>=t.confirmMs&&settled;
        const triple=s.triple?wantsT:wantsT&&s.tSince!=null&&now-s.tSince>=t.confirmMs&&settled;
        if(pinched||rpinched||triple)s.lastPinchAt=now;
        // pointing with the middle finger (index and the others curled) moves the cursor on the middle fingertip, held a moment so a passing pose does not jump it
        const e2=(a,b)=>d3(a,0)>d3(b,0)*t.extendRatio,midOnly=e2(12,10)&&!e2(8,6)&&!e2(16,14)&&!e2(20,18)&&!wantsI&&!wantsM&&!s.pinched&&!s.rpinched&&!fist;
        if(midOnly){if(s.midSince==null)s.midSince=now;}else s.midSince=null;
        const useMid=midOnly&&(s.useMid||now-s.midSince>=t.poseHoldMs);s.useMid=useMid;
        const tip=useMid?points[12]:points[8];
        if(fist&&!s.grabOffset)s.grabOffset={x:(s.out?.x??tip.x)-wrist.x,y:(s.out?.y??tip.y)-wrist.y};if(!fist)s.grabOffset=null;
        const pos=s.cursor.filter(fist?wrist.x+s.grabOffset.x:tip.x,fist?wrist.y+s.grabOffset.y:tip.y,now/1000);
        s.trail.push({...pos,at:now});while(s.trail.length>1&&now-s.trail[0].at>t.trailMs)s.trail.shift();
        if(!s.pinched&&!s.rpinched){let aim=s.trail[0];for(const p of s.trail)if(p.at<=now-t.aimLagMs)aim=p;s.aim={x:aim.x,y:aim.y};}
        // the palm does not move when fingers close, so a press that drags follows the palm: a cursor riding a fingertip jumps a few
        // centimetres while pinching, which made every click look like a drag
        const palm=s.palmF.filter(PALM.reduce((a,j)=>a+points[j].x,0)/PALM.length,PALM.reduce((a,j)=>a+points[j].y,0)/PALM.length,now/1000);
        const rr=Math.atan2((1-raw[9].x)-(1-raw[0].x),-(raw[9].y-raw[0].y));
        s.rollU=s.rollRaw===null?rr:s.rollU+wrap(rr-s.rollRaw);s.rollRaw=rr;const roll=s.rollF.filter(s.rollU,now/1000);
        // Turning the forearm (how a fist is naturally rotated) barely moves the knuckle line in the picture but tips the knuckles in depth:
        // the index knuckle comes forward as the little-finger knuckle goes back. 5 Nov trace: this swings 15 degrees where the image roll swings 4.
        // Depth: the hand's size in the picture from its flat knuckle line and wrist-to-knuckle length (2D only: the camera's z estimate is noisy and made push/pull jitter). Bigger = nearer.
        if(!s.depthF)s.depthF=new OneEuro(.6,.03);const d2=(a,b)=>Math.hypot((raw[a].x-raw[b].x)*cw,(raw[a].y-raw[b].y)*ch),depth=s.depthF.filter(Math.sqrt(d2(0,9)*Math.max(1,d2(5,17))),now/1000);
        if(!s.twistF)s.twistF=new OneEuro(.8,.01);const twist=s.twistF.filter(Math.atan2(raw[17].z-raw[5].z,Math.max(1e-4,Math.abs(raw[17].x-raw[5].x))),now/1000);
        // Pitch: how far the hand is tipped toward or away from the camera (wrist to middle knuckle, depth against picture length). With roll and twist it is the whole wrist rotation.
        if(!s.pitchF)s.pitchF=new OneEuro(.8,.01);const pitch=s.pitchF.filter(Math.atan2(raw[9].z-raw[0].z,Math.max(1e-4,Math.hypot(raw[9].x-raw[0].x,raw[9].y-raw[0].y))),now/1000);
        // a fist is four fingertips pulled in to the palm; a pinch with the other fingers curled is NOT one (the index fingertip stays about a
        // hand-size away from the palm), and neither is anything where the thumb touches a fingertip, so a pinch can never start a tilt
        const ext=(a,b)=>d3(a,0)>d3(b,0)*t.extendRatio;
        const fingers={thumb:d3(4,0)>d3(2,0)*1.35||d3(4,6)>size*1.1,index:ext(8,6),middle:ext(12,10),ring:ext(16,14),pinky:ext(20,18)};
        const up=Object.values(fingers).filter(Boolean).length;
        const pose=pinched||rpinched||triple?'pinch':up>=4?'open':useMid?'middle':fingers.index&&!fingers.middle&&!fingers.ring&&!fingers.pinky?'point':fistShape?'fist':'none';
        if(pinched||rpinched||triple){s.held='pinch';s.pose='pinch';s.poseAt=now;}else if(s.pose!==pose){s.pose=pose;s.poseAt=now;if(s.held==='pinch')s.held='none';}else if(now-s.poseAt>=t.poseHoldMs){if(s.held!==pose&&s.held!=='pinch')s.changedAt=now;s.held=pose;}
        const flatShape=pose==='open'&&!pinched&&!rpinched&&!triple&&(s.flat?spread<t.flatOff:spread<t.flatOn);
        if(flatShape){if(s.flatSince==null)s.flatSince=now;}else s.flatSince=null;
        const flat=flatShape&&(s.flat||now-s.flatSince>=t.flatHoldMs);s.flat=flat;
        s.pinched=pinched;s.rpinched=rpinched;s.triple=triple;
        s.out={id,...pos,aimX:s.aim.x,aimY:s.aim.y,pinched,rpinched,triple,flat,hsize:rawSize,spread,sincePinch:s.lastPinchAt==null?1e9:now-s.lastPinchAt,gesture:s.held,points,span,fingers,pointerFinger:useMid?'middle':'index',handedness:label,palm,roll,twist,pitch,
               depth,conf:typeof conf==='number'?conf:1,openScore:up/5,flatScore:clamp(1-(spread-t.flatOn)/(t.flatOff-t.flatOn),0,1),near:clamp(1-(gap-t.pinchOn)/(t.pinchOff-t.pinchOn),0,1)>.3||clamp(1-(gapM-t.pinchOnM)/(t.pinchOffM-t.pinchOnM),0,1)>.3,idxRatio:d3(8,0)/Math.max(1e-6,d3(6,0)),midRatio:d3(12,0)/Math.max(1e-6,d3(10,0)),fistRatio:[8,12,16,20].reduce((a,i)=>a+dp(i),0)/4/size,fistScore:clamp(1-([8,12,16,20].reduce((a,i)=>a+dp(i),0)/4/size-.35)/(.75-.35),0,1),closeness:clamp(1-(gap-t.pinchOn)/(t.pinchOff-t.pinchOn),0,1),closenessM:clamp(1-(gapM-t.pinchOnM)/(t.pinchOffM-t.pinchOnM),0,1),gap,gapM};
        out.push(s.out);
      }
      for(const [id,s]of this.hands)if(!seen.has(id)){if(s.out)lost.push(s.out);this.hands.delete(id);}
      const open=out.length===1&&out[0].gesture==='open'&&!out[0].pinched&&!out[0].rpinched&&!out[0].triple;let fit=false;
      if(open){if(this.openSince===null)this.openSince=now;if(!this.fitLatched&&now-this.openSince>=t.fitHoldMs){fit=true;this.fitLatched=true;}}else{this.openSince=null;this.fitLatched=false;}
      return {hands:out,lost,fit,zoom:out.length===2&&out.every(h=>h.pinched)?{mid:{x:(out[0].palm.x+out[1].palm.x)/2,y:(out[0].palm.y+out[1].palm.y)/2},distance:distance(out[0].palm,out[1].palm)}:null};
    }
  }
  return {Engine,OneEuro,Point,TUNING,BONES,isClick,zoomMath,distance};
});
