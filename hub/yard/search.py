"""Searches for a set of numbers: random and grid are the baselines, CMA-ES (cma.py) is the real search and has to beat them.

`objective(candidate: dict) -> float` is higher-is-better and must be repeatable (same input, same score). `space` is {name: (low, high)}.
A learner earns its place only if it finds a better score than `random_search` and `grid_search` with the same number of tries.
"""
from __future__ import annotations

import itertools
import random


def random_search(objective, space: "dict[str, tuple[float, float]]", tries: int = 200, seed: int = 0) -> dict:
    rng = random.Random(seed)
    best = {"score": float("-inf"), "candidate": None, "tries": 0}
    for _ in range(tries):
        cand = {k: rng.uniform(lo, hi) for k, (lo, hi) in space.items()}
        s = objective(cand)
        best["tries"] += 1
        if s > best["score"]:
            best.update(score=s, candidate=cand)
    return best


def grid_search(objective, space: "dict[str, tuple[float, float]]", points: int = 4) -> dict:
    """`points` evenly spaced values per number: points ** len(space) tries, so keep both small."""
    axes = {k: [lo + (hi - lo) * i / max(points - 1, 1) for i in range(points)] for k, (lo, hi) in space.items()}
    best = {"score": float("-inf"), "candidate": None, "tries": 0}
    for combo in itertools.product(*axes.values()):
        cand = dict(zip(axes, combo))
        s = objective(cand)
        best["tries"] += 1
        if s > best["score"]:
            best.update(score=s, candidate=cand)
    return best


def cma_es(objective, space: "dict[str, tuple[float, float]]", tries: int = 200, seed: int = 0, **kw) -> dict:
    """CMA-ES (see cma.py). Built, but not used on any real number yet: it needs labelled hand traces and a replay score first (hub/yard/tunables.py)."""
    from .cma import cma_es as _cma
    return _cma(objective, space, tries=tries, seed=seed, **kw)
