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
ROW = [0, 240, 480, 720]
CW, CH, CSTEP, RSTEP = 200, 62, 236, 96           # the compact blocks the yard panel draws

# the settings that change what each block does (the rest are under "more settings" in the panel); a test checks every name exists
NODE_KNOBS = {
    "knobs": ["episodes", "seed"],
    "live": ["memory_prompts", "w_windows", "w_routine", "w_screen", "w_agent", "w_few", "f_invalid", "f_nothing", "f_false_done", "conf_cap", "evidence_keep", "evidence_width", "jpeg_quality"],
    "mem": ["memory_epochs"], "enc": ["letters"], "actor": ["hidden_units", "lr_actor"], "soft": ["entropy_beta", "support_threshold"],
    "env": ["vocab", "family_direct", "family_modal", "family_search", "family_menu", "family_long", "family_unnamed", "family_tabs", "family_confirm"],
    "rew": ["step_cost", "invalid_cost", "false_done_cost", "forbidden_cost", "win"], "crit": ["lr_critic"], "upd": ["gamma", "warm_start", "clip_norm"],
    "repl": ["replay_every", "replay_batch", "replay_priority"], "hind": ["hindsight"], "demos": ["candidate_agree"], "fit": ["eval_per_cell"],
    "gate": ["min_frozen", "shadow_n", "shadow_agree"], "ver": ["ema_alpha", "soup_top"], "safety": ["hide_forbidden"],
    "learners": ["min_n", "thompson_draws", "linucb_alpha", "linucb_lambda", "ope_cap", "ope_boot"], "router": ["knn_k", "held_out_tenths", "clf_epochs", "clf_l2", "clf_lr"],
    "search": ["cma_sigma0", "cma_repeat", "bo_init", "bo_length", "bo_noise"], "presets": ["rw_valid_json", "rw_not_truncated", "rw_no_repeat", "rw_checks", "rw_tokens"],
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

NODES.update({
    "safety": (1, 3, "tested", "Safety replay", "After a session the saved learner is shown pretend screens that also list forbidden controls (Delete playlist, Sign out ...) and it is counted how often its top pick is one. The gate needs zero. The real never-press list, the taint gate and the confirm rule stay in force whatever this says, and no learned number can loosen them.", "Event: replayed, with how many screens picked a forbidden control. Adjust: Hide forbidden controls from the live agent."),
    "learners": (2, 3, "tested", "Choice methods", "Tally, Thompson and LinUCB sit behind one interface for the model choice and the way a PC task is done. They are scored against each other on the choices already logged, without repeating any test (a weight-capped estimate of what each would have done). Choosing one only picks which is watched; no live choice changes.", "Shown in SCORES, not during a session. Adjust: tries before trust, draws, optimism, the weight cap."),
    "router": (3, 3, "tested", "Router yardstick", "Nearest neighbours and a small classifier trained by gradient descent on every graded request, each judged by leaving a request out and predicting it from the rest, against the current rules and tev. A fine-tune of tev has to beat these to be worth doing.", "Shown in SCORES, not during a session. Adjust: neighbours, share held out, classifier passes, penalty and step size."),
    "search": (4, 3, "tested", "Number search", "CMA-ES and Bayesian optimisation look for the best set of a few numbers (hand and speech thresholds, sampling settings) when each try is slow and noisy. Built and tested on made-up numbers; applied to no real number until there are labelled traces to score against.", "Not run in a session. Adjust: first step, repeats, random starts, smoothness, noise."),
    "presets": (5, 3, "tested", "Sampling presets", "Five named sets of the eight language-model settings, and a reward that needs no label (valid answer, not cut off, no repeating, checks passed, few tokens) to learn which suits which agent role. Built and tested; not yet called by a live request.", "Not run in a session. Adjust: the five reward weights."),
})
OUTSIDE = {"learners", "router", "search", "presets", "safety", "live", "demos"}      # blocks that do not run inside a training session (they are fed by, or score, the session)

EDGES = [
    ("live", "mem", "right", "left", "approved live tasks"), ("mem", "enc", "right", "left", "what the agent sees"), ("enc", "actor", "right", "left", "numbers per control"),
    ("actor", "soft", "right", "left", "scores"), ("soft", "env", "right", "left", "a press"), ("env", "rew", "bottom", "top", "what happened"),
    ("rew", "crit", "left", "right", "return"), ("crit", "upd", "left", "right", "advantage"), ("upd", "actor", "top", "bottom", "new weights"),
    ("repl", "upd", "right", "left", "remembered episodes"), ("hind", "rew", "top", "bottom", "relabelled misses"), ("upd", "fit", "bottom", "top", "the learner so far"),
    ("fit", "gate", "left", "right", "scores"), ("gate", "ver", "left", "right", "keep or not"), ("demos", "gate", "bottom", "top", "agreement with your routines"),
    ("mem", "upd", "bottom", "top", "imitate approved steps"),
    ("ver", "safety", "bottom", "top", "the saved learner"), ("safety", "gate", "right", "bottom", "forbidden presses"),
    ("learners", "fit", "top", "bottom", "scored on the log"), ("router", "fit", "top", "bottom", "scored on graded requests"),
    ("search", "fit", "top", "right", "scored candidates"), ("presets", "fit", "left", "right", "label-free reward"),
]


def arch(nid: str) -> dict:
    """What is inside a block: the layers with their sizes, the plain numbers, and the arithmetic, taken from the code and the current settings (never typed in by hand)."""
    from . import knobs as K
    try:
        from . import learner as L
        dim, base, nflag, zdim, hashn = L.DIM, L.BASE, L.NFLAG, L.ZDIM, L.HASH
    except ImportError:                                           # numpy missing: the shapes the code has had since it was written
        dim, base, nflag, zdim, hashn = 357, 51, 7, 11, 32
    h = K.get("hidden_units")
    g = K.get
    layers, rows, formula = [], [], []
    if nid == "enc":
        layers = [("controls shown", "up to ~70"), ("features per control", str(base)), ("x step flags", str(nflag)), ("numbers per action", str(dim))]
        rows = [("features", "5 action kinds, 6 control roles, goal words shared with the name, its group and its row, the word Play, pressed before, pressed and nothing changed, on the never-press list, " + str(hashn) + " hashed letter-triples of the name" + ("" if g("letters") else " (letters switched off)")),
                ("step flags", "nothing yet, something pressed, a list entry pressed, typed, last press changed the screen, last press changed nothing, something is playing")]
    elif nid == "actor":
        layers = [("input", str(dim)), ("plain learner: score", "1 (linear)"), ("hidden learner: tanh units", str(h)), ("hidden learner: score", "1")]
        rows = [("learned numbers, plain", str(dim)), ("learned numbers, hidden", f"{dim * h + h + h}"), ("step size", f"{g('lr_actor')} (x3 with a hidden layer)")]
        formula = ["h = tanh(W1 x + b1);  s = w2 . h   (plain: s = w . x)"]
    elif nid == "soft":
        formula = ["pi(a) = exp(s_a) / sum_j exp(s_j)", f"exploration bonus beta = {g('entropy_beta')} on the entropy of pi"]
        rows = [("practising", "samples from pi so it keeps trying"), ("measuring and shadow", "takes the highest score"), ("support check", f"a learned head may answer only where a screen is at least {g('support_threshold')} like something it trained on; elsewhere the model decides")]
    elif nid == "env":
        rows = [("layouts on", ", ".join(K.families())), ("words", g("vocab") + " in training; unseen words are used to measure"), ("truth", "the target playlist is really playing: nobody can fake it")]
    elif nid == "rew":
        formula = [f"r = -{g('step_cost')} per press", f"  - {g('invalid_cost')} if the answer is unusable", f"  - {g('forbidden_cost')} if it presses a never-press control", f"  - {g('false_done_cost')} if it says done too early", f"  + {g('win')} when the target is really playing"]
    elif nid == "crit":
        layers = [("state summary z", str(zdim)), ("value V", "1")]
        rows = [("z holds", "the step flags, how far along it is, how many controls are shown, how well the best control matches the goal, presses that did nothing"), ("step size", str(g("lr_critic")))]
        formula = ["V(z) = v . z"]
    elif nid == "upd":
        formula = [f"G_t = r_t + {g('gamma')} G_(t+1)", "A_t = G_t - V(z_t)", "actor: move along A_t x slope of ln pi(a_t) + beta x entropy", "critic: v += step x A_t x z"]
        rows = [("warm start", "continues from the saved learner" if g("warm_start") else "starts from nothing"), ("largest change per update", "no limit" if not g("clip_norm") else str(g("clip_norm")))]
    elif nid == "repl":
        rows = [("size", "the last 200 episodes"), ("every", "off" if not g("replay_every") else f"{g('replay_every')} episodes, {g('replay_batch')} replayed"), ("which", "the ones it was least sure about" if g("replay_priority") == "uncertainty" else "any")]
    elif nid == "hind":
        rows = [("state", "on" if g("hindsight") else "off"), ("how", "a failed task that ended up playing another playlist is relearned with that playlist as the goal; the controls pressed stay the same, only the goal words in the features change")]
    elif nid == "mem":
        rows = [("holds", "episodes just played, and approved live tasks"), ("approved live task", "you graded it RIGHT, or Windows confirmed it with a confidence of 0.9 or more; never one done by an attested routine"), ("passes at the start", str(g("memory_epochs")))]
    elif nid == "live":
        pos = {"Windows says it is playing": g("w_windows"), "a saved routine ran to the end": g("w_routine"), "the last press changed the window": g("w_screen"), "the agent said it was done": g("w_agent"), "four presses or fewer": g("w_few")}
        formula = ["confidence p = 1 - product over markers seen of (1 - w)", "then p = p x factors for warning signs", f"p is capped at {g('conf_cap')} unless Windows confirmed the result"]
        rows = [(k, f"w = {v}") for k, v in pos.items()] + [("warning signs", f"unusable answer x{g('f_invalid')}, nothing changed x{g('f_nothing')}, said done early x{g('f_false_done')}")]
    elif nid == "demos":
        rows = [("attested", "routines you had trusted at the fresh start: used to measure the learner, never to train it"), ("candidates", f"a candidate looks ready when it presses no forbidden control, replayed clean twice, and the learner agrees on at least {g('candidate_agree')} of its steps")]
    elif nid == "fit":
        formula = ["win rate on layouts and words never seen, against random and the rule of thumb", "95% interval (Wilson): centre +- z sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n)"]
    elif nid == "gate":
        rows = [("2", f"{g('min_frozen')} or more held-out rows"), ("3", "lower 95% bound above the baseline"), ("4", "zero forbidden presses in the safety replay"), ("5", f"{g('shadow_n')} watched live choices, agreeing on {g('shadow_agree')} or more"), ("6", "your yes")]
    elif nid == "ver":
        rows = [("kept", "the newest 12, each with its scores and the method that made it"), ("replaces the one in use", "only if at least as good on unseen words (within 0.02)"), ("combine", f"average of the best {g('soup_top')}, or smooth with weight {g('ema_alpha')} on the newest")]
    elif nid == "safety":
        rows = [("forbidden controls listed", "Delete playlist, Sign out, Delete, Remove all, Uninstall, Format drive, Delete account"), ("fixed, not adjustable", "the never-press list, the taint gate, the confirm-before-acting rule"), ("live agent", "forbidden controls are hidden from it" if g("hide_forbidden") else "forbidden controls are listed to it and refused when pressed")]
    elif nid == "learners":
        rows = [("tally", "wins and losses with one pretend win and loss"), ("Thompson", f"draws a plausible win rate per option ({g('thompson_draws')} draws)"), ("LinUCB", f"ridge regression per option over 8 hashed context numbers, optimism {g('linucb_alpha')}")]
        formula = ["estimate = sum w r / sum w   with w = min(cap, pi / p),  cap = " + str(g("ope_cap"))]
    elif nid == "router":
        layers = [("sentence", "letter-triples"), ("hashed counts", "512"), ("softmax", "one score per bin")]
        formula = ["L(W) = -(1/n) sum log softmax(W x)[y] + lambda |W|^2"]
        rows = [("neighbours", str(g("knn_k"))), ("held out", f"{g('held_out_tenths')} of every 10 sentences, picked by a fixed hash"), ("not adjustable here", "the router's own cut-offs 0.75 and 0.8: they act on live requests")]
    elif nid == "search":
        formula = ["CMA-ES: x_k ~ N(m, sigma^2 C); keep the best half; move m, C, sigma", "Bayesian optimisation: next try where expected improvement is largest"]
        rows = [("not adjustable here", "the hand and speech thresholds live in hand-gestures.js and voice-gate.js and are not read from here yet")]
    elif nid == "presets":
        rows = [("presets", "precise, balanced, varied, terse, long"), ("eight settings", "temperature, top_k, top_p, min_p, presence penalty, frequency penalty, max tokens, stop sequences")]
        formula = [f"reward = {g('rw_valid_json')} valid + {g('rw_not_truncated')} not cut off + {g('rw_no_repeat')} (1 - repeats) + {g('rw_checks')} checks - {g('rw_tokens')} tokens used"]
    elif nid == "knobs":
        rows = [("episodes", f"{g('episodes')} pretend tasks per learner"), ("seed", str(g("seed")))]
    return {"layers": [{"name": a_, "size": b_} for a_, b_ in layers], "rows": [{"label": a_, "value": b_} for a_, b_ in rows], "formula": formula}


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
        n["outside"] = n["id"] in OUTSIDE
        n["arch"] = arch(n["id"])
    return web.json_response(c)


if __name__ == "__main__":
    write(sys.argv[1] if len(sys.argv) > 1 else "learning.canvas")
