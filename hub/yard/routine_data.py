"""Your trusted routines as learning data.

A routine you trusted is a thing you checked and approved: the request it answers, the steps it presses (with the control each one names), and how often it replayed clean. That is
data the learners can use, so they do (the switch "Use my trusted routines as training data" in the settings of the TRUSTED ROUTINES block; on by default).

What it gives, and what it does not:
  router    the request a routine answers, with the bin it belongs to (open an app: launch_app, do something in it: app_task), as one more example for the router yardsticks and the
            fine-tune plan. One routine is one sentence, so a handful of routines is a handful of rows; the fine-tune needs a hundred.
  policy    each step that presses a named control becomes a screen (the routine's control among decoy controls, earlier steps already pressed) with the routine's press as the approved
            answer. The learner imitates these at the start of a practice session, weighted by `routine_weight` and by how sure the model said it was when the step was recorded.
  the test  a share of the routines is kept out (the same fixed split as the router's held-out sentences): the learner is measured on routines it was not trained on. With too few routines
            for that, everything trains and the report says it was trained on, not tested.

The confidence stored on a step is the model's own word when it recorded the step, not a measurement. It is used as a weight (never above 1, never below one half) and never as a label:
the label is that YOU trusted the routine.
Nothing here presses anything; the screens are pretend.
"""
from __future__ import annotations

import json
import random

from aiohttp import web

routes = web.RouteTableDef()
LAUNCH = ("App", "Uri")


def _sentence(title: str) -> str:
    """What the routine answers, as a request: its title without the label punctuation ("Apple Music: play something from the adhd playlist")."""
    return " ".join(str(title or "").replace(":", " ").split()).strip()


def trusted() -> "list[dict]":
    """[{id, title, text, bin, successes, failures, steps: [{role, name, confidence}]}] for every routine you have trusted, as they are now."""
    from ..features import pc_control as PC
    out = []
    try:
        with PC._db() as db:
            for r in db.execute("SELECT id, intent, title, tool, successes, failures FROM pc_routines WHERE status='trusted' ORDER BY created").fetchall():
                steps = []
                for s in db.execute("SELECT tool, args_json, target_json FROM pc_steps WHERE routine_id=? ORDER BY ordinal", (r["id"],)).fetchall():
                    try:
                        tgt, args = json.loads(s["target_json"] or "{}"), json.loads(s["args_json"] or "{}")
                    except ValueError:
                        continue
                    name = tgt.get("name") or args.get("name")
                    if name:
                        conf = tgt.get("confidence")
                        steps.append({"role": str(tgt.get("control") or tgt.get("role") or "button"), "name": str(name), "confidence": float(conf) if isinstance(conf, (int, float)) else None})
                out.append({"id": r["id"], "title": r["title"], "text": _sentence(r["title"]), "bin": "launch_app" if r["tool"] in LAUNCH else "app_task",
                            "successes": r["successes"], "failures": r["failures"], "steps": steps})
    except Exception:  # noqa: BLE001 - no routine store here (a test, a fresh install): nothing to learn from
        return []
    return out


def enabled() -> bool:
    from . import knobs as K
    return bool(K.get("routine_data"))


def is_held_out(rt: dict) -> bool:
    from . import fitness as FIT, knobs as K
    return K.get("routine_data_test") and FIT.held_out(rt["text"])


def split(rts: "list[dict] | None" = None) -> "tuple[list[dict], list[dict]]":
    """(train, held_out). A held-out routine is never trained on. With fewer than three routines nothing is held out: a test of one routine would be noise, and the report says so."""
    rts = trusted() if rts is None else rts
    if len(rts) < 3:
        return list(rts), []
    held = [r for r in rts if is_held_out(r)]
    return [r for r in rts if r not in held], held


def router_rows() -> "list[dict]":
    """One example per trusted routine for the router: {"text", "label", "source"}. Off when the switch is off."""
    from . import knobs as K
    if not enabled() or not K.get("routine_router"):
        return []
    return [{"text": r["text"], "label": r["bin"], "source": "trusted routine"} for r in trusted() if r["text"]]


def screens(rts: "list[dict]", seed: int = 0, decoys: int = 4) -> "list[tuple[dict, int, float]]":
    """[(screen, id of the control the routine presses, weight)] for the named-control steps of the routines."""
    from . import demos as DM, knobs as K
    rng = random.Random(seed)
    out = []
    for rt in rts:
        conf = {s["name"]: s["confidence"] for s in rt["steps"]}
        for i, st, o, cl, want in DM.screens({"title": rt["title"], "steps": rt["steps"]}, rng, decoys):
            c = conf.get(st["name"])
            w = float(K.get("routine_weight")) * (1.0 if c is None else max(0.5, min(1.0, float(c))))
            out.append((o, want, w))
    return out


def imitate(learner, rts: "list[dict]", epochs: int, seed: int = 0) -> float:
    """Imitate the routines' steps `epochs` times (new decoys each time). Returns the mean probability the learner gave the routines' press, on the last pass."""
    p = 0.0
    for e in range(max(0, epochs)):
        p = learner.imitate_screens(screens(rts, seed + e))
    return p


def summary() -> dict:
    """What is used, for the panel: per routine and in total."""
    from . import knobs as K
    rts = trusted()
    train, held = split(rts)
    held_ids = {r["id"] for r in held}
    rows = [{"id": r["id"], "title": r["title"], "text": r["text"], "bin": r["bin"], "steps": len(r["steps"]), "replays_ok": r["successes"], "replays_bad": r["failures"],
             "confidence": (round(sum(s["confidence"] for s in r["steps"] if s["confidence"] is not None) / max(1, sum(1 for s in r["steps"] if s["confidence"] is not None)), 2)
                            if any(s["confidence"] is not None for s in r["steps"]) else None),
             "used_as": "test (kept out of training)" if r["id"] in held_ids else "training"} for r in rts]
    return {"on": enabled(), "router_on": bool(K.get("routine_router")), "epochs": K.get("routine_epochs"), "routines": rows, "sentences": len(router_rows()), "steps": sum(r["steps"] for r in rows),
            "held_out": len(held), "note": ("fewer than three routines: all of them train, none is kept for a test" if len(rts) < 3 else "")}


@routes.get("/api/yard/routine-data")
async def api_routine_data(request: web.Request) -> web.Response:
    return web.json_response(summary())
