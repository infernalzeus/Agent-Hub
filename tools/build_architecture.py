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
EDGES=[('devices','network'),('network','hub'),('board','hub'),('smith','router'),('router','hub'),('hub','apps'),('router','apps'),('hub','media'),('hub','pc'),('hub','graph'),('hub','missions'),('missions','orchestrator'),('orchestrator','worktree'),('worktree','review'),('worktree','graph'),('skills','orchestrator'),('smith','neo'),('smith','doctor'),('neo','orchestrator'),('doctor','missions'),('doctor','neo')]
def interactive():
    nodes=''.join('<button type="button" class="circuit-node%s" data-arch-node="%s" style="--col:%s;--row:%s"><span class="circuit-pins" aria-hidden="true"></span>%s<b>%s</b><small>%s</small></button>' % (' circuit-core' if key=='hub' else '',key,col,row,'<img src="assets/agent-hub-mark.png" alt="" width="56" height="56">' if key=='hub' else '',escape(label),escape(note)) for key,label,note,col,row,description in NODES)
    model=json.dumps({'nodes':{n[0]:n[5] for n in NODES},'edges':EDGES},separators=(',',':'))
    return '<div class="architecture-shell"><div class="circuit-board" data-architecture="%s"><svg class="circuit-wires" aria-hidden="true"></svg>%s</div><div class="circuit-caption"><b>FOLLOW A CONNECTION</b><p>Select a component to see its role and connections. Solid traces carry work; dashed traces connect helpers and skills.</p></div></div>' % (escape(model,quote=True),nodes)
def diagram(tall=False):
    mark='data:image/png;base64,'+b64encode((Path(__file__).resolve().parent.parent/'docs/assets/agent-hub-mark.png').read_bytes()).decode('ascii')
    w,h=(760,1240) if tall else (1440,860)
    coords={}
    for i,(key,label,note,col,row,desc) in enumerate(NODES):
        if tall:
            order=['devices','network','board','smith','router','hub','apps','media','pc','graph','missions','orchestrator','worktree','neo','doctor','skills','review'];idx=order.index(key);x=30+(idx%2)*370;y=25+(idx//2)*132;bw,bh=330,100
        else:x=35+(col-1)*354;y=25+(row-1)*164;bw,bh=306,112
        coords[key]=(x,y,bw,bh)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Agent Hub circuit-board architecture"><rect width="{w}" height="{h}" fill="#05070c"/><defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L8 4L0 8" fill="#00e676"/></marker></defs>']
    for a,b in EDGES:
        x,y,bw,bh=coords[a];xx,yy,ww,hh=coords[b]
        if xx>x:sx,sy,tx,ty=x+bw,y+bh/2,xx,yy+hh/2;d=f'M{sx} {sy}H{(sx+tx)/2}V{ty}H{tx}'
        else:sx,sy,tx,ty=x+bw/2,y+bh,xx+ww/2,yy;d=f'M{sx} {sy}V{(sy+ty)/2}H{tx}V{ty}'
        dash=' stroke-dasharray="6 5"' if a in ('smith','skills','neo','doctor') else ''
        out.append(f'<path d="{d}" fill="none" stroke="#00e676" stroke-opacity=".38" stroke-width="1.7" marker-end="url(#ah)"{dash}/>')
    for key,label,note,col,row,desc in NODES:
        x,y,bw,bh=coords[key]
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" fill="#091525" stroke="#00e676" stroke-opacity=".5"/>')
        for side in (x-6,x+bw):
            for j in range(5):out.append(f'<rect x="{side}" y="{y+20+j*15}" width="6" height="3" fill="#00e676" fill-opacity=".6"/>')
        if key=='hub':out.append(f'<image href="{mark}" x="{x+10}" y="{y+25}" width="60" height="60"/>')
        cx=x+bw/2+(22 if key=='hub' else 0)
        out.append(f'<text x="{cx}" y="{y+45}" fill="#00e676" font-family="Orbitron,system-ui" font-size="18" text-anchor="middle">{escape(label)}</text><text x="{cx}" y="{y+75}" fill="#b4d1c4" font-family="Outfit,system-ui" font-size="16" text-anchor="middle">{escape(note)}</text>')
    out.append('</svg>');return ''.join(out)
def wide():return diagram()
def tall():return diagram(True)
if __name__=='__main__':
    docs=Path(__file__).resolve().parent.parent/'docs'
    (docs/'architecture.svg').write_text(wide(),encoding='utf-8')
    (docs/'architecture-tall.svg').write_text(tall(),encoding='utf-8')
