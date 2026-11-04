"""What the yard keeps, and why a learner is never just overwritten.

Two things persist, and they are different:

  1. THE EXPERIENCE (append-only). One line per finished practice session in `sessions.jsonl` (when, how many episodes, how each method did on
     known and unseen words). The live Hub's own experience is the learning log and the shadow log; those are appended too. Nothing here is rewritten.

  2. THE LEARNERS (versioned snapshots). Each finished session saves its two small networks as `versions/v<n>.json` (a few hundred kilobytes of numbers)
     with the scores it earned. `policy.json`, the one the shadow mode reads, is only replaced when the new learner is at least as good on words it
     never saw as the one it replaces (within 0.02), so a bad session cannot make things worse. Old versions stay, newest 12 kept, so any can be restored.

A learner is a small fixed-shape network whose numbers are what is saved. It is not retrained from scratch each time and it is not frozen: the next
session starts from nothing today (the yard is cheap), and starting from the best saved version is the planned next step.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

KEEP = 12
TOLERANCE = 0.02


def _dir(base: Path) -> Path:
    d = base / "versions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def versions(base: Path) -> "list[dict]":
    out = []
    try:
        for f in sorted((base / "versions").glob("v*.json"), key=lambda p: int(p.stem[1:])):
            m = json.loads(f.read_text(encoding="utf-8")).get("meta", {})
            out.append(m)
    except (OSError, ValueError):
        pass
    return out


def save(base: Path, policy_file: Path, rep: dict, weights: dict) -> dict:
    """Record a finished session. Returns what happened: the version number and whether `policy_file` was replaced."""
    prior = versions(base)
    n = (prior[-1]["n"] + 1) if prior else 1
    held = rep["means"]["learned, linear"]["held"]
    best_before = max((m["held"] for m in prior if m.get("in_use_ever")), default=None)
    adopted = best_before is None or held >= best_before - TOLERANCE
    meta = {"n": n, "at": rep["at"], "episodes": rep["episodes"], "seed": rep["seed"], "known": rep["means"]["learned, linear"]["train"], "held": held,
            "hidden_known": rep["means"]["learned, one hidden layer"]["train"], "hidden_held": rep["means"]["learned, one hidden layer"]["held"],
            "layouts": len(rep["table"]["learned, linear"]), "in_use_ever": bool(adopted), "warm_from": rep.get("warm_from"),
            "total_episodes": (prior[-1].get("total_episodes", prior[-1]["episodes"]) if prior else 0) + rep["episodes"]}
    (_dir(base) / f"v{n}.json").write_text(json.dumps({"meta": meta, "weights": weights}), encoding="utf-8")
    base.mkdir(parents=True, exist_ok=True)
    log = base / "sessions.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**meta, "adopted": bool(adopted), "means": rep["means"]}) + "\n")
    lines = log.read_text(encoding="utf-8").splitlines()
    if len(lines) > 200:                                           # the history is a small table, not a growing archive
        log.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    if adopted:
        policy_file.write_text(json.dumps({**weights, "version": n}), encoding="utf-8")
    for old in sorted(_dir(base).glob("v*.json"), key=lambda p: int(p.stem[1:]))[:-KEEP]:
        old.unlink(missing_ok=True)
    return {"version": n, "adopted": bool(adopted), "held": held, "best_before": best_before}


def current_version(policy_file: Path) -> "int | None":
    try:
        return json.loads(policy_file.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None
