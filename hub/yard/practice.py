"""Run episodes in the practice yard: train a policy, measure it against two baselines on layouts and labels it never saw, say why failures failed.

Every episode is the REAL `desktop_agent.attempt` driven against a pretend app, with a policy standing in for the language model. A success is
read from the pretend app's own state (the target is playing), never from the agent's own verdict.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

import numpy as np

from ..features import desktop_agent as DA
from ..runtime import STATE
from . import learner as L
from .world import APP, FAMILIES, World

STEP_COST, INVALID_COST, FALSE_DONE_COST, WIN = 0.02, 0.1, 0.5, 1.0
REPORT = STATE / "data" / "yard" / "report.json"        # under data/, which is never committed or shipped
POLICY = REPORT.with_name("policy.json")
_LOOP = asyncio.new_event_loop()


def run_episode(world: World, decide, max_steps: int = DA.MAX_STEPS) -> dict:
    res = _LOOP.run_until_complete(DA.attempt(world.goal, APP, decide, tree=world.tree, media=world.media, click=world.click,
                                              type_=world.type_, key=world.key, settle=0, max_steps=max_steps, shadow=False))
    trace = res.get("trace") or []
    return {"success": world.success(), "agent_said_ok": bool(res.get("ok")), "trace": trace, "steps": len(trace),
            "invalid": sum(1 for t in trace if t.get("do") == "invalid"),
            "false_done": sum(1 for t in trace if t.get("do") == "done") - (1 if res.get("ok") else 0)}


def rewards(ep: dict) -> "list[float]":
    out = [-STEP_COST - (INVALID_COST if t.get("do") == "invalid" else 0.0) for t in ep["trace"]]
    for i, t in enumerate(ep["trace"]):
        if t.get("do") == "done" and not (ep["agent_said_ok"] and i == len(ep["trace"]) - 1):
            out[i] -= FALSE_DONE_COST
    if out and ep["success"]:
        out[-1] += WIN
    return out


def cause(world: World) -> str:
    """Why a failed episode failed. Walk the correct path on a fresh copy of the same app and ask, at each stage, whether the control that
    moves it forward is even listed for the agent. If one is not, no policy could have chosen it; if all are, the policy chose badly."""
    fresh = World(world.family, world.seed, world.vocab)
    for _ in range(8):
        need = fresh.needed()
        if not need:
            break
        nodes = _LOOP.run_until_complete(fresh.tree())
        shown = {(c["node"]["x"], c["node"]["y"]) for c in DA.controls(nodes, APP, fresh.goal)}
        missing = [n for n in nodes if (n.get("x"), n.get("y")) in need and (n["x"], n["y"]) not in shown]
        if missing:
            m = missing[0]
            return ("a control with no name is never listed" if not m["name"].strip() else
                    "a list entry past the list cap is never listed" if m["control"] == "list item" else "the control is not listed")
        x, y = sorted(need)[0]
        n = next(n for n in nodes if (n.get("x"), n.get("y")) == (x, y))
        if n["control"] == "edit":
            _LOOP.run_until_complete(fresh.type_(" ".join(fresh.target.casefold().split()), [x, y]))
        else:
            _LOOP.run_until_complete(fresh.click(x, y))
        if fresh.success():
            break
    return "listed, but the policy did not choose it"


class Stopped(Exception):
    """The person pressed STOP."""


CONTROL = {"running": False, "stop": False, "phase": "", "done": 0, "total": 0}      # read by the page every second or two; written only here


def _tick(phase: "str | None" = None) -> None:
    if phase:
        CONTROL["phase"] = phase
    if CONTROL["stop"]:
        raise Stopped()
    CONTROL["done"] += 1


def train(episodes: int, hidden: int = 0, seed: int = 0, families=FAMILIES, every: int = 200, vocab: str = "wide", letters: bool = True) -> "tuple[L.Learner, list]":
    lr = L.Learner(hidden=hidden, seed=seed, letters=letters)
    rng = np.random.default_rng(seed + 7)
    curve, recent = [], []
    for k in range(episodes):
        _tick()
        w = World(rng.choice(list(families)), int(rng.integers(0, 10_000)), vocab)
        pol = lr.policy(True)
        ep = run_episode(w, pol)
        recent.append(ep["success"])
        if pol.records:
            lr.update(pol.records, rewards(ep)[:len(pol.records)])
        if (k + 1) % every == 0:
            curve.append((k + 1, round(float(np.mean(recent[-every:])), 3)))
    return lr, curve


def evaluate(make, n: int = 30, families=FAMILIES) -> dict:
    out = {}
    for fam in families:
        out[fam] = {}
        for vocab in ("train", "held"):
            eps, causes = [], {}
            for s in range(n):
                _tick()
                w = World(fam, 100_000 + s, vocab)
                ep = run_episode(w, make())
                eps.append(ep)
                if not ep["success"]:
                    c = cause(w)
                    causes[c] = causes.get(c, 0) + 1
            out[fam][vocab] = {"success": round(sum(e["success"] for e in eps) / n, 3), "steps": round(float(np.mean([e["steps"] for e in eps])), 2),
                               "false_done": sum(max(0, e["false_done"]) for e in eps), "invalid": sum(e["invalid"] for e in eps), "why_failed": causes}
    return out


def ablation(episodes: int = 3000, seed: int = 0, n_eval: int = 30) -> list:
    """Which ingredient makes a policy work on words it never saw: the letters of names, a wider set of words in training, a hidden layer?"""
    rows = []
    for letters in (True, False):
        for vocab in ("train", "wide"):
            for hidden in (0, 16):
                lr, _ = train(episodes, hidden, seed, vocab=vocab, letters=letters)
                res = evaluate(lambda: lr.policy(False), n_eval, [f for f in FAMILIES if f != "unnamed"])
                m = lambda v: round(float(np.mean([res[f][v]["success"] for f in res])), 3)
                rows.append({"letters_of_names": letters, "training_words": vocab, "hidden_units": hidden, "seen_words": m("train"), "unseen_words": m("held")})
    return rows


def practice(episodes: int = 3000, seed: int = 0, n_eval: int = 30, write: bool = True, with_ablation: bool = False) -> dict:
    t0 = time.time()
    CONTROL.update(running=True, stop=False, phase="training the plain learner", done=0, total=2 * episodes + 4 * len(FAMILIES) * 2 * n_eval)
    try:
        return _practice(episodes, seed, n_eval, write, with_ablation, t0)
    except Stopped:
        return {"stopped": True, "done": CONTROL["done"], "total": CONTROL["total"]}
    finally:
        CONTROL.update(running=False, stop=False)


def _practice(episodes: int, seed: int, n_eval: int, write: bool, with_ablation: bool, t0: float) -> dict:
    lin, c_lin = train(episodes, 0, seed)
    CONTROL["phase"] = "training the one-hidden-layer learner"
    mlp, c_mlp = train(episodes, 16, seed)
    CONTROL["phase"] = "measuring on layouts and words it has not seen"
    t_train = time.time() - t0
    table = {"random": evaluate(lambda: L.random_policy(5), n_eval),
             "rule of thumb": evaluate(lambda: L.greedy_policy, n_eval),
             "learned, linear": evaluate(lambda: lin.policy(False), n_eval),
             "learned, one hidden layer": evaluate(lambda: mlp.policy(False), n_eval)}
    rep = {"at": time.time(), "episodes": episodes, "seed": seed, "eval_per_cell": n_eval, "train_seconds": round(t_train, 1),
           "curve": {"linear": c_lin, "hidden16": c_mlp}, "table": table,
           "means": {p: {v: round(float(np.mean([t[f][v]["success"] for f in FAMILIES])), 3) for v in ("train", "held")} for p, t in table.items()},
           "caveat": "pretend apps written by the same hand that wrote the features; numbers show what the method can and cannot learn, not how it will do on a real app"}
    if with_ablation:
        rep["ablation"] = ablation(episodes, seed, n_eval)
    if write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        POLICY.write_text(json.dumps({"linear": lin.actor.dump(), "hidden16": mlp.actor.dump()}), encoding="utf-8")
    return rep


def show(rep: dict) -> None:
    print(f"{rep['episodes']} episodes, trained in {rep['train_seconds']} s, {rep['eval_per_cell']} unseen apps per cell")
    for p, t in rep["table"].items():
        print(f"\n{p}   mean success: seen words {rep['means'][p]['train']}, unseen words {rep['means'][p]['held']}")
        for f, v in t.items():
            print(f"  {f:8} seen {v['train']['success']:.2f} ({v['train']['steps']} steps)   unseen words {v['held']['success']:.2f}   {v['held']['why_failed'] or v['train']['why_failed'] or ''}")
    print("\nlearning curve (success over each block of training episodes):", rep["curve"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval", type=int, default=30)
    ap.add_argument("--ablation", action="store_true")
    a = ap.parse_args()
    show(practice(a.episodes, a.seed, a.eval, with_ablation=a.ablation))
