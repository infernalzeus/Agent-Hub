"""What a yard policy sees, what it can do, and a small actor-critic that learns from how episodes end.

Observation = the very prompt the desktop agent shows a model (the goal, the history so far, the numbered controls), parsed back
into numbers. So a learned policy, the two baselines and a real language model are interchangeable: each is an async
`decide(system, prompt) -> JSON text`, called by the real `desktop_agent.attempt`.

Action = one of the closed set `parse_action` already allows: press a listed control, type into a listed edit box, press a key,
say done, say stuck. A policy cannot invent a control or a verb, and the agent's own never-press list still applies.

State space (what a step is described by):
    per candidate action  action kind (5), control role (7), words shared with the goal (name, group, row), the word "play", pressed
                          before, pressed before and nothing changed, on the never-press list, 32 hashed letter-triples of the name
    per step (crossed)    nothing yet / something pressed / a list entry pressed / typed already / last press changed the screen /
                          last press changed nothing / something is playing
Every candidate feature is multiplied by every step flag (7 x 51 = 357 numbers), so "a menu item right after a button that opened
something" can be told apart from "a menu item at the start". The critic sees only the step flags plus step count, number of
controls shown, best word overlap and how many presses did nothing.

Learner = advantage actor-critic (REINFORCE with a learned baseline): the actor scores each candidate (a linear scorer, or one
hidden layer of tanh units), a softmax turns scores into a choice, the critic estimates the return from the step's state, and the
actor moves along advantage x gradient of log-probability plus a small entropy bonus (the explore side). numpy only, CPU, no
training outside the yard.
"""
from __future__ import annotations

import json
import re
import zlib

import numpy as np

from ..features import pc_control as PC

ROLES = ("button", "list item", "edit", "menu item", "tab", "hyperlink")
KINDS = ("click", "type", "key", "done", "stuck")
HASH = 32
BASE = len(KINDS) + len(ROLES) + 1 + 3 + 1 + 3 + HASH          # 51
NFLAG = 7
DIM = BASE * NFLAG
ZDIM = NFLAG + 4
_LINE = re.compile(r'^(\d+)\. (.+?) "(.*)"(?: in "(.*?)")?(?: on the row of "(.*?)")?(?: \[.*\])?$')
_PRESSED = re.compile(r"pressed (\d+) (.+?) “(.*?)”")


def _tokens(s: str) -> "set[str]":
    return set(re.findall(r"[a-z0-9]+", (s or "").casefold()))


def parse(prompt: str) -> dict:
    """The prompt `desktop_agent.brief` builds, back into goal, step, history and controls."""
    lines = prompt.split("\n")
    goal = next((l[6:] for l in lines if l.startswith("GOAL: ")), "")
    step = int((re.search(r"STEP (\d+) of", prompt) or [0, 1])[1]) - 1
    section, hist, controls = "", [], []
    for l in lines:
        if l.startswith("SO FAR:"):
            section = "h"
        elif l.startswith("CONTROLS:"):
            section = "c"
        elif section == "h" and l.strip() and l.strip() != "(nothing yet)":
            hist.append(l)
        elif section == "c":
            m = _LINE.match(l)
            if m:
                controls.append({"id": int(m[1]), "role": m[2], "name": m[3], "path": m[4] or "", "row": m[5] or ""})
    pressed = [(m[2], m[3]) for h in hist for m in [_PRESSED.search(h)] if m]
    unchanged = {(m[2], m[3]) for h in hist for m in [_PRESSED.search(h)] if m and "NOTHING on screen changed" in h}
    last = next((h for h in reversed(hist) if "pressed" in h or "typed" in h), "")
    return {"goal": goal, "goal_words": PC.target_words(goal), "step": step, "controls": controls, "pressed": set(pressed), "unchanged": unchanged,
            "n_pressed": len(pressed), "typed": any("typed" in h for h in hist), "item_pressed": any(r == "list item" for r, _ in pressed),
            "last_changed": bool(last) and "the screen changed" in last, "last_nothing": bool(last) and "NOTHING on screen changed" in last,
            "playing": "NOW PLAYING: nothing" not in prompt}


def flags(o: dict) -> np.ndarray:
    return np.array([1.0, o["n_pressed"] > 0, o["item_pressed"], o["typed"], o["last_changed"], o["last_nothing"], o["playing"]], dtype=float)


def _base(kind: str, c: "dict | None", o: dict, letters: bool = True) -> np.ndarray:
    v = np.zeros(BASE)
    v[KINDS.index(kind)] = 1.0
    if c is None:
        return v
    role = ROLES.index(c["role"]) if c["role"] in ROLES else len(ROLES)
    v[len(KINDS) + role] = 1.0
    i = len(KINDS) + len(ROLES) + 1
    want = set(o["goal_words"]) or {"\0"}
    nt = _tokens(c["name"])
    v[i], v[i + 1], v[i + 2] = len(nt & want) / len(want), len(_tokens(c["path"]) & want) / len(want), len(_tokens(c["row"]) & want) / len(want)
    v[i + 3] = "play" in nt
    key = (c["role"], c["name"])
    v[i + 4], v[i + 5], v[i + 6] = key in o["pressed"], key in o["unchanged"], bool(PC.never_press(c["name"]))
    pad = f"  {c['name'].casefold()}  "
    for k in range(len(pad) - 2 if letters else 0):
        v[i + 7 + zlib.crc32(pad[k:k + 3].encode()) % HASH] += 1.0 / max(1, len(pad) - 2) ** .5
    return v


def candidates(o: dict, letters: bool = True) -> "tuple[list[dict], np.ndarray]":
    """Every action allowed now, and its crossed feature row. `letters` off hides the spelling of names (an ablation)."""
    acts = [{"do": "click", "id": c["id"]} for c in o["controls"]]
    rows = [_base("click", c, o, letters) for c in o["controls"]]
    for c in o["controls"]:
        if c["role"] == "edit":
            acts.append({"do": "type", "id": c["id"], "text": " ".join(o["goal_words"])})
            rows.append(_base("type", c, o, letters))
    for kind, extra in (("key", {"text": "enter"}), ("done", {}), ("stuck", {})):
        acts.append({"do": kind, **extra})
        rows.append(_base(kind, None, o, letters))
    f = flags(o)
    return acts, np.stack([np.concatenate([r * x for x in f]) for r in rows])


def critic_input(o: dict) -> np.ndarray:
    best = max([len(_tokens(c["name"]) & set(o["goal_words"])) for c in o["controls"]] or [0])
    return np.concatenate([flags(o), [o["step"] / 9, len(o["controls"]) / 70, min(best, 3) / 3, min(len(o["unchanged"]), 3) / 3]])


class Actor:
    """Scores candidate rows. hidden=0 is linear; otherwise one tanh layer."""

    def __init__(self, hidden: int = 0, seed: int = 0):
        r = np.random.default_rng(seed)
        self.h = hidden
        if hidden:
            self.W1, self.b1, self.w2 = r.normal(0, .1, (DIM, hidden)), np.zeros(hidden), r.normal(0, .1, hidden)
        else:
            self.w = np.zeros(DIM)

    def forward(self, X):
        if not self.h:
            return X @ self.w, None
        h = np.tanh(X @ self.W1 + self.b1)
        return h @ self.w2, h

    def step(self, X, h, ds, lr):
        """Move the parameters along d(objective)/d(score) = ds, for the rows X."""
        if not self.h:
            self.w += lr * (X.T @ ds)
            return
        dh = np.outer(ds, self.w2) * (1 - h * h)
        self.w2 += lr * (h.T @ ds)
        self.W1 += lr * (X.T @ dh)
        self.b1 += lr * dh.sum(0)

    def dump(self) -> dict:
        return {"hidden": self.h, **({"W1": self.W1.tolist(), "b1": self.b1.tolist(), "w2": self.w2.tolist()} if self.h else {"w": self.w.tolist()})}

    @classmethod
    def load(cls, d: dict) -> "Actor":
        a = cls(d["hidden"])
        if d["hidden"]:
            a.W1, a.b1, a.w2 = np.array(d["W1"]), np.array(d["b1"]), np.array(d["w2"])
        else:
            a.w = np.array(d["w"])
        return a


def softmax(s):
    e = np.exp(s - s.max())
    return e / e.sum()


class Learner:
    def __init__(self, hidden: int = 0, seed: int = 0, lr: float = 0.05, lr_critic: float = 0.05, gamma: float = 0.95, entropy: float = 0.02, letters: bool = True):
        self.letters = letters
        self.actor, self.v, self.rng = Actor(hidden, seed), np.zeros(ZDIM), np.random.default_rng(seed + 1)
        self.lr, self.lr_c, self.gamma, self.beta = lr * (0.3 if hidden else 1.0), lr_critic, gamma, entropy

    def policy(self, explore: bool):
        """An async `decide(system, prompt)` for the real agent. While `explore` is on it samples from the softmax and keeps what it did."""
        records: list = []

        async def decide(system: str, prompt: str) -> str:
            o = parse(prompt)
            acts, X = candidates(o, self.letters)
            s, h = self.actor.forward(X)
            p = softmax(s)
            a = int(self.rng.choice(len(acts), p=p)) if explore else int(np.argmax(s))
            records.append({"X": X, "h": h, "p": p, "a": a, "z": critic_input(o)})
            return json.dumps(acts[a])
        decide.records = records
        return decide

    def update(self, records: list, rewards: "list[float]") -> float:
        """One episode: returns, advantage = return - critic, move the actor and the critic. Returns the mean advantage."""
        g, rets = 0.0, []
        for r in reversed(rewards):
            g = r + self.gamma * g
            rets.append(g)
        rets.reverse()
        adv_all = []
        for rec, ret in zip(records, rets):
            v = float(self.v @ rec["z"])
            adv = ret - v
            adv_all.append(adv)
            self.v += self.lr_c * adv * rec["z"]
            p = rec["p"]
            e = np.zeros_like(p)
            e[rec["a"]] = 1.0
            ent = -(p * np.log(p + 1e-12)).sum()
            ds = adv * (e - p) + self.beta * (-p * (np.log(p + 1e-12) + ent))
            self.actor.step(rec["X"], rec["h"], np.clip(ds, -2, 2), self.lr)
        return float(np.mean(adv_all)) if adv_all else 0.0


# ---- the two baselines the learner has to beat
def random_policy(seed: int = 0):
    r = np.random.default_rng(seed)

    async def decide(system: str, prompt: str) -> str:
        acts, _ = candidates(parse(prompt))
        return json.dumps(acts[int(r.integers(len(acts)))])
    return decide


async def greedy_policy(system: str, prompt: str) -> str:
    """What a rule of thumb does: press the unpressed control that shares the most words with the goal, preferring one called Play."""
    o = parse(prompt)
    if o["playing"]:
        return json.dumps({"do": "done"})
    best, top = None, -1.0
    want = set(o["goal_words"])
    for c in o["controls"]:
        if (c["role"], c["name"]) in o["pressed"] or c["role"] == "edit":
            continue
        nt = _tokens(c["name"])
        score = 2 * len(nt & want) + len(_tokens(c["path"]) & want) + (1.0 if "play" in nt else 0.0)
        if score > top:
            best, top = c, score
    return json.dumps({"do": "click", "id": best["id"]} if best else {"do": "stuck"})
