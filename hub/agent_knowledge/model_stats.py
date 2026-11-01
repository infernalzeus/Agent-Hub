"""What the local models measurably do on this PC, and how missions have gone on them: the basis for choosing a model.

Two sources:

* `model_measurements.json` (written by `tools/probe_models.py`): load time, speed, graphics-card share, whether a
  schema-constrained answer parses, whether a tool call is made, whether working code is written. Measured on 1 Nov 2026:
  every gemma4 variant parses 5 of 5 and calls tools, at 130 to 180 tokens a second entirely on the card, *once hidden
  thinking is off* (with it on, a small token budget came back empty: 2 of 5).
* `model_outcomes.json` (written after each hub-verified mission): which model ran, whether the project's own tests then
  passed, how long it took. A local model that keeps failing its small tasks stops being the first choice by itself.

The rule that follows (see `prefer_local`): a small, single mission on a model measured usable goes to the local model first
and falls back to the cloud model if it fails; anything big or long, or a local model with a poor record, goes cloud first.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..runtime import STATE, write_json

MEASURED = Path(__file__).with_name("model_measurements.json")
OUTCOMES = STATE / "model_outcomes.json"
SMALL_BRIEF_CHARS = 600
MIN_SAMPLES = 4
MIN_RATE = 0.6


def measurements() -> dict:
    try:
        d = json.loads(MEASURED.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _bare(model: str) -> str:
    return model.split("/", 1)[1] if model.startswith("ollama/") else model


def measurement(model: str) -> "dict | None":
    return measurements().get(_bare(model))


def usable(model: str) -> bool:
    """Measured to load, to produce parseable structured output (4 of 5) and to make tool calls. Unmeasured counts as unknown."""
    m = measurement(model)
    return bool(m and m.get("loads") and (m.get("json_ok_of_5") or 0) >= 4 and m.get("tool_call"))


def broken(model: str) -> bool:
    """Measured NOT to load. Unmeasured is not broken."""
    m = measurement(model)
    return bool(m) and m.get("loads") is False


def _outcomes() -> "list[dict]":
    try:
        d = json.loads(OUTCOMES.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def record(models, ok: bool, secs: float, chars: int) -> None:
    """After a hub-verified mission: `ok` means the project's own checks passed."""
    rows = _outcomes()
    for m in (models or [])[:1]:                     # the model that did the work (the first one used)
        rows.append({"model": m, "ok": bool(ok), "secs": round(float(secs or 0), 1), "chars": int(chars or 0), "at": time.time()})
    write_json(OUTCOMES, rows[-200:])


def rate(model: str, last: int = 20) -> "tuple[int, float]":
    rows = [r for r in _outcomes() if r.get("model") == model][-last:]
    return len(rows), (sum(1 for r in rows if r["ok"]) / len(rows) if rows else 0.0)


def prefer_local(local_model: str, brief: "str | None") -> bool:
    if not usable(local_model):
        return False
    if brief is not None and len(brief) > SMALL_BRIEF_CHARS:
        return False
    n, ok = rate(local_model)
    return n < MIN_SAMPLES or ok >= MIN_RATE
