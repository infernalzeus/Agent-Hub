"""A validation check from your attested routines: would the learned policy press what your trusted routine presses?

Your attested routines were checked by you, so they make a good yardstick, and never a training sample. For each step of a routine that presses a named control, this
builds the choice the learner would face (the routine's control among decoys, with the earlier steps already pressed) and asks the learner which control it picks.
The share it gets the same as the routine is the agreement. It is measured in the yard only, on pretend screens built from your routine's own control names, and it
never presses anything on the PC.
"""
from __future__ import annotations

import json
import random

from . import settings as YS

DECOYS = [("button", "Add to queue"), ("button", "Share"), ("button", "Follow"), ("button", "Radio"), ("button", "Next"), ("button", "Previous"), ("menu item", "Delete playlist")]


def steps_of(db, rid: str) -> "list[dict]":
    """The named-control steps of one routine, in order: [{"role", "name"}]. Steps without a named control (a launch, an address) are left out."""
    steps = []
    for r in db.execute("SELECT tool, args_json, target_json FROM pc_steps WHERE routine_id=? ORDER BY ordinal", (rid,)).fetchall():
        try:
            tgt, args = json.loads(r["target_json"] or "{}"), json.loads(r["args_json"] or "{}")
        except ValueError:
            continue
        name = tgt.get("name") or args.get("name")
        if name:
            steps.append({"role": str(tgt.get("control") or tgt.get("role") or "button"), "name": str(name)})
    return steps


def routines() -> "list[dict]":
    """[{"id", "title", "steps": [{"role", "name"}]}] for the routines attested at the fresh start. Steps without a named control are left out."""
    from ..features import pc_control as PC
    out = []
    try:
        with PC._db() as db:
            for g in YS.golden().get("routines", []):
                out.append({"id": g["id"], "title": g.get("title", ""), "steps": steps_of(db, g["id"])})
    except Exception:  # noqa: BLE001 - no routine store
        return []
    return out


def screens(rt: dict, rng: "random.Random", decoys: int = 4):
    """The choices a routine presents, one per named-control step: yields (step number, step, screen dict `o`, control list, id of the routine's control)."""
    from ..features import pc_control as PC
    pressed: set = set()
    for i, st in enumerate(rt["steps"]):
        pool = [d for d in DECOYS + [(s["role"], s["name"]) for s in rt["steps"] if s["name"] != st["name"]] if d[1] != st["name"]]
        controls = [(st["role"], st["name"])] + rng.sample(pool, min(decoys, len(pool)))
        rng.shuffle(controls)
        cl = [{"id": k + 1, "role": r, "name": n, "path": "", "row": ""} for k, (r, n) in enumerate(controls)]
        goal = rt["title"] or "do the task"
        o = {"goal": goal, "goal_words": PC.target_words(goal), "step": i, "controls": cl, "pressed": set(pressed), "unchanged": set(), "n_pressed": i,
             "typed": False, "item_pressed": any(r == "list item" for r, _ in pressed), "last_changed": i > 0, "last_nothing": False, "playing": False}
        yield i, st, o, cl, next(c["id"] for c in cl if c["name"] == st["name"])
        pressed.add((st["role"], st["name"]))


def agreement(lr, rts: "list[dict] | None" = None, seed: int = 0, decoys: int = 4) -> dict:
    """lr is a yard Learner. Returns {"routines", "steps", "agree", "rate"} and per-routine rows."""
    import numpy as np
    from . import learner as L
    rts = routines() if rts is None else rts
    rng = random.Random(seed)
    total = agree = 0
    rows = []
    for rt in rts:
        if not rt["steps"]:
            continue
        ok = 0
        for i, st, o, cl, want in screens(rt, rng, decoys):
            acts, X = L.candidates(o, lr.letters)
            pick = acts[int(np.argmax(lr.actor.forward(X)[0]))]
            ok += pick.get("do") == "click" and pick.get("id") == want
        rows.append({"id": rt["id"], "title": rt["title"], "steps": len(rt["steps"]), "agree": ok})
        total += len(rt["steps"])
        agree += ok
    return {"routines": len(rows), "steps": total, "agree": agree, "rate": round(agree / total, 3) if total else None, "rows": rows}
