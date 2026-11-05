"""Who is in the Hub, who calls whom, and which of their choices the learners can see.

  GET /api/hub/agent-map   {nodes, edges, coverage, gaps, complete}

The nodes are NOT typed in here: they are every persona file (hub/agent_knowledge/agents/*.md) plus every Hub helper (hub/features/helpers.py). The edges come
from the helpers' own `calls` lists, the team roster and the work-type rosters. The only hand-written part is COVERAGE: for each node, what it decides, whether
that decision is written to the learning log, which learner reads it, and why not when it is not. `complete` is false the moment a persona or helper exists
that COVERAGE has never been asked about, so a new agent cannot slip in without somebody deciding what the learners should know about it
(packaging/test_agent_map.py fails on it). This is the checklist to read before building the real reinforcement learner (TD3 / CMA-ES).
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

# state: learned = a learner reads it today · logged = recorded, no learner yet · gap = a real decision nobody records · by-design = deliberately not learned
_P = "persona"
COVERAGE: "dict[str, dict]" = {
    "smith": {"decides": "what you meant (which command), and when to hand over to another helper", "kind": "route", "state": "logged",
              "note": "Every route is written to the learning log. TEACH can label it exactly; the route learner (R5) needs 100 exact labels first."},
    "router": {"decides": "open an app, a Hub command, a task inside an app, or just talk", "kind": "route", "state": "logged",
               "note": "Same events as Smith. Fixed rules today, so there is nothing to learn from until the labels exist."},
    "desktop": {"decides": "how to do a PC task: replay a saved routine or try it afresh (the rung)", "kind": "rung", "state": "learned",
                "note": "The PC-task bandit (R4) reads it once an app has three exact results each way."},
    "yard": {"decides": "which control to press in the pretend apps (and, in shadow mode, in the live desktop agent)", "kind": "yard", "state": "learned",
             "note": "Actor-critic, 8 layouts, versioned saves, adopted only if it beats the best save on unseen words. Never acts on the live PC yet."},
    "bandit-model": {"decides": "which model runs a mission", "kind": "model", "state": "learned", "note": "A tally per (model, size of brief); silent until two models have three exact results each."},
    "bandit-rung": {"decides": "replay or try afresh, per app", "kind": "rung", "state": "learned", "note": "Same table as the desktop agent's rung."},
    "recorder": {"decides": "nothing: it only writes down the others' choices", "kind": "none", "state": "by-design", "note": "The source of every other learner."},
    "doctor": {"decides": "what is wrong and what to change; the owner applies or discards the result", "kind": "fix", "state": "logged",
               "note": "Your APPLY or DISCARD is written to the learning log as an exact label (kind fix, since 5 Nov). Nothing learns from it yet."},
    "neo": {"decides": "how a new or edited agent is written", "kind": "none", "state": "by-design",
            "note": "A drafted agent has no outcome that can be marked right or wrong in a short time, so it is not learned. The owner reads every draft before saving."},
    "orchestrator": {"decides": "which agent does which step of a plan", "kind": _P, "state": "logged",
                     "note": "When you APPLY or DISCARD a mission, each step's agent is written to the learning log with that verdict (kind persona, since 5 Nov). Nothing learns from it yet."},
}
_PERSONA_DEFAULT = {"decides": "nothing alone: it is chosen by the orchestrator and runs on a model the model bandit picks", "kind": "model", "state": "logged",
                    "note": "Its model is logged with the mission result; which persona was picked is logged with your verdict."}
_UTILITY = {"scout": {"decides": "what an unfamiliar repo needs to be fronted by the Hub", "kind": "none", "state": "by-design",
                      "note": "Runs once per app; the manifest it writes is read and checked by a person."}}


def _nodes() -> "list[dict]":
    from .. import agent_knowledge as AK
    from . import helpers as H
    out = []
    for a in AK.list_agents():
        if a["name"] in ("neo", "scout"):
            kind = "agent"
        else:
            kind = "persona"
        out.append({"id": a["name"], "name": a["name"], "kind": kind, "origin": "persona file", "mode": a.get("mode", "")})
    ids = {n["id"] for n in out}
    for h in H.build():
        if h["id"] in ids:                   # neo is both a persona file and a helper row: one node, the helper's description wins
            for n in out:
                if n["id"] == h["id"]:
                    n["kind"] = h["kind"]; n["origin"] = "persona file + helper"
            continue
        out.append({"id": h["id"], "name": h["name"], "kind": h["kind"], "origin": "helper"})
    return out


def _edges() -> "list[dict]":
    from .. import agent_knowledge as AK
    from . import helpers as H
    edges = []
    for h in H.build():
        for c in h.get("calls", []):
            edges.append({"from": h["id"], "to": c, "why": "calls"})
    try:
        import json
        team = json.loads((AK.AGENTS_DIR / "team.json").read_text(encoding="utf-8"))
        for r in team.get("roster", []):
            edges.append({"from": team.get("primary", "orchestrator"), "to": r, "why": "may give a step to"})
        for key, prof in AK.profiles().items():
            for r in prof.get("roster", []):
                e = {"from": "orchestrator", "to": r, "why": "may give a %s step to" % prof.get("label", key)}
                if not any(x["from"] == e["from"] and x["to"] == e["to"] for x in edges):
                    edges.append(e)
    except Exception:  # noqa: BLE001
        pass
    edges += [{"from": "router", "to": "recorder", "why": "every route is written down"},
              {"from": "desktop", "to": "recorder", "why": "every PC-task way and result is written down"},
              {"from": "recorder", "to": "bandit-model", "why": "is read by"}, {"from": "recorder", "to": "bandit-rung", "why": "is read by"},
              {"from": "desktop", "to": "yard", "why": "is watched by (shadow mode, never acts)"}]
    return edges


def build() -> dict:
    nodes = _nodes()
    cov = {}
    for n in nodes:
        c = COVERAGE.get(n["id"]) or _UTILITY.get(n["id"])
        if c is None and n["kind"] == "persona":
            c = _PERSONA_DEFAULT
        cov[n["id"]] = c
    ids = {n["id"] for n in nodes}
    edges = [e for e in _edges() if e["from"] in ids and e["to"] in ids]
    missing = [i for i, c in cov.items() if c is None]
    gaps = [{"id": i, "decides": c["decides"], "note": c["note"]} for i, c in cov.items() if c and c["state"] == "gap"]
    return {"nodes": nodes, "edges": edges, "coverage": {i: c for i, c in cov.items() if c}, "gaps": gaps, "unasked": missing, "complete": not missing}


@routes.get("/api/hub/agent-map")
async def api_agent_map(request: web.Request) -> web.Response:
    return web.json_response(build())
