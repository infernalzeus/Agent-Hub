"""The two switches of the learning layer, kept in one small file so they can be flipped from the practice page, the API or by hand.

learning: the learning log (hub/features/learning.py) notes every choice the Hub makes (route, model, desktop step) and how it turned out.
shadow:   the trained practice-yard policy watches each live desktop-agent step and records what it would have pressed. It never presses anything.

Both default to on. The older environment variables HUB_LEARNING_LOG=0 and HUB_YARD_SHADOW=0 still switch them off and win over the file.
Reads are cached for a few seconds because the learning log is called on every decision.
"""
from __future__ import annotations

import json
import os
import time

from ..runtime import STATE

FILE = STATE / "data" / "yard" / "settings.json"
KEYS = {"learning": "HUB_LEARNING_LOG", "shadow": "HUB_YARD_SHADOW"}
_CACHE: dict = {"at": 0.0, "data": {}, "file": None}
_TTL = 5.0


def _read() -> dict:
    now = time.monotonic()
    if now - _CACHE["at"] > _TTL or _CACHE["file"] != FILE:
        _CACHE["file"] = FILE
        try:
            d = json.loads(FILE.read_text(encoding="utf-8"))
            _CACHE["data"] = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _CACHE["data"] = {}
        _CACHE["at"] = now
    return _CACHE["data"]


def flag(name: str) -> bool:
    if os.environ.get(KEYS[name], "1") == "0":
        return False
    return _read().get(name) is not False


def current() -> dict:
    return {k: {"on": flag(k), "forced_off_by_environment": os.environ.get(v, "1") == "0"} for k, v in KEYS.items()}


def update(changes: dict) -> dict:
    """Only the two known booleans are accepted; anything else is ignored."""
    data = dict(_read())
    for k in KEYS:
        if isinstance(changes.get(k), bool):
            data[k] = changes[k]
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: data[k] for k in KEYS if k in data}, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)
    _CACHE["at"] = 0.0
    return current()
