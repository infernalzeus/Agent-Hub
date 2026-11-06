"""Sampling settings for a language model call: named presets, a reward that needs no label, and a tally over the presets per agent role.

The eight settings are temperature, top_k, top_p, min_p, presence penalty, frequency penalty, max tokens and stop sequences. Five presets cover the usual choices; the Hub
records which preset a call used and how the answer scored, and a tally (the same Thompson or tally learner used elsewhere) learns which preset suits which role.

The reward needs no grading from you: the answer was valid, it was not cut off, it did not repeat itself, the checks passed, and it used few tokens. The size of each part is
adjustable (KNOBS, "Sampling presets"). Your own approval of a mission always outranks it. Built and tested here; not yet called by any live model request.
"""
from __future__ import annotations

import json
import re

PRESETS = {
    "precise": {"temperature": 0.0, "top_k": 20, "top_p": 0.8, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.0, "max_tokens": 1024},
    "balanced": {"temperature": 0.4, "top_k": 40, "top_p": 0.9, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.1, "max_tokens": 2048},
    "varied": {"temperature": 0.9, "top_k": 80, "top_p": 0.95, "min_p": 0.02, "presence_penalty": 0.3, "frequency_penalty": 0.3, "max_tokens": 2048},
    "terse": {"temperature": 0.2, "top_k": 30, "top_p": 0.85, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.2, "max_tokens": 256},
    "long": {"temperature": 0.5, "top_k": 50, "top_p": 0.92, "min_p": 0.03, "presence_penalty": 0.1, "frequency_penalty": 0.1, "max_tokens": 8192},
}


def repeat_ratio(text: str, n: int = 4) -> float:
    """The share of word n-grams that already appeared: 0 for varied text, near 1 for a loop."""
    w = re.findall(r"\w+", (text or "").casefold())
    grams = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    return 1.0 - len(set(grams)) / len(grams) if grams else 0.0


def label_free_reward(text: str, finish_reason: str = "stop", tokens: int = 0, max_tokens: int = 2048, checks_passed: "bool | None" = None, expect_json: bool = False) -> dict:
    """{"reward", "parts"}. Higher is better. The parts are returned so you can see why."""
    from . import knobs as K
    valid = 1.0
    if expect_json:
        try:
            json.loads(text)
        except (ValueError, TypeError):
            valid = 0.0
    parts = {"valid": K.get("rw_valid_json") * valid,
             "not_cut_off": K.get("rw_not_truncated") * (0.0 if finish_reason in ("length", "max_tokens") else 1.0),
             "no_repeat": K.get("rw_no_repeat") * (1.0 - repeat_ratio(text)),
             "checks": K.get("rw_checks") * (1.0 if checks_passed else 0.0 if checks_passed is False else 0.5),
             "tokens": -K.get("rw_tokens") * min(1.0, tokens / max(1, max_tokens))}
    return {"reward": round(sum(parts.values()), 4), "parts": {k: round(v, 4) for k, v in parts.items()}}


def rows_for_tally(calls: "list[dict]", role: str) -> "list[dict]":
    """calls: [{"role", "preset", "reward" (0..1 scaled by you), ...}] -> rows the tally learners read (ok when the reward is above the role's median)."""
    mine = [c for c in calls if c.get("role") == role and c.get("preset") in PRESETS and isinstance(c.get("reward"), (int, float))]
    if not mine:
        return []
    med = sorted(c["reward"] for c in mine)[len(mine) // 2]
    return [{"kind": "preset", "context": role, "chosen": c["preset"], "ok": c["reward"] >= med, "at": c.get("at", i), "p": 1.0} for i, c in enumerate(mine)]
