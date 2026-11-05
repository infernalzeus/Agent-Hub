"""Draw docs/architecture.svg (wide) and docs/architecture-tall.svg (phone) from one description of the Hub.

    python tools/build_architecture.py

One list of lanes below is the single source for both pictures. Wording rules for the public page: never "AI" (say autonomous LLM,
local model, agent), no version numbers or counts, no cloud or account claims, nothing that is not built.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
BG, GREEN, INK, MUTE = "#05070c", "#00e676", "#e6fbf1", "#a8cbb9"
ORB, OUT = "Orbitron,Segoe UI,sans-serif", "Outfit,Segoe UI,sans-serif"

# (lane title, one-line caption, [(box title, box note), ...])
LANES = [
    ("AUTONOMOUS LLM", "Runs on OpenCode, Claude Code or a local model. Your repo is untouched until you press APPLY.",
     [("MISSIONS", "ask by text or voice"), ("DISPATCH", "split into briefs"), ("WORKTREE", "a private copy"), ("REVIEW", "read the diff"), ("APPLY", "or discard it")]),
    ("AGENTS + SKILLS", "A team of agents that hand work on, skills you can add, and a repair helper whose fixes you approve.",
     [("AGENT TEAM", "orchestrator and more"), ("SKILLS", "add or write your own"), ("DOCTOR", "you press APPLY")]),
    ("PC CONTROL", "Windows only. Shell and registry tools are switched off.",
     [("SAY IT", "plain words"), ("LOOK", "finds controls by name"), ("ASK FIRST", "shows the press"), ("ACT", "click, type, open"), ("CHECK", "the window changed")]),
    ("MEDIA VAULT", "Runs on your PC; copy results to your phone.",
     [("DOWNLOAD", "yt-dlp"), ("CONVERT", "ffmpeg"), ("SAVE", "to your folder"), ("BROWSE", "your drives"), ("RECEIVE", "from your phone")]),
    ("GIT GRAPH", "One dot per project, read straight from git, including the copies agents are working in.",
     [("PROJECT MAP", "status at a glance"), ("DIFF", "line by line")]),
]
FRONT = [("BOARD", "3D glass dashboard"), ("TALK", "spoken or typed"), ("ROUTER", "cheapest answer first")]
DEVICES = ["PHONE", "TABLET", "LAPTOP"]


def t(x, y, s, size, fill, font, weight="400", ls="0", anchor="start", op="1"):
    return ('<text x="%.1f" y="%.1f" fill="%s" fill-opacity="%s" font-family="%s" font-size="%s" font-weight="%s" letter-spacing="%s" text-anchor="%s">%s</text>'
            % (x, y, fill, op, font, size, weight, ls, anchor, escape(s)))


def box(x, y, w, h, title, note, strong=False):
    sw, so = ("1.6", ".8") if strong else ("1.2", ".45")
    out = '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="#0b1220" fill-opacity=".92" stroke="%s" stroke-opacity="%s" stroke-width="%s"/>' % (x, y, w, h, GREEN, so, sw)
    out += t(x + w / 2, y + (h / 2 - 2 if note else h / 2 + 3), title, 8.2, GREEN, ORB, "700", "0.9", "middle")
    if note:
        out += t(x + w / 2, y + h / 2 + 11, note, 7.6, MUTE, OUT, anchor="middle", op=".85")
    return out


def frame(x, y, w, h, label):
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s" fill-opacity=".022" stroke="%s" stroke-opacity=".22" stroke-dasharray="7 5"/>' % (x, y, w, h, GREEN, GREEN)
            + t(x + 14, y + 16, label, 8.5, GREEN, ORB, "700", "1.6", op=".75"))


def arrow(x1, y1, x2, y2, dashed=False):
    return ('<path d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-opacity=".55" stroke-width="1.2" fill="none"%s marker-end="url(#ah)"/>'
            % (x1, y1, x2, y2, GREEN, ' stroke-dasharray="4 3"' if dashed else ""))


def svg(w, h, body, label):
    return ('<svg width="%d" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="%s">'
            '<rect width="%d" height="%d" fill="%s"/><defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0,1 L7,4 L0,7 z" fill="%s" fill-opacity=".6"/></marker></defs>%s</svg>' % (w, w, h, escape(label), w, h, BG, GREEN, body))


LABEL = ("Agent Hub drawn as a circuit board. Phone, tablet and laptop reach the Hub on your PC over a private Tailscale network. "
         "The Hub has a 3D board, TALK and a router that sends each ask to the cheapest thing that can answer. From the router: autonomous LLM missions "
         "(missions, dispatch, a private worktree, review, apply), a team of agents with skills and a repair helper, PC control through Windows MCP, "
         "the media vault, and the git graph, which reads the worktrees.")


def wide() -> str:
    W, H = 1120, 640
    b = []
    # access
    b.append(frame(18, 150, 250, 190, "ACCESS"))
    for i, d in enumerate(DEVICES):
        b.append(box(34, 176 + i * 44, 86, 34, d, ""))
        b.append(arrow(120, 193 + i * 44, 160, 245))
    b.append(box(160, 215, 96, 60, "TAILSCALE", "private network", True))
    b.append(t(34, 332, "Nothing is exposed to the internet.", 8.5, MUTE, OUT, op=".7"))
    b.append(arrow(256, 245, 318, 245))
    # hub frame
    b.append(frame(318, 40, 786, 580, "THE HUB ON YOUR PC"))
    fx = 338
    for i, (n, s) in enumerate(FRONT):
        b.append(box(fx, 170 + i * 80, 150, 54, n, s, i == 2))
    b.append(arrow(fx + 75, 224, fx + 75, 250))
    b.append(arrow(fx + 75, 304, fx + 75, 330))
    # lanes
    ys = [64, 190, 290, 392, 494]
    bus = fx + 150 + 18
    mid = [y + 40 for y in ys]
    b.append('<path d="M%.1f 357 L%.1f 357" stroke="%s" stroke-opacity=".55" stroke-width="1.2"/>' % (fx + 150, bus, GREEN))
    b.append('<path d="M%.1f %.1f L%.1f %.1f" stroke="%s" stroke-opacity=".55" stroke-width="1.2"/>' % (bus, mid[0], bus, mid[-1], GREEN))
    x0 = bus + 28
    for (title, cap, boxes), y in zip(LANES, ys):
        b.append(arrow(bus, y + 40, x0 - 2, y + 40))
        b.append(t(x0, y + 12, title, 8.5, GREEN, ORB, "700", "1.6", op=".85"))
        b.append(t(x0, y + 24, cap, 8, MUTE, OUT, op=".75"))
        for i, (n, s) in enumerate(boxes):
            bx = x0 + i * 108
            b.append(box(bx, y + 32, 94, 44, n, s))
            if i:
                b.append(arrow(bx - 14, y + 54, bx, y + 54))
    # apply loops back to dispatch
    b.append('<path d="M%.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" stroke="%s" stroke-opacity=".4" stroke-width="1.1" fill="none" stroke-dasharray="4 3" marker-end="url(#ah)"/>'
             % (x0 + 4 * 108 + 47, 64 + 76, x0 + 4 * 108 + 47, 64 + 100, x0 + 108 + 47, 64 + 100, x0 + 108 + 47, 64 + 78, GREEN))
    b.append(t(x0 + 2 * 108 + 47, 64 + 108, "re-plan if the review asks for it", 7.6, MUTE, OUT, anchor="middle", op=".7"))
    return svg(W, H, "".join(b), LABEL)


def tall() -> str:
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
        inner.append(box(30, yy, 300, 38, n, s, i == 2))
        yy += 38
        if i < 2:
            inner.append(arrow(180, yy, 180, yy + 14))
            yy += 14
    yy += 8
    for title, cap, boxes in LANES:
        inner.append(arrow(180, yy - 6, 180, yy + 8))
        yy += 12
        inner.append(t(30, yy + 8, title, 8.5, GREEN, ORB, "700", "1.6", op=".85"))
        words, line, lines = cap.split(), "", []
        for wd in words:
            if len(line) + len(wd) > 58:
                lines.append(line.strip())
                line = ""
            line += wd + " "
        lines.append(line.strip())
        for k, ln in enumerate(lines):
            inner.append(t(30, yy + 21 + k * 10, ln, 7.8, MUTE, OUT, op=".75"))
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
    b.append(t(180, yy + 22, "Missions work on a copy; the Git Graph reads that copy.", 7.8, MUTE, OUT, anchor="middle", op=".7"))
    H = int(yy + 36)
    return svg(W, H, "".join(b), LABEL)


if __name__ == "__main__":
    (DOCS / "architecture.svg").write_text(wide(), encoding="utf-8")
    (DOCS / "architecture-tall.svg").write_text(tall(), encoding="utf-8")
    print("wrote architecture.svg and architecture-tall.svg")
