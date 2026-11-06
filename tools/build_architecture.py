"""Keep the pre-Codex circuit layout; update only its labels, wiring and additions.

The unmodified reference is tools/site_parts/architecture-original.svg from
4df980c. Tailscale belongs inside ACCESS, not to the mission execution chain.
"""
from pathlib import Path
from html import escape
import json
import xml.etree.ElementTree as ET

ROLE_BADGES={'orchestrator': 'M12 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM5 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM19 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM12 8v4M12 12l-6 4M12 12l6 4', 'neo': 'M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z', 'doctor': 'M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z'}
NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
PARTS=Path(__file__).resolve().parent/'site_parts'
# id, label, bounds in the ORIGINAL drawing, explanation
NODES=[
 ('phone','PHONE',(46,150,86,34),'Your phone opens the same Hub interface through private device access.'),
 ('tablet','TABLET',(46,198,86,34),'Your tablet reaches the Hub on your PC; it does not run a separate agent backend.'),
 ('laptop','LAPTOP',(46,246,86,34),'Open the Hub from a laptop on the same private network.'),
 ('network','TAILSCALE',(174,183,96,34),'Tailscale connects your devices privately to the PC. It is the access boundary, not an agent or a processing step.'),
 ('hub','AGENT HUB',(300,150,148,100),'The Hub runs on your PC. Its dashboard opens apps, files, projects and controls directly; TALK is another input route.'),
 ('smith','TALK / SMITH',(350,330,112,32),'Smith receives typed or spoken requests. The router chooses a command, saved routine, app action or mission from what the request needs.'),
 ('router','ROUTER',(516,58,80,34),'Route an ask to the existing capability that can handle it. Code work can go directly to Missions; media and PC tasks take their own routes.'),
 ('missions','MISSIONS',(614,58,80,34),'Select a project or create a new one, describe the goal, and run work in a private git worktree. A question can pause the work for your answer.'),
 ('runtime','AGENT RUN',(712,58,80,34),'Run the chosen agent through a configured runtime, including OpenCode or Claude Code. Planning and delegation depend on the selected mission mode.'),
 ('worktree','WORKTREE',(810,58,80,34),'Implementation and checks happen in a separate working copy. A coding mission returns changed files and its diff.'),
 ('review','REVIEW',(908,58,80,34),'Read the result, review notes and changed lines before deciding whether to apply or discard the mission.'),
 ('apply','APPLY',(1006,58,80,34),'Applying merges the reviewed coding change. Discarding removes the mission copy. A suggested Hub repair does not restart your application for you.'),
 ('skills','SKILLS',(498,126,92,32),'Bundled, vendor and user-authored SKILL.md instructions are available to agents. Catalogue entries are distinct from skills already installed.'),
 ('orchestrator','ORCHESTRATOR',(664,126,108,32),'For an orchestrated mission, plan the goal and delegate scoped briefs to named work agents. It is one role, not the whole Hub.'),
 ('team','WORK AGENTS',(664,180,108,30),'Coding, testing, review, research, writing, delivery and design roles receive task-specific briefs. Their results return to the mission.'),
 ('graph','GIT GRAPH',(804,126,96,32),'Each dot is a discovered project. Project links come from wikilinks between project entity pages; branches and worktree diffs are separate from those links.'),
 ('pc','PC CONTROL',(516,290,104,34),'Desktop tasks inspect an app, choose a named control, act and inspect the result again. A named-control press can require approval; task-level desktop runs are a separate route.'),
 ('mcp','WINDOWS MCP',(670,290,118,34),'Windows MCP supplies desktop app, control, input and inspection tools. Music success is checked against Windows media-session playback state, not just a changed button label.'),
 ('download','YT-DLP',(516,400,92,34),'Download source media on the PC. Format selection, conversion and destination belong to the media job.'),
 ('convert','FFMPEG',(630,400,80,34),'Convert media to the selected output format on the PC.'),
 ('files','FILE BROWSER',(734,400,118,34),'Browse folders you allowed. It can show media outputs and incoming files; not every file passes through the media converter.'),
 ('smb','SHARED DRIVE',(876,400,72,34),'A configured shared drive is another file-access option. It is not a compulsory final step after every download.'),
 ('hands','HAND CONTROL',(44,408,236,42),'Camera landmarks control the browser board: pointer, pinch click and drag, fist rotation and open-palm fit. Hand control is a direct dashboard input, not an agent action.'),
 ('neo','NEO',(804,176,108,30),'Draft an agent persona from the job you describe. Review and save its instructions before adding it to your team.'),
 ('doctor','THE DOCTOR',(44,502,150,38),'Inspect Hub facts and propose a repair mission. You review its diff, choose APPLY and decide when to restart.'),
 ('apps','YOUR APPS',(226,502,180,38),'Open ingested web apps through the Hub address. An app can start on demand; it need not run a mission to open.'),
 ('routines','SAVED ROUTINES',(516,502,154,38),'Replay a saved action sequence when it matches the task and current machine. A failed replay can return to inspection instead of pretending it succeeded.'),
 ('schedule','SCHEDULE',(700,502,154,38),'A trigger decides when a request runs. Repetition does not automatically turn a single capability call into an agent mission.'),
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
 ('smith','neo','M462 346H488V166H858V176'),
 ('smith','doctor','M350 346H294V468H119V502'),
 ('doctor','missions','M119 502V482H286V8H654V58'),
 ('neo','team','M804 191H790V195H772'),
 ('hub','apps','M374 250V284H306V490H316V502'),
 ('router','routines','M584 92V114H1074V486H593V502'),
 ('router','schedule','M576 92V118H1090V478H777V502'),
 ('schedule','missions','M854 521H1104V16H654V58'),
]

def _add(root,tag,attrs,text=None):
    node=ET.SubElement(root,'{'+NS+'}'+tag,{k:str(v) for k,v in attrs.items()})
    node.text=text
    return node

def diagram(tall=False, interactive=False):
    # Both exports deliberately keep the SAME left-to-right architecture.
    root=ET.parse(PARTS/'architecture-original.svg').getroot()
    root.set('shape-rendering','geometricPrecision')
    root.set('text-rendering','geometricPrecision')
    root.set('viewBox','0 0 1120 580');root.attrib.pop('width',None)
    root.set('aria-label','Agent Hub: original left-to-right circuit architecture, with current routes and private Tailscale access.')
    root[0].set('height','580')
    for el in list(root):
        if el.tag.endswith('path') and el.attrib.get('stroke-linecap')=='round':root.remove(el)
    replacements={
      'OpenCode':'Router','Dispatch':'Agent run','Agent Team':'Work agents','SMB':'Drive',
      'one app on your PC · binds 127.0.0.1':'one Hub on your PC',
      'Every device reaches one address. Nothing is exposed to the internet.':'Your devices connect privately to the same Hub.',
      'A successful run is kept as a routine and replayed next time.':'Inspect → act → verify. Reuse a routine when it fits.',
      'the worktree diff, drawn live':'projects · links · worktree diffs',
      're-plan and carry on, until you apply or discard':'review, answer or re-plan; APPLY remains your choice',
      'Fetch it, convert it, and reach your drives from the phone in your hand.':'Download and convert on the PC; browse or receive files from your devices.',
      'TALK':'SMITH / TALK'}
    for el in root:
        if el.tag.endswith('text') and el.text in replacements:el.text=replacements[el.text]
    # Original diagram ends at y=492. Additions occupy its existing bottom margin
    # and the space below ACCESS without moving ANY original component.
    for key,label,(x,y,w,h),description in NODES:
        if key not in ('hands','neo','doctor','apps','routines','schedule'):continue
        _add(root,'rect',dict(x=x,y=y,width=w,height=h,rx=2,fill='#0b1220',stroke='#00e676',**{'stroke-opacity':'.5'}))
        _add(root,'text',dict(x=x+w/2,y=y+h/2+3,fill='#00e676',**{'text-anchor':'middle','font-family':'Orbitron,Segoe UI,sans-serif','font-size':'9','font-weight':'700'}),label)
    _add(root,'text',{'x':44,'y':396,'fill':'#87bba3','font-size':9,'font-family':'Outfit,system-ui'},'DIRECT DASHBOARD INPUT')
    _add(root,'text',{'x':44,'y':488,'fill':'#87bba3','font-size':9,'font-family':'Outfit,system-ui'},'HELPERS + APPS')
    _add(root,'text',{'x':509,'y':488,'fill':'#87bba3','font-size':9,'font-family':'Outfit,system-ui'},'REUSE + TIMING')
    _add(root,'text',{'x':712,'y':110,'fill':'#a8cbb9','font-size':8,'font-family':'Outfit,system-ui'},'OpenCode · Claude Code')
    badges=ROLE_BADGES
    for key in ('orchestrator','neo','doctor'):
        x,y,w,h=next(n[2] for n in NODES if n[0]==key)
        group=_add(root,'g',{'transform':f'translate({x+7} {y+h/2-8}) scale(.65)','fill':'none','stroke':'#00e676','stroke-width':1.8,'stroke-linecap':'round','stroke-linejoin':'round'})
        _add(group,'path',{'d':badges[key]})
    for el in root:
        if el.tag.endswith('text') and el.text in ('Orchestrator','NEO','THE DOCTOR'):
            el.set('x',str(float(el.get('x'))+8))
    # Wiring is inserted behind the unchanged chip faces, never over their text.
    wires=ET.Element('{'+NS+'}g',{'class':'original-wires','fill':'none'})
    for a,b,d in EDGES:
        _add(wires,'path',{'d':d,'stroke':'#00e676','stroke-width':1.4,'stroke-opacity':'.72','marker-end':'url(#ah)','data-from':a,'data-to':b,'class':'original-trace'})
    # Give crossing routes a visible gap: crossing lines are not junctions.
    import re
    def segments(d):
        result=[];x=y=0
        for op,numbers in re.findall(r'([MLHV])([^MLHV]+)',d):
            values=[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?',numbers)]
            nx,ny=(values[0],values[1]) if op in 'ML' else (values[0],y) if op=='H' else (x,values[0])
            if op!='M':result.append((x,y,nx,ny))
            x,y=nx,ny
        return result
    routes=[segments(d) for _,_,d in EDGES]
    for i,path in enumerate(wires):
        rebuilt=[]
        for x,y,nx,ny in routes[i]:
            cuts=[]
            if x==nx:
                for j,other in enumerate(routes):
                    if i==j:continue
                    for ax,ay,bx,by in other:
                        if ay==by and min(ax,bx)<x<max(ax,bx) and min(y,ny)<ay<max(y,ny):cuts.append(ay)
            rebuilt.append(f'M{x} {y}')
            if cuts:
                direction=1 if ny>y else -1
                for cut in sorted(set(cuts),reverse=direction<0):rebuilt.append(f'L{x} {cut-direction*3.5} M{x} {cut+direction*3.5}')
            rebuilt.append(f'L{nx} {ny}')
        path.set('d',' '.join(rebuilt))
        path.attrib.pop('marker-end',None)
    for i,(a,b,d) in enumerate(EDGES):
        x,y,nx,ny=routes[i][-1]
        import math
        length=math.hypot(nx-x,ny-y)
        _add(wires,'path',{'d':f'M{nx-(nx-x)/length*.1} {ny-(ny-y)/length*.1}L{nx} {ny}','stroke':'#00e676','stroke-width':1.4,'marker-end':'url(#ah)','data-from':a,'data-to':b,'class':'original-arrow'})
    root.insert(2,wires)
    # Labels use the page's loaded fonts in both normal and enlarged views.
    for el in root.iter():
        if el.tag.endswith('text') and 'fill-opacity' in el.attrib:
            el.set('fill-opacity',str(max(.85,float(el.get('fill-opacity')))))
    if interactive:
        for key,label,(x,y,w,h),description in NODES:
            g=_add(root,'g',{'data-arch-node':key,'class':'original-node','role':'button','tabindex':0,'aria-label':label,'aria-pressed':'false'})
            _add(g,'title',{},label+' — '+description)
            _add(g,'rect',{'x':x,'y':y,'width':w,'height':h,'rx':2,'fill':'transparent','stroke':'transparent'})
    return ET.tostring(root,encoding='unicode')

def interactive():
    model=json.dumps({'labels':{n[0]:n[1] for n in NODES},'nodes':{n[0]:n[3] for n in NODES}})
    return '<div class="architecture-shell static-architecture"><div class="architecture-viewport"><div class="original-map" data-architecture="'+escape(model,quote=True)+'">'+diagram(interactive=True)+'</div></div><aside class="arch-tip" hidden aria-live="polite"><b></b><p></p><button type="button" aria-label="Close architecture description">×</button></aside></div>'

def wide():return diagram()
def tall():return diagram(True)
if __name__=='__main__':
    docs=Path(__file__).resolve().parent.parent/'docs'
    (docs/'architecture.svg').write_text(wide(),encoding='utf-8')
    (docs/'architecture-tall.svg').write_text(tall(),encoding='utf-8')
