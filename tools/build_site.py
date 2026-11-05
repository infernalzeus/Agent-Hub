"""Write docs/index.html (the public website) from the scene data below.

    python tools/build_site.py

One screen, no scrolling: a landing page (the original four tiles around the live core, Agent Smith's TALK button, DOWNLOAD and SOURCE) and one
glass scene per tool. Every step says what happens AND what you do. The TALK scene on a big screen is the animated machine from the original
page (markup in tools/site_parts/machine.html, styles in docs/assets/flow.css). Wording rules: never "AI" (say autonomous LLM, local model,
agent), no version numbers or counts, no claims about cloud, accounts or auto-update, and no status above what has been seen running.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
V = "20261105d"
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
    ("agents", "AGENTS + SKILLS", "AGENTS + SKILLS", "A team you can read and extend.", [("Live", "")],
     "Roles, handoffs, skills and repairs you approve.", "Your Hub, any device", "Manage the team from your browser."),
    ("architecture", "ARCHITECTURE", "ARCHITECTURE", "How it fits together.", [("Live", "")],
     "Drawn from the Hub as it is built today: Smith, Neo and the Doctor included.", "Windows · macOS · Linux", "Desktop control is Windows only."),
    ("install", "GET STARTED", "GET STARTED", "Your PC, within reach.", [("Live", "")],
     "Install, connect, bookmark.", "Windows · macOS · Linux", "macOS builds are unsigned."),
]

# title, short line, what happens, what you do, you-decide?
STEPS = {
    "missions": [
        ("Ask", "Type it or say it", "No form to learn. A sentence typed on the board, spoken to TALK from your phone, or the first step of a saved automation.", "Type or say what you want, from any device.", 0),
        ("Route", "Cheapest answer first", "Most questions never need an agent. The router walks a ladder and stops at the first rung that can answer, so you are not paying a model to tell you the time.", "Nothing. The hub picks the cheapest way.", 0),
        ("Plan", "Split it into briefs", "One planner reads the ask and proposes the pieces. Briefs that do not depend on each other run side by side; one that needs earlier work waits for it.", "Nothing, unless it asks you a question.", 0),
        ("Work", "In a private copy", "Each mission gets its own git worktree on its own branch. Your files do not change while it runs, and a provider hiccup moves the run to the next model instead of failing it.", "Nothing. Watch it appear in the Git Graph if you like.", 0),
        ("Ask you", "It parks if it is stuck", "An agent at a real fork does not guess. The run parks, the question reaches whichever device is open, and your answer resumes the same mission. It never asks for a password or a key.", "Answer the question from whichever device you have.", 1),
        ("Review", "Read the diff", "When the work is done the mission stops with the diff beside it. This is the one decision the system will not make for you.", "Read the diff. This part is yours.", 1),
        ("Apply", "Or discard", "Apply merges the branch into your repo. Discard removes the copy and the branch. An automation waiting on this carries on only if you applied.", "Press APPLY to merge it, or DISCARD to throw it away.", 1),
    ],
    "pc": [
        ("Say it", "In plain words", "“Open Apple Music and play my liked songs.” Speak to TALK or type it. No scripting, no recorded macro to maintain.", "Say or type what you want done.", 0),
        ("Look", "Find it by name, not by pixel", "Windows MCP reads the controls on screen, so it finds Play by what it is, not by where it was last time.", "Nothing.", 0),
        ("Ask first", "You see the press before it happens", "It shows the control it found and waits for your yes before touching anything.", "Look at the press it shows, then say yes or no.", 1),
        ("Act", "Click, type, open", "Windows MCP presses the control. Shell, registry, file and process tools are switched off, so it can drive apps but not rewrite the machine.", "Nothing. It cannot rewrite the machine.", 0),
        ("Check", "Did it actually work?", "A press only counts if the window changed. A replay that leaves the window as it was is not counted as a success.", "Nothing.", 0),
        ("Remember", "Learned once, replayed after", "A run that worked is saved as a routine. It starts as a candidate and is trusted only after it has worked twice.", "Nothing. Ask again later and it replays.", 0),
    ],
    "media": [
        ("Download", "yt-dlp, audio or video", "The download runs on your PC, as audio or as video.", "Paste a link, or say what to save.", 0),
        ("Convert", "ffmpeg makes the format you picked", "ffmpeg turns it into the format you chose, on your PC.", "Pick the format.", 0),
        ("Save", "To the folder you chose", "The result is saved to the folder you picked, not to someone else's server.", "Pick the folder.", 0),
        ("It is yours to use", "Browse it, or copy it to your phone", "Browse it here, or copy it from your phone. Files you send from your phone land in your inbox on the PC.", "Open it, or copy it to your phone.", 0),
    ],
    "graph": [
        ("One dot per project", "Found in your own folders", "The map finds your projects in the folders you chose and draws one dot for each, read straight from git.", "Open the Git Graph.", 0),
        ("Status at a glance", "Changes waiting, orphaned copies", "See which projects have changes waiting and which agent copies have been left behind.", "Look for dots with changes waiting.", 0),
        ("Open the diff", "Changed files, line by line", "Tap a dot to see exactly what an agent changed, including the copy it is working in right now.", "Tap a dot and read what changed.", 0),
        ("Your move", "Merge the branch, or leave it", "Merge the agent's branch, or leave it. Nothing is merged for you.", "Merge it, or leave it.", 1),
    ],
    "install": [
        ("Install", "On your own machine", "Download it for your system and run it. The first run asks what to set up, and every step says what it downloads. Desktop control is Windows only.", "Choose your system below and run the installer.", 0),
        ("Private access", "Install Tailscale", "Install Tailscale on this PC and on your phone, so they can reach each other privately.", "Install Tailscale on both devices.", 0),
        ("Connect", "Your own network", "Sign both into the same private network. Nothing is exposed to the internet.", "Sign both devices into the same network.", 0),
        ("Open", "Keep it within reach", "Open the hub address and save the bookmark to your home screen.", "Open the address and save the bookmark.", 0),
    ],
    "skills": [
        ("Add a skill", "Pick one, add it to your agents", "A skill is a pack of instructions an agent can follow, such as how to make a launch video. Adding one gives your agents that ability.", "Open the Skills tab and press ADD TO MY AGENTS.", 0),
        ("Write your own", "It is just a SKILL.md file", "A skill is one text file of instructions. Write it for the work you want done.", "Write the file and drop it in.", 0),
        ("Every agent gets them", "OpenCode and Claude Code", "Skills are published to the skill folders of OpenCode and Claude Code, so any agent session can use them.", "Nothing. They are there when an agent needs them.", 0),
    ],
}

TALK_PHONE = [
    ("What's the weather in Leeds?", "A routine that worked before", "Smith answers from a saved routine. No model call, no agent started.", "Ask. That is all.", 0),
    ("Add a dark-mode toggle to settings", "This changes code, so it becomes a mission", "Smith starts a mission: planned and worked in a private copy. Your repo has not changed; the diff is waiting on you.", "Read the diff later and press APPLY.", 1),
    ("Play my liked songs in Apple Music", "This needs the desktop, so it goes to PC control", "Smith hands it to the desktop agent, which finds the control, shows you the press, does it, and checks the window changed.", "Say yes to the press it shows.", 0),
    ("Save this video as audio", "A media job: a tool, not an agent", "Downloaded and converted on your PC. Open it in the browser, or copy it from your phone.", "Open the file or copy it.", 0),
    ("What did the agents change?", "A question about your repos: plain git", "One dot per project, read straight from git. Tap one to see exactly what an agent changed.", "Tap a dot.", 0),
    ("Every morning, summarise new PRs", "This runs on a clock", "Ran on its clock and stopped at review. Nothing applies while you sleep.", "Review it in the morning.", 1),
]

# image, name, one line, chips, what you do
AGENTS = [
    ("smith", "Agent Smith", "The voice you talk to: Talk, spoken answers, and the Hub's own commands.", ["To Router", "To Desktop agent", "To The Doctor", "To Neo"],
     "Press TALK, then speak or type. Smith answers out loud and on screen, and hands the job to whoever should do it."),
    ("neo", "Neo", "Designs a new agent from a plain description and hands back one ready-to-save file.", ["From Smith", "To your team"],
     "Describe the job in plain words, read the file Neo hands back, and save it. The new agent joins your team."),
    ("doctor", "The Doctor", "Diagnoses the Hub when something is wrong and proposes a fix as a diff in Missions. Never restarts anything.", ["From Smith", "Works in Missions"],
     "Say “Smith, something is wrong” or press ASK THE DOCTOR on a red item. Read the diff and press APPLY. Restarting stays yours."),
    ("desktop-agent", "Desktop agent", "Presses and types in apps on this PC for a goal, one step at a time, checking the screen after each.", ["From Smith", "Windows only"],
     "Say what you want done. It shows each press and asks first."),
    ("orchestrator", "orchestrator", "Asks what it must, then splits your ask into steps, independent ones side by side. Writes no code.", ["To coder", "To reviewer", "To researcher"],
     "Answer its question if it asks one. Otherwise nothing."),
    ("coder", "coder", "Ships the smallest change that works, in the project's own style. Leaves what you didn't ask about alone.", ["From orchestrator", "To reviewer"],
     "Nothing. You read the result in the diff."),
    ("reviewer", "reviewer", "The skeptic. Never edits; says ship, changes-needed or blocked, and points at the line.", ["From coder"],
     "Read its verdict, then the diff."),
    ("tester", "tester", "Tries to break it before you do: writes the tests, runs them, reports what failed and why.", ["From orchestrator"],
     "Nothing. The failures show up in the review."),
]


def chips(items):
    return "".join('<span class="chip %s">%s%s</span>' % ("tested" if n != "Live" else "", escape(n), (" · " + escape(note)) if note else "") for n, note in items)


def slab(inner, cls="", z=20, d=36):
    """A glass slab: the front face plus a five-sided volume behind it, the way the dashboard draws a block in 3D."""
    return ('<div class="slabbox %s" style="--z:%dpx;--d:%dpx"><i class="vol" aria-hidden="true"><b class="back"></b><b class="left"></b><b class="right"></b><b class="top"></b><b class="bottom"></b></i>%s</div>'
            % (cls, z, d, inner))


def small_blocks(chips_, line, runs, runs_line):
    a = ('<button class="blk small-block" type="button" aria-expanded="false" data-more><span class="label">Status</span>%s<span class="line">%s</span><span class="more">%s</span></button>'
         % (chips(chips_), escape(line), escape(LEGEND)))
    b = ('<button class="blk small-block" type="button" aria-expanded="false" data-more><span class="label">Runs on</span><span class="line strong">%s</span><span class="line">%s</span>'
         '<span class="more">Everything runs on your own PC and your own network: no cloud, no account.</span></button>' % (escape(runs), escape(runs_line)))
    return '<aside class="side-blocks">%s%s</aside>' % (slab(a, "side s1", 48, 22), slab(b, "side s2", 48, 22))


def _auto_wrap(lis, with_downloads=False):
    dl = ""
    if with_downloads:
        dl = ('<div class="downloads"><a class="action" href="%s/releases/latest/download/Agent-Hub-Setup.exe">Windows</a>'
              '<a class="action" href="%s/releases/latest/download/Agent-Hub-macOS.dmg">macOS</a>'
              '<a class="action" href="%s/releases/latest/download/Agent-Hub-Linux.tar.gz">Linux</a></div>' % (REPO, REPO, REPO))
    return ('<div class="auto" data-auto><ol class="auto-steps">%s</ol><div class="auto-detail">%s<img class="pic" alt="" hidden><p class="kicker"></p><h3></h3><p class="d"></p>'
            '<div class="you"><span class="yl">What you do</span><p></p></div><div class="chips-row"></div><span class="bar" aria-hidden="true"></span></div></div>' % (lis, dl))


def auto(steps, with_downloads=False):
    lis = []
    for i, (t, em, d, you, gate) in enumerate(steps):
        lis.append('<li><button class="st%s" type="button" data-t="%s" data-k="%s" data-d="%s" data-you="%s"%s><span class="num">%d</span><span class="sb"><b>%s</b><em>%s</em></span></button>'
                   '<p class="more-static">%s <b>You:</b> %s</p></li>'
                   % (" gate" if gate else "", escape(t, True), escape(em, True), escape(d, True), escape(you, True), ' aria-pressed="true"' if i == 0 else ' aria-pressed="false"',
                      i + 1, escape(t), escape(em), escape(d), escape(you)))
    return _auto_wrap("".join(lis), with_downloads)


def agents_body() -> str:
    lis = []
    for i, (img, name, role, ch, you) in enumerate(AGENTS):
        kind = "Hub helper" if img in ("smith", "neo", "doctor", "desktop-agent") else "Team agent"
        lis.append('<li><button class="st card" type="button" data-t="%s" data-k="%s" data-d="%s" data-you="%s" data-img="%s%s.png" data-chips="%s"%s>'
                   '<img class="av" src="%s%s.png" alt="" width="40" height="40"><span class="sb"><b>%s</b></span></button>'
                   '<p class="more-static">%s <b>You:</b> %s</p></li>'
                   % (escape(name, True), kind, escape(role, True), escape(you, True), AG, img, escape("|".join(ch), True), ' aria-pressed="true"' if i == 0 else ' aria-pressed="false"',
                      AG, img, escape(name), escape(role), escape(you)))
    agents = _auto_wrap("".join(lis)).replace('class="auto"', 'class="auto agents-auto"', 1)
    skills = auto(STEPS["skills"])
    return ('<div class="agency"><div class="tabs" role="tablist"><button class="tab" role="tab" type="button" aria-selected="true" data-tab="agents">AGENTS</button>'
            '<button class="tab" role="tab" type="button" aria-selected="false" data-tab="skills">SKILLS</button></div>'
            '<div class="tabpanel" data-panel="agents">%s</div><div class="tabpanel" data-panel="skills" hidden>%s</div></div>' % (agents, skills))


def scene(sid, label, headline, chips_, line, runs, runs_line, body, wide=False, extra_head=""):
    main = ('<article class="blk main-block"><header class="blk-h"><p class="label">%s</p><h2 id="%s-title" tabindex="-1">%s</h2><span class="hchips">%s</span>%s</header><div class="blk-b">%s</div></article>'
            % (escape(label), sid, escape(headline), chips(chips_), extra_head, body))
    return ('<section class="scene" id="%s" aria-labelledby="%s-title"><div class="board%s" data-tilt>%s%s</div></section>'
            % (sid, sid, " wide" if wide else "", slab(main, "main", 20, 36), "" if wide else small_blocks(chips_, line, runs, runs_line)))


def build() -> str:
    machine = (Path(__file__).resolve().parent / "site_parts" / "machine.html").read_text(encoding="utf-8")
    machine = machine.replace("You say", "You say it to Smith").replace("The hub decides", "Smith decides")
    parts = []
    for sid, door, label, headline, ch, line, runs, runs_line in SCENES:
        if sid == "talk":
            smith = '<span class="smith-card"><img src="%ssmith.png" alt="Agent Smith" width="44" height="44"><span>Press TALK, or type. Smith answers out loud and on screen.</span></span>' % AG
            body = ('<div class="talk-desktop"><div class="fit"><div class="flow">%s</div></div></div><div class="talk-phone">%s</div>' % (machine, auto(TALK_PHONE)))
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, body, wide=True, extra_head=smith))
        elif sid == "agents":
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, agents_body()))
        elif sid == "architecture":
            body = ('<button class="arch-open" type="button" data-zoom aria-label="Enlarge the architecture diagram"><picture class="architecture-picture"><source media="(max-width:650px) and (orientation:portrait)" srcset="architecture-tall.svg">'
                    '<img src="architecture.svg" alt="Agent Hub architecture: devices reach the Hub over a private network; Agent Smith hears you and routes the ask; Neo designs new agents; the Doctor repairs the Hub; missions, PC control, media and the git graph" width="1120" height="760"></picture></button>'
                    '<div class="zoom" hidden><button class="zoom-x" type="button" data-zoom-close>Close ✕</button><div class="zoom-scroll"><picture><source media="(max-width:650px) and (orientation:portrait)" srcset="architecture-tall.svg">'
                    '<img src="architecture.svg" alt="" width="1120" height="760"></picture></div></div>')
            enlarge = '<button class="enlarge" type="button" data-zoom>ENLARGE ⤢</button>'
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, body, wide=True, extra_head=enlarge))
        elif sid == "install":
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, auto(STEPS[sid], with_downloads=True)))
        else:
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, auto(STEPS[sid])))
    tiles = [s for s in SCENES if s[0] in ("missions", "pc", "media", "graph")]
    doors = "".join(slab('<a class="door blk" href="#%s">%s</a>' % (sid, escape(door)), "doorbox", 40, 34) for sid, door, *_ in tiles)
    smith_btn = slab('<a class="smith-btn blk" href="#talk" aria-label="Talk to Agent Smith"><img src="%ssmith.png" alt="" width="52" height="52"><span><b>TALK</b><em>Agent Smith</em></span></a>' % AG, "smithbox", 50, 30)
    head = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<meta name="description" content="Your most powerful PC tools at your fingertips, any device. Agent Hub brings autonomous LLM missions, desktop control, media and projects together.">'
        '<title>Agent Hub — InfernalZeus</title><link rel="icon" href="assets/favicon-32.png" sizes="32x32"><link rel="icon" href="assets/favicon.ico" sizes="any">'
        '<link rel="apple-touch-icon" href="assets/favicon-180.png"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;600;700;800&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">'
        '<link rel="stylesheet" href="assets/flow.css?v=%s"><link rel="stylesheet" href="assets/site.css?v=%s"></head>\n' % (V, V))
    landing = (
        '<section class="scene landing active" id="landing" aria-labelledby="landing-title"><canvas id="hub-grid" aria-hidden="true"></canvas><div class="tilt-layer" data-tilt>'
        '<h1 class="hero-title" id="landing-title" tabindex="-1">Agent Hub</h1>'
        '<div class="mark-host" id="hero-mark" role="img" aria-label="Agent Hub globe and crystalline core"><noscript><img src="assets/agent-hub-mark.png" alt="" width="256" height="256"></noscript></div>'
        '<p class="tagline">Your most powerful PC tools at your fingertips, any device.</p>'
        '<div class="actions"><a class="action primary" href="#install">DOWNLOAD</a><a class="action" href="%s">SOURCE ↗</a></div>'
        '<nav class="more-links" aria-label="More"><a href="#agents">AGENTS + SKILLS</a><a href="#architecture">ARCHITECTURE</a></nav>'
        '%s<nav class="doors" aria-label="The tools">%s</nav></div></section>' % (REPO, smith_btn, doors))
    body = ('<body><header class="site-header"><a class="brand" href="#" data-home aria-label="Agent Hub — return to landing"><img src="assets/agent-hub-mark.png" alt="" width="44" height="44">AGENT HUB</a>'
            '<a class="projects" href="https://infernalzeus.github.io/">← PROJECTS</a></header><main class="stage">%s%s</main>'
            '<script src="assets/agent-hub-mark.min.js?v=20261105b" defer></script><script src="assets/depth-lift-site.js?v=%s" defer></script>'
            '<script src="assets/site.js?v=%s" defer></script></body></html>\n' % (landing, "".join(parts), V, V))
    return head + body


if __name__ == "__main__":
    (DOCS / "index.html").write_text(build(), encoding="utf-8")
    print("wrote docs/index.html")
