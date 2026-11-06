"""The learning layer drawn as an Obsidian canvas: the same file opens in Obsidian and is drawn live in the yard's FLOW tab.

One list of nodes and one list of arrows (the JSON Canvas format: nodes with x, y, width, height and text; edges from one node's side to another's). The FLOW tab
reads it from `/api/yard/canvas`, draws it, and animates what `events.py` reports: an arrow lights when information travels along it, a node pulses when it works, and
a node shows a green flash when its weights improved. Each node's text is what its info button explains.

Write the canvas file:   python -m hub.yard.flow <path to learning.canvas>
Colours follow the plan: red not built, orange built and never tested, blue tested by Claude, green tested by you, cyan working on it.
"""
from __future__ import annotations

import json
import sys

from aiohttp import web

routes = web.RouteTableDef()
COLOUR = {"todo": "#ff5c5c", "built": "#e0a53c", "tested": "#3ba7ff", "user": "#00e676", "now": "#41ebff"}
W, H = 300, 150                                   # the cards of the Obsidian canvas file (large, so their text fits)
COL = [0, 380, 760, 1140, 1520, 1900]
ROW = [0, 240, 480]
CW, CH, CSTEP, RSTEP = 200, 62, 236, 96           # the compact blocks the yard panel draws

# the settings that change what each block does (the rest are under "more settings" in the panel); a test checks every name exists
NODE_KNOBS = {
    "knobs": ["episodes", "seed"], "live": ["memory_prompts"], "mem": ["memory_epochs"], "enc": ["letters"], "actor": ["hidden_units", "lr_actor"], "soft": ["entropy_beta"],
    "env": ["vocab", "family_direct", "family_modal", "family_search", "family_menu", "family_long", "family_unnamed", "family_tabs", "family_confirm"],
    "rew": ["step_cost", "invalid_cost", "false_done_cost", "win"], "crit": ["lr_critic"], "upd": ["gamma", "warm_start", "clip_norm"],
    "repl": ["replay_every", "replay_batch", "replay_priority"], "hind": ["hindsight"], "demos": [], "fit": ["eval_per_cell"],
    "gate": ["min_frozen", "shadow_n", "shadow_agree"], "ver": ["ema_alpha", "soup_top"],
}

# id: (column, row, state, title, what it is, what it emits / what you can adjust)
NODES = {
    "live": (0, 0, "tested", "Live shadow memory", "While shadow mode is on, every live PC task the Hub does is kept: the controls the agent saw at each step, what it pressed, how the task ended and how sure the Hub is that it worked. Attested routines are kept apart as checks and never used here.", "Event: live>mem when a session reads approved live tasks. Adjust: Live memory (keep what the live agent saw, passes over approved live tasks)."),
    "mem": (1, 0, "tested", "Memory block", "The rows a session can draw from: pretend-app episodes it just played, and the approved live tasks. Rows older than the fresh start are never used. A held-out third of the labelled routes is kept apart for judging.", "Events: mem>enc as a task is read into features; mem>upd when approved live steps are imitated. Adjust: Replay and hindsight, Live memory."),
    "enc": (2, 0, "tested", "Features (encoder)", "Turns what the agent sees into numbers: for each control it could press, 51 features (its kind, its role, how many goal words its name shares, whether it was pressed before, 32 hashed letter-triples of its name) multiplied by 7 flags for where the task is, so a menu item after a button that opened something looks different from one at the start. The encoder is fixed: only the actor and critic learn.", "Event: enc>actor each step. Adjust: Learn from the letters of names (Yard session)."),
    "actor": (3, 0, "tested", "Actor", "Scores every control the agent could press. A linear scorer, or one hidden layer of tanh units. This is the part that is saved as the learned file. Its weights are what change when something has been learned.", "Events: weights, with how far the numbers moved. Adjust: Hidden layer size, Actor step size (Learner)."),
    "soft": (4, 0, "tested", "Choice (softmax)", "Turns the scores into probabilities and picks one control: sampled while practising so it keeps exploring, the best one when it is measured or watching the live agent. A bonus for staying varied keeps it from settling too early.", "Event: soft>env at every press. Adjust: Exploration bonus (Learner)."),
    "env": (5, 0, "tested", "Pretend app", "A pretend music player with a hidden state. It answers like a real app: its control tree, its clicks, what Windows would say is playing. Eight layouts, each with its own trap; the training words and the unseen words differ. Whether the target is really playing is the one reward nobody can fake.", "Event: episode, with the layout and the number of presses. Adjust: Pretend layouts, Words used in training, Unseen apps per cell."),
    "rew": (5, 1, "tested", "Reward", "-0.02 for every press, -0.1 for an unusable answer, -0.5 for saying done too early, +1 when the target is really playing (the sizes are adjustable). A late reward is spread back to the choices that led to it by the discount.", "Event: reward, with the episode's total return. Adjust: Rewards, Discount."),
    "crit": (4, 1, "tested", "Critic", "Learns how much return to expect from where the task is (11 numbers: the step flags, how far along it is, how many controls are shown, how well the best control matches the goal, how many presses did nothing). The advantage is what happened minus what it expected; a choice is reinforced only by the surprise.", "Event: advantage. Adjust: Critic step size (Learner)."),
    "upd": (3, 1, "tested", "Update", "Moves the actor's numbers along advantage times the slope of the log-probability of the chosen control, plus the exploration bonus, and the critic's numbers towards the return. This is the step in which weights change; the size of the change is shown on the actor.", "Events: update, with how far the numbers moved and their total size. Adjust: step sizes, discount, exploration, largest change per update (Weights)."),
    "repl": (2, 1, "tested", "Replay buffer", "Remembers recent episodes with how unsure the learner was; every N episodes some are learned from again, the unsure ones more often. Off unless you set a number.", "Event: replay. Adjust: Replay every N episodes, Episodes per replay, Which episodes are replayed."),
    "hind": (5, 2, "tested", "Hindsight", "A failed task that ended up playing some other playlist is also learned from as a success for that other playlist (the controls stay the same, only the goal words change). Off by default.", "Event: relabel. Adjust: Hindsight relabelling."),
    "knobs": (0, 1, "tested", "Session", "Every number of the layer you can change by hand, in the KNOBS tab. Changes are saved and read the moment they are used. Safety rules (never-press list, taint gate, confirm before acting) cannot be changed here.", "Event: session, with the settings a session starts with."),
    "demos": (1, 1, "tested", "Attested checks", "The routines you checked and trusted. They are never training samples. After a session the learner is asked, step by step on pretend screens built from your routine's control names, which control it would press; the share that match your routine is shown.", "Event: agreement, with the share that match. Adjust: nothing; it only measures."),
    "fit": (3, 2, "tested", "Fitness", "How well it does on layouts and words it has never seen, against random and the rule of thumb the Hub already uses. A block of training that scores clearly higher than the one before is announced as an improvement of the weights.", "Events: improved, evaluated. Adjust: Unseen apps per cell."),
    "gate": (2, 2, "tested", "Gate", "A new version replaces the one in use only if it is at least as good on unseen words (within a small tolerance). Nothing here ever acts on your PC: it only decides which saved learner the shadow watcher uses.", "Event: decided. Adjust: Gate numbers act on live promotion, not on this check."),
    "ver": (1, 2, "tested", "Saved versions", "Each finished session is saved as a version (a few hundred kilobytes of plain numbers) with its scores and the method that made it. The newest twelve are kept so one can be restored. Weight tools can average, smooth or compare versions.", "Event: saved, with the version number and whether it is now the one in use."),
}

EDGES = [
    ("live", "mem", "right", "left", "approved live tasks"), ("mem", "enc", "right", "left", "what the agent sees"), ("enc", "actor", "right", "left", "numbers per control"),
    ("actor", "soft", "right", "left", "scores"), ("soft", "env", "right", "left", "a press"), ("env", "rew", "bottom", "top", "what happened"),
    ("rew", "crit", "left", "right", "return"), ("crit", "upd", "left", "right", "advantage"), ("upd", "actor", "top", "bottom", "new weights"),
    ("repl", "upd", "right", "left", "remembered episodes"), ("hind", "rew", "top", "bottom", "relabelled misses"), ("upd", "fit", "bottom", "top", "the learner so far"),
    ("fit", "gate", "left", "right", "scores"), ("gate", "ver", "left", "right", "keep or not"), ("demos", "gate", "bottom", "top", "agreement with your routines"),
    ("mem", "upd", "bottom", "top", "imitate approved steps"),
]


def canvas(compact: bool = False) -> dict:
    """The Obsidian canvas (large cards with their full text), or with compact=True the small blocks and unlabelled arrows the yard panel draws."""
    nodes = []
    for nid, (c, r, st, title, what, emits) in NODES.items():
        text = "## " + title + "\n\n" + what + "\n\n*" + emits + "*"
        if compact:
            nodes.append({"id": nid, "type": "text", "x": c * CSTEP, "y": r * RSTEP, "width": CW, "height": CH, "color": COLOUR[st], "text": text})
        else:
            nodes.append({"id": nid, "type": "text", "x": COL[c], "y": ROW[r], "width": W, "height": H, "color": COLOUR[st], "text": text})
    edges = []
    for a_, b_, fs, ts, lab in EDGES:
        e = {"id": a_ + ">" + b_, "fromNode": a_, "fromSide": fs, "toNode": b_, "toSide": ts, "toEnd": "arrow"}
        if not compact:
            e["label"] = lab
        edges.append(e)
    return {"nodes": nodes, "edges": edges}


def write(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(canvas(), f, indent=1, ensure_ascii=False)


@routes.get("/api/yard/canvas")
async def api_canvas(request: web.Request) -> web.Response:
    compact = request.query.get("compact") == "1"
    c = canvas(compact)
    for n in c["nodes"]:
        title, _, rest = n["text"].partition("\n\n")
        n["title"], n["info"] = title.lstrip("# ").strip(), rest.replace("*", "").strip()
        if compact:
            n["info"] = n["info"].split(". ")[0].rstrip(".") + "."                  # one sentence in the panel; the whole text is in the Obsidian canvas
            n.pop("text", None)
        n["state"] = next(k for k, v in COLOUR.items() if v == n["color"])
        n["knobs"] = NODE_KNOBS.get(n["id"], [])
    return web.json_response(c)


if __name__ == "__main__":
    write(sys.argv[1] if len(sys.argv) > 1 else "learning.canvas")
