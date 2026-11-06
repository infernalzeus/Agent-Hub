"""A support check: has the learner seen anything like this? If not, it should defer to the model instead of guessing (the idea behind conservative offline RL).

`Support.fit(matrix)` remembers the rows it trained on. `Support.covered(x)` is True when the nearest training row is close enough (cosine similarity at or
above `threshold`). A learned control head would be asked about a screen only where this says yes; elsewhere the language model decides, as it does today.
Not wired to anything live.
"""
from __future__ import annotations

import numpy as np


class Support:
    def __init__(self, threshold: "float | None" = None):
        from . import knobs as K
        self.threshold = K.get("support_threshold") if threshold is None else threshold
        self.rows = np.zeros((0, 0))

    def fit(self, matrix) -> "Support":
        m = np.asarray(matrix, dtype=float)
        n = np.linalg.norm(m, axis=1, keepdims=True)
        self.rows = m / np.where(n == 0, 1.0, n)
        return self

    def nearest(self, x) -> float:
        if not len(self.rows):
            return 0.0
        v = np.asarray(x, dtype=float)
        nv = np.linalg.norm(v)
        return float((self.rows @ (v / nv)).max()) if nv else 0.0

    def covered(self, x) -> bool:
        return self.nearest(x) >= self.threshold

    def coverage(self, matrix) -> float:
        m = np.asarray(matrix, dtype=float)
        return float(np.mean([self.covered(r) for r in m])) if len(m) else 0.0


def rerank(model_scores: "dict[str, float]", afford: "dict[str, float]", covered: "dict[str, bool] | None" = None) -> "tuple[str, dict]":
    """Re-rank, do not replace (the SayCan idea). `model_scores` is how useful the language model thinks each control is (0..1); `afford` is how likely the learned head
    thinks pressing it works here (0..1). Where the learned head has seen nothing like this (`covered` False) its say is ignored and the model's order stands.
    Returns the pick and the combined scores: score(a) = model(a) x afford(a)."""
    out = {}
    for a, m in model_scores.items():
        use = covered is None or covered.get(a, True)
        out[a] = m * (afford.get(a, 0.5) if use else 1.0)
    return max(out, key=lambda a: (out[a], model_scores[a], a)), out
