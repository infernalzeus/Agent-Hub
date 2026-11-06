"""The yard's memory: a replay buffer, hindsight relabelling, and the approved live tasks a session may learn from.

REPLAY BUFFER. Remembers recent practice episodes with how surprising each one was (how unsure the learner was at its choices). A replay draws some again, the
surprising ones more often ("uncertainty" mode; "uniform" draws any). Priority by uncertainty rather than by error follows the reports that error-based priority
favours noisy episodes.

HINDSIGHT. A practice task that failed but ended with some OTHER playlist playing is, for that other playlist, a success. `relabel` rebuilds each step as if the goal
had been that playlist (the controls stay the same, only the goal words in the features change) so the learner also learns from what it accidentally did right.

LIVE TASKS. While shadow is on, each live step's controls list is kept (shadow.py). `live_dataset` joins those steps to the task evidence and keeps only tasks you graded
RIGHT, or that Windows confirmed with a confidence of 0.9 or more, and never a task done by an attested routine. A session may imitate those steps (`Learner.imitate`).
"""
from __future__ import annotations

import json
import math

import numpy as np

from ..runtime import STATE


class ReplayBuffer:
    def __init__(self, size: int = 200, priority: str = "uncertainty"):
        self.items: "list[tuple[list, list, float]]" = []
        self.size, self.mode = size, priority

    def add(self, records: list, rewards: list, priority: float) -> None:
        self.items.append((records, rewards, float(priority)))
        if len(self.items) > self.size:
            self.items.pop(0)

    def __len__(self) -> int:
        return len(self.items)

    def sample(self, n: int, rng) -> "list[tuple[list, list]]":
        if not self.items:
            return []
        n = min(n, len(self.items))
        pri = np.array([p for _, _, p in self.items]) + 1e-6 if self.mode == "uncertainty" else np.ones(len(self.items))
        idx = rng.choice(len(self.items), size=n, replace=False, p=pri / pri.sum())
        return [(self.items[i][0], self.items[i][1]) for i in idx]


def surprise(records: list) -> float:
    """Mean normalised entropy of the learner's choice probabilities over an episode: 0 = always sure, 1 = guessing."""
    vals = []
    for r in records:
        p = np.asarray(r["p"], dtype=float)
        if len(p) > 1:
            vals.append(float(-(p * np.log(p + 1e-12)).sum() / math.log(len(p))))
    return float(np.mean(vals)) if vals else 0.0


def relabel(lr, records: list, goal: str) -> list:
    """The same episode, as if `goal` had been the goal. Needs each record's prompt."""
    from ..features import pc_control as PC
    from . import learner as L
    out = []
    for r in records:
        if not r.get("prompt"):
            continue
        o = L.parse(r["prompt"])
        o["goal"], o["goal_words"] = goal, PC.target_words(goal)
        acts, X = L.candidates(o, lr.letters)
        s, h = lr.actor.forward(X)
        out.append({"X": X, "h": h, "p": L.softmax(s), "a": r["a"], "z": L.critic_input(o), "prompt": r["prompt"]})
    return out


MEMORY_STEPS = STATE / "data" / "yard" / "memory_steps.jsonl"


def live_dataset() -> "list[dict]":
    """[{"prompt", "do", "role", "name", "task"}] for the steps of approved live tasks, oldest first. Attested routines never appear."""
    from . import evidence as EV
    try:
        steps = [json.loads(l) for l in MEMORY_STEPS.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    labels = EV._labels()
    approved = []
    for r in EV._rows():
        g = (labels.get(r["id"]) or {}).get("grade")
        if r.get("attested") or g in ("wrong", "skip") or r.get("way") != "agent":
            continue
        if g == "right" or (r.get("ok") and r.get("markers", {}).get("windows_confirms") and r.get("confidence", 0) >= 0.9):
            approved.append(r)
    from . import learner as L
    out = []
    for r in approved:
        lo, hi = r["at"] - r["seconds"] - 10, r["at"] + 5
        mine = [s for s in steps if lo <= s["at"] <= hi and str(s.get("goal", "")).casefold() == str(r["goal"])[:80].casefold()]
        for s in sorted(mine, key=lambda s: s["step"]):
            o = L.parse(s["prompt"])
            c = next((c for c in o["controls"] if c["id"] == (s.get("live") or {}).get("id")), None)
            do = (s.get("live") or {}).get("do")
            if do in ("click", "type") and c is None:
                continue
            out.append({"prompt": s["prompt"], "do": do, "role": c["role"] if c else None, "name": c["name"] if c else None, "task": r["id"]})
    return out
