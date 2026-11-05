"""The numbers a search would tune later, written down in one place. NOTHING here tunes anything: this is the inventory the CMA-ES step (not built) will read.

Each row says where the number lives, what it is now, and the range a search may try. The hand numbers are READ from hub/static/hand-gestures.js (the
TUNING object) and the speech-gate numbers from hub/static/voice-gate.js (the D object), so the "now" column cannot drift from the code; a test checks
that every name here still exists there. Ranges are my first guesses from how each number behaves (a fraction of hand size, milliseconds) and are
meant to be argued with.

What is missing for a real search, and is therefore the work still to do:
  - labelled hand traces: SAVE TRACE records the numbers, but nobody has marked what each trace was MEANT to be (a tap, a drag, nothing);
  - the score: replay a trace through the engine with a candidate number set and count presses that match the marked intent (and false ones);
  - the search itself: `search.cma_es` raises NotImplementedError; `search.random_search` and `search.grid_search` exist as the baselines it must beat.
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"

# name -> (low, high, what it changes)
HAND = {
    "pinchOn": (0.14, 0.30, "how close thumb and index must be to start a press (fraction of hand size)"),
    "pinchOff": (0.26, 0.45, "how far apart they must open to let go"),
    "pinchOnM": (0.16, 0.34, "the same for thumb and middle finger (right click)"),
    "tripleHoldMs": (120, 450, "how long three fingertips must stay together before zoom starts"),
    "flatHoldMs": (200, 700, "how long a flat palm must be held before it pans"),
    "confirmMs": (30, 140, "how long a pose must last before it counts (anti-flicker)"),
    "settleMs": (100, 400, "pause after a gesture before the next can start"),
    "clickSlop": (8, 36, "how far the pointer may drift during a press and still be a click (pixels)"),
}
VOICE = {
    "over": (1.6, 4.0, "how much louder than the room a sound must be to count as speech"),
    "quietMs": (800, 2200, "how long it must be quiet before the turn ends"),
}


def _read(path: Path, pattern: str) -> "dict[str, float]":
    text = path.read_text(encoding="utf-8")
    m = re.search(pattern, text, re.S)
    if not m:
        return {}
    return {k: float(v) for k, v in re.findall(r"([A-Za-z0-9]+)\s*:\s*(-?\.?\d+(?:\.\d+)?)", m.group(1))}


def current() -> "dict[str, dict[str, float]]":
    """{'hand': {name: value now}, 'voice': {name: value now}} read from the shipped JavaScript."""
    return {"hand": _read(STATIC / "hand-gestures.js", r"const TUNING=Object\.freeze\(\{(.*?)\}\)"),
            "voice": _read(STATIC / "voice-gate.js", r"const D = \{(.*?)\};")}


def inventory() -> "list[dict]":
    now = current()
    rows = []
    for group, table, src in (("hand", HAND, "hub/static/hand-gestures.js"), ("voice", VOICE, "hub/static/voice-gate.js")):
        for name, (lo, hi, what) in table.items():
            rows.append({"group": group, "name": name, "now": now[group].get(name), "low": lo, "high": hi, "what": what, "where": src, "searched": False})
    return rows
