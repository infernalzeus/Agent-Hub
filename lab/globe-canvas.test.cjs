'use strict';
process.chdir(__dirname);
// Browser-free refinement checks and screenshots with the native Canvas API.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const {createCanvas}=require(process.env.CANVAS_MODULE || '@napi-rs/canvas');
fs.mkdirSync('globe-verification',{recursive:true});
function emitter(target) {
  const listeners=new Map();
  target.addEventListener=(name,fn)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);};
  target.removeEventListener=(name,fn)=>listeners.get(name)?.delete(fn);
  target.emit=(name,event={})=>{if(!event.type)event.type=name;event.preventDefault||=()=>{};event.stopPropagation||=()=>{};for(const fn of listeners.get(name)||[])fn(event);};
  target.dispatchEvent=event=>{target.emit(event.type,event);return true;};
  return target;
}
function fixture(size,reduced=false) {
  let now=1000, callback, nextId=1;
  const doc=emitter({hidden:false});
  const image={hidden:false,style:{visibility:''}};
  const host=emitter({ownerDocument:doc,style:{position:'relative',width:'',height:''},getBoundingClientRect:()=>({left:0,top:0,width:size,height:size}),querySelectorAll:()=>[image],appendChild(c){this.canvas=c;c.parentNode=this;},removeChild(c){this.canvas=null;c.parentNode=null;}});
  doc.createElement=()=>{
    const c=emitter(createCanvas(1,1));c.style={};c.setAttribute=()=>{};
    c.getBoundingClientRect=host.getBoundingClientRect;c.setPointerCapture=()=>{};c.hasPointerCapture=()=>false;c.releasePointerCapture=()=>{};
    return c;
  };
  const window=emitter({document:doc,devicePixelRatio:2,Event,performance:{now:()=>now},getComputedStyle:()=>({position:'relative'}),requestAnimationFrame(fn){callback=fn;return nextId++;},cancelAnimationFrame(){callback=null;}});
  vm.runInNewContext(fs.readFileSync('assets/agent-hub-globe.js','utf8'),{window,console});
  const g=window.AgentHubGlobe.mount(host,{size,reducedMotion:reduced});
  function step(dt=1000/30){now+=dt;const fn=callback;callback=null;if(fn)fn(now);}
  return {host,g,image,window,step,advance(dt){now+=dt;}};
}
const report={checks:[]};
const f=fixture(220), c=f.host.canvas,ctx=c.getContext('2d');
let strokes=0,node=0,position=new Float64Array(2),spriteCount=0;
const originalStroke=ctx.stroke.bind(ctx),originalDraw=ctx.drawImage.bind(ctx);
ctx.stroke=function(){strokes++;originalStroke();};
ctx.drawImage=function(...args){
  if(args.length===9&&args[3]===32&&args[4]===32){if(node===200){position[0]=args[5]+args[7]/2;position[1]=args[6]+args[8]/2;}node++;spriteCount++;}
  originalDraw(...args);
};
function frame(){node=0;strokes=0;f.step();return Array.from(position);}
frame();assert.equal(node,576);assert.equal(strokes,64);
report.checks.push('576 nodes and live connection-packet pass');
c.emit('pointerenter',{pointerType:'mouse',clientX:110,clientY:110});
c.emit('pointermove',{pointerType:'mouse',clientX:145,clientY:122,pointerId:1});
frame();const before=Array.from(position);
c.emit('pointerleave');frame();const after=Array.from(position);
assert(Math.hypot(before[0]-after[0],before[1]-after[1])>.00001);
report.checks.push('idle rotation resumes immediately on pointer leave');
for(let i=0;i<120;i++)frame();
fs.writeFileSync('globe-verification/refined-live.png',c.toBuffer('image/png'));
let pulses=0;f.host.addEventListener('pulse',()=>pulses++);c.emit('click');assert.equal(pulses,1);
report.checks.push('click dispatches exactly one centre-out pulse');
for(let i=0;i<18;i++)frame();fs.writeFileSync('globe-verification/refined-pulse.png',c.toBuffer('image/png'));
f.g.setState('dormant');frame();assert.equal(strokes,32);c.emit('click');assert.equal(pulses,1);
fs.writeFileSync('globe-verification/refined-dormant.png',c.toBuffer('image/png'));
report.checks.push('dormant disables travelling highlights and click pulses');
f.g.destroy();assert.equal(f.host.canvas,null);assert.equal(f.image.hidden,false);
const still=fixture(72,true);const start=still.g.stats.frames;still.step();assert.equal(still.g.stats.frames,start);
fs.writeFileSync('globe-verification/refined-72.png',still.host.canvas.toBuffer('image/png'));still.g.destroy();
report.checks.push('refined small mark and reduced-motion still frame');
const measured=fixture(138);measured.step();const times=[];
for(let i=0;i<120;i++){const t=performance.now();measured.step();times.push(performance.now()-t);}
times.sort((a,b)=>a-b);
report.nativeCanvasTiming={samples:times.length,meanMs:times.reduce((a,b)=>a+b,0)/times.length,p95Ms:times[Math.floor(times.length*.95)],maxMs:times.at(-1),dpr:2,renderer:'@napi-rs/canvas CPU; not a browser performance measurement'};
measured.g.destroy();
const board=createCanvas(1056,480),boardCtx=board.getContext('2d');
boardCtx.fillStyle='#070a25';boardCtx.fillRect(0,0,1056,480);
for(let i=0;i<3;i++){
  const g=fixture(220,true);for(let j=0;j<i*8;j++)g.host.canvas.emit('keydown',{key:'ArrowRight'});
  for(let j=0;j<i*3;j++)g.host.canvas.emit('keydown',{key:'ArrowUp'});
  boardCtx.drawImage(g.host.canvas,i*352+20,20,312,312);g.g.destroy();
}
fs.writeFileSync('globe-verification/refined-orientations.png',board.toBuffer('image/png'));
fs.writeFileSync('globe-verification/refinement-report.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));

