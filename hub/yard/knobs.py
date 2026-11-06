"""Every number of the learning layer that can be adjusted by hand, in one place, with its range, what it does and when a change takes effect.

The yard's KNOBS tab shows these as sliders and switches. A change is saved to data/yard/knobs.json and is read at the moment the number is used, so:
    "next session"  takes effect the next time you press START A SESSION in the yard
    "now"           takes effect on the next thing that uses it (a score, a gate check, a confidence)
Defaults equal what the code used before this registry existed, so changing nothing changes nothing.

NOT adjustable here, on purpose (shown at the bottom of the tab, with the reason): the never-press list, the taint gate and the confirm-before-acting rule (safety:
nothing learned may loosen them), the router's own cut-offs 0.75 and 0.8 (they act on live requests, not on practice), and the hand and speech thresholds (they live in
hand-gestures.js and voice-gate.js and are not read from here yet).
"""
from __future__ import annotations

import json
import os
import time

from aiohttp import web

from ..runtime import STATE

routes = web.RouteTableDef()
FILE = STATE / "data" / "yard" / "knobs.json"
FAMILIES = ("direct", "modal", "search", "menu", "long", "unnamed", "tabs", "confirm")       # the same eight layouts as world.FAMILIES (a test keeps them equal)

# name: (group, label, default, low, high, step or choices, when, what it does)
_RAW = [
    ("Yard session", "episodes", "Episodes per session", 1500, 100, 3000, 100, "next session", "How many pretend tasks each learner tries in one session. More takes longer and usually learns more"),
    ("Yard session", "eval_per_cell", "Unseen apps per cell when measuring", 20, 4, 60, 2, "next session", "How many apps it has never seen are used to score each method on each layout"),
    ("Yard session", "seed", "Random seed", 0, 0, 9999, 1, "next session", "Changes which pretend apps are drawn. A warm start adds the version number to it"),
    ("Yard session", "warm_start", "Continue from the saved learner", True, None, None, None, "next session", "On: a session starts from the version in use and improves it. Off: it starts from nothing"),
    ("Yard session", "hidden_units", "Hidden layer size", 16, 2, 64, 2, "next session", "Units in the one hidden tanh layer of the second learner"),
    ("Yard session", "letters", "Learn from the letters of names", True, None, None, None, "next session", "Off hides the spelling of control names (an ablation): it then has to learn from roles and word overlap only"),
    ("Yard session", "vocab", "Words used in training", "wide", None, None, ("wide", "train"), "next session", "wide: many labels for Play. train: only three, so unseen words test what it memorised"),
    ("Learner", "lr_actor", "Actor step size", 0.05, 0.001, 0.3, 0.001, "next session", "How far the actor's numbers move per update (three times larger with a hidden layer)"),
    ("Learner", "lr_critic", "Critic step size", 0.05, 0.001, 0.3, 0.001, "next session", "How far the critic's numbers move per update"),
    ("Learner", "gamma", "Discount", 0.95, 0.5, 0.999, 0.001, "next session", "How much a later reward counts against an earlier one (1 means all alike)"),
    ("Learner", "entropy_beta", "Exploration bonus", 0.02, 0.0, 0.2, 0.005, "next session", "A small reward for keeping its choices varied, so it keeps trying different controls"),
    ("Rewards", "step_cost", "Cost of each press", 0.02, 0.0, 0.2, 0.005, "next session", "Taken off for every step, so quicker is better"),
    ("Rewards", "invalid_cost", "Cost of an unusable answer", 0.1, 0.0, 1.0, 0.05, "next session", "Extra cost when the answer is not a listed control"),
    ("Rewards", "false_done_cost", "Cost of saying done too early", 0.5, 0.0, 2.0, 0.05, "next session", "Extra cost when it says done and the task is not done"),
    ("Rewards", "forbidden_cost", "Cost of pressing a forbidden control", 0.0, 0.0, 2.0, 0.05, "next session", "Off at 0. Taken off when it presses a control on the never-press list in practice (Delete, Sign out ...), so it learns to avoid them. The real never-press list stops the press on the PC whatever this says"),
    ("Rewards", "win", "Reward for finishing", 1.0, 0.1, 5.0, 0.1, "next session", "Added at the end when the target is really playing"),
    ("Safety (tighten only)", "hide_forbidden", "Hide forbidden controls from the agent", False, None, None, None, "now", "On: controls on the never-press list are not listed to the desktop agent at all, instead of being refused when it tries to press them. It can only make the agent safer"),
    ("Candidate routines", "candidate_agree", "Agreement needed to look ready", 0.6, 0.1, 1.0, 0.05, "now", "How often the learner must press the same controls as a candidate routine, on pretend screens, before the yard calls it ready"),
    ("Replay and hindsight", "replay_every", "Replay every N episodes (0 = off)", 0, 0, 200, 5, "next session", "Re-learn from remembered episodes, the more surprising ones more often"),
    ("Replay and hindsight", "replay_batch", "Episodes per replay", 8, 1, 64, 1, "next session", "How many remembered episodes are replayed each time"),
    ("Replay and hindsight", "replay_priority", "Which episodes are replayed", "uncertainty", None, None, ("uncertainty", "uniform"), "next session", "uncertainty: the ones it was least sure about. uniform: any"),
    ("Replay and hindsight", "hindsight", "Hindsight relabelling", False, None, None, None, "next session", "A failed task that ended up playing something else is also learned from as a success for that other thing"),
    ("Live memory", "memory_prompts", "Keep what the live agent saw", True, None, None, None, "now", "While shadow is on, store each live step's controls list so a session can learn from approved real tasks"),
    ("Live memory", "memory_epochs", "Passes over approved live tasks (0 = off)", 0, 0, 5, 1, "next session", "At the start of a session, imitate the steps of live tasks you or Windows confirmed. Attested routines are never used"),
    ("Task confidence", "w_windows", "Weight: Windows says it is playing", 0.85, 0.0, 1.0, 0.01, "now", "Marker that the result is really there"),
    ("Task confidence", "w_routine", "Weight: a saved routine ran to the end", 0.45, 0.0, 1.0, 0.01, "now", "Marker"),
    ("Task confidence", "w_screen", "Weight: the last press changed the window", 0.35, 0.0, 1.0, 0.01, "now", "Marker"),
    ("Task confidence", "w_agent", "Weight: the agent said it was done", 0.25, 0.0, 1.0, 0.01, "now", "Marker"),
    ("Task confidence", "w_few", "Weight: four presses or fewer", 0.10, 0.0, 1.0, 0.01, "now", "Marker"),
    ("Task confidence", "f_invalid", "Factor: an unusable answer", 0.75, 0.0, 1.0, 0.01, "now", "Multiplies the confidence down"),
    ("Task confidence", "f_nothing", "Factor: the last press changed nothing", 0.50, 0.0, 1.0, 0.01, "now", "Multiplies the confidence down"),
    ("Task confidence", "f_false_done", "Factor: said done early and was wrong", 0.70, 0.0, 1.0, 0.01, "now", "Multiplies the confidence down"),
    ("Task confidence", "conf_cap", "Ceiling without Windows confirming", 0.75, 0.3, 1.0, 0.01, "now", "A task nobody independently checked is never surer than this"),
    ("Task confidence", "evidence_keep", "Tasks kept (with pictures)", 150, 20, 500, 10, "now", "Older ones and their pictures are removed"),
    ("Task confidence", "evidence_width", "Picture width (pixels)", 640, 240, 1280, 40, "now", "Smaller saves space"),
    ("Task confidence", "jpeg_quality", "Picture quality", 55, 20, 90, 5, "now", "Lower saves space"),
    ("Learners", "min_n", "Tries before a tally is trusted", 3, 1, 10, 1, "now", "Results an option needs before the tally has an opinion"),
    ("Learners", "thompson_draws", "Thompson draws", 200, 50, 2000, 50, "now", "How many random draws decide a Thompson pick (more is steadier)"),
    ("Learners", "linucb_alpha", "LinUCB optimism", 0.6, 0.0, 3.0, 0.05, "now", "How much it favours options it knows little about"),
    ("Learners", "linucb_lambda", "LinUCB regularisation", 1.0, 0.1, 10.0, 0.1, "now", "Pulls its estimates towards zero until there is evidence"),
    ("Scoring past choices", "ope_cap", "Largest weight one logged row can have", 10.0, 1.0, 50.0, 1.0, "now", "Stops one rare choice deciding an off-policy estimate"),
    ("Scoring past choices", "ope_boot", "Resamples for the interval", 200, 50, 1000, 50, "now", "More is steadier and slower"),
    ("Router yardstick", "knn_k", "Neighbours", 3, 1, 9, 1, "now", "How many similar graded requests vote"),
    ("Router yardstick", "held_out_tenths", "Share held out for judging (tenths)", 3, 1, 5, 1, "now", "Of every ten sentences, how many are never trained on"),
    ("Router yardstick", "clf_epochs", "Classifier passes", 200, 20, 1000, 20, "now", "Gradient steps of the small router classifier"),
    ("Router yardstick", "clf_l2", "Classifier penalty", 0.01, 0.0, 1.0, 0.005, "now", "Keeps its numbers small so it does not memorise"),
    ("Router yardstick", "clf_lr", "Classifier step size", 0.5, 0.01, 2.0, 0.01, "now", "How far each step moves"),
    ("Gate", "min_frozen", "Held-out rows needed", 50, 10, 500, 10, "now", "A new version cannot be judged on fewer"),
    ("Gate", "shadow_n", "Shadow choices needed", 30, 5, 300, 5, "now", "Real choices it must be watched on, recording only"),
    ("Gate", "shadow_agree", "Agreement needed in shadow", 0.8, 0.5, 1.0, 0.01, "now", "How often it must agree with, or beat, the current way"),
    ("Search", "cma_sigma0", "CMA-ES first step", 0.3, 0.05, 0.6, 0.01, "now", "Size of the first guesses around the middle of each range"),
    ("Search", "cma_repeat", "Repeats per candidate", 1, 1, 5, 1, "now", "Average this many noisy scores per candidate"),
    ("Search", "bo_init", "Bayesian optimisation: random starts", 5, 3, 20, 1, "now", "Tries before the model of the score is used"),
    ("Search", "bo_length", "Bayesian optimisation: smoothness", 0.3, 0.05, 1.0, 0.01, "now", "How far apart two settings can be and still score alike"),
    ("Search", "bo_noise", "Bayesian optimisation: noise", 0.001, 0.0, 0.3, 0.001, "now", "How noisy the score is believed to be"),
    ("Weights", "ema_alpha", "Smoothing weight of the newest version", 0.3, 0.0, 1.0, 0.05, "now", "0 keeps the old numbers, 1 takes the new ones"),
    ("Weights", "soup_top", "Versions averaged in a soup", 3, 1, 10, 1, "now", "How many of the best saved versions are tried in a soup"),
    ("Weights", "clip_norm", "Largest change per update (0 = no limit)", 0.0, 0.0, 10.0, 0.1, "now", "Shrinks a change that is too large"),
    ("Support", "support_threshold", "Seen-before similarity", 0.6, 0.1, 0.99, 0.01, "now", "How alike a screen must be to something trained on before the learner may answer"),
    ("Sampling presets", "rw_valid_json", "Reward: valid answer", 1.0, 0.0, 5.0, 0.1, "now", "Label-free reward part"),
    ("Sampling presets", "rw_not_truncated", "Reward: not cut off", 1.0, 0.0, 5.0, 0.1, "now", "Label-free reward part"),
    ("Sampling presets", "rw_no_repeat", "Reward: no repeating", 0.5, 0.0, 5.0, 0.1, "now", "Label-free reward part"),
    ("Sampling presets", "rw_checks", "Reward: checks passed", 2.0, 0.0, 5.0, 0.1, "now", "Label-free reward part"),
    ("Sampling presets", "rw_tokens", "Penalty: tokens used", 0.2, 0.0, 5.0, 0.1, "now", "Label-free reward part, taken off"),
]
for _f in FAMILIES:
    _RAW.append(("Pretend layouts", "family_" + _f, f"Layout: {_f}", True, None, None, None, "next session", "Include this pretend-app layout in practice and measuring"))

SPEC = {}
for g, name, label, default, lo, hi, step, when, info in _RAW:
    if isinstance(default, bool):
        kind = "bool"
    elif isinstance(default, str):
        kind, lo, hi, choices = "choice", None, None, step
        SPEC[name] = {"group": g, "label": label, "default": default, "kind": kind, "choices": list(choices), "when": when, "info": info}
        continue
    elif isinstance(default, int):
        kind = "int"
    else:
        kind = "float"
    SPEC[name] = {"group": g, "label": label, "default": default, "kind": kind, "low": lo, "high": hi, "step": step, "when": when, "info": info}

FIXED = [("Never-press list", "Controls such as close, delete and sign out are never pressed. Nothing learned may loosen this."),
         ("Taint gate", "After reading content from outside, the Hub does not act on it. Nothing learned may loosen this."),
         ("Confirm before acting", "Risky actions ask first. Nothing learned may loosen this."),
         ("Router cut-offs 0.75 and 0.8", "They decide live requests, not practice; they are changed in the Hub's own decision settings."),
         ("Hand and speech thresholds", "They live in hand-gestures.js and voice-gate.js and are not read from here yet. CMA-ES is built to tune them once there are labelled traces.")]

_CACHE: dict = {"mtime": None, "data": {}, "file": None}


def _load() -> dict:
    try:
        m = FILE.stat().st_mtime
    except OSError:
        _CACHE.update(mtime=None, data={}, file=FILE)
        return {}
    if _CACHE["mtime"] != m or _CACHE["file"] != FILE:
        try:
            d = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        _CACHE.update(mtime=m, data=d if isinstance(d, dict) else {}, file=FILE)
    return _CACHE["data"]


def _clean(name: str, v):
    s = SPEC[name]
    if s["kind"] == "bool":
        if not isinstance(v, bool):
            raise ValueError(f"{name} must be true or false")
        return v
    if s["kind"] == "choice":
        if v not in s["choices"]:
            raise ValueError(f"{name} must be one of {s['choices']}")
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number")
    v = max(s["low"], min(s["high"], v))
    return int(round(v)) if s["kind"] == "int" else float(v)


def get(name: str):
    """The current value: what you set, else the default. Never raises for a known name."""
    s = SPEC[name]
    d = _load()
    if name in d:
        try:
            return _clean(name, d[name])
        except ValueError:
            pass
    return s["default"]


def set_many(changes: dict) -> dict:
    cur = dict(_load())
    for k, v in changes.items():
        if k not in SPEC:
            raise KeyError(k)
        cur[k] = _clean(k, v)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    os.replace(tmp, FILE)
    _CACHE["mtime"] = None
    return values()


def reset(name: "str | None" = None) -> dict:
    cur = {} if name is None else {k: v for k, v in _load().items() if k != name}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    _CACHE["mtime"] = None
    return values()


def values() -> dict:
    return {k: get(k) for k in SPEC}


def families() -> "list[str]":
    on = [f for f in FAMILIES if get("family_" + f)]
    return on or list(FAMILIES)                                       # never an empty set


def describe() -> dict:
    cur = _load()
    items = [{"name": k, **s, "value": get(k), "changed": k in cur and get(k) != s["default"]} for k, s in SPEC.items()]
    return {"knobs": items, "fixed": [{"name": a, "why": b} for a, b in FIXED], "at": time.time()}


@routes.get("/api/yard/knobs")
async def api_knobs(request: web.Request) -> web.Response:
    return web.json_response(describe())


@routes.post("/api/yard/knobs")
async def api_knobs_set(request: web.Request) -> web.Response:
    """{"episodes": 800, "hindsight": true}: set one or more. Out-of-range numbers are clamped; a wrong type or an unknown name is refused."""
    try:
        b = await request.json()
        if not isinstance(b, dict) or not b:
            raise ValueError("send an object")
        set_many(b)
    except (KeyError, ValueError, TypeError) as exc:
        raise web.HTTPBadRequest(text=str(exc)[:160])
    return web.json_response(describe())


@routes.post("/api/yard/knobs/reset")
async def api_knobs_reset(request: web.Request) -> web.Response:
    """{"name": "episodes"} puts one back to its default; {} puts all of them back."""
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    name = b.get("name") if isinstance(b, dict) else None
    if name is not None and name not in SPEC:
        raise web.HTTPBadRequest(text="unknown knob")
    reset(name)
    return web.json_response(describe())
