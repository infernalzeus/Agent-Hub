"""The Chats page (/chats): every conversation in one place.

  GET /chats      this page (also embedded as the CHATS tab of the Auto-LLM block)

Three sections, all read from things that already exist:
  TALK WITH SMITH   the lines of this browser tab's LOG of kind "chat" (written by voice.js and the landing page),
                    with a button that opens the chat window.
  QUICK CHAT        a project-less OpenCode chat (the same two calls the old QUICK CHAT button made).
  AGENT SESSIONS    Claude Code and Codex conversations, and OpenCode missions, from /api/home/state.
"""
from __future__ import annotations

from aiohttp import web

from .embed import embedded

routes = web.RouteTableDef()

_HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chats</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Outfit:wght@400;600&display=swap">
<style>
:root{--bg:#080c28;--bg2:#0d1050;--bd:rgba(0,230,118,.22);--ac:#00e676;--cy:#41ebff;--tx:#d6f5e6;--mu:rgba(214,245,230,.62)}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(160deg,var(--bg),var(--bg2));color:var(--tx);font:400 14px/1.5 Outfit,system-ui,sans-serif;padding:16px max(16px,env(safe-area-inset-left))}
main{max-width:980px;margin:0 auto}
h1,h2{font-family:Orbitron,sans-serif;letter-spacing:.08em;color:var(--ac);margin:0}
h1{font-size:20px}h2{font-size:12px;margin:22px 0 8px;text-transform:uppercase}
.sub{color:var(--mu);margin:4px 0 10px}
.card{border:1px solid var(--bd);border-radius:12px;background:rgba(6,10,36,.6);padding:12px 14px}
.row{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid rgba(0,230,118,.08);min-width:0}
.row:last-child{border-bottom:0}
.row time{color:var(--mu);font-variant-numeric:tabular-nums;white-space:nowrap;font-size:12px}
.row b{font:700 9px Orbitron,sans-serif;letter-spacing:1px;color:var(--cy);white-space:nowrap;min-width:64px}
.row span{min-width:0;overflow-wrap:anywhere}
.row small{color:var(--mu);display:block}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
button{font:700 10px Orbitron,sans-serif;letter-spacing:1px;color:var(--ac);background:rgba(6,10,36,.78);border:1px solid var(--bd);border-radius:8px;padding:9px 14px;min-height:38px;cursor:pointer}
button:hover{border-color:var(--ac);background:rgba(0,230,118,.1)}button:disabled{opacity:.5;cursor:default}
.empty{color:var(--mu)}.err{color:#ff9d9d;margin-top:8px}
</style></head><body><main>
<h1>CHATS</h1>
<p class="sub">Your conversations in one place: the talk with Smith (also what you said on the landing page), a quick OpenCode chat, and your agent sessions.</p>

<h2>Talk with Smith</h2>
<div class="card"><div id="talk"></div>
<div class="btns"><button id="open-chat" type="button">OPEN CHAT WINDOW</button></div></div>

<h2>Quick chat</h2>
<div class="card"><div class="sub" style="margin:0">A chat with no project, run by OpenCode. It opens in its own tab.</div>
<div class="btns"><button id="quick" type="button">START A QUICK CHAT</button></div><div class="err" id="quick-err" hidden></div></div>

<h2>Agent sessions</h2>
<div class="card" id="sessions"><div class="empty">Loading.</div></div>
</main>
<script>
const $=(i)=>document.getElementById(i);
const ago=(s)=>{s=Math.max(0,s|0);return s<90?s+' s ago':s<5400?Math.round(s/60)+' min ago':s<172800?Math.round(s/3600)+' h ago':Math.round(s/86400)+' d ago';};
function row(kind,main,sub,when){const d=document.createElement('div');d.className='row';const b=document.createElement('b');b.textContent=kind;const s=document.createElement('span');s.textContent=main;if(sub){const m=document.createElement('small');m.textContent=sub;s.appendChild(m);}d.append(b,s);if(when){const t=document.createElement('time');t.textContent=when;d.appendChild(t);}return d;}
function talk(){
  const box=$('talk');box.replaceChildren();let rows=[];
  try{rows=(JSON.parse(sessionStorage.getItem('agenthub:log')||'[]')||[]).filter(r=>r.kind==='chat').slice(0,40);}catch(e){}
  if(!rows.length){const d=document.createElement('div');d.className='empty';d.textContent='Nothing said yet in this tab. Left-click TALK to start listening, or open the chat window to type.';box.appendChild(d);return;}
  rows.forEach(r=>{const m=/^(You|Smith): ?(.*)$/s.exec(r.t||'');box.appendChild(row(m?m[1].toUpperCase():'CHAT',m?m[2]:r.t,'',new Date(r.at).toLocaleTimeString([],{hour12:false})));});
}
$('open-chat').onclick=()=>{const v=(window.parent&&window.parent!==window&&window.parent.HubVoice)||window.HubVoice;if(v&&v.open)v.open(false);else location.href='/';};
$('quick').onclick=async()=>{
  const b=$('quick'),e=$('quick-err');b.disabled=true;b.textContent='STARTING';e.hidden=true;
  try{
    const r=await fetch('/api/opencode/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:'scratch'}),signal:AbortSignal.timeout(45000)});
    if(!r.ok)throw new Error((await r.text())||r.status);const s=await r.json();
    const c=await fetch('/api/opencode/projects/'+encodeURIComponent(s.slug)+'/chats',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
    if(!c.ok)throw new Error((await c.text())||'could not create a chat');const j=await c.json();
    if(j.url)window.open(j.url,'oc-scratch');else throw new Error('no chat URL returned');
  }catch(x){e.textContent='Quick chat could not start: '+(x.message||x);e.hidden=false;}
  finally{b.disabled=false;b.textContent='START A QUICK CHAT';}
};
async function sessions(){
  const box=$('sessions');
  try{
    const st=await (await fetch('/api/home/state',{cache:'no-store'})).json();const ss=st.sessions||{};
    const all=[].concat(ss.needs_you||[],ss.working||[],ss.idle||[]);box.replaceChildren();
    if(!all.length){const d=document.createElement('div');d.className='empty';d.textContent='No agent sessions found.';box.appendChild(d);return;}
    all.slice(0,40).forEach(s=>box.appendChild(row((s.agent||s.runtime||'').toUpperCase(),s.brief||'(no title)',[s.project,s.status,s.last].filter(Boolean).join(' · ').slice(0,220),ago(s.age_s))));
  }catch(e){box.textContent='Could not read sessions: '+(e.message||e);}
}
talk();sessions();window.addEventListener('storage',talk);setInterval(talk,4000);setInterval(sessions,20000);
</script></body></html>"""


@routes.get("/chats")
async def chats_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_HTML, request), content_type="text/html", charset="utf-8")
