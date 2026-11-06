"""The two switches of the learning layer, kept in one small file so they can be flipped from the practice page, the API or by hand.

learning: the learning log (hub/features/learning.py) notes every choice the Hub makes (route, model, desktop step) and how it turned out.
shadow:   the trained practice-yard policy watches each live desktop-agent step and records what it would have pressed. It never presses anything.

EXPERIMENTAL. Both default to OFF: nothing is recorded until you switch shadow mode on, on the reinforcement-learning panel (the R button).
The panel's switch sets both together. The older environment variables HUB_LEARNING_LOG=0 and HUB_YARD_SHADOW=0 still force them off and win over the file.
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


def experimental() -> bool:
    """The master switch of the whole personal learning layer. OFF by default: the R button is hidden, nothing is recorded, nothing is trained.
    HUB_EXPERIMENTAL=1 forces it on."""
    return os.environ.get("HUB_EXPERIMENTAL") == "1" or _read().get("experimental") is True


def flag(name: str) -> bool:
    if os.environ.get(KEYS[name], "1") == "0":
        return False
    return experimental() and _read().get(name) is True


def current() -> dict:
    out = {k: {"on": flag(k), "forced_off_by_environment": os.environ.get(v, "1") == "0"} for k, v in KEYS.items()}
    out["fresh_since"] = fresh_since()
    out["experimental"] = {"on": experimental(), "forced_on_by_environment": os.environ.get("HUB_EXPERIMENTAL") == "1"}
    return out


def fresh_since() -> float:
    """When the learning layer's FRESH START happened (seconds since the epoch), or 0.0 if it never did. Learners read only rows from this moment on;
    everything older stays in the logs for audit and is never used as a training sample."""
    try:
        return float(_read().get("since") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _golden_file():
    return FILE.with_name("golden.json")


def golden() -> dict:
    """The routines you had already checked and trusted when the fresh start happened: {"at", "routines": [{"id", "title"}]}. They are CHECKS (replay them and see
    they still work), never training samples."""
    try:
        d = json.loads(_golden_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _snapshot_golden() -> None:
    try:
        from ..features import pc_control as PC
        with PC._db() as db:
            rows = db.execute("SELECT id, title FROM pc_routines WHERE status='trusted'").fetchall()
        routines = [{"id": r["id"], "title": r["title"]} for r in rows]
    except Exception:  # noqa: BLE001 - no routine store here (tests, a fresh install): nothing to attest
        routines = []
    _golden_file().parent.mkdir(parents=True, exist_ok=True)
    _golden_file().write_text(json.dumps({"at": round(time.time(), 1), "routines": routines}), encoding="utf-8")


def fresh_start() -> dict:
    """FRESH START: from now on the learners see only new rows, and the trusted routines of this moment are kept apart as checks. Nothing is deleted."""
    data = dict(_read())
    data["since"] = round(time.time(), 1)
    _write(data)
    _snapshot_golden()
    return current()


def _write(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: data[k] for k in KEYS if k in data}
    if data.get("since"):
        keep["since"] = data["since"]
    if "experimental" in data:
        keep["experimental"] = bool(data["experimental"])
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)
    _CACHE["at"] = 0.0


def update(changes: dict) -> dict:
    """Only the two known booleans, {"experimental": bool} and {"fresh": true} are accepted; anything else is ignored. The first time shadow mode is switched on it also makes the fresh start."""
    data = dict(_read())
    for k in KEYS:
        if isinstance(changes.get(k), bool):
            data[k] = changes[k]
    if isinstance(changes.get("experimental"), bool):
        data["experimental"] = changes["experimental"]
        if not changes["experimental"]:
            data["shadow"] = data["learning"] = False              # switching the layer off switches everything in it off
    elif data.get("shadow") is True or data.get("learning") is True:
        data["experimental"] = True                               # turning a learning switch on is a deliberate act that implies the layer is wanted
    first = data.get("shadow") is True and not data.get("since")
    _write(data)
    if changes.get("fresh") is True or first:
        return fresh_start()
    return current()
