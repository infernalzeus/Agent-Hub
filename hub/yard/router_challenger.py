"""A challenger for the router that learns from EVERY graded request, not only the corrected ones: nearest neighbours over letter-triples.

Each graded request is an example: the sentence and the bin that was right for it (the bin it chose if you said RIGHT, the bin you named if you said WRONG
and gave one). To predict a new sentence, count the bins of its k most similar graded sentences, weighted by similarity. The similarity is cosine over counts
of three-letter pieces, so "open outlook" and "open outlook please" are close and "what is the weather" is far, with no model and no GPU.

`loo_accuracy()` is the fair test: leave each graded sentence out, predict it from the rest, count how often it is right. It is compared with how often the
current rules-plus-tev answer was right on the same sentences. It is a challenger measured on the log; it changes nothing live.

This is not the planned fine-tune of tev. That is a training run (a loss minimised over all graded requests, judged on held-out ones) and needs your go-ahead
because it would use the GPU. This is its cheap yardstick: a fine-tune is only worth doing if it beats this.
"""
from __future__ import annotations

import math
import re
from collections import Counter


def _grams(text: str) -> Counter:
    s = "  " + " ".join(re.findall(r"[a-z0-9']+", (text or "").casefold())) + "  "
    return Counter(s[i:i + 3] for i in range(len(s) - 2))


def _cos(a: Counter, b: Counter) -> float:
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class KNN:
    def __init__(self, k: "int | None" = None):
        from . import knobs as K
        self.k = K.get("knn_k") if k is None else k
        self.items: "list[tuple[Counter, str]]" = []

    def fit(self, examples: "list[tuple[str, str]]") -> "KNN":
        self.items = [(_grams(t), label) for t, label in examples]
        return self

    def predict(self, text: str, skip: "int | None" = None) -> "tuple[str | None, float]":
        g = _grams(text)
        sims = sorted(((_cos(g, x), lab) for i, (x, lab) in enumerate(self.items) if i != skip), reverse=True)[:self.k]
        votes: "dict[str, float]" = {}
        for s, lab in sims:
            votes[lab] = votes.get(lab, 0.0) + s
        if not votes or sum(votes.values()) == 0:
            return None, 0.0
        best = max(votes, key=lambda b: (votes[b], b))
        return best, votes[best] / sum(votes.values())


def examples() -> "list[dict]":
    """Graded requests after the fresh start: {"text", "label", "rules_right"}. Skipped and deleted ones are not used."""
    from ..features import binning as BIN
    from . import settings as YS
    rows = BIN._rows()
    since = YS.fresh_since()
    verdicts: "dict[float, dict]" = {}
    hidden = set()
    for r in rows:
        if r.get("kind") == "verdict":
            if r.get("grade") in ("skip", "delete"):
                hidden.add(r.get("of"))
            elif isinstance(r.get("ok"), bool):
                verdicts[r.get("of")] = r
    out = []
    for r in rows:
        at = r.get("at")
        if r.get("kind") in ("outcome", "verdict") or not at or at in hidden or not r.get("text") or (since and at < since):
            continue
        v = verdicts.get(at)
        if not v:
            continue
        label = r.get("bin") if v["ok"] else v.get("correct")
        if label:
            out.append({"text": str(r["text"]), "label": str(label), "rules_right": bool(v["ok"])})
    return out


def loo_accuracy(ex: "list[dict]", k: "int | None" = None) -> dict:
    n = len(ex)
    if n < 5:
        return {"n": n, "ready": False, "needs": 5}
    knn = KNN(k).fit([(e["text"], e["label"]) for e in ex])
    right = sum(1 for i, e in enumerate(ex) if knn.predict(e["text"], skip=i)[0] == e["label"])
    cur = sum(1 for e in ex if e["rules_right"])
    return {"n": n, "ready": True, "k": knn.k, "knn": round(right / n, 3), "current": round(cur / n, 3), "better": right > cur}
