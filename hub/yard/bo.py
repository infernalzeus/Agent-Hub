"""Bayesian optimisation: a search for a few numbers when every try is slow, noisy and you can afford only a few.

It keeps a model of the score (a Gaussian process with a smooth kernel) fitted to the tries so far, and picks the next try where the model says an improvement is most
likely and largest (expected improvement):

    k(x, x') = exp(-|x - x'|^2 / (2 l^2))                         the kernel: nearby settings score alike, l is the smoothness
    mu(x), s(x)  from the process fitted to the tries (noise variance added on the diagonal)
    EI(x) = (mu - best) Phi(z) + s phi(z),  z = (mu - best) / s    expected improvement over the best score so far

Numbers are searched on a 0..1 scale inside `space`. With two or three numbers and a small budget it usually beats random search and is the method to compare with CMA-ES
(which is steadier under noise); the KNOBS tab sets the number of random starts, the smoothness and the noise.
"""
from __future__ import annotations

import math

import numpy as np


def _k(A, B, length):
    d = ((A[:, None, :] - B[None, :, :]) ** 2).sum(-1)
    return np.exp(-d / (2 * length * length))


def _phi(z):
    return np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _Phi(z):
    return 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))


def bayes_opt(objective, space: "dict[str, tuple[float, float]]", tries: int = 30, seed: int = 0, init: "int | None" = None, length: "float | None" = None, noise: "float | None" = None) -> dict:
    from . import knobs as K
    init = K.get("bo_init") if init is None else init
    length = K.get("bo_length") if length is None else length
    noise = K.get("bo_noise") if noise is None else noise
    names = list(space)
    n = len(names)
    lo = np.array([space[k][0] for k in names], dtype=float)
    hi = np.array([space[k][1] for k in names], dtype=float)
    rng = np.random.default_rng(seed)

    def decode(u):
        return {k: float(lo[i] + (hi[i] - lo[i]) * u[i]) for i, k in enumerate(names)}

    X, y = [], []
    best = {"score": float("-inf"), "candidate": None, "tries": 0}

    def tryit(u):
        cand = decode(u)
        s = float(objective(cand))
        X.append(u)
        y.append(s)
        best["tries"] += 1
        if s > best["score"]:
            best.update(score=s, candidate=cand)

    for _ in range(min(init, tries)):
        tryit(rng.random(n))
    while best["tries"] < tries:
        A = np.array(X)
        yy = np.array(y)
        mean, sd = yy.mean(), yy.std() or 1.0
        z = (yy - mean) / sd
        Kmat = _k(A, A, length) + (noise + 1e-8) * np.eye(len(A))
        Kinv = np.linalg.inv(Kmat)
        cand = rng.random((400, n))
        Ks = _k(cand, A, length)
        mu = Ks @ Kinv @ z
        var = np.maximum(1e-12, 1.0 - np.einsum("ij,jk,ik->i", Ks, Kinv, Ks))
        s = np.sqrt(var)
        zbest = z.max()
        zz = (mu - zbest) / s
        ei = (mu - zbest) * _Phi(zz) + s * _phi(zz)
        tryit(cand[int(np.argmax(ei))])
    return best
