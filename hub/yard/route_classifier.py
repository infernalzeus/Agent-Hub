"""A small router classifier trained by gradient descent on EVERY graded request: the cheap, processor-only cousin of the planned tev fine-tune.

Each sentence becomes a vector of hashed letter-triple counts (the same pieces as the nearest-neighbour yardstick). A softmax regression is fitted by minimising

    L(W) = -(1/n) sum_i log softmax(W x_i)[y_i] + lambda |W|^2        cross-entropy over all graded requests, plus a small penalty on the size of W

by plain gradient descent, the same objective a fine-tune of a language model minimises, only with a few thousand numbers instead of billions. It is judged by leaving each
graded request out and predicting it from a model trained on the rest (k-fold here), against the current rules and tev and against nearest neighbours. Nothing is coded
by hand about which words mean which bin: the optimiser finds it from your taps. No GPU, no model server.
"""
from __future__ import annotations

import zlib

import numpy as np

DIM = 512


def featurize(text: str) -> np.ndarray:
    import re
    s = "  " + " ".join(re.findall(r"[a-z0-9']+", (text or "").casefold())) + "  "
    v = np.zeros(DIM)
    for i in range(len(s) - 2):
        v[zlib.crc32(s[i:i + 3].encode()) % DIM] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v


class Softmax:
    def __init__(self, epochs: "int | None" = None, l2: "float | None" = None, lr: "float | None" = None):
        from . import knobs as K
        self.epochs = K.get("clf_epochs") if epochs is None else epochs
        self.l2 = K.get("clf_l2") if l2 is None else l2
        self.lr = K.get("clf_lr") if lr is None else lr
        self.labels: "list[str]" = []
        self.W = np.zeros((0, DIM))

    def fit(self, texts: "list[str]", labels: "list[str]") -> "Softmax":
        self.labels = sorted(set(labels))
        X = np.stack([featurize(t) for t in texts])
        y = np.array([self.labels.index(l) for l in labels])
        W = np.zeros((len(self.labels), DIM))
        Y = np.eye(len(self.labels))[y]
        for _ in range(self.epochs):
            Z = X @ W.T
            Z -= Z.max(1, keepdims=True)
            P = np.exp(Z)
            P /= P.sum(1, keepdims=True)
            W -= self.lr * (((P - Y).T @ X) / len(X) + self.l2 * W)
        self.W = W
        return self

    def predict(self, text: str) -> "tuple[str, float]":
        z = self.W @ featurize(text)
        p = np.exp(z - z.max())
        p /= p.sum()
        i = int(p.argmax())
        return self.labels[i], float(p[i])


def kfold_accuracy(ex: "list[dict]", folds: int = 5) -> dict:
    n = len(ex)
    if n < 10 or len({e["label"] for e in ex}) < 2:
        return {"n": n, "ready": False, "needs": 10}
    right = 0
    for f in range(folds):
        test = [i for i in range(n) if i % folds == f]
        train = [i for i in range(n) if i % folds != f]
        if not test or len({ex[i]["label"] for i in train}) < 2:
            continue
        m = Softmax().fit([ex[i]["text"] for i in train], [ex[i]["label"] for i in train])
        right += sum(1 for i in test if m.predict(ex[i]["text"])[0] == ex[i]["label"])
    return {"n": n, "ready": True, "classifier": round(right / n, 3), "current": round(sum(1 for e in ex if e["rules_right"]) / n, 3)}
