"""Calibration: turn "how sure it says it is" into "how often it is right", fitted to what you marked. Pure Python, no numpy.

    platt_fit(pairs)       p_cal = sigmoid(a * logit(p) + b), a and b by regularised log-loss on (p, right) pairs
    ece(pairs)             expected calibration error: the average gap between what it says and how often it is right, by confidence band
    fit_marker_weights()   a logistic regression of "you said right" on the markers of a PC task (see evidence.py), with the same cross-fold Brier score as
                           the hand-set formula, so a fitted version is adopted only if it is clearly better

Nothing here changes a number the Hub uses. It proposes; the plan's gate and your yes decide.
"""
from __future__ import annotations

import math


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _logit(p: float) -> float:
    p = min(1 - 1e-4, max(1e-4, p))
    return math.log(p / (1 - p))


def platt_fit(pairs: "list[tuple[float, float]]", l2: float = 0.1, iters: int = 400, lr: float = 0.3) -> "tuple[float, float]":
    """pairs of (stated confidence, 1.0 if it was right else 0.0). Returns (a, b); (1, 0) means already calibrated."""
    a, b = 1.0, 0.0
    n = max(1, len(pairs))
    for _ in range(iters):
        ga = l2 * (a - 1.0)
        gb = 0.0
        for p, y in pairs:
            z = _logit(p)
            e = _sig(a * z + b) - y
            ga += e * z / n
            gb += e / n
        a -= lr * ga
        b -= lr * gb
    return a, b


def platt_apply(a: float, b: float, p: float) -> float:
    return _sig(a * _logit(p) + b)


def brier(pairs: "list[tuple[float, float]]") -> "float | None":
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None


def ece(pairs: "list[tuple[float, float]]", bins: int = 5) -> "float | None":
    if not pairs:
        return None
    tot = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        inb = [(p, y) for p, y in pairs if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        if inb:
            tot += len(inb) / len(pairs) * abs(sum(p for p, _ in inb) / len(inb) - sum(y for _, y in inb) / len(inb))
    return tot


def _fit_logistic(X: "list[list[float]]", y: "list[float]", l2: float = 0.5, iters: int = 300, lr: float = 0.2) -> "list[float]":
    d = len(X[0]) + 1
    w = [0.0] * d
    n = len(X)
    for _ in range(iters):
        g = [l2 * w[j] if j else 0.0 for j in range(d)]
        for xi, yi in zip(X, y):
            e = _sig(w[0] + sum(w[j + 1] * xi[j] for j in range(d - 1))) - yi
            g[0] += e / n
            for j in range(d - 1):
                g[j + 1] += e * xi[j] / n
        w = [wj - lr * gj for wj, gj in zip(w, g)]
    return w


def fit_marker_weights(graded: "list[tuple[dict, float]]", keys: "list[str]", current, folds: int = 5, min_rows: int = 30) -> dict:
    """graded: [(markers, 1.0 if you said right else 0.0)]. `current(markers) -> p` is the hand-set formula. Compares the two by cross-fold Brier."""
    if len(graded) < min_rows:
        return {"ready": False, "needs": min_rows, "have": len(graded)}
    X = [[1.0 if m.get(k) else 0.0 for k in keys] for m, _ in graded]
    y = [v for _, v in graded]
    idx = list(range(len(graded)))
    fitted, base = [], []
    for f in range(folds):
        test = [i for i in idx if i % folds == f]
        train = [i for i in idx if i % folds != f]
        if not test or not train:
            continue
        w = _fit_logistic([X[i] for i in train], [y[i] for i in train])
        for i in test:
            fitted.append((_sig(w[0] + sum(w[j + 1] * X[i][j] for j in range(len(keys)))), y[i]))
            base.append((current(graded[i][0]), y[i]))
    w = _fit_logistic(X, y)
    bf, bb = brier(fitted), brier(base)
    return {"ready": True, "rows": len(graded), "weights": {"bias": round(w[0], 3), **{k: round(w[j + 1], 3) for j, k in enumerate(keys)}},
            "brier_fitted": round(bf, 4), "brier_current": round(bb, 4), "better": bf < bb - 0.01}
