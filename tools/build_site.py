"""Write docs/index.html (the public website) from the scene data below.

    python tools/build_site.py

One screen, no scrolling: a landing page (the original four tiles around the live core, Agent Smith's TALK button, DOWNLOAD and SOURCE) and one
glass scene per tool. Every step says what happens AND what you do. The TALK scene on a big screen is the animated machine from the original
page (markup in tools/site_parts/machine.html, styles in docs/assets/flow.css). Wording rules: never "AI" (say autonomous LLM, local model,
agent), no version numbers or counts, no claims about cloud, accounts or auto-update, and no status above what has been seen running.
"""
from __future__ import annotations

import re
import json

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
import sys as _sys
_sys.path.insert(0, str(DOCS.parent))
from hub.agent_knowledge import AGENT_NAMES      # the names of the four core agents come from the one place that holds them
V = "20261109-architecture-first-paint"
REPO = "https://github.com/infernalzeus/Agent-Hub"
AG = "assets/agents/"
LEGEND = "Live: seen running on a real machine. Unit-tested: the logic is tested, not yet seen running. Built, not tried: built and tested without the real hardware."

# id, tile label, scene label, headline, chips, status line, runs-on, runs-on line
SCENES = [
    ("talk", "TALK", "TALK · AGENT SMITH", "Say it once. Smith does the rest.", [("Live", "typed"), ("Unit-tested", "voice")],
     "The voice path is tested; typed asks have been seen running.", "Phone, tablet, laptop", "Browser access to your own PC."),
    ("missions", "AUTONOMOUS LLM", "AUTONOMOUS LLM", "Your project. Your decision.", [("Live", "")],
     "An agent works in a private copy. You APPLY or DISCARD.", "Windows · macOS · Linux", "Reach your PC from any device."),
    ("pc", "MCP CONTROL", "MCP CONTROL", "It asks before it presses anything.", [("Unit-tested", "")],
     "Built and unit-tested; a replay on a real desktop has not been recorded yet.", "Windows only", "Windows MCP drives desktop apps."),
    ("media", "MEDIA VAULT", "MEDIA VAULT", "Download, convert, browse, receive.", [("Live", "")],
     "Download, convert, browse and receive.", "Windows · macOS · Linux", "Files stay on your PC and network."),
    ("graph", "GIT GRAPH", "GIT GRAPH", "Every project as one dot.", [("Live", "")],
     "Project status and worktree diffs.", "Windows · macOS · Linux", "Reads your local git projects."),
    ("agents", "AGENCY", "AGENCY", "A team you can read and extend.", [("Live", "")],
     "Roles, handoffs, skills and repairs you approve.", "Your Hub, any device", "Manage the team from your browser."),
    ("hands", "HAND CONTROL", "HAND CONTROL", "Your hands move the Hub board.", [("Built, not tried", "gestures")],
     "Camera recognition seen running; physical board gestures still need a hardware trial.", "Camera + browser", "Explicit camera start; board controls only."),
    ("architecture", "ARCHITECTURE", "ARCHITECTURE", "How it fits together.", [("Live", "")],
     "Your devices reach one Hub, with PC tools and helpers behind it.", "Windows · macOS · Linux", "Desktop control is Windows only."),
    ("install", "GET STARTED", "GET STARTED", "Your PC, within reach.", [("Live", "")],
     "Install, connect, bookmark.", "Windows · macOS · Linux", "macOS builds are unsigned."),
]

# title, short line, what happens, what you do, you-decide?
STEPS = {'missions': [('Ask',
               'YOU',
               'Smith receives your request and hands it to the router.',
               'Type or say: add a dark-mode toggle to settings.',
               0),
              ('Route',
               'HUB · ROUTER',
               'A code change becomes a mission, rather than a direct answer.',
               'Check that the request says what you want.',
               0),
              ('Plan',
               'PLANNER AGENT',
               'The planner divides the mission into briefs for named agents.',
               'Answer if the planner needs a decision.',
               0),
              ('Work',
               'CODING AGENT',
               'The agent changes a private git worktree, not your project.',
               'Watch progress; your working files stay untouched.',
               0),
              ('Ask you',
               'AGENT → YOU',
               'A blocked mission parks with a question, then resumes.',
               'Answer the question from your open device.',
               1),
              ('Review',
               'YOU',
               'The finished mission stops with its diff ready to read.',
               'Read the changed lines and the review.',
               1),
              ('Apply or discard',
               'YOU',
               'APPLY merges the branch. DISCARD removes the private copy.',
               'Choose APPLY or DISCARD. Nothing merges for you.',
               1)],
 'pc': [('Say it',
         'YOU → SMITH',
         'Smith hands the request to the Windows desktop agent.',
         'Ask for the named Play control in Apple Music.',
         0),
        ('Look',
         'DESKTOP AGENT',
         'Windows MCP finds the control by name, not by pixel.',
         'Wait while it identifies the control.',
         0),
        ('Ask first',
         'YOU · APPROVAL GATE',
         'The proposed press is shown before the agent acts.',
         'Read the proposal; say yes or no.',
         1),
        ('Act', 'WINDOWS MCP', 'The approved click or typing is sent to the app.', 'Watch the app respond.', 0),
        ('Check',
         'DESKTOP AGENT',
         'A desktop music task checks Windows media-session playback state and the track, rather than trusting a changed button label.',
         'Review the result the agent reports.',
         0),
        ('Remember', 'HUB', 'A successful run is saved as a candidate routine.', 'Ask again later to use the saved routine.', 0)],
 'media': [('Download',
            'YOU → YT-DLP',
            'The audio or video download runs on your own PC.',
            'Paste a link: save this video as audio.',
            0),
           ('Convert', 'FFMPEG', 'The file is converted into the format you picked.', 'Choose the output format.', 0),
           ('Save', 'YOU → HUB', 'The result goes to the folder you selected.', 'Pick the destination folder.', 0),
           ('Browse or receive',
            'YOU',
            "Browse the PC's files or send a file from your phone.",
            'Open a result, copy it, or use the phone inbox.',
            0)],
 'graph': [('Open the map',
            'YOU',
            'The map draws projects found in your chosen folders.',
            'Open Git Graph and choose a project dot.',
            0),
           ('Read its status',
            'HUB · GIT',
            'Git reports changes and the copies agents are using.',
            'Check the project and its working branches.',
            0),
           ('Inspect the diff',
            'YOU',
            'Changed files and lines appear for the selected copy.',
            'Tap the worktree, then read its diff.',
            0),
           ('Merge or leave',
            'YOU',
            'The branch stays separate until you choose to merge it.',
            'Merge the branch, or leave it as it is.',
            1)],
 'install': [('Install',
              'YOU',
              'An installed Hub opens a first-run setup wizard.',
              'Choose your system and run the installer.',
              0),
             ('Choose tools',
              'YOU → SETUP',
              'Setup asks which optional tools to prepare.',
              'Choose what you need; read each setup prompt.',
              0),
             ('Connect privately',
              'YOU · TAILSCALE',
              'Your PC and phone join the same private network.',
              'Join the same private Tailscale network.',
              0),
             ('Open the Hub',
              'YOU',
              'The browser reaches your PC through that private network.',
              'Save the Hub address to your home screen.',
              0)],
 'skills': [('Bundled skills', 'HUB', "23 ship with the Hub, each a plain SKILL.md you can read.", 'Open SKILLS and read one.', 0),
            ('Add to my agents', 'YOU → HUB', 'The skill becomes available to your agents.', 'Press ADD TO MY AGENTS.', 0),
            ('A catalogue skill', 'HUB', 'Optional extras, such as Launch videos. Rendering stays on this PC.', 'Add only if you want it.', 0),
            ('Write your own', 'YOU', 'A folder with a SKILL.md: name, when to use it, instructions.', 'Write the file, add the skill.', 0)]}

TALK_PHONE = [
    ("What's the weather in Leeds?", "A routine that worked before", "If a matching routine is available, Smith reuses the lookup. Otherwise the Hub chooses another route; this example does not imply a weather routine is preinstalled.", "Ask. That is all.", 0),
    ("Add a dark-mode toggle to settings", "This changes code, so it becomes a mission", "Smith starts a mission: planned and worked in a private copy. Your repo has not changed; the diff is waiting on you.", "Read the diff later and press APPLY.", 1),
    ("Play my liked songs in Apple Music", "This needs the desktop, so it goes to PC control", "Smith hands it to the desktop agent, which inspects controls, operates the app step by step, and verifies Windows playback.", "Watch the task inspect the app, act and verify Windows playback.", 0),
    ("Save this video as audio", "A media job: a tool, not an agent", "Downloaded and converted on your PC. Open it in the browser, or copy it from your phone.", "Open the file or copy it.", 0),
    ("What did the agents change?", "A question about your repos: plain git", "One dot per project, read straight from git. Tap one to see exactly what an agent changed.", "Tap a dot.", 0),
    ("Every morning, summarise new PRs", "This runs on a clock", "Ran on its clock and stopped at review. Nothing applies while you sleep.", "Review it in the morning.", 1),
]

# image, name, what it is / does / cannot do / example, chips, what you do
# Every line below is read from the Hub's own files (hub/agent_knowledge/agents/*.md, the router, the Doctor, the desktop agent).
AGENTS = [('smith', 'Agent Smith', 'Hears you, answers aloud and sends each request the right way. Never acts alone.', ['Router', 'Desktop agent', 'Neo', 'Doctor'], 'Press TALK or type.'),
 ('router', 'The router', 'Sorts a request before any model is used, and learns from your grades.', ['Routine', 'Mission', 'PC task', 'Media'], 'Grade its choices in TEACH.'),
 ('orchestrator', 'orchestrator', 'Plans a mission as briefs for the other agents. Writes no code.', ['To coder', 'To tester', 'To reviewer'], 'Answer if it asks.'),
 ('coder', 'coder', 'Makes the change in a private copy. Your repo stays put until APPLY.', ['From Victor', 'To reviewer'], 'Read the diff.'),
 ('reviewer', 'reviewer', 'Read-only skeptic: ship, changes-needed or blocked.', ['From coder'], 'Read its verdict.'),
 ('tester', 'tester', 'Writes and runs the tests, reports what failed.', ['From Victor'], 'Read the failures.'),
 ('researcher', 'researcher', 'Reads code, docs and the web. Read-only.', ['From Victor'], 'Read the findings.'),
 ('neo', 'Neo', 'Designs a new agent from a description. Ten more roles ship ready to switch on.', ['From Smith', 'To your team'], 'Describe the job, save the file.'),
 ('doctor', 'The Doctor', 'Diagnoses the Hub and proposes a fix. You press APPLY and restart.', ['Mission', 'Checks', 'Your APPLY'], 'Review the diff.'),
 ('desktop-agent', 'Desktop agent', 'Works inside Windows apps. Says so when it cannot find something.', ['Windows only', 'Local model'], 'Approve the press.')]


def chips(items):
    return ""

def slab(inner, cls="", z=8, d=0):
    return '<div class="slabbox %s" style="--z:8px;--d:0px">%s</div>' % (cls, inner)

def small_blocks(chips_, line, runs, runs_line):
    return ""

def _auto_wrap(lis, with_downloads=False):
    dl = ""
    if with_downloads:
        dl = '<div class="downloads">' + ''.join('<a class="action" href="%s/releases/latest/download/%s"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="3" y="3" width="18" height="13"/><path d="M12 16v5M7 21h10"/></svg>%s</a>' % (REPO, f, n) for n, f in [("Windows", "Agent-Hub-Setup.exe"),("macOS", "Agent-Hub-macOS.dmg"),("Linux", "Agent-Hub-Linux.tar.gz")]) + '</div>'
    return ('<div class="auto" data-auto><ol class="auto-steps" aria-label="How it works">%s</ol><div class="auto-detail">'
            '<div class="you"><span class="yl">YOU DO</span><p></p></div><div class="detail-copy"><p class="kicker"></p><h3></h3><p class="d"></p></div>'
            '<div class="visual" data-visual aria-label="Illustrated handoff"></div>%s<img class="pic" alt="" hidden><div class="chips-row"></div><span class="bar" aria-hidden="true"></span></div></div>' % (lis, dl))


def auto(steps, with_downloads=False):
    lis=[]
    for i,(title,who,does,you,gate) in enumerate(steps):
        lis.append('<li><button class="st%s" type="button" data-t="%s" data-k="%s" data-d="%s" data-you="%s" aria-pressed="%s"><span class="num">%d</span><span class="sb"><b>%s</b><em>%s</em></span></button><p class="more-static">%s <b>You do:</b> %s</p></li>' % (" gate" if gate else "",escape(title,True),escape(who,True),escape(does,True),escape(you,True),"true" if i==0 else "false",i+1,escape(title),escape(who),escape(does),escape(you)))
    return _auto_wrap(''.join(lis),with_downloads)


def _source_text(rel, name):
    """The text of a module-level string constant, read from the Hub's own source without importing it."""
    import ast
    tree = ast.parse((Path(__file__).resolve().parent.parent / rel).read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == name:
            return ast.literal_eval(node.value).strip()
    return ''


def agents_body():
    principal = [next(a for a in AGENTS if a[0]==key) for key in ("orchestrator","neo","smith","doctor")]
    lis=[]
    for i,(img,name,role,ch,you) in enumerate(principal):
        role = {'orchestrator': 'Victor, the orchestrator. Turns your goal into scoped briefs, assigns the right specialists and manages dependencies between their tasks. Brings their results back for review. Plans and delegates; it does not edit project code.', 'smith': 'Your voice and text front door to the Hub. Checks known commands and routines, then routes your request to a tool, desktop task, helper or mission. You can ask follow-up questions in the same conversation.', 'neo': 'Designs agents for the job you describe. Drafts their responsibilities, instructions and working preferences as an editable persona. You review and save the definition before adding that agent to your team.', 'doctor': 'Investigates Hub problems using current diagnostics, logs and configuration. Explains the likely cause and proposes a repair in a private working copy. You review the diff, choose APPLY and decide when to restart.'}[img]
        definition=role
        if img in ('orchestrator','neo'):
            definition=(Path(__file__).resolve().parent.parent/'hub/agent_knowledge/agents'/f'{img}.md').read_text(encoding='utf-8').split('---',2)[-1].strip()
        elif img=='smith':
            definition="Smith's standing instructions (hub/features/voice.py), before the live Hub state is added:" + chr(10) + chr(10) + _source_text('hub/features/voice.py','_SYSTEM')
        elif img=='doctor':
            definition="The Doctor's standing instructions (hub/features/support.py), before the live Hub facts are added:" + chr(10) + chr(10) + _source_text('hub/features/support.py','RULES')
        lis.append('<li><button data-definition="%s" class="st card" type="button" data-t="%s" data-k="AGENCY" data-d="%s" data-you="%s" data-img="%s%s.svg" aria-pressed="%s"><img class="av" src="%s%s.svg" alt="" width="48" height="48"><span class="sb"><b>%s</b><em>%s</em></span></button></li>' % (escape(definition,True),escape(AGENT_NAMES[img][0] if img in AGENT_NAMES else name,True),escape(role,True),escape(you,True),AG,img,'true' if i==0 else 'false',AG,img,escape(AGENT_NAMES[img][0] if img in AGENT_NAMES else name),{'orchestrator':AGENT_NAMES['orchestrator'][1] + ' · plans and delegates','smith':'Voice and chat','neo':'Designs agents','doctor':'Repairs the Hub'}[img]))
    agents=_auto_wrap(''.join(lis)).replace('class="auto"','class="auto agents-auto"',1)
    groups={
      'Code': ['coder','tester','reviewer','scout'],
      'Research': ['analyst','researcher','data-analyst'],
      'Writing': ['copywriter','editor','doc-writer','ops-writer'],
      'Delivery': ['product-manager','project-manager'],
      'Design': ['designer','compliance-reviewer']}
    rows=[]
    for group, names in groups.items():
        for name in names:
            source=Path(__file__).resolve().parent.parent/'hub/agent_knowledge/agents'/f'{name}.md'
            definition=source.read_text(encoding='utf-8')
            about=re.search(r'^about:\s*(.+)$',definition,re.M)
            description=re.search(r'^description:\s*(.+)$',definition,re.M)
            text=(about or description).group(1).strip().strip('"')
            rows.append('<button type="button" class="work-agent" data-work-group="%s" data-work-description="%s" data-work-definition="%s"%s><b>%s</b><span>%s</span></button>' % (group,escape(text,True),escape(definition.split('---',2)[-1].strip(),True),' hidden' if group!='Code' else '',escape(name),escape(text)))
    examples = (
        '<div class="work-examples"><div class="work-examples-controls" role="group" aria-label="Example requests">'
        '<button type="button" class="ui-btn" data-work-example="calculator" aria-pressed="true">Simple ask</button>'
        '<button type="button" class="ui-btn" data-work-example="launch" aria-pressed="false">Bigger ask</button></div>'
        '<article data-work-scenario="calculator"><h3>Build a simple calculator</h3>'
        '<p>Victor, the orchestrator, briefs one coder to build a calculator with four operations and handle invalid input. The coder returns the working change for your review.</p>'
        '<ol class="work-briefs"><li><b>Coder</b><span>Implement the calculator and check the basic cases.</span></li></ol></article>'
        '<article data-work-scenario="launch" hidden><h3>Build and launch a calculator site</h3>'
        '<p>Victor breaks the request into briefs. The crew grows with the task, and briefs that depend on earlier work run after it.</p>'
        '<ol class="work-briefs"><li><b>Designer</b><span>Sketch the interface for phone and desktop.</span></li>'
        '<li><b>Coder</b><span>Build the calculator and integrate the design.</span></li>'
        '<li><b>Copywriter</b><span>Draft the launch page and social copy for the intended audience.</span></li>'
        '<li><b>Tester</b><span>Check calculations, edge cases and keyboard access.</span></li>'
        '<li><b>Reviewer</b><span>Assess the proposed changes before you decide what to apply.</span></li></ol></article></div>'
    )
    work = ('<div class="work-panel"><nav class="work-categories" aria-label="Work types">'
            + ''.join('<button type="button" class="ui-btn" data-work-category="%s" aria-pressed="%s">%s</button>'
                      % (g, str(g == 'Code').lower(), g) for g in groups)
            + '</nav><div class="work-list">' + ''.join(rows) + '</div><section class="work-reading">'
            + examples + '<div class="work-role" hidden><div class="work-role-head"><p class="work-description" aria-live="polite"></p>'
            '<button type="button" class="ui-btn" data-work-examples-back>Examples</button></div><pre class="work-definition"></pre></div></section></div>')
    return '<div class="agency"><div class="tabs" role="tablist" aria-label="Agency"><button class="tab" role="tab" type="button" aria-selected="true" data-tab="agents">CORE CREW</button><button class="tab" role="tab" type="button" aria-selected="false" data-tab="work">OPERATIVES</button><button class="tab" role="tab" type="button" aria-selected="false" data-tab="skills">SKILLS</button></div><div class="tabpanel" data-panel="agents">%s</div><div class="tabpanel" data-panel="work" hidden>%s</div><div class="tabpanel" data-panel="skills" hidden>%s</div></div>' % (agents,work,auto(STEPS['skills']))

def scene(sid, label, headline, chips_, line, runs, runs_line, body, wide=False, extra_head=""):
    main = ('<article class="blk main-block"><header class="blk-h"><p class="label">%s</p><h2 id="%s-title" tabindex="-1">%s</h2>%s</header><div class="blk-b">%s</div></article>' % (escape(label),sid,escape(headline),extra_head,body))
    return '<section class="scene" id="%s" aria-labelledby="%s-title"><div class="board wide" data-tilt>%s</div></section>' % (sid,sid,slab(main,"main"))


# Ordered stories. Each row separates the responsible actor, the result and the user's action.

STORY = {
 "talk": ("Press TALK or type: save this video as audio.","Smith routes it to media; the result appears on your PC.","Typed: Live. Voice: Unit-tested, not seen running."),
 "missions": ("Add a dark-mode toggle to settings.","A mission, its private branch and a diff waiting for you.","OpenCode, Claude Code or configured local models. APPLY is yours."),
 "pc": ("Open Apple Music and play my liked songs.","A proposed press, your approval, then a checked result.","Windows only · Unit-tested. Shell, registry, file and process tools off."),
 "media": ("Save this video as audio.","A download, a conversion and a file in your chosen folder.","Your PC does the download and conversion; it must stay on."),
 "graph": ("What did the agents change?", "A project map, its working branch and the changed lines.","Reads local git projects. You choose whether to merge."),
 "agents": ("Make an agent that reviews my writing.","Neo gives you a persona file to read and save.","The Doctor proposes a diff. APPLY and restarting stay yours."),
 "install": ("Choose your system, then open the first-run wizard.","Tool choices, private-device access and a Hub bookmark.","Unsigned macOS builds. Desktop control is Windows only.")}

STEPS["hands"] = [
 ("Start", "YOU", "Start Hands from the dashboard or the Hands tab of the log. The camera is opt-in and tracking runs on your device. The board overlays a hand skeleton with labelled fingertips.", "Start the camera explicitly in your Hub.", 1),
 ("Point", "INDEX FINGER", "The fingertip is your cursor. Hold your finger still over Settings. The ring fills, then Settings opens.", "Point at a control and hold still.", 0),
 ("Drag", "THUMB + INDEX + MIDDLE", "Bring thumb, index and middle together. The point between them carries the block, window or panel under it; open your fingers to drop it.", "Pinch three fingers, move, then let go.", 0),
 ("Take control", "FIST, THEN OPEN PALM", "With fist control enabled, make a fist and then open your palm to pan or zoom. In View: 3D, turn a closed fist to tilt the board. Hand Setup lets you inspect and change gesture rules.", "Make a fist, then open your hand and move it.", 0)]


STEPS['graph'] = [
 ("Project map", "YOUR PROJECTS", "Projects orbit category hubs such as My Repo and Collab Projects. Select a project to see its status, links and available work.", "Choose a project in the example map.", 0),
 ("Connections", "PROJECT CONTEXT", "Project connections come from wikilinks between discovered projects’ entity pages. They are separate from branches and worktrees.", "Select a connected project to follow its context.", 0),
 ("New project", "MISSIONS", "Choose New Project in Missions. The Hub scaffolds a git repository before creating the mission's private worktree.", "Name a project in this browser-only example.", 0),
 ("Private work", "MISSION WORKTREE", "Agents change a separate git worktree. Your project's working files stay untouched until review.", "Inspect the working branch and its changed files.", 0),
 ("Review diff", "YOU", "Read the project agent-branch diff and choose whether to merge it in Git Graph. Mission APPLY and DISCARD remain separate decisions in Missions.", "Read the changed lines, or return to the map.", 1)]

STORY['talk']=("Press TALK, or choose an example below.","Smith answers or opens the tool that handles the request.","")
STORY['hands']=("Choose HANDS in the dashboard, then point at a block.","Pan, zoom, drag and turn the board with your hand.","Every gesture can be switched off or changed in the HANDS menu.")
STEPS['skills']=[
 ("Hub library","SKILLS","Preview a skill’s purpose and example workflow. In your Hub, open the installed skill to read its instructions.","Choose a topic or search the skill library.",0),
 ("Open-source skills","OPEN SOURCE","Browse third-party skills by publisher and licence, including Apache-2.0 and MIT. Catalogue entries remain separate from installed skills.","Open a skill to see its scope, origin and a worked example.",0),
 ("Add a skill","CATALOGUE","Launch videos (brag) is available through the Hub catalogue from latent-spaces.","Review the skill and add it when it fits your work.",0),
 ("Write your own","NEW SKILL","Describe a reusable task, read the drafted SKILL.md, then save it.","Describe the task and review the instructions before saving.",0)]

# Keep the short card summaries distinct from the explicit handoff flows.

def story(sid, body):
    ask, seen, _ = STORY[sid]
    return '<div class="story">%s<footer class="story-foot"><div class="try-panel"><h3>YOUR ACTION</h3><p>%s</p></div><div class="result-panel"><h3>IN THE HUB</h3><p class="expect">%s</p></div></footer></div>' % (body,escape(ask),escape(seen))

def talk_table():
    destinations=["Saved routine","Mission","Desktop agent","Media tools","Git Graph","Scheduled mission"]
    rows=''.join('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % ('<button type="button" data-talk-example="%s">%s</button>' % (TALK_PHONE.index(t),escape(t[0])),dest,escape(result)) for t,dest,result in zip(TALK_PHONE,destinations,['Answer aloud and on screen','Private-copy mission and review diff','Proposed press for your approval','Saved audio file on your PC','Project map and changed lines','Scheduled run, stopped at review']))
    return '<table class="say-table"><caption>YOU SAY → SMITH SENDS IT → YOU GET</caption><thead><tr><th>You say</th><th>Smith sends it to</th><th>You get / you do</th></tr></thead><tbody>'+rows+'</tbody></table>'


def skill_examples():
    examples={
      'debugging-methodology':'Example: a settings toggle does not persist.\n\n1. Reproduce the failure with one clear action.\n2. Compare the displayed setting with the saved value.\n3. Find where the two diverge.\n4. Make the smallest correction.\n5. Repeat the original action and check persistence.',
      'testing-conventions':'Example: check a new settings toggle.\n\nCover the user-visible behavior: initial value, changing it, and reopening settings. Include a failure case that matters. Report the result and any remaining gap.',
      'python-aiohttp-webapp':'Example: add a settings endpoint.\n\nValidate the incoming value, perform the intended change asynchronously, and return a clear result. The interface should show an actionable error if saving fails.',
      'frontend-design':'Example: improve a project browser.\n\nDefine the main action, establish a readable hierarchy, use the existing brand, and make selected and empty states clear. Check the same task on a phone and desktop.',
      'mcp-builder':'Example: expose a project-status tool.\n\nGive the tool a focused purpose, define its inputs, describe its result, and return useful errors. Keep its permissions appropriate to the job.',
      'webapp-testing':'Example: review a project browser.\n\nOpen the map, select a project, inspect a changed file, and return. Check keyboard access, narrow layouts, errors and any unexpected overlap.',
      'brag':'Example: explain a finished feature in a short launch video.\n\nChoose the user benefit, plan the shots, use relevant app footage, then review the rendered result. Launch videos is an optional catalogue skill; adding it is separate from browsing its entry.'}
    scope = {
      'debugging-methodology': 'Use this for failures and regressions. Reduce the repro, read the exception chain, bisect against a known good case and instrument the boundary where values diverge. Verify that the original failure and nearby cases pass.',
      'testing-conventions': 'Use this to choose meaningful checks. Assert observable behaviour, isolate external dependencies at their boundaries and cover edge cases. Use real temporary storage when persistence itself is under test.',
      'python-aiohttp-webapp': 'Use this for async Hub-style web services. Keep blocking work off the event loop, reuse the app’s routing pattern, use async subprocesses and release resources in the cleanup hook.',
      'frontend-design': 'Use this to design or substantially reshape an interface. Define its audience and main job, build a visual hierarchy from its content, and make typography, interaction and responsive layout work together.',
      'mcp-builder': 'Use this to design an MCP server for an external service. Map useful workflows to tool inputs and results, implement permissions and informative errors, and evaluate tasks an agent should be able to complete.',
      'webapp-testing': 'Use this to exercise a local web app through a real browser. Check the rendered state, interact with controls and inspect screenshots and console output when behaviour differs from expectations.',
      'brag': 'This optional catalogue entry covers launch-video production. It is an example of a skill you can browse separately from the skills already installed in your Hub.'
    }
    examples = {name: scope[name] + chr(10) * 2 + example for name, example in examples.items()}
    return json.dumps(examples,ensure_ascii=False).replace('<','\\u003c')


def build() -> str:
    machine = (Path(__file__).resolve().parent / "site_parts" / "machine.html").read_text(encoding="utf-8")
    machine = machine.replace("You say", "You say it to Smith").replace("The hub decides", "Smith decides").replace("split into briefs, run side by side", "split into briefs for worker agents")
    machine = machine.replace('finds controls by name, not pixel','reads the app’s available controls').replace('Ask, then act','Act, then inspect').replace('shows the press, waits for yes','a named press can require approval').replace('the window must actually change','verify the requested outcome').replace('Saved as a routine, trusted after it works twice.','Successful steps can be kept as a routine.').replace('Found the control, showed you the press, did it,','Inspected the app, acted step by step,').replace('and checked the window changed.','and verified Windows playback.').replace('A routine that worked before','If a matching routine exists').replace('Answered from a saved routine.','A matching routine replays the lookup.').replace('weather, time — no model','reuse the lookup, not a stale answer')
    machine = re.sub(r'<span class="chip [^"]+">.*?</span>', "", machine)
    parts = []
    for sid, door, label, headline, ch, line, runs, runs_line in SCENES:
        if sid == "talk":
            smith = '<span class="smith-card"><span class="smith-input">Speak or type</span><img src="%ssmith.svg" alt="" width="52" height="52"><span class="smith-name">Smith</span></span>' % AG
            body = story(sid, '<div class="talk-desktop"><div class="fit"><div class="flow">%s</div></div>%s</div><div class="talk-phone">%s</div>' % (machine, talk_table(), auto(TALK_PHONE)))
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, body, wide=True, extra_head=smith))
        elif sid == "agents":
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, story(sid, agents_body())))
        elif sid == "architecture":
            import build_architecture as ba
            body = ba.interactive() + '<div class="zoom" role="dialog" aria-modal="true" aria-label="Enlarged architecture" hidden><div class="zoom-tools"><button class="zoom-x" type="button" data-zoom-close>Close ×</button><button type="button" data-zoom-in aria-label="Zoom in">+</button><button type="button" data-zoom-out aria-label="Zoom out">−</button></div><div class="zoom-scroll"><div class="zoom-map"></div></div></div>'
            parts.append(scene(sid,label,headline,ch,line,runs,runs_line,body,wide=True,extra_head='<button class="enlarge" type="button" data-zoom>ENLARGE ⤢</button>'))
        elif sid == "install":
            download_buttons = '<div class="downloads">' + ''.join('<a class="action" href="%s/releases/latest/download/%s"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="3" y="3" width="18" height="13"/><path d="M12 16v5M7 21h10"/></svg>%s</a>' % (REPO, f, n) for n, f in [("Windows", "Agent-Hub-Setup.exe"),("macOS", "Agent-Hub-macOS.dmg"),("Linux", "Agent-Hub-Linux.tar.gz")]) + '</div>'
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, story(sid, auto(STEPS[sid])), extra_head=download_buttons))
        else:
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, story(sid, auto(STEPS[sid]))))
    tiles = [s for s in SCENES if s[0] in ("missions", "pc", "media", "graph")]
    doors = "".join(slab('<a class="door blk" href="#%s">%s</a>' % (sid, escape(door)), "doorbox", 40, 52) for sid, door, *_ in tiles)
    smith_btn = slab('<a class="smith-btn blk" href="#talk" aria-label="Talk to Agent Smith"><img src="%ssmith.svg" alt="" width="52" height="52"><span><b>TALK</b><em>Agent Smith</em></span></a>' % AG, "smithbox", 50, 30)
    head = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>html.site-boot{background:#080c28}html.site-boot :is(.site-header,.stage){opacity:0;pointer-events:none}</style>'
        '<script>document.documentElement.classList.add("site-boot");setTimeout(()=>document.documentElement.classList.remove("site-boot"),5000)</script>'
        '<meta name="description" content="Your most powerful PC tools at your fingertips, any device. Agent Hub brings autonomous LLM missions, desktop control, media and projects together.">'
        '<title>Agent Hub — InfernalZeus</title><link rel="icon" href="assets/favicon-32.png?v=%s" sizes="32x32" type="image/png"><link rel="icon" href="assets/favicon.svg?v=%s" sizes="any" type="image/svg+xml">'
        '<link rel="apple-touch-icon" href="assets/favicon-180.png"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;600;700;800&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">'
        '<link rel="stylesheet" href="assets/flow.css?v=%s"><link rel="stylesheet" href="assets/site.css?v=%s"><link rel="stylesheet" href="assets/site-demos.css?v=%s"></head>\n' % (V, V, V, V, V))
    landing = (
        '<section class="scene landing active" id="landing" aria-labelledby="landing-title"><canvas id="hub-grid" aria-hidden="true"></canvas><div class="tilt-layer" data-tilt>'
        '<h1 class="hero-title" id="landing-title" tabindex="-1">Agent Hub</h1>'
        '<div class="mark-host" id="hero-mark" role="img" aria-label="Agent Hub globe and crystalline core"><noscript>Agent Hub</noscript></div>'
        '<p class="tagline">Your most powerful tools<br>At your fingertips<br>Any device</p>'
        '<div class="landing-controls"><div class="actions"><a class="action primary" href="#install">DOWNLOAD</a><a class="action" href="%s">SOURCE ↗</a></div>'
        '<form class="wishlist-form" data-endpoint="https://script.google.com/macros/s/AKfycbz2T9CWYAWuEUBqfz5awCmd7z4GSPKna63rh5Im9yg6lStm32PGHfylbPcYV4RnYYUypw/exec"><div><input id="wishlist-email" type="email" autocomplete="email" placeholder="Learn to build your own Agent Hub" title="Type in your email" data-email-prompt aria-label="Email for the build guide wishlist" required><button type="submit">JOIN</button></div><p role="status" hidden></p></form>'
        '<nav class="more-links" aria-label="More"><a href="#agents">AGENCY</a><a href="#architecture">ARCHITECTURE</a><a href="#hands">HAND CONTROL</a></nav></div>'
        '%s<nav class="doors" aria-label="The tools">%s</nav></div></section>' % (REPO, smith_btn, doors))
    body = ('<body><header class="site-header"><a class="brand" href="#" data-home aria-label="Agent Hub — return to landing"><img src="assets/agent-hub-logo-176.png" alt="" width="44" height="44" decoding="async">AGENT HUB</a>'
            '<a class="projects" href="https://infernalzeus.github.io/" data-projects><span class="old-project-arrow" aria-hidden="true">←</span><span><span class="projects-owner">INFERNALZEUS - </span>PROJECTS</span></a></header><main class="stage">%s%s</main>'
            '<script src="assets/agent-hub-mark.min.js?v=20261105b" defer></script><script src="assets/depth-lift-site.js?v=%s" defer></script>'
            '<script src="assets/hand-player.js?v=%s" defer></script>'
            '<script src="assets/site.js?v=%s" defer></script></body></html>\n' % (landing, "".join(parts), V, V, V))
    payload='<script type="application/json" id="site-skill-library">'+skill_examples()+'</script>'
    return head + body.replace('<script src="assets/agent-hub-mark',payload+'<script src="assets/agent-hub-mark',1)


if __name__ == "__main__":
    (DOCS / "index.html").write_text(build(), encoding="utf-8")
    print("wrote docs/index.html")
