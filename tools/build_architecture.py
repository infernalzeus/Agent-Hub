"""Hub-centred public architecture. Shared modules for wide and portrait diagrams."""
from html import escape
from pathlib import Path

TOOLS = [
    ('MEDIA + FILES', 'Download · convert · inbox', 'media'),
    ('DESKTOP CONTROL', 'Windows MCP · approval first', 'pc'),
    ('PROJECTS + GIT', 'Project map · branches · diffs', 'graph'),
    ('MISSIONS', 'Private worktree · your review', 'missions'),
]

def diagram(tall=False):
    w,h=(640,920) if tall else (1440,720)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Your devices connect through a private network to Agent Hub and its PC tools">',
    '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#41ebff"/></marker></defs>',
    '<style>text{font-family:Outfit,system-ui,sans-serif}.wire{fill:none;stroke:#41ebff;stroke-width:2;stroke-opacity:.65;marker-end:url(#ah)}.fl{stroke-dasharray:7 5}.module{fill:#07162c;fill-opacity:.42;stroke:#41ebff;stroke-opacity:.5}</style>']
    def text(x,y,t,size=20,color='#d9ffe9',anchor='middle'):
        out.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" text-anchor="{anchor}">{escape(t)}</text>')
    def box(x,y,bw,bh,title,note,size=21):
        out.append(f'<rect class="module" x="{x-bw/2}" y="{y-bh/2}" width="{bw}" height="{bh}"/>')
        text(x,y-4,title,size,'#00e676');text(x,y+24,note,16)
    def wire(points):
        out.append('<path class="wire fl" d="'+'M'+'L'.join(f'{x} {y}' for x,y in points)+'"/>')
    if tall:
        box(320,60,540,82,'YOUR DEVICES','Phone · tablet · laptop')
        wire([(320,102),(320,132)])
        box(320,175,540,82,'PRIVATE DEVICE NETWORK','Reach your own PC · Tailscale')
        wire([(320,217),(320,240),(420,240),(420,260)])
        box(145,335,240,110,'INPUTS','Mouse · touch · voice',19)
        text(145,382,'Hands: board controls',15)
        wire([(266,335),(355,335)])
        out.append('<image href="assets/agent-hub-mark.png" x="355" y="260" width="130" height="130"/>')
        text(420,422,'AGENT HUB',26,'#00e676');text(420,450,'Runs on your PC',18)
        wire([(420,461),(420,490),(160,490),(160,515)])
        wire([(420,461),(420,515)])
        for i,(title,note,key) in enumerate(TOOLS):
            x=160 if i%2==0 else 480;y=565 if i<2 else 705
            if i>=2:wire([(x,y-96),(x,y-51)])
            box(x,y,292,98,title,note,19)
        wire([(320,757),(320,794)])
        box(320,846,600,96,'EXTEND YOUR HUB','Own web apps · Smith · Neo · Doctor · skills',21)
    else:
        box(180,337,294,130,'YOUR DEVICES','Phone · tablet · laptop',24)
        wire([(328,337),(380,337)])
        box(485,337,206,112,'PRIVATE NETWORK','Tailscale',20)
        wire([(590,337),(665,337)])
        out.append('<image href="assets/agent-hub-mark.png" x="675" y="245" width="180" height="180"/>')
        text(765,463,'AGENT HUB',30,'#00e676');text(765,494,'Runs on your PC',21)
        box(765,97,360,94,'CHOOSE YOUR INPUT','Mouse · touch · voice · hands',22)
        wire([(765,145),(765,234)])
        for i,(title,note,key) in enumerate(TOOLS):
            y=90+i*159
            wire([(865,337),(944,337),(944,y),(1000,y)])
            box(1200,y,394,106,title,note,23)
        wire([(765,505),(765,568)])
        box(765,625,424,102,'EXTEND YOUR HUB','Own web apps · helpers · skills',23)
        text(215,578,'ONE FRONT DOOR',22,'#41ebff')
        text(215,613,'The PC runs the work.',21)
        text(215,644,'Other devices stay within reach.',18)
    out.append('</svg>')
    return ''.join(out)

def wide(): return diagram(False)
def tall(): return diagram(True)

if __name__=='__main__':
    docs=Path(__file__).resolve().parent.parent/'docs'
    (docs/'architecture.svg').write_text(wide(),encoding='utf-8')
    (docs/'architecture-tall.svg').write_text(tall(),encoding='utf-8')
