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
    """The sizes come from the KNOBS tab (defaults: -0.02 a step, -0.1 an unusable answer, -0.5 for saying done early, +1 for finishing)."""
    from . import knobs as K
    from ..features import pc_control as PC
    step, invalid, false_done, win, forbidden = K.get("step_cost"), K.get("invalid_cost"), K.get("false_done_cost"), K.get("win"), K.get("forbidden_cost")
    out = [-step - (invalid if t.get("do") == "invalid" else 0.0) - (forbidden if t.get("do") == "click" and PC.never_press(str(t.get("control") or "")) else 0.0) for t in ep["trace"]]
    for i, t in enumerate(ep["trace"]):
        if t.get("do") == "done" and not (ep["agent_said_ok"] and i == len(ep["trace"]) - 1):
            out[i] -= false_done
    if out and ep["success"]:
        out[-1] += win
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


def train(episodes: int, hidden: int = 0, seed: int = 0, families=None, every: int = 200, vocab: "str | None" = None, letters: "bool | None" = None,
          start: "dict | None" = None, label: str = "learner") -> "tuple[L.Learner, list]":
    """Train one learner on pretend apps. Everything adjustable comes from the KNOBS tab, and each step of the process is announced to the FLOW tab (events.py)."""
    from . import events as EV, knobs as K, memory as MEM
    families = families or K.families()
    vocab = vocab or K.get("vocab")
    letters = K.get("letters") if letters is None else letters
    lr = L.Learner(hidden=hidden, seed=seed, letters=letters)
    if start:
        lr.restore(start)                                       # a warm start: continue from the saved learner
    rng = np.random.default_rng(seed + 7)
    buf = MEM.ReplayBuffer(200, K.get("replay_priority"))
    every_replay, batch, hindsight = K.get("replay_every"), K.get("replay_batch"), K.get("hindsight")
    curve, recent = [], []
    prev_block = None
    EV.emit("enc", "ready", f"{label}: {hidden or 'no'} hidden units, {lr.vec().size} learned numbers", edge="mem>enc")
    for k in range(episodes):
        _tick()
        w = World(rng.choice(list(families)), int(rng.integers(0, 10_000)), vocab)
        pol = lr.policy(True)
        before = lr.vec()
        ep = run_episode(w, pol)
        recent.append(ep["success"])
        if pol.records:
            rw = rewards(ep)[:len(pol.records)]
            adv = lr.update(pol.records, rw)
            moved = float(np.linalg.norm(lr.vec() - before))
            buf.add(pol.records, rw, MEM.surprise(pol.records))
            EV.emit("env", "episode", f"{w.family}: {ep['steps']} presses, {'finished' if ep['success'] else 'did not finish'}", ep["steps"], edge="soft>env")
            EV.emit("rew", "reward", f"return {sum(rw):+.2f}", sum(rw), edge="env>rew")
            EV.emit("crit", "advantage", f"mean advantage {adv:+.3f}", adv, edge="rew>crit")
            EV.emit("upd", "update", f"numbers moved by {moved:.4f}", moved, edge="crit>upd", total=float(np.linalg.norm(lr.vec())))
            EV.emit("actor", "weights", f"actor changed by {moved:.4f}", moved, edge="upd>actor")
        if hindsight and not ep["success"] and pol.records and getattr(w, "playing", None) and w.playing != w.target:
            recs = MEM.relabel(lr, pol.records, f"play the {w.playing} playlist")
            if recs:
                lr.update(recs, rewards({**ep, "success": True})[:len(recs)])
                EV.emit("hind", "relabel", f"a miss that played '{w.playing}' counted as a success for that", edge="hind>rew")
        if every_replay and (k + 1) % every_replay == 0 and len(buf):
            for recs, rw in buf.sample(batch, rng):
                lr.update(recs, rw)
            EV.emit("repl", "replay", f"replayed {min(batch, len(buf))} remembered episodes ({K.get('replay_priority')})", edge="repl>upd")
        if (k + 1) % every == 0:
            rate = round(float(np.mean(recent[-every:])), 3)
            curve.append((k + 1, rate))
            better = prev_block is not None and rate > prev_block + 0.005
            EV.emit("fit", "improved" if better else "block", f"{label}: success {rate:.0%} over the last {every}" + (f" (was {prev_block:.0%}): the weights improved" if better else ""), rate,
                    edge="upd>fit", improved=bool(better))
            prev_block = rate
    return lr, curve


def evaluate(make, n: int = 30, families=None) -> dict:
    from . import knobs as K
    families = families or K.families()
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
            from . import events as EV
            EV.emit("fit", "evaluated", f"{fam} with {vocab} words: {sum(e['success'] for e in eps)} of {n} apps solved", sum(e["success"] for e in eps) / n, edge="upd>fit")
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


def _saved_start() -> "dict | None":
    """The learner that is in use, if one was saved with its critic (older saves had only the actor and cannot be continued)."""
    try:
        d = json.loads(POLICY.read_text(encoding="utf-8"))
        return d if d.get("linear_state") and d.get("hidden_state") else None
    except (OSError, ValueError):
        return None


def practice(episodes: "int | None" = None, seed: "int | None" = None, n_eval: "int | None" = None, write: bool = True, with_ablation: bool = False, warm: "bool | None" = None) -> dict:
    from . import events as EV, knobs as K
    episodes = K.get("episodes") if episodes is None else episodes
    n_eval = K.get("eval_per_cell") if n_eval is None else n_eval
    seed = K.get("seed") if seed is None else seed
    warm = K.get("warm_start") if warm is None else warm
    t0 = time.time()
    start = _saved_start() if warm else None
    if start:
        seed = seed + int(start.get("version") or 0) + 1                  # a new run of pretend apps each session, not the same ones again
    n_fam = len(K.families())
    CONTROL.update(running=True, stop=False, phase="training the plain learner", done=0, total=2 * episodes + 4 * n_fam * 2 * n_eval)
    EV.clear()
    EV.emit("knobs", "session", f"session starts: {episodes} episodes, {n_eval} unseen apps per cell, " + ("warm start" if start else "from nothing"))
    try:
        return _practice(episodes, seed, n_eval, write, with_ablation, t0, start)
    except Stopped:
        EV.emit("gate", "stopped", "stopped: nothing was saved")
        return {"stopped": True, "done": CONTROL["done"], "total": CONTROL["total"]}
    finally:
        CONTROL.update(running=False, stop=False)


def _practice(episodes: int, seed: int, n_eval: int, write: bool, with_ablation: bool, t0: float, start: "dict | None" = None) -> dict:
    from . import demos as DM, events as EV, knobs as K, memory as MEM
    hidden = K.get("hidden_units")
    fams = K.families()
    live_note = None
    lin_start, mlp_start = (start or {}).get("linear_state"), (start or {}).get("hidden_state")
    epochs = K.get("memory_epochs")
    if epochs:
        data = MEM.live_dataset()
        live_note = {"steps": len(data), "tasks": len({d["task"] for d in data})}
        EV.emit("live", "memory", f"{live_note['steps']} steps of {live_note['tasks']} approved live tasks", live_note["steps"], edge="live>mem")
    lin, c_lin = train(episodes, 0, seed, families=fams, start=lin_start, label="plain learner")
    CONTROL["phase"] = f"training the one-hidden-layer learner ({hidden} units)"
    mlp, c_mlp = train(episodes, hidden, seed, families=fams, start=mlp_start, label="hidden-layer learner")
    if epochs and live_note and live_note["steps"]:
        for _ in range(epochs):
            p_lin, p_mlp = lin.imitate(data), mlp.imitate(data)
        EV.emit("mem", "imitated", f"imitated {live_note['steps']} approved live steps; it now gives the approved press {p_lin:.0%} (plain) and {p_mlp:.0%} (hidden)", p_lin, edge="mem>upd")
    CONTROL["phase"] = "measuring on layouts and words it has not seen"
    t_train = time.time() - t0
    table = {"random": evaluate(lambda: L.random_policy(5), n_eval, fams),
             "rule of thumb": evaluate(lambda: L.greedy_policy, n_eval, fams),
             "learned, linear": evaluate(lambda: lin.policy(False), n_eval, fams),
             "learned, one hidden layer": evaluate(lambda: mlp.policy(False), n_eval, fams)}
    demo = DM.agreement(lin)
    if demo["steps"]:
        EV.emit("demos", "agreement", f"the plain learner presses what your attested routines press on {demo['agree']} of {demo['steps']} steps", demo["rate"], edge="demos>gate")
    rep = {"at": time.time(), "episodes": episodes, "seed": seed, "eval_per_cell": n_eval, "train_seconds": round(t_train, 1),
           "curve": {"linear": c_lin, "hidden16": c_mlp}, "table": table, "layouts": fams, "hidden_units": hidden, "live_memory": live_note, "attested_agreement": demo,
           "methods": {"linear": "advantage actor-critic, linear scorer", "hidden16": f"advantage actor-critic, {hidden} tanh units"},
           "warm_from": (start or {}).get("version"), "knobs": {k: v for k, v in K.values().items() if k in ("episodes", "lr_actor", "lr_critic", "gamma", "entropy_beta", "hindsight", "replay_every", "step_cost", "win")},
           "means": {p: {v: round(float(np.mean([t[f][v]["success"] for f in t])), 3) for v in ("train", "held")} for p, t in table.items()},
           "caveat": "pretend apps written by the same hand that wrote the features; numbers show what the method can and cannot learn, not how it will do on a real app"}
    if with_ablation:
        rep["ablation"] = ablation(episodes, seed, n_eval)
    if write:
        from . import store
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        rep["saved"] = store.save(REPORT.parent, POLICY, rep, {"linear": lin.actor.dump(), "hidden16": mlp.actor.dump(), "linear_state": lin.dump(), "hidden_state": mlp.dump()})
        REPORT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        sv = rep["saved"] if isinstance(rep["saved"], dict) else {}
        EV.emit("ver", "saved", f"saved as version {sv.get('version', '?')}; " + ("now the one in use" if sv.get("adopted") else "kept, not better than the one in use"), sv.get("version"), edge="gate>ver")
        EV.emit("gate", "decided", "a new version replaces the one in use only if it is at least as good on words it never saw", edge="fit>gate")
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
