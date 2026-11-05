"""Write docs/index.html (the public website) from the scene data below.

    python tools/build_site.py

One screen, no scrolling: a landing page with eight doors, and one glass scene per door. The TALK scene on a big screen is the animated
machine from the original page (docs/assets/flow.css, markup in docs/assets/machine.html); every other scene is an auto-playing step list
that you can also tap. Wording rules: never "AI" (say autonomous LLM, local model, agent), no version numbers or counts, no claims about
cloud, accounts or auto-update, and no status above what has been seen running (Live / Unit-tested / Built, not tried).
"""
from __future__ import annotations

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
V = "20261105c"
REPO = "https://github.com/infernalzeus/Agent-Hub"

STATUS_LEGEND = "Live: seen running on a real machine. Unit-tested: the logic is tested, not yet seen running. Built, not tried: built and tested without the real hardware."

# id, door label, scene label, headline, status chip(s), status line, runs-on, runs-on line
SCENES = [
    ("talk", "TALK", "TALK", "Say it once. The hub does the rest.", [("Live", "typed"), ("Unit-tested", "voice")],
     "The voice path is tested; typed asks have been seen running.", "Phone, tablet, laptop", "Browser access to your own PC."),
    ("missions", "AUTONOMOUS LLM", "AUTONOMOUS LLM", "Your project. Your decision.", [("Live", "")],
     "An agent works in a private copy. You APPLY or DISCARD.", "Windows · macOS · Linux", "Reach your PC from any device."),
    ("pc", "PC CONTROL", "PC CONTROL", "It asks before it presses anything.", [("Unit-tested", "")],
     "Built and unit-tested; a replay on a real desktop has not been recorded yet.", "Windows only", "Windows MCP drives desktop apps."),
    ("media", "MEDIA VAULT", "MEDIA VAULT", "Download, convert, browse, receive.", [("Live", "")],
     "Download, convert, browse and receive.", "Windows · macOS · Linux", "Files stay on your PC and network."),
    ("graph", "GIT GRAPH", "GIT GRAPH", "Every project as one dot.", [("Live", "")],
     "Project status and worktree diffs.", "Windows · macOS · Linux", "Reads your local git projects."),
    ("agents", "AGENTS + SKILLS", "AGENTS + SKILLS", "A team you can read and extend.", [("Live", "")],
     "Roles, handoffs, skills and repairs you approve.", "Your Hub, any device", "Manage the team from your browser."),
    ("architecture", "ARCHITECTURE", "ARCHITECTURE", "How it fits together.", [("Live", "")],
     "Drawn from the Hub as it is built today.", "Windows · macOS · Linux", "Desktop control is Windows only."),
    ("install", "GET STARTED", "GET STARTED", "Your PC, within reach.", [("Live", "")],
     "Install, connect, bookmark.", "Windows · macOS · Linux", "macOS builds are unsigned."),
]

# (title, short line, detail, you-decide?)
STEPS = {
    "missions": [
        ("Ask", "Type it or say it", "No form to learn. A sentence typed on the board, spoken to TALK from your phone, or the first step of a saved automation.", 0),
        ("Route", "Cheapest answer first", "Most questions never need an agent. The router walks a ladder and stops at the first rung that can answer, so you are not paying a model to tell you the time.", 0),
        ("Plan", "Split it into briefs", "One planner reads the ask and proposes the pieces. Briefs that do not depend on each other run side by side; one that needs earlier work waits for it.", 0),
        ("Work", "In a private copy", "Each mission gets its own git worktree on its own branch. Your files do not change while it runs, and a provider hiccup moves the run to the next model instead of failing it.", 0),
        ("Ask you", "It parks if it is stuck", "An agent at a real fork does not guess. The run parks, the question reaches whichever device is open, and your answer resumes the same mission. It never asks for a password or a key.", 1),
        ("Review", "Read the diff", "When the work is done the mission stops with the diff beside it. This is the one decision the system will not make for you.", 1),
        ("Apply", "Or discard", "Apply merges the branch into your repo. Discard removes the copy and the branch. An automation waiting on this carries on only if you applied.", 1),
    ],
    "pc": [
        ("Say it", "In plain words", "“Open Apple Music and play my liked songs.” Speak to TALK or type it. No scripting, no recorded macro to maintain.", 0),
        ("Look", "Find it by name, not by pixel", "Windows MCP reads the controls on screen, so it finds Play by what it is, not by where it was last time.", 0),
        ("Ask first", "You see the press before it happens", "It shows the control it found and waits for your yes before touching anything.", 1),
        ("Act", "Click, type, open", "Windows MCP presses the control. Shell, registry, file and process tools are switched off, so it can drive apps but not rewrite the machine.", 0),
        ("Check", "Did it actually work?", "A press only counts if the window changed. A replay that leaves the window as it was is not counted as a success.", 0),
        ("Remember", "Learned once, replayed after", "A run that worked is saved as a routine. It starts as a candidate and is trusted only after it has worked twice.", 0),
    ],
    "media": [
        ("Download", "yt-dlp, audio or video", "Paste a link or ask in plain words. The download runs on your PC, as audio or as video.", 0),
        ("Convert", "ffmpeg makes the format you picked", "ffmpeg turns it into the format you chose, on your PC.", 0),
        ("Save", "To the folder you chose", "The result is saved to the folder you picked, not to someone else's server.", 0),
        ("It is yours to use", "Browse it, or copy it to your phone", "Browse it here, or copy it from your phone. Files you send from your phone land in your inbox on the PC.", 0),
    ],
    "graph": [
        ("One dot per project", "Found in your own folders", "The map finds your projects in the folders you chose and draws one dot for each, read straight from git.", 0),
        ("Status at a glance", "Changes waiting, orphaned copies", "See which projects have changes waiting and which agent copies have been left behind.", 0),
        ("Open the diff", "Changed files, line by line", "Tap a dot to see exactly what an agent changed, including the copy it is working in right now.", 0),
        ("Your move", "Merge the branch, or leave it", "Merge the agent's branch, or leave it. Nothing is merged for you.", 1),
    ],
    "agents": [
        ("Smith", "The helper you talk to", "Smith is the helper you talk to; the request goes to the right tool or agent.", 0),
        ("Neo", "Makes an agent from a sentence", "Neo drafts an agent from your description. You review the role, then add it to your team.", 0),
        ("The team", "Roles that hand work on", "Agents have their own roles and hand work to each other. The planner splits a mission into briefs and hands them to agents in private copies.", 0),
        ("Skills", "Abilities you can add", "Give an agent a new ability by adding a skill, or write your own for the work you want done.", 0),
        ("Doctor", "Repairs you approve", "The Doctor proposes a repair to the Hub and hands the change to you. You review it, then press APPLY.", 1),
    ],
    "install": [
        ("Install", "On your own machine", "Download it for your system and run it. The first run asks what to set up, and every step says what it downloads. Desktop control is Windows only.", 0),
        ("Private access", "Install Tailscale", "Install Tailscale on this PC and on your phone, so they can reach each other privately.", 0),
        ("Connect", "Your own network", "Sign both into the same private network. Nothing is exposed to the internet.", 0),
        ("Open", "Keep it within reach", "Open the hub address and save the bookmark to your home screen.", 0),
    ],
}

TALK_PHONE = [
    ("What's the weather in Leeds?", "A routine that worked before", "Answered from a saved routine. No model call, no agent started.", 0),
    ("Add a dark-mode toggle to settings", "This changes code, so it becomes a mission", "Planned and worked in a private copy. Your repo has not changed; the diff is waiting on you.", 1),
    ("Play my liked songs in Apple Music", "This needs the desktop, so it goes to PC control", "Found the control, showed you the press, did it, and checked the window changed.", 0),
    ("Save this video as audio", "A media job: a tool, not an agent", "Downloaded and converted on your PC. Open it in the browser, or copy it from your phone.", 0),
    ("What did the agents change?", "A question about your repos: plain git", "One dot per project, read straight from git. Tap one to see exactly what an agent changed.", 0),
    ("Every morning, summarise new PRs", "This runs on a clock", "Ran on its clock and stopped at review. Nothing applies while you sleep.", 1),
]

ICON = {
    "talk": '<path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4"/>',
}


def chips(items):
    out = []
    for name, note in items:
        cls = "tested" if name != "Live" else ""
        out.append('<span class="chip %s">%s%s</span>' % (cls, escape(name), (" · " + escape(note)) if note else ""))
    return "".join(out)


def small_blocks(sid, chips_, line, runs, runs_line):
    return (
        '<aside class="side-blocks">'
        '<button class="blk small-block" type="button" aria-expanded="false" data-more><span class="label">Status</span>%s<span class="line">%s</span>'
        '<span class="more">%s</span></button>'
        '<button class="blk small-block" type="button" aria-expanded="false" data-more><span class="label">Runs on</span><span class="line strong">%s</span>'
        '<span class="line">%s</span><span class="more">Tap again to close. Everything runs on your own PC and your own network: no cloud, no account.</span></button>'
        '</aside>' % (chips(chips_), escape(line), escape(STATUS_LEGEND), escape(runs), escape(runs_line)))


def auto(steps, with_downloads=False, key=""):
    lis = []
    for i, (t, em, d, gate) in enumerate(steps):
        lis.append(
            '<li><button class="st%s" type="button" data-t="%s" data-k="%s" data-d="%s"%s><span class="num">%d</span><span class="sb"><b>%s</b><em>%s</em></span></button>'
            '<p class="more-static">%s</p></li>' % (" gate" if gate else "", escape(t, True), escape(em, True), escape(d, True), ' aria-pressed="true"' if i == 0 else ' aria-pressed="false"',
                                                    i + 1, escape(t), escape(em), escape(d)))
    dl = ""
    if with_downloads:
        dl = ('<div class="downloads"><a class="action" href="%s/releases/latest/download/Agent-Hub-Setup.exe">Windows</a>'
              '<a class="action" href="%s/releases/latest/download/Agent-Hub-macOS.dmg">macOS</a>'
              '<a class="action" href="%s/releases/latest/download/Agent-Hub-Linux.tar.gz">Linux</a></div>' % (REPO, REPO, REPO))
    return ('<div class="auto" data-auto><ol class="auto-steps">%s</ol><div class="auto-detail">%s<p class="kicker"></p><h3></h3><p class="d"></p><span class="bar" aria-hidden="true"></span></div></div>'
            % ("".join(lis), dl))


def scene(sid, label, headline, chips_, line, runs, runs_line, body, wide=False):
    return (
        '<section class="scene" id="%s" aria-labelledby="%s-title"><div class="board%s" data-tilt><i class="slab s3" aria-hidden="true"></i><i class="slab s2" aria-hidden="true"></i><i class="slab s1" aria-hidden="true"></i>'
        '<article class="blk main-block"><header class="blk-h"><p class="label">%s</p><h2 id="%s-title" tabindex="-1">%s</h2><span class="hchips">%s</span></header>'
        '<div class="blk-b">%s</div></article>%s</div></section>'
        % (sid, sid, " wide" if wide else "", escape(label), sid, escape(headline), chips(chips_), body, "" if wide else small_blocks(sid, chips_, line, runs, runs_line)))


def build() -> str:
    machine = (Path(__file__).resolve().parent / "site_parts" / "machine.html").read_text(encoding="utf-8")
    parts = []
    for sid, door, label, headline, ch, line, runs, runs_line in SCENES:
        if sid == "talk":
            body = ('<div class="talk-desktop"><div class="fit"><div class="flow">%s</div></div></div>'
                    '<div class="talk-phone">%s</div>' % (machine, auto([(a, b, c, g) for a, b, c, g in TALK_PHONE])))
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, body, wide=True))
        elif sid == "architecture":
            body = ('<button class="arch-open" type="button" data-zoom aria-label="Enlarge the architecture diagram"><picture class="architecture-picture"><source media="(max-width:650px) and (orientation:portrait)" srcset="architecture-tall.svg"><img src="architecture.svg" '
                    'alt="Agent Hub architecture: private device access, the board and Talk, the router, autonomous LLM missions, agents and skills, PC control, media and the git graph" '
                    'width="1120" height="640"></picture><span class="arch-hint">Tap to enlarge</span></button>'
                    '<div class="zoom" hidden><button class="zoom-x" type="button" data-zoom-close>Close ✕</button><div class="zoom-scroll"><picture>'
                    '<source media="(max-width:650px) and (orientation:portrait)" srcset="architecture-tall.svg"><img src="architecture.svg" alt="" width="1120" height="640"></picture></div></div>')
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, body, wide=True))
        elif sid == "install":
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, auto(STEPS[sid], with_downloads=True)))
        else:
            parts.append(scene(sid, label, headline, ch, line, runs, runs_line, auto(STEPS[sid])))
    doors = "".join('<a class="door blk" href="#%s">%s<span aria-hidden="true">↗</span></a>' % (sid, escape(door)) for sid, door, *_ in SCENES)
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
        '<nav class="doors" aria-label="Explore Agent Hub">%s</nav></div></section>' % (REPO, doors))
    body = ('<body><header class="site-header"><a class="brand" href="#" data-home aria-label="Agent Hub — return to landing"><img src="assets/agent-hub-mark.png" alt="" width="44" height="44">AGENT HUB</a>'
            '<a class="projects" href="https://infernalzeus.github.io/">← PROJECTS</a></header><main class="stage">%s%s</main>'
            '<script src="assets/agent-hub-mark.min.js?v=20261105b" defer></script><script src="assets/depth-lift-site.js?v=20261105b" defer></script>'
            '<script src="assets/site.js?v=%s" defer></script></body></html>\n' % (landing, "".join(parts), V))
    return head + body


if __name__ == "__main__":
    (DOCS / "index.html").write_text(build(), encoding="utf-8")
    print("wrote docs/index.html")
