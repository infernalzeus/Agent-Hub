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
         "from": "routing decisions, mission and PC-task outcomes", "amount": f"shadow {'on' if shadow_on else 'off'} | log {'on' if learning_on else 'off'}",
         "changes": "writes only; nothing reads it live", "needs": "SHADOW MODE on",
         "details": [("log", f"{sum(k.get('events', 0) for k in per.values())} events since the fresh start; {st.get('before_fresh_start', 0)} before it, unused"),
                     ("fresh start", time.strftime("%d %b %H:%M", time.localtime(since)) if since else "never"),
                     ("shadow lines", str(shadow_lines))]},
        {"id": "router", "name": "Router: what you meant", "state": "recording" if graded or rd["sentences"] else "off",
         "from": "graded requests (TEACH), requests behind trusted routines", "amount": f"{len(graded)} graded | {rd['sentences']} from routines",
         "changes": "rules decide; kNN and softmax routers scored alongside; tev gets the nearest settled sentences when local decisions are on",
         "needs": f"~100 settled sentences for a fine-tune ({len(graded) + rd['sentences']})",
         "details": [("decision log", f"{len(decisions)} requests, last {_ago(max((r['at'] for r in decisions), default=0))}; {len(new)} since the fresh start (the TEACH queue)"),
                     ("fine-tune", "not started: needs the data above and a GPU route for PyTorch")]},
        {"id": "bandits", "name": "Model and PC-way choice", "state": "recording" if any(per.get(k, {}).get("events") for k in ("model", "rung")) else "off",
         "from": "result per model per mission; result per PC way (replay | agent)", "amount": f"{per.get('model', {}).get('events', 0)} model | {per.get('rung', {}).get('events', 0)} PC-way results",
         "changes": "model order: rules decide (the local model's record on your checks, whether a model works); with presets on APPLY the tally moves its pick to the front, once two models have 3 results each", "needs": "finished missions and PC tasks with a result",
         "details": [("learners", "tally, Thompson and LinUCB are scored on the same rows (SCORES); only the tally can act, and only in APPLY. The order and what works: MODELS tab")]},
        {"id": "presets", "name": "Sampling presets", "state": {"off": "off", "shadow": "shadow-picks", "apply": "live"}.get(mode, "off"),
         "from": "every finished mission step, label-free reward", "amount": f"{ps['calls']} steps | mode {mode}",
         "changes": ("apply mode: an agent uses the tally pick; " if mode != "apply" else "agents use the tally pick; ") + "a preset you choose per agent always applies",
         "needs": "~10 scored steps per role",
         "details": [("your choices", ", ".join(f"{k}: {v}" for k, v in PRE.choices().items()) or "none: every agent uses its own settings")]
                    + [(r["role"], f"{r['calls']} steps, next pick {(r['pick'] or {}).get('name', '-')}") for r in ps["roles"]]},
        {"id": "policy", "name": "Learner for PC controls", "state": "shadow" if (shadow_on and shadow_lines) else "practice" if rep else "off",
         "from": "pretend apps (practice), trusted-routine steps, approved live tasks", "amount": f"{rep.get('episodes', 0)} episodes | {rd['steps']} routine steps",
         "changes": "never presses; in shadow it logs its pick beside the live agent",
         "needs": "approved live tasks, then 30 watched choices to promote",
         "details": [("last practice", f"{_ago(rep.get('at', 0))}, {rep.get('episodes', 0)} episodes on pretend apps"),
                     ("seen layouts", f"{round(100 * lin.get('train', 0))} %" if lin else "no session yet"),
                     ("unseen layouts", f"{round(100 * lin.get('held', 0))} % (random {round(100 * (means.get('random') or {}).get('held', 0))} %, rule of thumb {round(100 * rule.get('held', 0))} %)" if lin else "-"),
                     ("scope", "pretend apps only; no real-app data yet")]},
        {"id": "routines", "name": "Your trusted routines", "state": "recording" if rd["on"] and rd["routines"] else "off",
         "from": "routines you trusted", "amount": f"{len(rd['routines'])} routines | {rd['sentences']} requests | {rd['steps']} steps",
         "changes": "feed the router and the PC-controls learner (switch in ROUTINES)", "needs": "more trusted routines",
         "details": [(r["text"], f"{r['bin']}, {r['steps']} steps, replayed {r['replays_ok']} good / {r['replays_bad']} bad, {r['used_as']}") for r in rd["routines"]]},
    ]
    nxt = ("shadow off: nothing is recorded. Enable SHADOW MODE, then use Talk and PC tasks and approve routines." if not (shadow_on or learning_on)
           else "recording: grade requests in TEACH, approve routines in ROUTINES.")
    return {"rows": rows, "next": nxt, "switches": [{"key": "routine_data", "label": "Trusted routines teach the learners", "on": rd["on"]}]}


@routes.get("/api/yard/overview")
async def api_overview(request: web.Request) -> web.Response:
    return web.json_response(overview())
