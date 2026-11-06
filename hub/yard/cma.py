"""CMA-ES (covariance matrix adaptation evolution strategy): a search for the best set of a few continuous numbers when each try is noisy and costly.

Each round it draws `lam` candidate sets from a Gaussian around a mean m (shape C, overall step sigma), scores them, keeps the best half, and moves
m towards them, stretches C along the directions that worked, and grows or shrinks sigma depending on whether the steps agree:

    x_k = m + sigma * B D z_k,  z_k ~ N(0, I)                    k = 1..lam
    m   <- sum_{i <= mu} w_i x_{i:lam}                           the best mu, weighted
    C   <- (1 - c1 - cmu) C + c1 p_c p_c^T + cmu sum w_i y_i y_i^T,  y_i = (x_i - m_old) / sigma
    sigma <- sigma * exp((c_sigma / d_sigma) (|p_sigma| / E|N(0,I)| - 1))

It is the plain version (Hansen's tutorial). Numbers are searched on a 0..1 scale inside `space` bounds, so every number is treated alike. The objective is
higher-is-better; with noise, pass `repeat` to average a few evaluations per candidate. It has to beat `search.random_search` with the same number of tries
before it is used on anything.
"""
from __future__ import annotations

import math

import numpy as np


def cma_es(objective, space: "dict[str, tuple[float, float]]", tries: int = 200, seed: int = 0, sigma0: "float | None" = None, repeat: "int | None" = None) -> dict:
    from . import knobs as K
    sigma0 = K.get("cma_sigma0") if sigma0 is None else sigma0
    repeat = K.get("cma_repeat") if repeat is None else repeat
    names = list(space)
    n = len(names)
    lo = np.array([space[k][0] for k in names], dtype=float)
    hi = np.array([space[k][1] for k in names], dtype=float)
    rng = np.random.default_rng(seed)

    def decode(u):
        return {k: float(lo[i] + (hi[i] - lo[i]) * min(1.0, max(0.0, u[i]))) for i, k in enumerate(names)}

    lam = 4 + int(3 * math.log(n))
    mu = lam // 2
    w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    w /= w.sum()
    mueff = 1.0 / float((w ** 2).sum())
    cc = (4 + mueff / n) / (n + 4 + 2 * mueff / n)
    cs = (mueff + 2) / (n + mueff + 5)
    c1 = 2 / ((n + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0.0, math.sqrt((mueff - 1) / (n + 1)) - 1) + cs
    chi = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
    m = np.full(n, 0.5)
    sigma = sigma0
    C = np.eye(n)
    pc = np.zeros(n)
    ps = np.zeros(n)
    best = {"score": float("-inf"), "candidate": None, "tries": 0}
    gen = 0
    while best["tries"] < tries:
        vals, B = np.linalg.eigh(C)
        D = np.sqrt(np.maximum(vals, 1e-20))
        Z = rng.standard_normal((lam, n))
        Y = Z * D @ B.T
        X = m + sigma * Y
        scores = []
        for x in X:
            if best["tries"] >= tries:
                break
            cand = decode(x)
            s = float(np.mean([objective(cand) for _ in range(repeat)]))
            best["tries"] += 1
            scores.append(s)
            if s > best["score"]:
                best.update(score=s, candidate=cand)
        if len(scores) < lam:
            break
        order = np.argsort(scores)[::-1][:mu]
        yw = (w[:, None] * Y[order]).sum(axis=0)
        m = m + sigma * yw
        invsqrt = B @ np.diag(1 / D) @ B.T
        ps = (1 - cs) * ps + math.sqrt(cs * (2 - cs) * mueff) * (invsqrt @ yw)
        gen += 1
        hsig = np.linalg.norm(ps) / math.sqrt(1 - (1 - cs) ** (2 * gen)) / chi < 1.4 + 2 / (n + 1)
        pc = (1 - cc) * pc + (math.sqrt(cc * (2 - cc) * mueff) * yw if hsig else 0.0)
        C = (1 - c1 - cmu) * C + c1 * np.outer(pc, pc) + cmu * sum(w[i] * np.outer(Y[o], Y[o]) for i, o in enumerate(order))
        sigma *= math.exp((cs / damps) * (np.linalg.norm(ps) / chi - 1))
        sigma = min(sigma, 1.0)
    return best
