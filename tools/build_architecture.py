"""Circuit-board architecture, informed by abb997c and updated to current Hub routes."""
from pathlib import Path
from html import escape
import json
from base64 import b64encode
NODES=[
 ('devices','YOUR DEVICES','Phone · tablet · laptop',1,2,'Your devices open one Hub browser interface.'),
 ('network','PRIVATE ACCESS','Tailscale',1,3,'Your devices reach the Hub over your private network.'),
 ('board','DASHBOARD','Mouse · touch · hands',1,1,'Open tools directly on the board. Hand gestures move its browser controls.'),
 ('hub','AGENT HUB','Runs on your PC',2,3,'One front door to the PC tools, projects, files and apps you choose.'),
 ('smith','AGENT SMITH','Speak or type',2,1,'Smith receives spoken or typed requests and hands them to the router or a helper.'),
 ('router','ROUTER','Choose the right route',3,1,'A request can use a saved routine, a Hub command, an app tool or a mission.'),
 ('apps','YOUR WEB APPS','Open · run on demand',4,1,'The Hub starts an app when you open it, serves it through the same Hub address, and can stop it after it is idle.'),
 ('media','MEDIA + FILES','Download · convert · inbox',3,2,'Media tools run on the PC: yt-dlp downloads, ffmpeg converts, and files go to your chosen folders.'),
 ('pc','PC CONTROL','Windows MCP',3,3,'The desktop agent locates a named control, asks before acting, and checks the result.'),
 ('graph','GIT GRAPH','Project · branch · diff',3,4,'The graph reads projects and their working copies. Select a project to inspect its changed files.'),
 ('missions','MISSIONS','Goal → private work',4,2,'A code request becomes a mission with a private worktree. The original project waits for your decision.'),
 ('orchestrator','ORCHESTRATOR','Plan and delegate',4,3,'The orchestrator plans the mission and hands precise briefs to appropriate agents.'),
 ('worktree','PRIVATE WORKTREE','Implement · test · review',4,4,'Agents work in a private copy; the diff can be read from the mission or Git Graph.'),
 ('review','YOUR DECISION','APPLY · DISCARD',4,5,'Read the diff. APPLY merges the change; DISCARD removes the private copy. A repair never restarts the Hub for you.'),
 ('skills','SKILL LIBRARY','Hub · open source · yours',3,5,'Readable SKILL.md instructions are available to the agents. Add an open-source skill or write your own.'),
 ('neo','NEO','Design an agent',1,5,'Describe a job; Neo drafts an agent definition. Read it and save it before using that agent.'),
 ('doctor','THE DOCTOR','Diagnose → propose repair',2,5,'The Doctor reads Hub facts and proposes a repair through a mission. You approve its diff and choose when to restart.'),
]
EDGES=[('devices','network'),('network','hub'),('board','hub'),('smith','router'),('router','hub'),('router','missions'),('router','media'),('router','pc'),('router','graph'),('hub','apps'),('router','apps'),('hub','media'),('hub','pc'),('hub','graph'),('hub','missions'),('missions','orchestrator'),('orchestrator','worktree'),('worktree','review'),('worktree','graph'),('skills','orchestrator'),('smith','neo'),('smith','doctor'),('neo','orchestrator'),('doctor','missions'),('doctor','neo')]
LAYERS=[
 ('access','DEVICES + ACCESS',['devices','network']),
 ('hub','HUB + INPUT',['hub','board','router']),
 ('tools','PC TOOLS',['apps','media','pc','graph']),
 ('agents','AGENTS + SKILLS',['smith','orchestrator','neo','doctor','skills']),
 ('work','WORK + REVIEW',['missions','worktree','review'])]

def interactive():
    lookup={n[0]:n for n in NODES}
    layers=[]
    for key,title,ids in LAYERS:
        nodes=[]
        for node in ids:
            nid,label,note,col,row,description=lookup[node]
            mark='<img src="assets/agent-hub-mark.png" alt="" width="56" height="56">' if nid=='hub' else ''
            nodes.append('<button type="button" class="circuit-node%s" data-arch-node="%s" aria-pressed="false"><span class="circuit-pins" aria-hidden="true"></span>%s<b>%s</b><small>%s</small></button>' % (' circuit-core' if nid=='hub' else '',nid,mark,escape(label),escape(note)))
        layers.append('<section class="arch-layer%s" data-arch-layer="%s"><h3>%s</h3><div class="arch-layer-nodes">%s</div></section>' % (' current-layer' if key=='hub' else '',key,title,''.join(nodes)))
    model=json.dumps({'nodes':{n[0]:n[5] for n in NODES},'edges':EDGES,'labels':{n[0]:n[1] for n in NODES}},separators=(',',':'))
    tabs='<nav class="arch-layer-tabs" aria-label="Architecture layers">'+''.join('<button type="button" data-layer-tab="%s" aria-pressed="%s">%s</button>' % (key,str(key=='hub').lower(),title) for key,title,ids in LAYERS)+'</nav>'
    return '<div class="architecture-shell">%s<div class="circuit-board layered-board" data-architecture="%s"><svg class="circuit-wires" aria-hidden="true"></svg>%s</div><div class="circuit-caption"><b>FOLLOW A CONNECTION</b><p>Select a component to inspect its role.</p><div class="arch-connections"></div></div></div>' % (tabs,escape(model,quote=True),''.join(layers))

def diagram(tall=False):
    mark='data:image/png;base64,'+b64encode((Path(__file__).resolve().parent.parent/'docs/assets/agent-hub-mark.png').read_bytes()).decode('ascii')
    w,h=(760,1500) if tall else (1440,900)
    coords={};frames=[]
    for i,(key,title,ids) in enumerate(LAYERS):
        if tall:
            x,y,bw=24,20+i*292,712
            for j,n in enumerate(ids):coords[n]=(x+18+(j%2)*344,y+52+(j//2)*72,324,60)
            frames.append((x,y,bw,274,title))
        else:
            x,y,bw=22+i*284,28,260
            for j,n in enumerate(ids):coords[n]=(x+15,y+70+j*146,230,112)
            frames.append((x,y,bw,840,title))
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Agent Hub architecture grouped by devices, Hub, tools, agents and reviewed work"><rect width="{w}" height="{h}" fill="#05070c"/><defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L8 4L0 8" fill="#00e676"/></marker></defs>']
    for x,y,bw,bh,title in frames:
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="#081322" stroke="#00e676" stroke-opacity=".22"/><text x="{x+15}" y="{y+28}" fill="#7cceaf" font-family="system-ui" font-size="15">{title}</text>')
    for i,(a,b) in enumerate(EDGES):
        x,y,bw,bh=coords[a];xx,yy,ww,hh=coords[b]
        sx,sy,tx,ty=x+bw,y+bh/2,xx,yy+hh/2
        if tall:
            bus=8+(i%5)*3;d=f'M{sx} {sy}H{w-bus}V{ty}H{tx+ww}'
        elif xx==x:
            bus=x+bw+7;d=f'M{sx} {sy}H{bus}V{ty}H{tx+ww}'
        else:
            bus=850+(i%5)*6;d=f'M{sx} {sy}H{sx+7}V{bus}H{tx-8}V{ty}H{tx}'
        highlight=a=='router' and b=='missions'
        out.append(f'<path d="{d}" fill="none" stroke="{"#41ebff" if highlight else "#00e676"}" stroke-opacity="{1 if highlight else .22}" stroke-width="{2.6 if highlight else 1.2}" marker-end="url(#ah)"/>')
    for key,label,note,col,row,desc in NODES:
        x,y,bw,bh=coords[key];cx=x+bw/2
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="3" fill="#091525" stroke="#00e676" stroke-opacity=".6"/>')
        if key=='hub':out.append(f'<image href="{mark}" x="{x+8}" y="{y+bh/2-20}" width="40" height="40"/>');cx+=18
        out.append(f'<text x="{cx}" y="{y+bh/2-5}" fill="#00e676" font-family="Orbitron,system-ui" font-size="14" text-anchor="middle">{escape(label)}</text><text x="{cx}" y="{y+bh/2+18}" fill="#b4d1c4" font-family="Outfit,system-ui" font-size="13" text-anchor="middle">{escape(note)}</text>')
    out.append('</svg>');return ''.join(out)

def wide():return diagram()
def tall():return diagram(True)
if __name__=='__main__':
    docs=Path(__file__).resolve().parent.parent/'docs'
    (docs/'architecture.svg').write_text(wide(),encoding='utf-8')
    (docs/'architecture-tall.svg').write_text(tall(),encoding='utf-8')
