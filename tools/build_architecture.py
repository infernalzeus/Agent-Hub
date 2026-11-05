"""Draw docs/architecture.svg (wide) and docs/architecture-tall.svg (phone) from one description of the Hub.

    python tools/build_architecture.py

One list of lanes below is the single source for both pictures. Wording rules for the public page: never "AI" (say autonomous LLM,
local model, agent), no version numbers or counts, no cloud or account claims, nothing that is not built.
What Smith, Neo and the Doctor do is taken from the Hub's own agent map and persona files.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
BG, GREEN, MUTE = "#05070c", "#00e676", "#a8cbb9"
ORB, OUT = "Orbitron,Segoe UI,sans-serif", "Outfit,Segoe UI,sans-serif"

# (lane title, one-line caption, [(box title, box note), ...], fed by: "router" or "smith")
LANES = [
    ("AUTONOMOUS LLM", "Runs on OpenCode, Claude Code or a local model. Your repo is untouched until you press APPLY.",
     [("MISSIONS", "ask by text or voice"), ("DISPATCH", "split into briefs"), ("WORKTREE", "a private copy"), ("REVIEW", "you read the diff"), ("APPLY", "or discard it")], "router"),
    ("NEO · MAKES AGENTS", "Smith calls Neo. You describe a job; Neo designs one agent file; you read it and save it; the orchestrator can pick it.",
     [("DESCRIBE", "a job, in plain words"), ("NEO", "designs one agent file"), ("REVIEW", "you read it, then save"), ("TEAM", "orchestrator picks it"), ("SKILLS", "abilities you add")], "smith"),
    ("THE DOCTOR · REPAIRS THE HUB", "Smith calls the Doctor. A mission on the Hub's own repo, in a private copy. Restarting stays yours.",
     [("ASK", "say it, or ASK THE DOCTOR"), ("FACTS", "the Hub's own status"), ("MISSION", "a fix in a private copy"), ("CHECKS", "compile and tests"), ("APPLY", "you press it")], "smith"),
    ("PC CONTROL", "Windows only. Smith hands it to the desktop agent. Shell and registry tools are switched off.",
     [("SAY IT", "plain words"), ("LOOK", "finds controls by name"), ("ASK FIRST", "shows the press"), ("ACT", "click, type, open"), ("CHECK", "the window changed")], "router"),
    ("MEDIA VAULT", "Runs on your PC; copy results to your phone.",
     [("DOWNLOAD", "yt-dlp"), ("CONVERT", "ffmpeg"), ("SAVE", "to your folder"), ("BROWSE", "your drives"), ("RECEIVE", "from your phone")], "router"),
    ("GIT GRAPH", "One dot per project, read straight from git, including the copies agents are working in.",
     [("PROJECT MAP", "status at a glance"), ("DIFF", "line by line")], "router"),
]
FRONT = [("BOARD", "3D glass dashboard"), ("AGENT SMITH", "hears you: voice or typed"), ("ROUTER", "cheapest answer first")]
DEVICES = ["PHONE", "TABLET", "LAPTOP"]

LABEL = ("Agent Hub drawn as a circuit board. Phone, tablet and laptop reach the Hub on your PC over a private Tailscale network. "
         "The Hub has a 3D board and Agent Smith, the voice you talk to. Smith sends each ask through the router, which picks the cheapest thing that can answer, "
         "and calls Neo, who designs new agents from a plain description, and the Doctor, who repairs the Hub as a mission you approve. "
         "From the router: autonomous LLM missions (missions, dispatch, a private worktree, review, apply), PC control through Windows MCP, the media vault, and the git graph.")


K = 1.0


def t(x, y, s, size, fill, font, weight="400", ls="0", anchor="start", op="1"):
    return ('<text x="%.1f" y="%.1f" fill="%s" fill-opacity="%s" font-family="%s" font-size="%s" font-weight="%s" letter-spacing="%s" text-anchor="%s">%s</text>'
            % (x, y, fill, op, font, round(size * K, 2), weight, ls, anchor, escape(s)))


def box(x, y, w, h, title, note, strong=False):
    sw, so = ("1.6", ".8") if strong else ("1.2", ".45")
    out = '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1" fill="#0b1220" fill-opacity=".92" stroke="%s" stroke-opacity="%s" stroke-width="%s"/>' % (x, y, w, h, GREEN, so, sw)
    out += t(x + w / 2, y + (h / 2 - 2 if note else h / 2 + 3), title, 8.2, GREEN, ORB, "700", "0.9", "middle")
    if note:
        out += t(x + w / 2, y + h / 2 + 11, note, 7.4, MUTE, OUT, anchor="middle", op=".85")
    return out


def frame(x, y, w, h, label):
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1" fill="%s" fill-opacity=".022" stroke="%s" stroke-opacity=".22" stroke-dasharray="7 5"/>' % (x, y, w, h, GREEN, GREEN)
            + t(x + 14, y + 16, label, 8.5, GREEN, ORB, "700", "1.6", op=".75"))


def arrow(x1, y1, x2, y2, dashed=False):
    return ('<path class="fl" d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-opacity=".6" stroke-width="1.2" fill="none"%s marker-end="url(#ah)"/>'
            % (x1, y1, x2, y2, GREEN, ' stroke-dasharray="4 3"' if dashed else ""))


def line(x1, y1, x2, y2, dashed=False):
    return ('<path class="fl" d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-opacity=".55" stroke-width="1.2" fill="none"%s/>' % (x1, y1, x2, y2, GREEN, ' stroke-dasharray="4 3"' if dashed else ""))


def svg(w, h, body):
    return ('<svg width="%d" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="%s"><rect width="%d" height="%d" fill="%s"/>'
            '<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,1 L7,4 L0,7 z" fill="%s" fill-opacity=".6"/></marker></defs>%s</svg>'
            % (w, w, h, escape(LABEL), w, h, BG, GREEN, body))


def wide() -> str:
    global K
    K = 1.22
    W, H = 1200, 760
    b = []
    b.append(frame(18, 200, 250, 190, "ACCESS"))
    for i, d in enumerate(DEVICES):
        b.append(box(34, 226 + i * 44, 86, 34, d, ""))
        b.append(arrow(120, 243 + i * 44, 160, 295))
    b.append(box(160, 265, 96, 60, "TAILSCALE", "private network", True))
    b.append(t(34, 382, "Nothing is exposed to the internet.", 8.5, MUTE, OUT, op=".7"))
    b.append(arrow(256, 295, 318, 295))
    b.append(frame(318, 40, 866, 700, "THE HUB ON YOUR PC"))
    fx = 338
    fy = [190, 300, 410]                       # BOARD, SMITH, ROUTER
    for (n, s), y in zip(FRONT, fy):
        b.append(box(fx, y, 150, 56, n, s, n != "BOARD"))
    b.append(arrow(fx + 75, fy[0] + 56, fx + 75, fy[1]))
    b.append(arrow(fx + 75, fy[1] + 56, fx + 75, fy[2]))
    ys = [64, 172, 280, 388, 496, 604]
    busR, busS = fx + 150 + 18, fx + 150 + 30
    x0 = busS + 26
    # Smith feeds Neo and the Doctor (dashed); the router feeds everything else
    smith_y, router_y = fy[1] + 28, fy[2] + 28
    router_lanes = [y + 40 for (title, cap, boxes, src), y in zip(LANES, ys) if src == "router"]
    smith_lanes = [y + 40 for (title, cap, boxes, src), y in zip(LANES, ys) if src == "smith"]
    b.append(line(fx + 150, router_y, busR, router_y))
    b.append(line(busR, min(router_lanes), busR, max(router_lanes)))
    b.append(line(fx + 150, smith_y, busS, smith_y, True))
    b.append(line(busS, min(smith_lanes), busS, max(smith_lanes), True))
    for (title, cap, boxes, src), y in zip(LANES, ys):
        bus = busR if src == "router" else busS
        b.append(arrow(bus, y + 40, x0 - 2, y + 40, src == "smith"))
        b.append(t(x0, y + 12, title, 8.5, GREEN, ORB, "700", "1.6", op=".85"))
        b.append(t(x0, y + 24, cap, 7.8, MUTE, OUT, op=".75"))
        for i, (n, s) in enumerate(boxes):
            bx = x0 + i * 122
            b.append(box(bx, y + 30, 110, 50, n, s))
            if i:
                b.append(arrow(bx - 12, y + 55, bx, y + 55))
    b.append(t(x0 + 3 * 122 + 55, 64 + 100, "re-plan if the review asks for it", 7.4, MUTE, OUT, anchor="middle", op=".7"))
    return svg(W, H, "".join(b))


def tall() -> str:
    global K
    K = 1.0
    W = 360
    b = []
    y = 16
    b.append(frame(12, y, 336, 62, "ACCESS"))
    for i, d in enumerate(DEVICES):
        b.append(box(26 + i * 104, y + 24, 92, 30, d, ""))
    y += 62
    b.append(arrow(180, y, 180, y + 22))
    y += 22
    b.append(box(110, y, 140, 38, "TAILSCALE", "private network", True))
    y += 38
    b.append(arrow(180, y, 180, y + 22))
    y += 22
    hub_top = y
    inner = []
    yy = y + 28
    for i, (n, s) in enumerate(FRONT):
        inner.append(box(30, yy, 300, 38, n, s, n != "BOARD"))
        yy += 38
        if i < 2:
            inner.append(arrow(180, yy, 180, yy + 14))
            yy += 14
    yy += 8
    for title, cap, boxes, src in LANES:
        inner.append(arrow(180, yy - 6, 180, yy + 8, src == "smith"))
        yy += 12
        inner.append(t(30, yy + 8, title, 8.5, GREEN, ORB, "700", "1.6", op=".85"))
        words, ln, lines = cap.split(), "", []
        for wd in words:
            if len(ln) + len(wd) > 58:
                lines.append(ln.strip())
                ln = ""
            ln += wd + " "
        lines.append(ln.strip())
        for k, s in enumerate(lines):
            inner.append(t(30, yy + 21 + k * 10, s, 7.8, MUTE, OUT, op=".75"))
        yy += 21 + len(lines) * 10 + 4
        per = 3
        for i, (n, s) in enumerate(boxes):
            r, c = divmod(i, per)
            bx, by = 30 + c * 104, yy + r * 48
            inner.append(box(bx, by, 94, 40, n, s))
            if c:
                inner.append(arrow(bx - 10, by + 20, bx, by + 20))
        yy += ((len(boxes) - 1) // per + 1) * 48 + 6
    b.append(frame(12, hub_top, 336, yy - hub_top + 6, "THE HUB ON YOUR PC"))
    b.append("".join(inner))
    return svg(W, int(yy + 24), "".join(b))


if __name__ == "__main__":
    (DOCS / "architecture.svg").write_text(wide(), encoding="utf-8")
    (DOCS / "architecture-tall.svg").write_text(tall(), encoding="utf-8")
    print("wrote architecture.svg and architecture-tall.svg")
