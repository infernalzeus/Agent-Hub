"""Keep the pre-Codex circuit layout; update only its labels, wiring and additions.

The unmodified reference is tools/site_parts/architecture-original.svg from
4df980c. Tailscale belongs inside ACCESS, not to the mission execution chain.
"""
from pathlib import Path
from html import escape
import json
import xml.etree.ElementTree as ET

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
PARTS=Path(__file__).resolve().parent/'site_parts'
# id, label, bounds in the ORIGINAL drawing, explanation
NODES=[
 ('phone','PHONE',(24,228,120,44),'Your phone opens the same Hub interface through the private network.'),
 ('tablet','TABLET',(24,308,120,44),'Your tablet reaches the Hub on your PC; it does not run a separate agent backend.'),
 ('laptop','LAPTOP',(24,388,120,44),'Open the Hub from a laptop on the same private network.'),
 ('network','TAILSCALE',(190,14,300,28),'Tailscale connects your devices privately to the PC. It is the access boundary, not an agent or a processing step.'),
 ('hub','AGENT HUB',(214,44,300,28),'The Hub runs on your PC. Its dashboard opens apps, files, projects and controls directly; TALK is another input route.'),
 ('smith','TALK / SMITH',(232,130,118,34),'Smith receives typed or spoken requests. The router chooses a command, saved routine, app action or mission from what the request needs.'),
 ('router','ROUTER',(392,240,100,56),'Route an ask to the existing capability that can handle it. Code work can go directly to Missions; media and PC tasks take their own routes.'),
 ('missions','MISSIONS',(552,130,112,34),'Select a project or create a new one, describe the goal, and run work in a private git worktree. A question can pause the work for your answer.'),
 ('runtime','AGENT RUN',(696,130,112,34),'Run the chosen agent through a configured runtime, including OpenCode or Claude Code. Planning and delegation depend on the selected mission mode.'),
 ('worktree','WORKTREE',(840,130,112,34),'Implementation and checks happen in a separate working copy. A coding mission returns changed files and its diff.'),
 ('review','REVIEW',(984,130,112,34),'Read the result, review notes and changed lines before deciding whether to apply or discard the mission.'),
 ('apply','APPLY',(1128,130,112,34),'Applying merges the reviewed coding change. Discarding removes the mission copy. A suggested Hub repair does not restart your application for you.'),
 ('skills','SKILLS',(696,64,112,34),'Bundled, vendor and user-authored SKILL.md instructions are available to agents. Catalogue entries are distinct from skills already installed.'),
 ('orchestrator','ORCHESTRATOR',(552,196,112,34),'For an orchestrated mission, plan the goal and delegate scoped briefs to named work agents. It is one role, not the whole Hub.'),
 ('team','WORK AGENTS',(696,196,112,34),'Coding, testing, review, research, writing, delivery and design roles receive task-specific briefs. Their results return to the mission.'),
 ('graph','GIT GRAPH',(840,64,112,34),'Each dot is a discovered project. Project links come from wikilinks between project entity pages; branches and worktree diffs are separate from those links.'),
 ('pc','PC CONTROL',(552,290,112,34),'Desktop tasks inspect an app, choose a named control, act and inspect the result again. A named-control press can require approval; task-level desktop runs are a separate route.'),
 ('mcp','WINDOWS MCP',(696,290,112,34),'Windows MCP supplies desktop app, control, input and inspection tools. Music success is checked against Windows media-session playback state, not just a changed button label.'),
 ('download','YT-DLP',(552,390,112,34),'Download source media on the PC. Format selection, conversion and destination belong to the media job.'),
 ('convert','FFMPEG',(696,390,112,34),'Convert media to the selected output format on the PC.'),
 ('files','FILE BROWSER',(840,390,112,34),'Browse folders you allowed. It can show media outputs and incoming files; not every file passes through the media converter.'),
 ('smb','SHARED DRIVE',(984,390,112,34),'A configured shared drive is another file-access option. It is not a compulsory final step after every download.'),
 ('hands','HAND CONTROL',(232,251,118,34),'Camera landmarks control the browser board. Point and pinch to click and drag; a fist takes control, then the open palm pans or zooms; in 3D a turn of the wrist rotates the board; two hands pinching zoom. A direct dashboard input, not an agent action.'),
 ('neo','NEO',(840,196,112,34),'Draft an agent persona from the job you describe. Review and save its instructions before adding it to your team.'),
 ('doctor','THE DOCTOR',(552,64,112,34),'Inspect Hub facts and propose a repair mission. You review its diff, choose APPLY and decide when to restart.'),
 ('apps','YOUR APPS',(232,390,118,34),'Open ingested web apps through the Hub address. An app can start on demand; it need not run a mission to open.'),
 ('routines','SAVED ROUTINES',(552,470,132,34),'Replay a saved action sequence when it matches the task and current machine. A failed replay can return to inspection instead of pretending it succeeded.'),
 ('schedule','SCHEDULE',(552,530,132,34),'A trigger decides when a request runs. Repetition does not automatically turn a single capability call into an agent mission.'),
]
EDGES=[
 ('phone','network','M132 167H145L152 174V193L159 200H174'),
 ('tablet','network','M132 215H145L159 200H174'),
 ('laptop','network','M132 263H145L152 256V207L159 200H174'),
 ('network','hub','M270 200H300'),
 ('hub','smith','M406 250V330'),
 ('hub','router','M448 180H458V75H516'),
 ('smith','router','M462 346H478V110H556V92'),
 ('router','missions','M596 75H614'),
 ('missions','runtime','M694 75H712'),
 ('runtime','worktree','M792 75H810'),
 ('worktree','review','M890 75H908'),
 ('review','apply','M988 75H1006'),
 ('missions','orchestrator','M654 92V112H700V126'),
 ('orchestrator','team','M718 158V180'),
 ('team','runtime','M772 195H784V108H760V92'),
 ('skills','runtime','M544 126V104H736V92'),
 ('worktree','graph','M850 92V126'),
 ('review','missions','M948 92V222H654V92'),
 ('router','pc','M596 75H606V262H568V290'),
 ('pc','mcp','M620 307H670'),
 ('router','download','M556 58V24H486V372H562V400'),
 ('download','convert','M608 417H630'),
 ('convert','files','M710 417H734'),
 ('hub','files','M330 250V368H793V400'),
 ('hub','smb','M318 250V480H912V434'),
 ('hands','hub','M162 408V316H300V224'),
 ('smith','neo','M350 346H300V486H99V502'),
 ('smith','doctor','M362 362V474H229V502'),
 ('doctor','missions','M284 521H292V16H654V58'),
 ('neo','team','M99 540V560H976V195H772'),
 ('hub','apps','M374 250V294H310V521'),
 ('router','routines','M584 92V114H970V486H593V502'),
 ('router','schedule','M576 92V118H984V478H777V502'),
 ('schedule','missions','M854 521H996V8H654V58'),
]

def _add(root,tag,attrs,text=None):
    node=ET.SubElement(root,'{'+NS+'}'+tag,{k:str(v) for k,v in attrs.items()})
    node.text=text
    return node

DRAW=[  # (from, to, path, kind) -- curated, left to right; every pair in EDGES still feeds the connection picker
 ('phone','hub','M144 250H214','n'),('tablet','hub','M144 330H214','n'),('laptop','hub','M144 410H214','n'),
 ('smith','router','M350 147H372V268H392','n'),('hands','router','M350 268H392','d'),
 ('router','missions','M492 268H520V147H552','n'),('router','pc','M520 268V307H552','n'),('router','download','M520 268V407H552','n'),
 ('missions','runtime','M664 147H696','n'),('runtime','worktree','M808 147H840','n'),('worktree','review','M952 147H984','n'),('review','apply','M1096 147H1128','n'),
 ('missions','orchestrator','M608 164V196','n'),('orchestrator','team','M664 213H696','n'),('team','runtime','M752 196V164','n'),('neo','team','M840 213H808','d'),
 ('skills','runtime','M752 98V130','n'),('doctor','missions','M608 98V130','d'),('worktree','graph','M896 130V98','n'),
 ('review','missions','M1040 164V258H536V147H552','d'),
 ('pc','mcp','M664 307H696','n'),
 ('download','convert','M664 407H696','n'),('convert','files','M808 407H840','n'),('files','smb','M952 407H984','n'),
 ('routines','router','M552 487H452V296','d'),('schedule','router','M552 547H432V296','d'),
]
ICONS={
 'phone':'M8 2h8a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM11 18h2',
 'tablet':'M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2',
 'laptop':'M4 5h16v10H4zM2 19h20',
 'smith':'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4',
 'hands':'M8 13V5a1.5 1.5 0 0 1 3 0v6M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V6a1.5 1.5 0 0 1 3 0v8c0 4-2 7-6 7s-4-2-6-5l-1-2a1.5 1.5 0 0 1 2.5-1.5L8 14',
 'apps':'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
 'router':'M12 3v6M12 9L5 15v5M12 9l7 6v5',
 'missions':'M5 21V4M5 4h11l-2 4 2 4H5',
 'runtime':'M7 7h10v10H7zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4',
 'worktree':'M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9',
 'review':'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
 'apply':'M4 12l5 5L20 6',
 'orchestrator':'M12 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM5 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM19 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM12 8v4M12 12l-6 4M12 12l6 4',
 'team':'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3 3-5 6-5s6 2 6 5M17 11a3 3 0 1 0 0-6M21 20c0-2-1.5-4-4-4.6',
 'neo':'M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z',
 'doctor':'M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z',
 'skills':'M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z',
 'graph':'M4 6a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM16 8a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM10 18a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM7.5 7.5l3.5 9M17 9.5L13.5 16.5',
 'pc':'M3 4h18v12H3zM8 21h8M12 16v5',
 'mcp':'M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3',
 'download':'M12 4v11M7 11l5 5 5-5M5 20h14',
 'convert':'M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4',
 'files':'M3 6h6l2 2h10v11H3z',
 'smb':'M3 14h18v6H3zM3 14l3-9h12l3 9M7 17h.01',
 'routines':'M4 9a8 8 0 0 1 14-3l2 2M20 4v4h-4M20 15a8 8 0 0 1-14 3l-2-2M4 20v-4h4',
 'schedule':'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
}
# dashed group boxes like the original circuit: (x, y, w, h, caption)
GROUPS=[(222,108,146,340,'INPUTS'),(540,50,712,200,'AUTONOMOUS LLM · private copy of your repo'),(540,272,300,66,'MCP CONTROL'),(540,372,568,66,'MEDIA VAULT'),(540,452,160,124,'REUSE + TIMING')]

def diagram(tall=False, interactive=False):
    """Drawn fresh, left to right: devices -> private network (Tailscale) containing the Hub -> inputs -> router -> what it hands work to."""
    root=ET.Element('{'+NS+'}svg',{'viewBox':'0 0 1310 650','role':'img','preserveAspectRatio':'xMidYMid meet',
        'aria-label':'Agent Hub architecture, left to right: your phone, tablet and laptop reach the Hub through a private Tailscale network; inside the Hub, inputs go to the router, which hands work to missions, desktop control, media tools, saved routines and the schedule.'})
    defs=_add(root,'defs',{})
    mk=_add(defs,'marker',{'id':'ah','viewBox':'0 0 8 8','refX':7,'refY':4,'markerWidth':7,'markerHeight':7,'orient':'auto'})
    _add(mk,'path',{'d':'M0 0L8 4L0 8Z','fill':'#00e676'})
    _add(root,'rect',{'x':0,'y':0,'width':1310,'height':650,'fill':'#050914'})
    mono={'font-family':'Orbitron,Segoe UI,sans-serif','font-weight':'700'}
    # the two containers: the private network holds the Hub
    _add(root,'rect',{'x':190,'y':14,'width':1098,'height':620,'rx':10,'fill':'#41ebff','fill-opacity':'.035','stroke':'#41ebff','stroke-opacity':'.55','stroke-dasharray':'6 5'})
    for r in range(3):
        for c in range(3):_add(root,'circle',{'cx':206+c*5,'cy':26+r*5,'r':1.6,'fill':'#41ebff'})
    _add(root,'text',dict({'x':228,'y':33,'fill':'#41ebff','font-size':'10'},**mono),'TAILSCALE · private network, nothing public')
    _add(root,'rect',{'x':214,'y':44,'width':1050,'height':560,'rx':8,'fill':'#00e676','fill-opacity':'.035','stroke':'#00e676','stroke-opacity':'.6'})
    _add(root,'image',{'href':'assets/agent-hub-logo-176.png','x':226,'y':48,'width':28,'height':28})
    _add(root,'text',dict({'x':262,'y':67,'fill':'#00e676','font-size':'10'},**mono),'AGENT HUB · runs on your PC')
    for x,y,w,h,t in GROUPS:
        _add(root,'rect',{'x':x,'y':y,'width':w,'height':h,'rx':2,'fill':'#00e676','fill-opacity':'.02','stroke':'#00e676','stroke-opacity':'.22','stroke-dasharray':'7 5'})
        tw=len(t)*5.6+14
        _add(root,'rect',{'x':x+10,'y':y-6,'width':tw,'height':12,'fill':'#05100f'})
        _add(root,'text',dict({'x':x+17,'y':y+3,'fill':'#00e676','fill-opacity':'.8','font-size':'8','letter-spacing':'1.2'},**mono),t)
    _add(root,'text',{'x':24,'y':216,'fill':'#87bba3','font-size':9,'font-family':'Outfit,system-ui'},'YOUR DEVICES')
    wires=_add(root,'g',{'class':'original-wires','fill':'none'})
    for a,b,d,kind in DRAW:
        at={'d':d,'stroke':'#00e676','stroke-width':1.5,'stroke-opacity':'.75' if kind=='n' else '.5','marker-end':'url(#ah)','data-from':a,'data-to':b,'class':'original-trace'}
        if kind=='d':at['stroke-dasharray']='5 4'
        _add(wires,'path',at)
    for key,label,(x,y,w,h),description in NODES:
        if key in ('network','hub'):continue
        dev=key in ('phone','tablet','laptop');col='#41ebff' if dev else '#00e676'
        _add(root,'rect',dict(x=x,y=y,width=w,height=h,rx=3,fill='#0b1220',stroke=col,**{'stroke-opacity':'.8' if dev or key=='router' else '.55','stroke-width':'1.6' if key=='router' else '1.2'}))
        ic=ICONS.get(key)
        if ic:
            g=_add(root,'g',{'transform':'translate(%s %s) scale(.62)'%(x+8,y+h/2-7.5),'fill':'none','stroke':col,'stroke-width':2.2,'stroke-linecap':'round','stroke-linejoin':'round','opacity':'.9'})
            _add(g,'path',{'d':ic})
        tx=x+(26+w)/2 if ic else x+w/2
        _add(root,'text',dict(x=tx,y=y+h/2+3,fill=col,**{'text-anchor':'middle','font-family':'Orbitron,Segoe UI,sans-serif','font-size':'9','font-weight':'700'}),label)
    if interactive:
        for key,label,(x,y,w,h),description in NODES:
            g=_add(root,'g',{'data-arch-node':key,'class':'original-node','role':'button','tabindex':0,'aria-label':label,'aria-pressed':'false'})
            _add(g,'title',{},label+' — '+description)
            _add(g,'rect',{'x':x,'y':y,'width':w,'height':h,'rx':2,'fill':'transparent','stroke':'transparent'})
    return ET.tostring(root,encoding='unicode')

def interactive():
    model=json.dumps({'nodes':{n[0]:n[3] for n in NODES},'labels':{n[0]:n[1] for n in NODES},'edges':[(a,b) for a,b,d in EDGES]},separators=(',',':'))
    return '<div class="architecture-shell original-shell arch-clean"><div class="architecture-viewport"><div class="original-map" data-architecture="%s">%s</div><div class="arch-tip" role="status" hidden><button type="button" aria-label="Close">&times;</button><b></b><p></p></div></div></div>'%(escape(model,quote=True),diagram(interactive=True))

def wide():return diagram()
def tall():return diagram(True)
if __name__=='__main__':
    docs=Path(__file__).resolve().parent.parent/'docs'
    (docs/'architecture.svg').write_text(wide(),encoding='utf-8')
    (docs/'architecture-tall.svg').write_text(tall(),encoding='utf-8')
