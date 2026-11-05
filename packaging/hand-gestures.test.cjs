const {test}=require('node:test');const assert=require('node:assert/strict');
const G=require('../hub/static/hand-gestures.js');
// the older tests feed one frame at a time and expect the hand at once; the presence rule has its own test at the end
{const E0=G.Engine;G.Engine=class extends E0{constructor(o={}){super({...o,tuning:{presentFrames:1,...(o.tuning||{})}});}};}
function marks(x=.5,gap=1,open=false){const a=Array.from({length:21},()=>({x,y:.7,z:0}));a[0]={x,y:.8,z:0};a[9]={x,y:.6,z:0};a[2]={x:x+.04,y:.7,z:0};a[6]={x:x-.05,y:.5,z:0};a[8]={x:x-.05,y:.3,z:0};a[4]={x:a[8].x+gap*.16,y:.3,z:0};for(const [pip,tip]of [[10,12],[14,16],[18,20]]){a[pip]={x:x+(pip-14)*.012,y:.55,z:0};a[tip]={x:a[pip].x,y:open?.27:.69,z:0};}return a;}
const result=(...hands)=>({landmarks:hands,handedness:hands.map(()=>[{categoryName:'Right',score:1}])});
function feed(e,gap,from,to,open=false){let out;for(let t=from;t<=to;t+=20)out=e.update(result(marks(.5,gap,open)),t,1000,800);return out;}
test('pinch on/off thresholds have hysteresis',()=>{let e=new G.Engine();feed(e,1,0,500);assert.equal(feed(e,.15,520,900).hands[0].pinched,true);assert.equal(feed(e,.28,920,1300).hands[0].pinched,true);assert.equal(feed(e,.5,1320,1700).hands[0].pinched,false);});
test('pinch confirms at 70ms, not a transient frame',()=>{let e=new G.Engine({tuning:{settleMs:0}});assert.equal(e.update(result(marks(.5,.1)),0,1000,800).hands[0].pinched,false);assert.equal(e.update(result(marks(.5,.1)),69,1000,800).hands[0].pinched,false);assert.equal(e.update(result(marks(.5,.1)),70,1000,800).hands[0].pinched,true);});
test('new pose settles for 220ms before pressing',()=>{let e=new G.Engine();for(const t of [0,70,200,419])assert.equal(e.update(result(marks(.5,.1)),t,1000,800).hands[0].pinched,false);assert.equal(e.update(result(marks(.5,.1)),420,1000,800).hands[0].pinched,true);});
test('press aims at the recent trail, 190ms before closure',()=>{let e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),trail=[];for(let i=0;i<5;i++)trail.push(e.update(result(marks(.4+i*.02,1)),i*100,1000,800).hands[0]);let pressed=e.update(result(marks(.5,.1)),500,1000,800).hands[0];assert.equal(pressed.pinched,true);assert.equal(pressed.aimX,trail[3].x);});
test('click slop rejects drags even if they return to the start',()=>{assert.equal(G.isClick({x:0,y:0},{x:10,y:10}),true);assert.equal(G.isClick({x:0,y:0},{x:20,y:0}),false);assert.equal(G.isClick({x:0,y:0},{x:1,y:1},25),false);});
test('a disappearing pinched hand is explicitly reported lost',()=>{let e=new G.Engine();feed(e,.1,0,600);let o=e.update(result(),620,1000,800);assert.equal(o.hands.length,0);assert.equal(o.lost.length,1);assert.equal(o.lost[0].pinched,true);});
test('hand identity survives array reorder and labels changing',()=>{let e=new G.Engine();let a=e.update(result(marks(.25),marks(.75)),0,1000,800);let b=e.update(result(marks(.75),marks(.25)),20,1000,800);assert.equal(a.hands[0].id,b.hands[1].id);assert.equal(a.hands[1].id,b.hands[0].id);});
test('a teleport discards the old press rather than moving it across the board',()=>{let e=new G.Engine();e.update(result(marks(.1,.1)),0,1000,800);let b=e.update(result(marks(.9,.1)),300,1000,800);assert.equal(b.lost.length,1);assert.equal(b.hands[0].pinched,false);});
test('two-hand zoom preserves its world midpoint and respects scale bounds',()=>{const z=G.zoomMath({x:50,y:50},{x:250,y:50},{distance:100,scale:1,world:{x:100,y:20}});assert.equal(z.scale,2);assert.equal(z.x+100*z.scale,150);assert.equal(z.y+20*z.scale,50);});
test('open hand held triggers FIT once per hold',()=>{let e=new G.Engine();let fits=0;for(let t=0;t<=1800;t+=20)fits+=Number(e.update(result(marks(.5,1,true)),t,1000,800).fit);assert.equal(fits,1);});
test('One Euro suppresses stationary noise without freezing a fast move',()=>{let f=new G.OneEuro(),v=[];for(let i=0;i<150;i++)v.push(f.filter(500+(i%2?5:-5),i/30));const rms=Math.sqrt(v.slice(30).reduce((s,x)=>s+(x-500)**2,0)/120);assert.ok(rms<2.5,rms);let end;for(let i=150;i<155;i++)end=f.filter(700,i/30);assert.ok(end>670,end);});
test('non-advancing timestamps cannot emit another pinch transition',()=>{let e=new G.Engine();let a=e.update(result(marks(.5,1)),10,1000,800);let b=e.update(result(marks(.5,.1)),10,1000,800);assert.equal(b.stale,true);assert.equal(b.hands[0].pinched,a.hands[0].pinched);});
test('a relaxed hand, thumb a few centimetres from the index finger, is not a pinch (the false pinches seen on a real hand)',()=>{const e=new G.Engine();let o;for(let t=0;t<2000;t+=20)o=e.update(result(marks(.5,.45)),t,1000,800).hands[0];assert.equal(o.pinched,false);assert.ok(o.gap>.34,o.gap);});
test('fingertips that overlap in the picture but are far apart in depth are not a pinch',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,.05);a[4]={...a[4],z:-.25};let o;for(let t=0;t<600;t+=20)o=e.update(result(a),t,1000,800).hands[0];assert.equal(o.pinched,false);assert.ok(o.gap>.34,o.gap);});
test('the palm stays put while the fingers close, so a click does not look like a drag',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}});let before,after;for(let t=0;t<600;t+=20)before=e.update(result(marks(.5,1)),t,1000,800).hands[0];for(let t=620;t<1200;t+=20)after=e.update(result(marks(.5,.1)),t,1000,800).hands[0];assert.ok(Math.hypot(after.palm.x-before.palm.x,after.palm.y-before.palm.y)<3);assert.equal(after.pinched,true);});
test('thumb, index and middle together is a zoom hold of its own, neither single pinch',()=>{const e=new G.Engine({tripleZoom:true,tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:(a[8].x+a[12].x)/2,y:(a[8].y+a[12].y)/2,z:0};let h=e.update(result(a),0,1000,800).hands[0];assert.equal(h.triple,false);      // not yet: the first moments of the hold may still be a left pinch
  for(let t=20;t<=400;t+=20)h=e.update(result(a),t,1000,800).hands[0];assert.equal(h.triple,true);assert.equal(h.pinched||h.rpinched,false);});
test('a three-finger hold that began as a left pinch hands over to the zoom after a moment',()=>{const e=new G.Engine({tripleZoom:true,tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:(a[8].x+a[12].x)/2,y:(a[8].y+a[12].y)/2,z:0};let h=e.update(result(a),0,1000,800).hands[0];assert.equal(h.pinched,true);for(let t=20;t<=400;t+=20)h=e.update(result(a),t,1000,800).hands[0];assert.equal(h.pinched,false);assert.equal(h.triple,true);});
test('a closed fist reads as a fist once held, and the roll follows a turn of the wrist',()=>{const e=new G.Engine();let o;const fist=()=>{const a=marks(.5,1);for(const [tip,pip]of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.78,z:0};a[4]={x:.62,y:.72,z:0};return a;};for(let t=0;t<600;t+=20)o=e.update(result(fist()),t,1000,800).hands[0];assert.equal(o.gesture,'fist');const r0=o.roll;const turn=(a,rad)=>a.map(p=>{const dx=p.x-.5,dy=p.y-.8;return{x:.5+dx*Math.cos(rad)-dy*Math.sin(rad),y:.8+dx*Math.sin(rad)+dy*Math.cos(rad),z:0};});for(let t=620;t<1400;t+=20)o=e.update(result(turn(fist(),.5)),t,1000,800).hands[0];assert.ok(Math.abs(Math.abs(o.roll-r0)-.5)<.12,o.roll-r0);});
test('a pinch with the other three fingers curled is never read as a fist, so it can never start a tilt',()=>{const e=new G.Engine();const a=marks(.5,.1);for(const [tip,pip]of [[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.78,z:0};const seen=new Set();let o;for(let t=0;t<1500;t+=20){o=e.update(result(a),t,1000,800).hands[0];seen.add(o.gesture);}assert.ok(!seen.has('fist'),[...seen].join());assert.equal(o.pinched,true);});
test('the half-curled approach to a pinch, index still reaching toward the thumb, is not a fist either',()=>{const e=new G.Engine();const a=marks(.5,.5);for(const [tip,pip]of [[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.78,z:0};const seen=new Set();for(let t=0;t<1500;t+=20)seen.add(e.update(result(a),t,1000,800).hands[0].gesture);assert.ok(!seen.has('fist'),[...seen].join());});
test('a tight fist with the thumb across the fingers is a fist, and a pinch within 700 ms of it is remembered',()=>{const e=new G.Engine();const a=marks(.5,1);for(const [tip,pip]of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.74,z:0};a[4]={x:a[8].x+.09,y:.7,z:0};let o;for(let t=0;t<800;t+=20)o=e.update(result(a),t,1000,800).hands[0];assert.equal(o.gesture,'fist');assert.ok(o.sincePinch>700);});
test('sincePinch counts up from the last pinch',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}});let o=e.update(result(marks(.5,.1)),0,1000,800).hands[0];assert.equal(o.pinched,true);for(let k=20;k<=300;k+=20)o=e.update(result(marks(.5,1,true)),k,1000,800).hands[0];assert.ok(o.sincePinch>200&&o.sincePinch<400,o.sincePinch);});
test('a larger tolerance accepts a click that a small one calls a drag',()=>{assert.equal(G.isClick({x:0,y:0},{x:30,y:0}),false);assert.equal(G.isClick({x:0,y:0},{x:30,y:0},0,64),true);});
module.exports={marks,result};

test('thumb to middle finger is a second, separate pinch while the cursor stays on the index finger',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={...a[12],x:a[12].x+.004};a[8]={...a[8],x:a[8].x-.14};const h=e.update(result(a),0,1000,800).hands[0];assert.equal(h.pointerFinger,'index');assert.equal(h.rpinched,true);assert.equal(h.pinched,false);});
test('a fist cannot initiate a grab',()=>{const e=new G.Engine({fistGrab:true});const a=marks();for(const [tip,pip]of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.78,z:0};a[4]={x:.95,y:.1,z:0};let o;for(let t=0;t<1000;t+=20)o=e.update(result(a),t,1000,800);assert.equal(o.hands[0].pinched,false);});

test('optional fist continues an established pinch then releases on open',()=>{const e=new G.Engine({fistGrab:true});feed(e,.1,0,600);const a=marks();for(const [tip,pip]of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:.78,z:0};a[4]={x:.95,y:.1,z:0};let o;for(let t=620;t<=1100;t+=20)o=e.update(result(a),t,1000,800);assert.equal(o.hands[0].pinched,true);o=feed(e,1,1120,1600,true);assert.equal(o.hands[0].pinched,false);});


test('a left pinch with the middle finger resting beside the index finger stays a left pinch (the middle finger has the wider threshold)',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:a[8].x+.03,y:a[8].y,z:0};let h=e.update(result(a),0,1000,800).hands[0];assert.equal(h.pinched,true);assert.equal(h.rpinched,false);for(let t=20;t<=200;t+=20)h=e.update(result(a),t,1000,800).hands[0];assert.equal(h.pinched,true);assert.equal(h.triple,false);});      // a quick pinch (under the 260 ms hold) stays a left click
test('a thumb on the middle fingertip with the index finger away is the right press',()=>{const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:a[12].x+.012,y:a[12].y,z:0};a[8]={...a[8],x:a[8].x-.14};const h=e.update(result(a),0,1000,800).hands[0];assert.equal(h.rpinched,true);assert.equal(h.pinched,false);});

const feedN=(e,a,from,to,step=20)=>{let h;for(let t=from;t<=to;t+=step)h=e.update(result(a),t,1000,800).hands[0];return h;};
test('pointing with the curled middle finger resting against the thumb is not a right press',()=>{
  const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,false);a[4]={x:a[12].x+.012,y:a[12].y,z:0};a[8]={...a[8],x:a[8].x-.14};   // point pose (ring and little finger curled) with the thumb on the curled middle finger
  const h=feedN(e,a,0,600);assert.equal(h.rpinched,false);assert.equal(h.gesture,'point');
});
test('a right press needs the ring or little finger out (the thumb on the middle fingertip, hand otherwise open)',()=>{
  const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:a[12].x+.012,y:a[12].y,z:0};a[8]={...a[8],x:a[8].x-.14};
  assert.equal(feedN(e,a,0,300).rpinched,true);
});
test('a flat palm (open, fingers together) engages after a short hold and reports its size; spread fingers do not',()=>{
  const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);let h=feedN(e,a,0,100);assert.equal(h.flat,false);
  h=feedN(e,a,120,700);assert.equal(h.flat,true);assert.ok(h.hsize>0);
  const w=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),b=marks(.5,1,true);b[8]={...b[8],x:b[8].x-.2};b[20]={...b[20],x:b[20].x+.2};      // fingers spread wide
  assert.equal(feedN(w,b,0,900).flat,false);
});
test('thumb, index and middle touching is the zoom hold, and the same hand with the index finger away is a right press: they cannot both be true',()=>{
  const zoom=new G.Engine({tripleZoom:true,tuning:{settleMs:0,confirmMs:0}}),b=marks(.5,1,true);b[4]={x:(b[8].x+b[12].x)/2,y:(b[8].y+b[12].y)/2,z:0};const hz=feedN(zoom,b,0,400);assert.equal(hz.triple,true);assert.equal(hz.rpinched,false);
  const right=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),c=marks(.5,1,true);c[4]={x:c[12].x+.012,y:c[12].y,z:0};c[8]={...c[8],x:c[8].x-.14};const hr=feedN(right,c,0,400);assert.equal(hr.rpinched,true);assert.equal(hr.triple,false);
});

test('the three-finger zoom hold is opt-in: by default a pinch with the middle finger resting beside it stays a left press (5 Nov trace: 10 of 15 left presses were cancelled by it)',()=>{
  const e=new G.Engine({tuning:{settleMs:0,confirmMs:0}}),a=marks(.5,1,true);a[4]={x:(a[8].x+a[12].x)/2,y:(a[8].y+a[12].y)/2,z:0};let h;for(let t=0;t<=600;t+=20)h=e.update(result(a),t,1000,800).hands[0];
  assert.equal(h.triple,false);assert.equal(h.pinched,true);
});

test('a hand must be present for 3 frames and plausible before it exists (ghost detections of 5 Nov)',()=>{
  const e=new G.Engine({tuning:{presentFrames:3}});
  assert.equal(e.update(result(marks(.5,1)),0,1000,800).hands.length,0);assert.equal(e.update(result(marks(.5,1)),80,1000,800).hands.length,0);
  assert.equal(e.update(result(marks(.5,1)),160,1000,800).hands.length,1);
  const f=new G.Engine({tuning:{presentFrames:1}}),low={landmarks:[marks(.5,1)],handedness:[[{categoryName:'Right',score:.3}]]};
  assert.equal(f.update(low,0,1000,800).hands.length,0);                                   // the model itself was unsure
  const tiny=marks(.5,1);tiny[9]={x:.5,y:.79,z:0};
  assert.equal(f.update(result(tiny),100,1000,800).hands.length,0);                        // far too small to be a hand
});
