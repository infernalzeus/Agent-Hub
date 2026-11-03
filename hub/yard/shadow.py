"""Shadow mode: what the learned policy would have pressed, written beside what the live agent did. It only records.

The live desktop agent asks a language model what to press. After it has the answer, `note` asks the yard's trained policy the same question
about the same screen and writes both choices down. Nothing here can change an answer, slow a task by more than a millisecond or raise: a
missing policy, a missing numpy or any error means no line is written and the task goes on exactly as before.

What the lines are for: before the learned policy is allowed to decide anything on a real app, it has to show on real screens that it
would have chosen as well as the model, and where it would have chosen differently. `summary()` is what the PRACTICE page shows.
Switch off with HUB_YARD_SHADOW=0.
"""
from __future__ import annotations

import json
import os
import time

from ..config import logger
from ..runtime import STATE

DIR = STATE / "data" / "yard"
POLICY = DIR / "policy.json"
LOG = DIR / "shadow.jsonl"
MAX_BYTES = 2_000_000
_CACHE: dict = {"mtime": None, "learner": None}


def enabled() -> bool:
    return os.environ.get("HUB_YARD_SHADOW", "1") != "0"


def _learner():
    try:
        mtime = POLICY.stat().st_mtime
    except OSError:
        return None
    if _CACHE["mtime"] != mtime:
        from . import learner as L                   # numpy is imported here, and only when a trained policy exists
        lr = L.Learner()
        lr.actor = L.Actor.load(json.loads(POLICY.read_text(encoding="utf-8"))["linear"])
        _CACHE.update(mtime=mtime, learner=lr)
    return _CACHE["learner"]


def _append(row: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
        os.replace(LOG, LOG.with_suffix(".jsonl.1"))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _label(act: dict, names: dict) -> dict:
    c = names.get(act.get("id"))
    return {"do": act.get("do"), "role": c["role"], "name": c["name"][:60]} if act.get("do") in ("click", "type") and c else {"do": act.get("do")}


def note(goal: str, app: str, prompt: str, act: dict, step: int) -> None:
    """One line: the live agent's choice at this step and the one the trained policy would have made. Never raises."""
    if not enabled():
        return
    try:
        lr = _learner()
        if lr is None:
            return
        from . import learner as L
        o = L.parse(prompt)
        acts, X = L.candidates(o, lr.letters)
        would = acts[int(lr.actor.forward(X)[0].argmax())]
        names = {c["id"]: c for c in o["controls"]}
        live_id = (act.get("control") or {}).get("id")
        live = {"do": act.get("do")} if live_id is None else {**_label({"do": act["do"], "id": live_id}, names)}
        agree = live.get("do") == would.get("do") and (live_id is None or live_id == would.get("id"))
        _append({"kind": "step", "at": round(time.time(), 1), "goal": goal[:80], "app": app[:40], "step": step, "live": live, "would": _label(would, names), "agree": bool(agree)})
    except Exception as exc:  # noqa: BLE001 - watching must never get in the way of doing
        logger.info("yard shadow: could not note a step: %s", exc)


def note_result(goal: str, app: str, ok: bool, steps: int) -> None:
    if not enabled() or not POLICY.exists():
        return
    try:
        _append({"kind": "result", "at": round(time.time(), 1), "goal": goal[:80], "app": app[:40], "ok": bool(ok), "steps": steps})
    except Exception as exc:  # noqa: BLE001
        logger.info("yard shadow: could not note a result: %s", exc)


def summary(last: int = 12) -> dict:
    try:
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        rows = []
    steps = [r for r in rows if r.get("kind") == "step"]
    return {"policy": POLICY.exists(), "enabled": enabled(), "steps": len(steps), "agree": sum(1 for r in steps if r.get("agree")),
            "tasks": sum(1 for r in rows if r.get("kind") == "result"), "tasks_ok": sum(1 for r in rows if r.get("kind") == "result" and r.get("ok")),
            "last": steps[-last:]}
