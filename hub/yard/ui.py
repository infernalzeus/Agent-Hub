"""The R panel (EXPERIMENTAL): the yard with its flow and the settings each block owns, TEACH, the routines, and the scores. Nothing else.

YARD    start or stop a session; the architecture as small blocks that light as information travels; click a block to see what it does and change its settings.
TEACH   grade what the Hub did (requests, missions, PC tasks) in /teach.
ROUTINES  the saved routines, which are attested, what the yard found out about the candidates, and FRESH START.
SCORES  how each part is doing against what, and the methods that could replace the current ones.
"""
from __future__ import annotations

from aiohttp import web

from ..embed import embedded

routes = web.RouteTableDef()

_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"><meta name="color-scheme" content="dark">
<title>AGENT HUB - Reinforcement learning</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
:root{--accent:#00e676;--text:rgba(214,245,230,.92);--mute:rgba(214,245,230,.58);--amber:#e0a53c;--red:#ff5c5c;--blue:#3ba7ff;--border:rgba(0,230,118,.22);--panel:rgba(8,12,40,.88)}
body{background:#080c28;color:var(--text);font:12.5px/1.4 Outfit,system-ui,sans-serif;padding:10px max(12px,env(safe-area-inset-left)) 24px}
main{max-width:1100px;margin:0 auto}
h2{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);margin:12px 0 4px}
.row{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:6px 0}
button{background:var(--panel);color:var(--accent);border:1px solid var(--accent);border-radius:7px;padding:5px 10px;font:700 10px Orbitron,system-ui,sans-serif;letter-spacing:.08em;cursor:pointer}
button:disabled{opacity:.5;cursor:default}button.on{background:var(--accent);color:#04120a}button.stop{border-color:var(--red);color:var(--red)}button.part{border-color:var(--amber);color:var(--amber)}button.skip{border-color:var(--border);color:var(--mute)}button.no{border-color:var(--red);color:var(--red)}
.chip{border:1px solid var(--border);border-radius:99px;padding:1px 8px;font-size:11px;color:var(--mute);display:inline-block}.chip.ok{color:var(--accent);border-color:var(--accent)}.chip.part{color:var(--amber);border-color:var(--amber)}.chip.no{color:var(--red);border-color:var(--red)}
.mute{color:var(--mute)}.yes{color:var(--accent)}.no{color:var(--red)}
.tabs{display:flex;gap:5px;margin:8px 0 4px;flex-wrap:wrap}.tabs button{padding:5px 12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:8px 10px;margin:6px 0}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:11.5px}
th{font:700 9.5px Orbitron,system-ui,sans-serif;letter-spacing:.06em;color:var(--accent);text-align:left;padding:4px 8px;border-bottom:1px solid var(--border)}td{padding:3px 8px;border-bottom:1px solid rgba(0,230,118,.08);vertical-align:top}
section{animation:fadein .18s ease}@keyframes fadein{from{opacity:0}to{opacity:1}}@media (prefers-reduced-motion:reduce){section{animation:none}}
iframe.teach{width:100%;height:80vh;min-height:460px;border:1px solid var(--border);border-radius:10px;background:#080c28}
#top-shadow.on{background:var(--accent);color:#04120a}
.flowwrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:rgba(8,12,40,.6);margin:6px 0}#flowsvg{width:100%;min-width:720px;height:auto;display:block}
.fnode{cursor:pointer}.fnode rect{fill:rgba(8,12,40,.92);stroke-width:1.8}.fnode.tested rect{stroke:#3ba7ff}.fnode.built rect{stroke:#e0a53c}.fnode.user rect{stroke:#00e676}.fnode.todo rect{stroke:#ff5c5c;stroke-dasharray:6 4}.fnode.now rect{stroke:#41ebff;stroke-dasharray:3 4}
.fnode text.ft{fill:#d6f5e6;font:700 14px Orbitron,system-ui,sans-serif}.fnode text.fl{fill:#9fe7c0;font:12px Outfit,system-ui,sans-serif}
.fnode.sel rect{stroke-width:3.4}.fnode.pulse rect{fill:rgba(20,40,70,.95);stroke-width:3.2}.fnode.improved rect{stroke:#00e676;stroke-width:4;filter:drop-shadow(0 0 7px #00e676)}
.fedge path{stroke:#6c8f7d;stroke-width:1.6;fill:none}.fedge.lit path{stroke:#41ebff;stroke-width:3.4;stroke-dasharray:10 6;animation:fdash .5s linear infinite}
@keyframes fdash{to{stroke-dashoffset:-16}}@media (prefers-reduced-motion:reduce){.fedge.lit path{animation:none}}
.krow{display:grid;grid-template-columns:minmax(140px,1.3fr) minmax(110px,2fr) 44px 30px;gap:2px 10px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(0,230,118,.08)}.krow:last-child{border:0}
.krow label{font-size:12px}.krow input[type=range]{width:100%;accent-color:var(--accent)}.krow select{font:11.5px Outfit,sans-serif;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:3px}
.krow .kv{font-size:11px;color:var(--amber)}.krow button.i{width:24px;height:24px;padding:0;border-radius:50%;font:700 12px Outfit,sans-serif;margin:0}
details>summary{cursor:pointer;color:var(--accent);font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.08em;padding:6px 0}details h2{margin-top:8px}
.rc .said{font-size:13.5px;margin-bottom:4px}.rc .why{font-size:11.5px;color:var(--mute);margin-top:3px}
.wy{border:1px solid var(--border);border-radius:8px;padding:8px;margin:6px 0;background:rgba(0,0,0,.2)}.wy h4{margin:0 0 4px;font:600 12px Outfit,system-ui,sans-serif}.wy .cand{display:grid;grid-template-columns:minmax(250px,1.6fr) 150px 2fr;gap:8px;align-items:center;font-size:11.5px;margin:2px 0}.wy .bar{height:7px;border-radius:4px;background:rgba(255,255,255,.08)}.wy .bar i{display:block;height:100%;border-radius:4px;background:var(--accent)}.wy .cand.top .nm{color:var(--accent)}.wy .cand.pr .nm:after{content:"  ◀ pressed";color:#e0a53c}.wy .bc{color:var(--mute);font-size:10.5px}.wy .mv{font-size:11px;color:#9fe7c0;margin-top:3px}
.band{background:rgba(0,230,118,.05);border:1px solid var(--border);border-radius:10px;padding:7px 10px;margin:0 0 8px}
.sess{border:1px solid rgba(0,230,118,.45);border-radius:12px;padding:0;margin:14px 0 8px;background:rgba(8,12,40,.55);overflow:hidden}
.sess-head{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--border);background:rgba(0,230,118,.06)}
.sess-head .ttl{font:700 11px Orbitron,system-ui,sans-serif;letter-spacing:.1em;color:var(--mute)}.sess-head .sp{flex:1}
button.big{background:var(--accent);color:#04120a;padding:8px 16px;font-size:11px}button.big:disabled{opacity:.5}
#result{padding:6px 12px 0}.sess .flowwrap{border:0;border-radius:0;background:transparent;margin:0}.sess #flog{padding:0 12px 8px}
.fnode.outside rect{stroke-dasharray:4 3;fill-opacity:.7}.fnode text.fl{fill:#9fe7c0}.fnode.outside text.fl{fill:#6c8f7d}
.fnode .fi circle{fill:rgba(8,12,40,.9);stroke:var(--accent);stroke-width:1.3}.fnode .fi text{fill:var(--accent);font:700 12px Outfit,sans-serif;pointer-events:none}.fnode .fi{cursor:pointer}
.fnode .fx{opacity:0;cursor:pointer;transition:opacity .15s}.fnode:hover .fx{opacity:.9}.fnode .fx circle{fill:rgba(8,12,40,.9);stroke:var(--mute);stroke-width:1.2}.fnode .fx text{fill:var(--mute);font:700 12px Outfit,sans-serif;pointer-events:none}
.fedge .hit{stroke:transparent;stroke-width:12;fill:none;cursor:pointer}.fedge.sel path:not(.hit){stroke:var(--accent);stroke-width:2.2}.fnode{touch-action:none}.fnode.pulse{filter:none}
.nh{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}.nh .sp{flex:1}.sub{font:700 10px Orbitron,system-ui,sans-serif;letter-spacing:.08em;color:var(--accent);margin:8px 0 2px}
.inside{border:1px solid var(--border);border-radius:8px;padding:8px;margin:6px 0;background:rgba(0,0,0,.2)}.irow{font-size:11.5px;margin:2px 0}.irow b{color:var(--accent);font-weight:600}
.chain{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:6px}.chain .arrow{color:var(--mute)}.chain .lay{border:1px solid var(--accent);border-radius:7px;padding:3px 8px;text-align:center;min-width:70px}.chain .ls{font:700 14px Orbitron,system-ui,sans-serif;color:var(--accent)}.chain .ln{font-size:10px;color:var(--mute)}
pre.formula{font:11.5px/1.5 Consolas,monospace;color:#9fe7c0;margin-top:6px;white-space:pre-wrap}
</style></head><body><main>
<div class="band"><div class="row" id="topbar" style="margin:0"><span class="chip part">EXPERIMENTAL</span><button id="top-shadow" type="button" aria-pressed="false"></button><span class="mute" id="top-note"></span></div></div>
<div class="tabs" role="tablist"><button type="button" data-tab="yard" class="on">YARD</button><button type="button" data-tab="teach">TEACH</button><button type="button" data-tab="routines">ROUTINES</button><button type="button" data-tab="scores">SCORES</button></div>

<section id="tab-yard">
<div class="sess">
<div class="sess-head"><span class="ttl">SESSION</span><button id="go" type="button" class="big">START A SESSION</button><button id="stop" type="button" class="stop" hidden>STOP</button><span class="mute" id="phase"></span><span class="chip part" id="msg" hidden></span><span class="sp"></span><button id="showall" type="button" class="skip" hidden>RESET LAYOUT</button><button id="kreset" type="button" class="stop" hidden>RESET SETTINGS</button></div>
<div class="mute" id="result"></div>
<div class="flowwrap"><svg id="flowsvg" role="img" aria-label="The learning layer"></svg></div>
<div class="mute" id="flog"></div>
</div>
<div class="card" id="nodebox" hidden></div>
</section>

<section id="tab-teach" hidden><iframe class="teach" id="teachframe" title="Teach" data-src="/teach"></iframe></section>

<section id="tab-routines" hidden>
<div class="row"><span class="mute" id="freshnote"></span><button id="fresh" type="button" class="part">FRESH START</button></div>
<div id="rlist"></div>
<h2>RECENT LIVE TASKS</h2><div class="mute" id="livenote"></div><div id="livelist"></div>
</section>

<section id="tab-scores" hidden>
<div class="wrap"><table id="fit"></table></div>
<h2>METHODS BEHIND EACH CHOICE</h2><div class="wrap"><table id="chal"></table></div>
<div class="mute" id="knn"></div><div class="mute" id="gateline"></div><div class="mute" id="tevline"></div>
</section>
</main>
<script>
(function(){
  const $=id=>document.getElementById(id),pct=v=>Math.round(v*100)+' %';
  const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
  const J=(u,o)=>fetch(u,Object.assign({cache:'no-store'},o||{})).then(r=>r.json());
  const POST=(u,b)=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  function head(t,cols){t.replaceChildren();const r=el('tr');cols.forEach(c=>r.appendChild(el('th',null,c)));t.appendChild(r);}

  // ---- the switch at the top
  function lamp(on){try{parent.postMessage({hubShadow:!!on},location.origin);}catch(e){}}
  async function switches(){try{const j=await J('/api/yard/settings'),sh=j.shadow||{},t=$('top-shadow');
    t.textContent='SHADOW MODE: '+(sh.on?'ON':'OFF');t.setAttribute('aria-pressed',String(!!sh.on));t.classList.toggle('on',!!sh.on);t.disabled=!!sh.forced_off_by_environment;
    t.onclick=async()=>{t.disabled=true;try{await POST('/api/yard/settings',{shadow:!sh.on,learning:!sh.on});}finally{await switches();}};lamp(sh.on);
    $('top-note').textContent=sh.forced_off_by_environment?'Held off by an environment variable.':sh.on?'Observing. Nothing is pressed.':'Off. Nothing is recorded.';}catch(e){}}

  // ---- YARD: the architecture as small blocks you can move, with the inside of each block one click away
  let CV=null,KN=null,gById={},eEls=[],lastN=0,timer=0,wasRunning=false,flog=[],sel=null,showInside=false,saveT={},POS={},HID=new Set(),NODE={};
  const NS='http://www.w3.org/2000/svg',sv=(t,a,x)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(x!=null)e.textContent=x;return e;};
  const LS='hub-rl-flow';
  function loadLayout(){try{const j=JSON.parse(localStorage.getItem(LS)||'{}');POS=j.pos||{};HID=new Set(j.hid||[]);}catch(e){POS={};HID=new Set();}}
  function saveLayout(){try{localStorage.setItem(LS,JSON.stringify({pos:POS,hid:[...HID]}));}catch(e){}}
  const at=n=>POS[n.id]||[n.x,n.y];
  function anchor(n,s){const [x,y]=at(n);return s==='left'?[x,y+n.height/2]:s==='right'?[x+n.width,y+n.height/2]:s==='top'?[x+n.width/2,y]:[x+n.width/2,y+n.height];}
  const dir=s=>s==='left'?[-1,0]:s==='right'?[1,0]:s==='top'?[0,-1]:[0,1];
  // Arrows run in straight lines with square corners through the gaps between blocks, never across one: a small grid search per arrow, blocks as walls, a cost for each turn and for
  // running along another arrow. It is redone whenever a block moves or is hidden, so the picture stays readable wherever you put things.
  const GRID=10,PAD=7,SIDE={right:0,bottom:1,left:2,top:3};
  function heapPush(h,x){h.push(x);let i=h.length-1;while(i>0){const q=(i-1)>>1;if(h[q][0]<=h[i][0])break;[h[q],h[i]]=[h[i],h[q]];i=q;}}
  function heapPop(h){const top=h[0],last=h.pop();if(h.length){h[0]=last;let i=0;for(;;){const l=2*i+1,r=l+1;let m=i;if(l<h.length&&h[l][0]<h[m][0])m=l;if(r<h.length&&h[r][0]<h[m][0])m=r;if(m===i)break;[h[m],h[i]]=[h[i],h[m]];i=m;}}return top;}
  function rounded(p,r){let d='M'+p[0][0]+' '+p[0][1];for(let i=1;i<p.length-1;i++){const a=p[i-1],b=p[i],c=p[i+1],l1=Math.hypot(b[0]-a[0],b[1]-a[1]),l2=Math.hypot(c[0]-b[0],c[1]-b[1]),k=Math.min(r,l1/2,l2/2);
      d+=' L'+(b[0]+(a[0]-b[0])/l1*k)+' '+(b[1]+(a[1]-b[1])/l1*k)+' Q'+b[0]+' '+b[1]+' '+(b[0]+(c[0]-b[0])/l2*k)+' '+(b[1]+(c[1]-b[1])/l2*k);}
    const z=p[p.length-1];return d+' L'+z[0]+' '+z[1];}
  function routeAll(){
    const vis=CV.nodes.filter(n=>!HID.has(n.id));if(!vis.length)return {};
    let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;vis.forEach(n=>{const [x,y]=at(n);x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x+n.width);y1=Math.max(y1,y+n.height);});
    const ox=Math.floor((x0-55)/GRID)*GRID+5,oy=Math.floor((y0-55)/GRID)*GRID+5,W=Math.ceil((x1-ox+60)/GRID),H=Math.ceil((y1-oy+60)/GRID),wall=new Uint8Array(W*H),used=new Uint8Array(W*H);
    const cx=x=>Math.floor((x-ox)/GRID),cy=y=>Math.floor((y-oy)/GRID),inb=(i,j)=>i>=0&&j>=0&&i<W&&j<H;
    vis.forEach(n=>{const [x,y]=at(n);for(let i=cx(x-PAD);i<=cx(x+n.width+PAD);i++)for(let j=cy(y-PAD);j<=cy(y+n.height+PAD);j++)if(inb(i,j))wall[j*W+i]=1;});
    const D=[[1,0],[0,1],[-1,0],[0,-1]],out={};
    // several arrows meeting one side of a block are spread along it (in the order of where they come from) instead of piling onto one point
    const slot={};CV.edges.forEach(e=>{if(HID.has(e.fromNode)||HID.has(e.toNode))return;[[e.fromNode,e.fromSide,e.toNode,'f'],[e.toNode,e.toSide,e.fromNode,'t']].forEach(([n,s,o,w])=>{(slot[n+'|'+s]=slot[n+'|'+s]||[]).push([e.id+'#'+w,o]);});});
    Object.keys(slot).forEach(k=>{const hz=k.endsWith('top')||k.endsWith('bottom');slot[k].sort((a,b)=>{const pa=at(NODE[a[1]]),pb=at(NODE[b[1]]);return (hz?pa[0]-pb[0]:pa[1]-pb[1])||(a[0]<b[0]?-1:1);});});
    const anchorE=(e,w)=>{const n=w==='f'?e.fromNode:e.toNode,s=w==='f'?e.fromSide:e.toSide,L=slot[n+'|'+s],i=L.findIndex(q=>q[0]===e.id+'#'+w),hz=s==='top'||s==='bottom',o=(i-(L.length-1)/2)*(hz?40:20),p=anchor(NODE[n],s);return hz?[p[0]+o,p[1]]:[p[0],p[1]+o];};
    const list=CV.edges.filter(e=>!HID.has(e.fromNode)&&!HID.has(e.toNode)).map(e=>{const pa=anchorE(e,'f'),pb=anchorE(e,'t');return {e,pa,pb,len:Math.abs(pa[0]-pb[0])+Math.abs(pa[1]-pb[1])};}).sort((p,q)=>p.len-q.len);
    list.forEach(({e,pa,pb})=>{
      const da=dir(e.fromSide),db=dir(e.toSide),gap=GRID*1.2,d0=SIDE[e.fromSide];
      const sa=[pa[0]+da[0]*gap,pa[1]+da[1]*gap],sb=[pb[0]+db[0]*gap,pb[1]+db[1]*gap];
      const s=[cx(sa[0]),cy(sa[1])],g=[cx(sb[0]),cy(sb[1])];
      const key=(i,j,d)=>(j*W+i)*4+d,best=new Map(),from=new Map(),open=[],hh=(i,j)=>Math.abs(i-g[0])+Math.abs(j-g[1]);
      best.set(key(s[0],s[1],d0),0);heapPush(open,[hh(s[0],s[1]),0,s[0],s[1],d0]);
      let found=null,guard=0;
      while(open.length&&guard++<80000){const [,c,i,j,d]=heapPop(open);if(c>(best.has(key(i,j,d))?best.get(key(i,j,d)):1e9))continue;if(i===g[0]&&j===g[1]){found=[i,j,d];break;}
        for(let nd=0;nd<4;nd++){if((nd+2)%4===d)continue;const ni=i+D[nd][0],nj=j+D[nd][1];if(!inb(ni,nj))continue;
          if(wall[nj*W+ni]&&!(ni===g[0]&&nj===g[1])&&!(ni===s[0]&&nj===s[1]))continue;
          const nc=c+1+(nd!==d?5:0)+(used[nj*W+ni]?4:0),k=key(ni,nj,nd);
          if(nc<(best.has(k)?best.get(k):1e9)){best.set(k,nc);from.set(k,[i,j,d]);heapPush(open,[nc+hh(ni,nj),nc,ni,nj,nd]);}}}
      const cell=(i,j)=>[ox+i*GRID+GRID/2,oy+j*GRID+GRID/2];
      let pts;
      if(found){let cur=found;const rev=[];while(cur){rev.push([cur[0],cur[1]]);cur=from.get(key(cur[0],cur[1],cur[2]));}rev.reverse();pts=rev.map(c=>cell(c[0],c[1]));rev.forEach(c=>{used[c[1]*W+c[0]]=1;});}
      else pts=[sa,sb];
      const first=da[0]!==0?[pts[0][0],pa[1]]:[pa[0],pts[0][1]],last=db[0]!==0?[pts[pts.length-1][0],pb[1]]:[pb[0],pts[pts.length-1][1]];
      const clean=[];[pa,first,...pts,last,pb].forEach(q=>{const n=clean.length;if(n&&Math.abs(clean[n-1][0]-q[0])<.5&&Math.abs(clean[n-1][1]-q[1])<.5)return;clean.push(q);});
      let k=1;while(k<clean.length-1){const a=clean[k-1],b=clean[k],c=clean[k+1];if((Math.abs(a[0]-b[0])<.5&&Math.abs(b[0]-c[0])<.5)||(Math.abs(a[1]-b[1])<.5&&Math.abs(b[1]-c[1])<.5))clean.splice(k,1);else k++;}
      out[e.id]=rounded(clean,8);});
    return out;}
  let rafE=0;
  function redrawEdges(){if(rafE)return;rafE=requestAnimationFrame(()=>{rafE=0;const R=routeAll();eEls.forEach(x=>{const d=R[x.e.id];x.g.style.display=d?'':'none';if(d){x.p.setAttribute('d',d);x.h.setAttribute('d',d);}});});}
  function fitView(){const vis=CV.nodes.filter(n=>!HID.has(n.id));if(!vis.length)return;let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;vis.forEach(n=>{const [x,y]=at(n);x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x+n.width);y1=Math.max(y1,y+n.height);});
    $('flowsvg').setAttribute('viewBox',(x0-12)+' '+(y0-12)+' '+(x1-x0+24)+' '+(y1-y0+24));}
  async function loadFlow(){
    try{CV=await J('/api/yard/canvas?compact=1');KN=await J('/api/yard/knobs');}catch(e){$('result').textContent='Could not read the yard: '+e.message;return;}
    loadLayout();const svg=$('flowsvg');svg.replaceChildren();const defs=sv('defs',{}),mk=sv('marker',{id:'farrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto'});mk.appendChild(sv('path',{d:'M0 0L10 5L0 10z',fill:'#8fb3a0'}));defs.appendChild(mk);svg.appendChild(defs);
    NODE={};CV.nodes.forEach(n=>NODE[n.id]=n);gById={};eEls=[];
    CV.edges.forEach(e=>{const g=sv('g',{class:'fedge','data-id':e.id}),p=sv('path',{'marker-end':'url(#farrow)'}),h=sv('path',{class:'hit'});g.appendChild(p);g.appendChild(h);g.appendChild(sv('title',{},NODE[e.fromNode].title+' → '+NODE[e.toNode].title+': '+e.label));h.onclick=()=>openEdge(e.id);svg.appendChild(g);eEls.push({e,g,p,h});});
    CV.nodes.forEach(n=>{const g=sv('g',{class:'fnode '+n.state+(n.outside?' outside':''),'data-id':n.id}),r=sv('rect',{width:n.width,height:n.height,rx:8});g.appendChild(r);
      g.appendChild(sv('text',{x:10,y:23,class:'ft'},n.title));const live=sv('text',{x:10,y:46,class:'fl'},n.outside?'outside a session':'');g.appendChild(live);g._live=live;
      const ib=sv('g',{class:'fi'});ib.appendChild(sv('circle',{cx:n.width-14,cy:14,r:9}));ib.appendChild(sv('text',{x:n.width-14,y:19,'text-anchor':'middle'},'i'));g.appendChild(ib);
      const xb=sv('g',{class:'fx'});xb.appendChild(sv('circle',{cx:n.width-14,cy:n.height-12,r:8}));xb.appendChild(sv('text',{x:n.width-14,y:n.height-8,'text-anchor':'middle'},'×'));g.appendChild(xb);
      ib.onpointerdown=ev=>ev.stopPropagation();ib.onclick=ev=>{ev.stopPropagation();openNode(n.id,true);};
      xb.onpointerdown=ev=>ev.stopPropagation();xb.onclick=ev=>{ev.stopPropagation();HID.add(n.id);saveLayout();place();};
      let drag=null;g.onpointerdown=ev=>{if(ev.button)return;const m=svg.getScreenCTM(),[x,y]=at(n);drag={px:ev.clientX,py:ev.clientY,x,y,s:1/m.a,moved:false};g.setPointerCapture(ev.pointerId);};
      g.onpointermove=ev=>{if(!drag)return;const dx=(ev.clientX-drag.px)*drag.s,dy=(ev.clientY-drag.py)*drag.s;if(!drag.moved&&Math.hypot(dx,dy)<4/ (1/drag.s))return;drag.moved=true;POS[n.id]=[Math.round((drag.x+dx)/10)*10,Math.round((drag.y+dy)/10)*10];g.setAttribute('transform','translate('+POS[n.id][0]+' '+POS[n.id][1]+')');redrawEdges();};
      g.onpointerup=ev=>{if(!drag)return;const moved=drag.moved;drag=null;if(moved){saveLayout();fitView();}else openNode(n.id,false);};
      svg.appendChild(g);gById[n.id]=g;});
    place();
  }
  function place(){CV.nodes.forEach(n=>{const g=gById[n.id],[x,y]=at(n);g.setAttribute('transform','translate('+x+' '+y+')');g.style.display=HID.has(n.id)?'none':'';});redrawEdges();fitView();
    $('showall').hidden=!(HID.size||Object.keys(POS).length);$('showall').textContent=HID.size?'SHOW ALL ('+HID.size+' HIDDEN) · RESET LAYOUT':'RESET LAYOUT';}
  $('showall').onclick=()=>{POS={};HID=new Set();saveLayout();place();};
  function knobRow(k){const row=el('div','krow'),lab=el('label',null,k.label);lab.title=k.info;row.append(lab);let inp;
    if(k.kind==='bool'){inp=el('input');inp.type='checkbox';inp.checked=!!k.value;inp.onchange=()=>put(k.name,inp.checked);row.append(inp,el('span'));}
    else if(k.kind==='choice'){inp=el('select');k.choices.forEach(c=>{const o=el('option',null,c);o.value=c;if(c===k.value)o.selected=true;inp.append(o);});inp.onchange=()=>put(k.name,inp.value);row.append(inp,el('span'));}
    else{inp=el('input');inp.type='range';inp.min=k.low;inp.max=k.high;inp.step=k.step;inp.value=k.value;const v=el('span','kv',String(k.value));inp.oninput=()=>{v.textContent=inp.value;clearTimeout(saveT[k.name]);saveT[k.name]=setTimeout(()=>put(k.name,k.kind==='int'?parseInt(inp.value,10):parseFloat(inp.value)),350);};row.append(inp,v);}
    const rs=el('button','i','↺');rs.title='Back to '+k.default;rs.style.visibility=k.changed?'visible':'hidden';rs.onclick=async()=>{await POST('/api/yard/knobs/reset',{name:k.name});await refreshKnobs();};row.append(rs);return row;}
  async function put(name,value){try{const r=await POST('/api/yard/knobs',{[name]:value});if(!r.ok){$('msg').hidden=false;$('msg').textContent=await r.text();}else{await refreshKnobs(true);}}catch(e){}}
  async function refreshKnobs(quiet){try{KN=await J('/api/yard/knobs');}catch(e){return;}$('kreset').hidden=!KN.knobs.some(k=>k.changed);if(!quiet&&sel)openNode(sel,showInside);}
  // the inside of a block: its layers drawn as a chain with their sizes, then the plain numbers, then the arithmetic
  function inside(n){const a=n.arch||{},wrap=el('div','inside');
    if(a.layers&&a.layers.length){const ch=el('div','chain');a.layers.forEach((l,i)=>{if(i)ch.append(el('span','arrow','→'));const b=el('div','lay');b.append(el('div','ls',l.size),el('div','ln',l.name));ch.append(b);});wrap.append(ch);}
    (a.rows||[]).forEach(r=>{const d=el('div','irow');d.append(el('b',null,r.label+': '),document.createTextNode(r.value));wrap.append(d);});
    if(a.formula&&a.formula.length){const f=el('pre','formula');f.textContent=a.formula.join('\\n');wrap.append(f);}
    if(n.id==='ver')versionsBox(wrap);return wrap;}
  async function versionsBox(wrap){try{const s=await J('/api/yard/status'),vs=(s.versions||[]).slice().reverse();if(!vs.length){wrap.append(el('div','mute','No version saved yet.'));return;}
      const box=el('div','irow');box.append(el('b',null,'versions: '));vs.slice(0,6).forEach(v=>{const inuse=s.in_use_version===v.n,b=el('button',inuse?'on':'skip',(inuse?'IN USE ':'RESTORE ')+'v'+v.n);b.title=Math.round(v.held*100)+' % on unseen words'+(v.methods?' · '+v.methods.linear:'');b.disabled=inuse;
        b.onclick=async()=>{if(!confirm('Make version '+v.n+' the one in use? Nothing is deleted.'))return;const r=await POST('/api/yard/rollback',{version:v.n});$('msg').hidden=false;$('msg').textContent=r.ok?'Version '+v.n+' is now in use.':(await r.text());loadResult();openNode('ver',true);};box.append(b,document.createTextNode(' '));});wrap.append(box);}catch(e){}}
  async function openNode(id,inn){try{const c=await J('/api/yard/canvas?compact=1');c.nodes.forEach(m=>{if(NODE[m.id])NODE[m.id].arch=m.arch;});KN=await J('/api/yard/knobs');}catch(e){}
    sel=id;showInside=!!inn;eEls.forEach(q=>q.g.classList.remove('sel'));Object.values(gById).forEach(g=>g.classList.toggle('sel',g.dataset.id===id));const n=NODE[id],box=$('nodebox');box.hidden=false;box.replaceChildren();
    const h=el('div','nh');h.append(el('b',null,n.title),document.createTextNode('  '+n.info),el('span','sp'));const tg=el('button',showInside?'on':'skip','INSIDE');tg.title='Layers, numbers and arithmetic';tg.onclick=()=>openNode(id,!showInside);h.append(tg);box.append(h);
    if(showInside)box.append(inside(n));
    const ks=n.knobs.map(name=>KN.knobs.find(k=>k.name===name)).filter(Boolean);
    if(ks.length){box.append(el('div','sub','SETTINGS'));ks.forEach(k=>box.append(knobRow(k)));}else box.append(el('div','mute','Nothing to adjust here.'));}
  // an arrow: what travels along it and what the block at the other end does with it, then how often it lit in the last session
  async function openEdge(id){const x=eEls.find(q=>q.e.id===id);if(!x)return;sel=null;Object.values(gById).forEach(g=>g.classList.remove('sel'));eEls.forEach(q=>q.g.classList.toggle('sel',q.e.id===id));
    const e=x.e,box=$('nodebox');box.hidden=false;box.replaceChildren();const h=el('div','nh');h.append(el('b',null,NODE[e.fromNode].title+' → '+NODE[e.toNode].title),document.createTextNode('  '+e.label));box.append(h,el('div','irow',e.info||''));
    const hist=el('div','mute','Looking at this session...');box.append(hist);
    try{const j=await J('/api/yard/events?since=0'),mine=j.events.filter(v=>v.edge===id);hist.textContent=mine.length?('Seen '+mine.length+' time'+(mine.length>1?'s':'')+' since the Hub started. Latest: '+mine[mine.length-1].text):'Nothing has travelled along this arrow since the Hub started. Start a session and it lights.';}catch(err){hist.textContent='';}}
  const flash=(e,c,ms)=>{e.classList.add(c);setTimeout(()=>e.classList.remove(c),ms);};
  function showEvents(evs){evs.forEach(ev=>{const g=gById[ev.node];if(g){g._live.textContent=(ev.text||'').slice(0,34);flash(g,ev.improved?'improved':'pulse',ev.improved?3500:450);}
      const x=eEls.find(q=>q.e.id===ev.edge);if(x)flash(x.g,'lit',550);
      if(['improved','saved','imitated','relabel','agreement','stopped','replayed'].includes(ev.kind))flog.unshift(ev);});
    flog=flog.slice(0,6);$('flog').replaceChildren(...flog.map(ev=>el('div',ev.improved?'yes':'mute',(ev.improved?'↑ ':'· ')+ev.text)));}
  async function poll(){try{const j=await J('/api/yard/events?since='+lastN);if(j.last<lastN)lastN=0;if(j.events.length){lastN=j.last;showEvents(j.events);}
      $('go').hidden=!!j.running;$('stop').hidden=!j.running;$('phase').textContent=j.running?(j.phase+' ('+Math.round(100*j.done/Math.max(1,j.total))+' %)'):'';
      if(wasRunning&&!j.running)loadResult();wasRunning=!!j.running;}catch(e){}}
  async function loadResult(){try{const s=await J('/api/yard/status'),r=s.report,box=$('result');
    if(!s.ready){box.textContent='numpy is not installed; practising needs it.';return;}
    if(!r){box.textContent='No session yet.';return;}
    const m=r.means||{},v=s.in_use_version,att=r.attested_agreement&&r.attested_agreement.rate!=null?' · agrees with your attested routines on '+pct(r.attested_agreement.rate):'',sf=r.safety?' · forbidden pressed on '+r.safety.breaches+' of '+r.safety.screens+' screens':'';
    box.textContent='Last session: version '+(v||'?')+', '+r.episodes+' episodes. Unseen words: learned '+pct((m['learned, linear']||{}).held||0)+' · rule of thumb '+pct((m['rule of thumb']||{}).held||0)+' · random '+pct((m.random||{}).held||0)+att+sf;}catch(e){}}
  $('go').onclick=async()=>{$('go').disabled=true;$('msg').hidden=true;try{const r=await POST('/api/yard/practice',{confirm:true});if(!r.ok)throw Error(await r.text()||('error '+r.status));const j=await r.json();
      if(j.stopped){$('msg').hidden=false;$('msg').textContent='Stopped. Nothing was saved.';}}catch(e){$('msg').hidden=false;$('msg').textContent=String(e.message||e);}finally{$('go').disabled=false;poll();loadResult();}};
  $('stop').onclick=async()=>{$('stop').disabled=true;try{await POST('/api/yard/practice/stop');}catch(e){}$('stop').disabled=false;};
  $('kreset').onclick=async()=>{if(!confirm('Put every number back to its default?'))return;await POST('/api/yard/knobs/reset',{});await refreshKnobs();};
  function flowStart(){if(!CV)loadFlow().then(()=>refreshKnobs(true));loadResult();if(!timer)timer=setInterval(poll,500);poll();}
  function flowStop(){clearInterval(timer);timer=0;}

  // ---- WHY: what the saved learner would press on each screen, with the features behind it and the weights a step would move
  function whyView(j){
    const box=el('div','wy');
    if(j.error){box.append(el('div','mute',j.error));return box;}
    box.append(el('div','mute',j.routine+': the learner would press the same control on '+j.agree+' of '+j.of+' steps. '+(j.note||'')));
    j.steps.forEach(s=>{const d=el('div','wy');d.append(el('h4',null,'Step '+s.step+(s.routine_presses?' - the routine presses '+s.routine_presses:'')+(s.live_did?' - the live agent did: '+s.live_did:'')));
      s.candidates.forEach(c=>{const r=el('div','cand'+(c.best?' top':'')+(c.pressed?' pr':''));r.append(el('span','nm',c.action),el('span','mute',pct(c.p)+' (score '+c.score+')'));const b=el('span','bar'),i=el('i');i.style.width=Math.max(1,Math.round(c.p*100))+'%';b.append(i);r.append(b);d.append(r);
        if(c.best||c.pressed)d.append(el('div','bc','because: '+c.because.map(x=>x.feature+' '+(x.part>0?'+':'')+x.part).join('; ')));});
      if(s.moves&&s.moves.length)d.append(el('div','mv','Learning from this press would move: '+s.moves.map(m=>m.weight+' '+(m.direction==='up'?'up':'down')+' '+Math.abs(m.change)).join('; ')));
      box.append(d);});
    return box;}
  async function liveTasks(){
    const L=$('livelist');L.replaceChildren();let j={tasks:[]};try{j=await J('/api/yard/why/live');}catch(e){}
    $('livenote').textContent=j.tasks.length?'Tasks the live agent did while shadow mode was on. WHY shows each screen it was given and what the saved learner would have pressed.':'None kept yet: switch shadow mode on, then do a task by voice.';
    j.tasks.forEach(t=>{const c=el('div','card rc');c.append(el('div','said',t.goal+' ('+t.steps+' steps)'),el('div','why',new Date(t.at*1000).toLocaleString()));const w=el('div'),b=el('button','skip','WHY');
      b.onclick=async()=>{if(w.childNodes.length){w.replaceChildren();return;}w.append(el('div','mute','Working it out...'));try{w.replaceChildren(whyView(await J('/api/yard/why/live?goal='+encodeURIComponent(t.goal)+'&at='+t.at)));}catch(e){w.replaceChildren(el('div','mute','Could not explain this one.'));}};
      c.append(b,w);L.append(c);});}

  // ---- ROUTINES
  async function routines(){
    const box=$('rlist');box.replaceChildren();let rows=[],gold={routines:[]},cands=[],s={};
    try{[rows,gold,cands,s]=await Promise.all([J('/api/pc/routines').then(j=>j.routines||[]),J('/api/yard/golden'),J('/api/yard/candidates').then(j=>j.candidates||[]).catch(()=>[]),J('/api/yard/settings')]);}catch(e){box.textContent='Could not read the routines: '+e.message;return;}
    $('freshnote').textContent=s.fresh_since?'Learners read only what happened after '+new Date(s.fresh_since*1000).toLocaleString()+'.':'Learners read everything until the first time shadow mode is switched on.';
    $('fresh').onclick=async()=>{if(!confirm('FRESH START: learners read only new rows from now on, and the routines trusted right now become attested checks. Nothing is deleted.'))return;await POST('/api/yard/settings',{fresh:true});routines();};
    const att=new Set((gold.routines||[]).map(r=>r.id)),chk={};cands.forEach(c=>chk[c.id]=c);
    if(!rows.length){box.append(el('div','card','No routines yet.'));return;}
    rows.forEach(r=>{const c=el('div','card rc');c.append(el('div','said',r.title));const m=el('div');
      m.append(el('span','chip '+(r.status==='trusted'?'ok':r.status==='disabled'?'no':'part'),r.status.toUpperCase()),document.createTextNode(' '),el('span','chip',r.successes+' good · '+r.failures+' bad'),document.createTextNode(' '),el('span','chip',r.updated?('last used '+new Date(r.updated*1000).toLocaleDateString()):'never used'));
      if(att.has(r.id)){m.append(document.createTextNode(' '),el('span','chip ok','attested: a check, never training'));}
      const k=chk[r.id];if(k){m.append(document.createTextNode(' '),el('span','chip '+(k.ready?'ok':'part'),k.ready?'yard: looks ready':'yard: not ready'));}
      c.append(m);if(k&&!k.ready)c.append(el('div','why',k.reasons.join('. ')+'.'));if(k&&k.ready)c.append(el('div','why','No forbidden control, replayed clean, and the learner agrees on '+(k.agree==null?'(no learner yet)':pct(k.agree))+' of its steps. Only you can approve it.'));
      const st=el('div','why'),wy=el('div'),why=el('button','skip','WHY');c.append(st,wy);const row=el('div','row'),see=el('button','skip','SHOW STEPS'),ok=el('button',null,'APPROVE'),off=el('button','part',r.status==='disabled'?'RE-ENABLE':'DISABLE'),del=el('button','no','DELETE'),rp=el('button','part','REPLAY');
      see.onclick=async()=>{try{const j=await J('/api/pc/routines/'+r.id+'/steps');st.textContent=(j.steps.length?j.steps.map(x=>(x.ordinal+1)+'. '+x.tool+' '+((x.target&&x.target.name)||'')).join('  >  '):'no steps (an app launch or an address)');}catch(e){st.textContent=String(e);}};
      ok.onclick=async()=>{await POST('/api/pc/routines/'+r.id+'/approve');routines();};
      off.onclick=async()=>{await POST('/api/pc/routines/'+r.id+'/status',{status:r.status==='disabled'?'candidate':'disabled'});routines();};
      del.onclick=async()=>{if(!confirm('Delete this routine for good? '+r.title))return;await fetch('/api/pc/routines/'+r.id,{method:'DELETE'});routines();};
      rp.onclick=async()=>{if(!confirm('Replay "'+r.title+'" now? It will press things on this PC.'))return;rp.disabled=true;st.textContent='Replaying...';try{const x=await POST('/api/pc/routines/'+r.id+'/run');st.textContent=x.ok?'It ran.':(await x.text());}catch(e){st.textContent=String(e);}rp.disabled=false;};
      ok.hidden=r.status==='trusted';rp.hidden=!att.has(r.id);why.onclick=async()=>{if(wy.childNodes.length){wy.replaceChildren();return;}wy.append(el('div','mute','Working it out...'));try{wy.replaceChildren(whyView(await J('/api/yard/why/routine/'+r.id)));}catch(e){wy.replaceChildren(el('div','mute','Could not explain this routine.'));}};
      row.append(see,why,ok,off,rp,del);c.append(row);box.append(c);});}

  // ---- SCORES
  async function scores(){const t=$('fit');head(t,['Part','Score','95 % interval','Evidence','Needs','Compared with']);
    let j;try{j=await J('/api/yard/fitness');}catch(e){t.append(el('tr'));return;}
    const rate=r=>r&&r.n?pct(r.rate):'-',iv=r=>r&&r.n?pct(r.lower95)+' to '+pct(r.upper95):'-';
    j.heads.forEach(h=>{
      if(h.options){const ks=Object.keys(h.options);if(!ks.length){const r=el('tr');r.append(el('td',null,h.head),el('td','mute','nothing labelled yet'),el('td'),el('td'),el('td','mute',h.needs),el('td','mute',h.baseline));t.append(r);}
        ks.forEach(k=>{const o=h.options[k],r=el('tr');r.append(el('td',null,h.head+': '+k),el('td',null,rate(o)),el('td','mute',iv(o)),el('td',null,o.k+' of '+o.n),el('td','mute',h.needs),el('td','mute',h.baseline));t.append(r);});return;}
      const r=el('tr');
      if(h.train){r.append(el('td',null,h.head),el('td',null,rate(h.train)),el('td','mute',iv(h.train)),el('td',null,h.train.n+' labelled; '+h.frozen.n+' held out'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else if(h.in_good_tasks){r.append(el('td',null,h.head),el('td',null,rate(h.in_good_tasks)),el('td','mute',iv(h.in_good_tasks)),el('td',null,h.tasks+' tasks'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else if(h.brier!==undefined){r.append(el('td',null,h.head),el('td',null,h.brier===null?'-':'Brier '+h.brier),el('td','mute','lower is better'),el('td',null,h.graded+' graded'),el('td','mute',h.needs),el('td','mute',h.baseline));}
      else{const sf=h.safety?('forbidden pressed on '+h.safety.breaches+' of '+h.safety.screens+' screens'):'no saved learner';
        r.append(el('td',null,h.head),el('td',null,h.means?Object.entries(h.means).map(([k,v])=>k+' '+pct(v.held)).join(' · '):'-'),el('td'),el('td','mute','unseen words; '+sf),el('td','mute',h.needs),el('td','mute',h.baseline));}
      t.append(r);});
    const ch=j.challengers||{},ct=$('chal');head(ct,['Choice','Method','Scored on','Agreed','Estimate','Worth (rows)','Watched']);
    if(!ch.error)['model','rung'].forEach(h=>(ch[h]||[]).forEach(l=>{const r=el('tr');r.append(el('td',null,h),el('td',null,l.learner),el('td','mute',l.available===false?('needs '+l.needs):(l.decided||0)+' choices'),el('td',null,l.available===false?'-':(l.agreed||0)),el('td',null,l.estimate==null?'-':pct(l.estimate)),el('td','mute',l.available===false?'-':(l.ess||0).toFixed(1)));
        const w=el('td'),b=el('button',null,(ch.selected||{})[h]===l.learner?'WATCHED':'WATCH');b.disabled=l.available===false||(ch.selected||{})[h]===l.learner;
        b.onclick=async()=>{await POST('/api/yard/learners',{head:h,learner:l.learner});scores();};w.append(b);r.append(w);ct.append(r);}));
    const k=ch.router_knn||{},c2=ch.router_classifier||{};
    $('knn').textContent=k.ready?('Router, graded requests left out one at a time: nearest neighbours right on '+pct(k.knn)+(c2.ready?', trained classifier on '+pct(c2.classifier):'')+', current rules and tev on '+pct(k.current)+' ('+k.n+' graded).'):('Router: needs '+(k.needs||5)+' graded requests, has '+(k.n||0)+'.');
    const g=j.gate||{};$('gateline').textContent='Gate for a new version: '+g.min_frozen+' held-out rows · zero forbidden presses · '+g.shadow_n+' watched live choices at '+pct(g.shadow_agree||0)+' · your yes.';
    try{const v=await J('/api/yard/tev');$('tevline').textContent='tev fine-tune: '+(v.enough?'enough graded requests ('+v.rows+'), ':'needs '+v.needed+' graded requests, has '+v.rows+' ('+v.held_out+' held out). ')+(v.hardware.cuda?'a CUDA device is available. ':v.hardware.note+'. ')+'Nothing runs until you say go.';}catch(e){}}

  // ---- tabs
  const TABS=['yard','teach','routines','scores'];
  function tab(name){if(!TABS.includes(name))name='yard';document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===name));
    TABS.forEach(n=>$('tab-'+n).hidden=n!==name);if(name==='yard')flowStart();else flowStop();
    if(name==='teach'){const f=$('teachframe');if(!f.src)f.src=f.dataset.src;}if(name==='routines'){routines();liveTasks();}if(name==='scores')scores();try{localStorage.setItem('hub-rl-tab',name);}catch(e){}}
  document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
  let first='yard';try{first=localStorage.getItem('hub-rl-tab')||'yard';}catch(e){}
  switches();tab(first);
})();
</script></body></html>
"""


@routes.get("/yard")
async def yard_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
