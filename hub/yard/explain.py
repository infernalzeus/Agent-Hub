"""Why the learner would press what it would press, and which of its numbers a step would move. Read-only: nothing here presses anything or changes a saved file.

For one screen it lists the controls the learner could press with the score it gives each, the probability that becomes, and the few features that made the score what it
is (the number the feature has times the learned weight). If you tell it which control was pressed and whether that turned out well (the advantage), it also says which
weights that one step would move the most: the update is `advantage x (features of the pressed control - the probability-weighted average of all of them)`.

It reads the same screens the yard uses: the ones built from one of your trusted routines (`demos.screens`), or a step the live agent really took (shadow memory keeps the prompt it
was shown). The actor it explains is the one in use (`policy.json`, the linear one the shadow watcher reads).
"""
from __future__ import annotations

import json
import random

from aiohttp import web

routes = web.RouteTableDef()
FLAGS = ("always", "something pressed earlier", "a list entry pressed", "typed something", "the last press changed the screen", "the last press changed nothing", "something is playing")


def base_names() -> "list[str]":
    from . import learner as L
    names = [f"it is a {k}" for k in L.KINDS] + [f"control is a {r}" for r in L.ROLES] + ["control is another kind"]
    names += ["goal words in its name", "goal words in its group", "goal words in its row", "its name has Play", "pressed earlier", "pressed and nothing changed", "on the never-press list"]
    return names + [f"spelling piece {k + 1}" for k in range(L.HASH)]


def feature_name(i: int) -> str:
    from . import learner as L
    b, f = base_names()[i % L.BASE], FLAGS[i // L.BASE]
    return b if f == "always" else f"{b} (when {f})"


def describe(act: dict, o: dict) -> str:
    c = next((c for c in o["controls"] if c["id"] == act.get("id")), None)
    if act["do"] == "click" and c:
        return f"press {c['role']} “{c['name']}”" + (f" in “{c['path']}”" if c["path"] else "")
    if act["do"] == "type" and c:
        return f"type the goal words into “{c['name']}”"
    return {"key": "press Enter", "done": "say the task is done", "stuck": "say it is stuck"}.get(act["do"], act["do"])


def _load_actor():
    from . import learner as L
    from . import shadow as SH
    if not SH.POLICY.exists():
        return None
    return L.Actor.load(json.loads(SH.POLICY.read_text(encoding="utf-8"))["linear"])


def _effective(actor, X):
    """The weight each feature has on each candidate's score: the learned weight for a linear actor, the slope through the hidden layer otherwise."""
    import numpy as np
    if not actor.h:
        return np.tile(actor.w, (X.shape[0], 1))
    h = np.tanh(X @ actor.W1 + actor.b1)
    return ((1 - h * h) * actor.w2) @ actor.W1.T


def screen(o: dict, actor, chosen: "int | None" = None, advantage: "float | None" = None, show: int = 5, top: int = 4, lr: float = 0.05) -> dict:
    """Explain one screen. `chosen` is the id of the control that was pressed (or None); `advantage` how much better than expected it turned out."""
    import numpy as np
    from . import learner as L
    acts, X = L.candidates(o)
    s, _ = actor.forward(X)
    p = L.softmax(s)
    W = _effective(actor, X)
    contrib = X * W
    order = list(np.argsort(-p))
    ci = next((j for j, a in enumerate(acts) if a.get("do") == "click" and a.get("id") == chosen), None) if chosen is not None else None
    pick = order[:show] + ([ci] if ci is not None and ci not in order[:show] else [])
    cands = []
    for j in pick:
        parts = sorted(range(X.shape[1]), key=lambda i: -abs(contrib[j][i]))[:top]
        cands.append({"action": describe(acts[j], o), "score": round(float(s[j]), 3), "p": round(float(p[j]), 3), "pressed": bool(j == ci), "best": bool(j == order[0]),
                      "because": [{"feature": feature_name(i), "has": round(float(X[j][i]), 2), "part": round(float(contrib[j][i]), 3)} for i in parts if abs(contrib[j][i]) > 1e-6]})
    out = {"goal": o["goal"], "step": o["step"] + 1, "controls": len(o["controls"]), "candidates": cands, "linear": not actor.h}
    if ci is not None and advantage is not None:
        delta = float(advantage) * (X[ci] - p @ X)
        mv = sorted(range(len(delta)), key=lambda i: -abs(delta[i]))[:6]
        out["moves"] = [{"weight": feature_name(i), "change": round(float(lr * delta[i]), 5), "direction": "up" if delta[i] > 0 else "down"} for i in mv if abs(delta[i]) > 1e-9]
        out["advantage"] = round(float(advantage), 3)
    return out


def routine(rid: str, seed: int = 0) -> dict:
    """The learner's view of each named-control step of one trusted routine, on the screens the agreement check builds."""
    from . import demos as DM
    actor = _load_actor()
    if actor is None:
        return {"error": "no saved learner yet: start a session first"}
    rt = next((r for r in DM.routines() if r["id"] == rid), None)
    if rt is None:
        rt = next((r for r in _any_routine(rid)), None)
    if rt is None or not rt["steps"]:
        return {"error": "no named-control steps in that routine"}
    steps = []
    for i, st, o, cl, want in DM.screens(rt, random.Random(seed)):
        e = screen(o, actor, chosen=want, advantage=1.0)
        e["routine_presses"] = f"{st['role']} “{st['name']}”"
        top = e["candidates"][0]
        e["agrees"] = top["pressed"]
        steps.append(e)
    return {"routine": rt["title"], "steps": steps, "agree": sum(1 for s in steps if s["agrees"]), "of": len(steps),
            "note": "Each step is shown as a choice among the routine's control and a few decoys. 'Weights moved' assumes this press was a good one (advantage +1): it is what learning from this step would change."}


def _any_routine(rid: str):
    """Any routine in the store (not only the attested ones), so a candidate can be explained before it is trusted."""
    from . import demos as DM
    try:
        from ..features import pc_control as PC
        with PC._db() as db:
            row = db.execute("SELECT id, title FROM pc_routines WHERE id=?", (rid,)).fetchone()
            if row:
                yield {"id": row["id"], "title": row["title"], "steps": DM.steps_of(db, rid)}
    except Exception:  # noqa: BLE001
        return


def _runs() -> "list[dict]":
    """The live tasks kept by shadow memory, one entry per run of a task (a run starts at its step 0), oldest first: {"goal", "at" (its first step), "rows": [...]}."""
    from . import memory as MEM
    runs: "list[dict]" = []
    try:
        lines = MEM.MEMORY_STEPS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not runs or r.get("step", 0) == 0 or runs[-1]["goal"] != r.get("goal"):
            runs.append({"goal": r.get("goal"), "at": r.get("at") or 0, "rows": []})
        runs[-1]["rows"].append(r)
    return runs


def live_tasks(limit: int = 12) -> "list[dict]":
    """Recent live tasks kept by shadow memory, newest first: goal, number of steps, when it started."""
    return [{"goal": r["goal"], "at": r["at"], "steps": len(r["rows"])} for r in reversed(_runs())][:limit]


def live_task(goal: str, at: float) -> dict:
    from . import learner as L
    actor = _load_actor()
    if actor is None:
        return {"error": "no saved learner yet: start a session first"}
    run = next((r for r in _runs() if r["goal"] == goal and abs(r["at"] - at) < 0.5), None)
    if run is None:
        return {"error": "that task is no longer in shadow memory"}
    out = []
    for r in sorted(run["rows"], key=lambda r: r.get("step", 0))[:20]:
        if not r.get("prompt"):
            continue
        o = L.parse(r["prompt"])
        live = r.get("live") or {}
        e = screen(o, actor, chosen=live.get("id") if live.get("do") == "click" else None, advantage=1.0 if live.get("do") == "click" else None)
        e["live_did"] = describe(live, o) if live else "(nothing recorded)"
        out.append(e)
    return {"routine": goal, "steps": out, "agree": sum(1 for s in out if s["candidates"] and s["candidates"][0]["pressed"]), "of": len(out),
            "note": "These are the screens the live agent was really shown. The first line of each is what the saved learner would press; the one marked pressed is what the live agent pressed."}


@routes.get("/api/yard/why/routine/{rid}")
async def api_why_routine(request: web.Request) -> web.Response:
    return web.json_response(routine(request.match_info["rid"]))


@routes.get("/api/yard/why/live")
async def api_why_live(request: web.Request) -> web.Response:
    q = request.query
    if q.get("goal"):
        try:
            return web.json_response(live_task(q["goal"], float(q.get("at", 0))))
        except ValueError:
            raise web.HTTPBadRequest(text="at must be a number")
    return web.json_response({"tasks": live_tasks()})
