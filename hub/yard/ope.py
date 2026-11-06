"""Off-policy evaluation: score a choice rule you have NOT run on choices that were already logged, without repeating any test.

A logged row says: in this situation the Hub chose `chosen` with probability `p`, and it turned out `ok`. A candidate rule would have chosen differently
on some rows; for those rows the log says nothing, so they are not counted. For the rows where the candidate would have made the same choice, each
result is weighted by how likely the candidate was to choose it divided by how likely the logger was to (inverse propensity weighting):

    w_i = min(cap, pi(chosen_i | x_i) / p_i)          the weight, capped so one odd row cannot decide everything
    V   = sum_i w_i r_i / sum_i w_i                   the SELF-NORMALISED estimate (SNIPS): stays between 0 and 1
    ESS = (sum w)^2 / sum w^2                         how many rows the estimate is really worth; small means do not trust it

The logger today is a fixed rule, so p = 1 and only agreeing rows count; that is honest, and it is why the estimate is usually "not enough rows".
Doubly robust estimators are left out on purpose: with logs this small they can be noisier than the plain estimate (Wang, Agarwal and Dudik, 2017).
"""
from __future__ import annotations

import random

CAP = 10.0          # the default; the KNOBS tab changes it


def weights(rows: "list[dict]", pi) -> "list[float]":
    """pi(row) -> the chance the candidate would have made the logged choice (1.0 or 0.0 for a deterministic rule)."""
    from . import knobs as K
    cap = K.get("ope_cap")
    out = []
    for r in rows:
        p = r.get("p")
        p = float(p) if isinstance(p, (int, float)) and p > 0 else 1.0
        out.append(min(cap, max(0.0, float(pi(r))) / p))
    return out


def snips(rows: "list[dict]", pi, seed: int = 0, boot: "int | None" = None) -> dict:
    """{"estimate", "ess", "used", "n", "ci": (low, high) or None}. Only rows with a result (ok True or False) are used."""
    from . import knobs as K
    boot = K.get("ope_boot") if boot is None else boot
    rows = [r for r in rows if isinstance(r.get("ok"), bool)]
    w = weights(rows, pi)
    sw = sum(w)
    used = sum(1 for x in w if x > 0)
    if sw <= 0:
        return {"estimate": None, "ess": 0.0, "used": 0, "n": len(rows), "ci": None}
    est = sum(x * (1.0 if r["ok"] else 0.0) for x, r in zip(w, rows)) / sw
    ess = sw * sw / sum(x * x for x in w)
    ci = None
    if used >= 5:
        rng = random.Random(seed)
        idx = [i for i, x in enumerate(w) if x > 0]
        sims = []
        for _ in range(boot):
            pick = [idx[rng.randrange(len(idx))] for _ in idx]
            d = sum(w[i] for i in pick)
            sims.append(sum(w[i] * (1.0 if rows[i]["ok"] else 0.0) for i in pick) / d)
        sims.sort()
        ci = (round(sims[int(0.025 * len(sims))], 3), round(sims[int(0.975 * len(sims)) - 1], 3))
    return {"estimate": round(est, 4), "ess": round(ess, 2), "used": used, "n": len(rows), "ci": ci}
