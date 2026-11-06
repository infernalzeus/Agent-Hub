"""Learners you can swap: one small interface, a registry, and a fair way to compare them on the choices already logged.

WHY. Better learning methods appear all the time. If each one is a class that follows the same few methods, replacing the learner behind a head (the model
choice, the way a PC task is done) is one name in a settings file, not a rewrite; and a new one can be tried against the current one on the same logged
rows before it is allowed anywhere near a live choice (see `gate.py`). Nothing here is called by the live Hub.

THE INTERFACE. A learner for a "which option" head has:
    name, description, needs                  what it is and what it needs (numpy, ...)
    fit(rows)                                 learn from labelled rows (oldest first); starting from nothing each time is fine at this size
    scores(ctx, options) -> {option: float}   how good it thinks each option is here
    choose(ctx, options) -> (option, p)       its pick and the chance it had of making that pick
    dump() / load(d)                          the numbers it learned, as plain JSON: this is the "model file" and it is versioned like the yard's

THE LEARNERS.
    tally      the mean of wins and losses per option (with one pretend win and loss), the one built since R3. Deterministic.
    thompson   draws a plausible win rate for each option from Beta(wins + 1, losses + 1) and takes the best draw; tries every option `min_n` times first
               so one option cannot take all the traffic when feedback is sparse.
    linucb     one ridge regression per option over a few hashed context numbers (app, brief size, ...), plus an optimism bonus that shrinks as evidence
               grows. Needs numpy. Useful once the choice depends on the situation, not just the option.
"""
from __future__ import annotations

import json
import math
import random
import zlib

from ..runtime import STATE
from . import ope

CONFIG = STATE / "data" / "yard" / "learners.json"
HEADS = ("model", "rung")


def _labelled(rows: "list[dict]", kind: str) -> "list[dict]":
    return [r for r in rows if r.get("kind") == kind and isinstance(r.get("ok"), bool)]


class Learner:
    name = "base"
    description = ""
    needs = ""

    def fit(self, rows: "list[dict]") -> "Learner":
        return self

    def scores(self, ctx: dict, options: "list[str]") -> "dict[str, float]":
        return {o: 0.5 for o in options}

    def choose(self, ctx: dict, options: "list[str]") -> "tuple[str, float]":
        s = self.scores(ctx, options)
        best = max(options, key=lambda o: (s[o], o))
        return best, 1.0

    def dump(self) -> dict:
        return {"name": self.name}

    @classmethod
    def available(cls) -> bool:
        return True


class Tally(Learner):
    name = "tally"
    description = "wins and losses per option, with one pretend win and loss; deterministic"

    def __init__(self, min_n: "int | None" = None):
        from . import knobs as K
        self.min_n = K.get("min_n") if min_n is None else min_n
        self.table: "dict[str, list[int]]" = {}

    def fit(self, rows):
        self.table = {}
        for r in rows:
            c = self.table.setdefault(str(r["chosen"]), [0, 0])
            c[0 if r["ok"] else 1] += 1
        return self

    def scores(self, ctx, options):
        out = {}
        for o in options:
            w, l = self.table.get(o, [0, 0])
            out[o] = (w + 1) / (w + l + 2) if w + l >= self.min_n else 0.5
        return out

    def dump(self):
        return {"name": self.name, "table": self.table, "min_n": self.min_n}


class Thompson(Learner):
    name = "thompson"
    description = "draws a plausible win rate per option and takes the best; tries each option a few times first"

    def __init__(self, min_n: "int | None" = None, seed: int = 0, draws: "int | None" = None):
        from . import knobs as K
        self.min_n, self.seed, self.draws = (K.get("min_n") if min_n is None else min_n), seed, (K.get("thompson_draws") if draws is None else draws)
        self.table: "dict[str, list[int]]" = {}

    def fit(self, rows):
        self.table = {}
        for r in rows:
            c = self.table.setdefault(str(r["chosen"]), [0, 0])
            c[0 if r["ok"] else 1] += 1
        return self

    def _tries(self, o):
        return sum(self.table.get(o, [0, 0]))

    def scores(self, ctx, options):
        out = {}
        for o in options:
            w, l = self.table.get(o, [0, 0])
            out[o] = (w + 1) / (w + l + 2)
        return out

    def choose(self, ctx, options):
        fresh = [o for o in options if self._tries(o) < self.min_n]
        if fresh:                                                    # warm-up: the least tried first, so no option is starved
            pick = min(fresh, key=lambda o: (self._tries(o), o))
            return pick, 1.0 / len(fresh)
        rng = random.Random(self.seed)
        wins = {o: 0 for o in options}
        for _ in range(self.draws):
            draw = {o: rng.betavariate(self.table.get(o, [0, 0])[0] + 1, self.table.get(o, [0, 0])[1] + 1) for o in options}
            wins[max(options, key=lambda o: (draw[o], o))] += 1
        pick = max(options, key=lambda o: (wins[o], o))
        return pick, max(wins[pick], 1) / self.draws

    def dump(self):
        return {"name": self.name, "table": self.table, "min_n": self.min_n}


class LinUCB(Learner):
    name = "linucb"
    description = "a ridge regression per option over a few hashed context numbers, plus an optimism bonus that shrinks with evidence"
    needs = "numpy"
    DIM = 8

    def __init__(self, alpha: "float | None" = None, lam: "float | None" = None):
        from . import knobs as K
        self.alpha, self.lam = (K.get("linucb_alpha") if alpha is None else alpha), (K.get("linucb_lambda") if lam is None else lam)
        self.A: dict = {}
        self.b: dict = {}

    @classmethod
    def available(cls) -> bool:
        try:
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    def _x(self, ctx: dict):
        import numpy as np
        x = np.zeros(self.DIM)
        x[0] = 1.0                                                  # a bias term
        for k, v in sorted((ctx or {}).items()):
            if isinstance(v, bool):
                x[1 + zlib.crc32(str(k).encode()) % (self.DIM - 1)] += 1.0 if v else -1.0
            elif isinstance(v, (int, float)):
                x[1 + zlib.crc32(str(k).encode()) % (self.DIM - 1)] += math.tanh(float(v) / 10.0)
            else:
                x[1 + zlib.crc32(f"{k}={v}".encode()) % (self.DIM - 1)] += 1.0
        return x

    def fit(self, rows):
        import numpy as np
        self.A, self.b = {}, {}
        for r in rows:
            o = str(r["chosen"])
            x = self._x(r.get("ctx") or {})
            A = self.A.setdefault(o, self.lam * np.eye(self.DIM))
            self.A[o] = A + np.outer(x, x)
            self.b[o] = self.b.get(o, np.zeros(self.DIM)) + (1.0 if r["ok"] else 0.0) * x
        return self

    def scores(self, ctx, options):
        import numpy as np
        x = self._x(ctx)
        out = {}
        for o in options:
            A = self.A.get(o, self.lam * np.eye(self.DIM))
            b = self.b.get(o, np.zeros(self.DIM))
            inv = np.linalg.inv(A)
            out[o] = float(inv @ b @ x + self.alpha * math.sqrt(max(0.0, float(x @ inv @ x))))
        return out

    def dump(self):
        return {"name": self.name, "alpha": self.alpha, "lam": self.lam, "A": {o: a.tolist() for o, a in self.A.items()}, "b": {o: v.tolist() for o, v in self.b.items()}}


REGISTRY = {c.name: c for c in (Tally, Thompson, LinUCB)}


def register(cls):
    """Add a learner of your own: `@register` on a Learner subclass makes it appear in the panel and in the comparison."""
    REGISTRY[cls.name] = cls
    return cls


def make(name: str, **cfg) -> Learner:
    if name not in REGISTRY:
        raise KeyError(f"no learner called {name!r}")
    if not REGISTRY[name].available():
        raise RuntimeError(f"{name} needs {REGISTRY[name].needs}")
    return REGISTRY[name](**cfg)


def evaluate(name: str, rows: "list[dict]", kind: str) -> dict:
    """Replay the log in order. At each labelled decision the learner has seen only the rows before it, proposes its pick among the options that
    were ever chosen in this context, and the logged result counts (off-policy, `ope.snips`) only when its pick equals what was really chosen."""
    rows = sorted(_labelled(rows, kind), key=lambda r: r.get("at") or 0)
    options_by_ctx: "dict[str, list[str]]" = {}
    scored, seen = [], []
    for r in rows:
        key = str(r.get("context"))
        opts = options_by_ctx.setdefault(key, [])
        if str(r["chosen"]) not in opts:
            opts.append(str(r["chosen"]))
        if len(opts) >= 2 and seen:
            lr = make(name).fit(seen)
            pick, p = lr.choose(r.get("ctx") or {}, list(opts))
            scored.append({**r, "_pi": p if pick == str(r["chosen"]) else 0.0})
        seen.append(r)
    est = ope.snips(scored, lambda x: x["_pi"])
    agreed = sum(1 for r in scored if r["_pi"] > 0)
    return {"learner": name, "decided": len(scored), "agreed": agreed, **est}


def compare(rows: "list[dict]", kind: str) -> "list[dict]":
    out = []
    for name, cls in REGISTRY.items():
        if not cls.available():
            out.append({"learner": name, "description": cls.description, "available": False, "needs": cls.needs})
            continue
        out.append({"description": cls.description, "available": True, **evaluate(name, rows, kind)})
    return out


def selected() -> dict:
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {h: d.get(h) if d.get(h) in REGISTRY else "tally" for h in HEADS}


def select(head: str, name: str) -> dict:
    if head not in HEADS or name not in REGISTRY:
        raise KeyError("unknown head or learner")
    cur = selected()
    cur[head] = name
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cur), encoding="utf-8")
    return cur
