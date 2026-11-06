"""Weight-space tools for the Hub's own small learners: combine, nudge, compare and undo saved versions by doing arithmetic on their numbers.

A learner's saved file is a dict of plain lists (see `learner.Actor.dump`): {"hidden": 0, "w": [...]} or {"hidden": H, "W1": [[...]], "b1": [...], "w2": [...]}.
Because it is only numbers, these operations work on any such file and need no training:

    average([a, b, c])        a "soup": the mean of several versions. Averaging versions trained from the same start often beats each one alone.
    greedy_soup(versions, f)  add versions one by one, best first, and keep each only if the score `f` on held-out rows does not fall.
    ema(old, new, alpha)      old*(1-alpha) + new*alpha: a smoothed learner that does not jump on one bad session.
    delta(a, b)               b - a, the "task vector": what one stretch of learning changed.
    apply(base, d, scale)     base + scale*d: add (or, with a negative scale, take away) what a stretch of learning changed.
    distance(a, b)            how far apart two versions are (Euclidean over every number).
    clip_delta(d, max_norm)   shrink a change that is too large, so one update cannot move the learner far.

The same ideas carry to a fine-tuned adapter of a language model (task arithmetic, model soups, merging): the plan keeps such adapters as SEPARATE files that
can be swapped or removed, because merging them into one set of numbers can make them interfere. Nothing here touches the live Hub.
"""
from __future__ import annotations

import numpy as np

_KEYS = ("w", "W1", "b1", "w2")


def _arrays(d: dict) -> "dict[str, np.ndarray]":
    return {k: np.asarray(d[k], dtype=float) for k in _KEYS if k in d}


def _same(a: dict, b: dict) -> None:
    if a.get("hidden") != b.get("hidden") or {k: np.shape(v) for k, v in _arrays(a).items()} != {k: np.shape(v) for k, v in _arrays(b).items()}:
        raise ValueError("these two learners do not have the same shape")


def _build(like: dict, arrays: "dict[str, np.ndarray]") -> dict:
    return {"hidden": like.get("hidden", 0), **{k: v.tolist() for k, v in arrays.items()}}


def average(dumps: "list[dict]", weights: "list[float] | None" = None) -> dict:
    if not dumps:
        raise ValueError("nothing to average")
    for d in dumps[1:]:
        _same(dumps[0], d)
    w = np.asarray(weights if weights is not None else [1.0] * len(dumps), dtype=float)
    w = w / w.sum()
    arrs = [_arrays(d) for d in dumps]
    return _build(dumps[0], {k: sum(wi * a[k] for wi, a in zip(w, arrs)) for k in arrs[0]})


def ema(old: dict, new: dict, alpha: "float | None" = None) -> dict:
    if alpha is None:
        from . import knobs as K
        alpha = K.get("ema_alpha")
    _same(old, new)
    a, b = _arrays(old), _arrays(new)
    return _build(old, {k: (1 - alpha) * a[k] + alpha * b[k] for k in a})


def delta(a: dict, b: dict) -> dict:
    _same(a, b)
    x, y = _arrays(a), _arrays(b)
    return _build(a, {k: y[k] - x[k] for k in x})


def apply(base: dict, d: dict, scale: float = 1.0) -> dict:
    _same(base, d)
    x, y = _arrays(base), _arrays(d)
    return _build(base, {k: x[k] + scale * y[k] for k in x})


def norm(d: dict) -> float:
    return float(np.sqrt(sum(float((a * a).sum()) for a in _arrays(d).values())))


def distance(a: dict, b: dict) -> float:
    return norm(delta(a, b))


def clip_delta(d: dict, max_norm: float) -> dict:
    n = norm(d)
    if n <= max_norm or n == 0:
        return d
    s = max_norm / n
    return _build(d, {k: v * s for k, v in _arrays(d).items()})


def greedy_soup(versions: "list[dict]", score) -> dict:
    """`score(dump) -> float` on rows the learner never trained on. Versions are tried best first; one joins the soup only if the soup's score does not drop."""
    if not versions:
        raise ValueError("nothing to soup")
    order = sorted(versions, key=score, reverse=True)
    chosen = [order[0]]
    best = score(order[0])
    for v in order[1:]:
        trial = average(chosen + [v])
        s = score(trial)
        if s >= best:
            chosen.append(v)
            best = s
    return {"soup": average(chosen), "used": len(chosen), "of": len(versions), "score": best}
