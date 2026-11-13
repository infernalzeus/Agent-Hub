"""The OVERVIEW tab of the reinforcement-learning panel: one row per thing that learns, in the order data travels.

    where the data comes from  ->  what learns from it  ->  what it changes today  ->  what it still needs

Every number is read from the same places the other tabs read (the decision log, the learning log, the practice report, the routine store, the preset tally); nothing here is estimated.
A row's state is one of: off (not recording), recording (collecting, changes nothing), practice (trained on pretend apps only), shadow (compares with the live agent, changes nothing),
shadow-picks (writes down what it would choose, changes nothing), live (changes what the Hub does).
"""
from __future__ import annotations

import json
import time

from aiohttp import web

routes = web.RouteTableDef()


def _ago(t: float) -> str:
    if not t:
        return "never"
    d = max(0, time.time() - t)
    return f"{int(d // 60)} min ago" if d < 5400 else f"{int(d // 3600)} h ago" if d < 172800 else time.strftime("%d %b", time.localtime(t))


def overview() -> dict:
    from ..features import binning as BIN, learning as LRN
    from . import presets as PRE, router_challenger as RC, routine_data as RD, settings as YS
    from ..runtime import STATE
    cur = YS.current()
    since = YS.fresh_since()
    rows_log = BIN._rows()
    decisions = [r for r in rows_log if r.get("kind") not in ("outcome", "verdict") and r.get("at")]
    new = [r for r in decisions if not since or r["at"] >= since]
    graded = RC.examples()
    rd = RD.summary()
    st = LRN.status()
    per = st.get("per_kind", {})
    ps = PRE.summary()
    rep = {}
    try:
        rep = json.loads((STATE / "data" / "yard" / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        shadow_lines = sum(1 for _ in (STATE / "data" / "yard" / "shadow.jsonl").open(encoding="utf-8"))
    except OSError:
        shadow_lines = 0
    means = (rep.get("means") or {})
    lin = means.get("learned, linear") or {}
    rule = means.get("rule of thumb") or {}
    shadow_on, learning_on = bool(cur["shadow"]["on"]), bool(cur["learning"]["on"])
    mode = PRE.mode()
    rows = [
        {"id": "recording", "name": "Recording", "state": "recording" if (shadow_on or learning_on) else "off",
         "from": "the choices the Hub makes and how they turned out", "amount": f"shadow {'on' if shadow_on else 'off'}, learning log {'on' if learning_on else 'off'}",
         "changes": "nothing: it only writes things down", "needs": "switch SHADOW MODE on (top of the panel), then use the Hub for real tasks",
         "details": [("learning log", f"{sum(k.get('events', 0) for k in per.values())} events since the fresh start; {st.get('before_fresh_start', 0)} older ones are kept apart and never used"),
                     ("fresh start", time.strftime("%d %b %H:%M", time.localtime(since)) if since else "never"),
                     ("shadow lines kept", str(shadow_lines))]},
        {"id": "router", "name": "Router: what you meant", "state": "recording" if graded or rd["sentences"] else "off",
         "from": "requests you graded (TEACH) and the request each trusted routine answers", "amount": f"{len(graded)} graded + {rd['sentences']} from routines",
         "changes": "nothing yet: the rules decide; a nearest-sentence and a softmax router are measured beside them. The local model (tev) is shown the nearest settled sentences when local decisions are on",
         "needs": f"about 100 settled sentences for a fine-tune (have {len(graded) + rd['sentences']})",
         "details": [("decision log", f"{len(decisions)} requests in all, last one {_ago(max((r['at'] for r in decisions), default=0))}; {len(new)} since the fresh start"),
                     ("why TEACH can be empty", "TEACH offers only requests made after the fresh start, and none has been logged since" if not new else f"{len(new)} offered there"),
                     ("fine-tune", "not started: needs the data above and a GPU route for PyTorch")]},
        {"id": "bandits", "name": "Model and PC-way choice", "state": "recording" if any(per.get(k, {}).get("events") for k in ("model", "rung")) else "off",
         "from": "which model finished a mission, and whether replaying a routine or trying afresh worked", "amount": f"{per.get('model', {}).get('events', 0)} model results, {per.get('rung', {}).get('events', 0)} PC-way results",
         "changes": "the model order, once two models have three exact results each; today nothing", "needs": "more finished missions and PC tasks with a result you or the checks gave",
         "details": [("tally, Thompson, LinUCB", "three learners are run side by side on the same rows (SCORES tab); only the plain tally may change the order")]},
        {"id": "presets", "name": "Sampling presets", "state": {"off": "off", "shadow": "shadow-picks", "apply": "live"}.get(mode, "off"),
         "from": "every finished mission step, scored without any grading", "amount": f"{ps['calls']} steps scored; mode {mode}",
         "changes": ("in apply mode an agent uses the preset the tally picks; " if mode != "apply" else "agents use the preset the tally picks; ") + "a preset you choose for an agent always applies",
         "needs": "about 10 scored steps per role before the tally says anything",
         "details": [("your choices", ", ".join(f"{k}: {v}" for k, v in PRE.choices().items()) or "none: every agent uses its own settings")]
                    + [(r["role"], f"{r['calls']} steps, next pick {(r['pick'] or {}).get('name', '-')}") for r in ps["roles"]]},
        {"id": "policy", "name": "Learner for PC controls", "state": "shadow" if (shadow_on and shadow_lines) else "practice" if rep else "off",
         "from": "pretend apps (practice), your trusted routines' steps, and live tasks you approved", "amount": f"{rep.get('episodes', 0)} practice episodes; {rd['steps']} routine steps",
         "changes": "nothing: it never presses anything. In shadow it notes what it would have pressed beside the live agent",
         "needs": "a few approved live tasks, then 30 watched choices before it may be promoted",
         "details": [("last practice", f"{_ago(rep.get('at', 0))}, {rep.get('episodes', 0)} episodes on pretend apps"),
                     ("success on layouts it trained on", f"{round(100 * lin.get('train', 0))} %" if lin else "no session yet"),
                     ("success on layouts it never saw", f"{round(100 * lin.get('held', 0))} % (random 0 %, rule of thumb {round(100 * rule.get('held', 0))} %)" if lin else "-"),
                     ("meaning", "a small network that only knows pretend apps; it has not learned your real apps yet")]},
        {"id": "routines", "name": "Your trusted routines", "state": "recording" if rd["on"] and rd["routines"] else "off",
         "from": "routines you trusted", "amount": f"{len(rd['routines'])} routines, {rd['sentences']} requests, {rd['steps']} steps",
         "changes": "they teach the router and the learner above (switch: ROUTINES tab)", "needs": "trust more routines; each adds a sentence and its steps",
         "details": [(r["text"], f"{r['bin']}, {r['steps']} steps, replayed {r['replays_ok']} good / {r['replays_bad']} bad, {r['used_as']}") for r in rd["routines"]]},
    ]
    nxt = ("Switch SHADOW MODE on, then do tasks by voice or Talk and trust the routines you like; the rows below fill in as you do." if not (shadow_on or learning_on)
           else "Keep using the Hub: trust good routines, press RIGHT or WRONG in TEACH when it picked wrongly.")
    return {"rows": rows, "next": nxt, "switches": [{"key": "routine_data", "label": "Trusted routines teach the learners", "on": rd["on"]}]}


@routes.get("/api/yard/overview")
async def api_overview(request: web.Request) -> web.Response:
    return web.json_response(overview())
