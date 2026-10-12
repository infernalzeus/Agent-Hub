"""Finding a recorded step on the screen again, by what it IS before what it LOOKS like.

A recorded routine used to find its target one way: crop a small picture of the
screen around the click, and look for those pixels again. That is what makes a
routine brittle. The picture changes when the theme changes, when DPI changes,
when the window is a different size, when a font renders a shade differently -
none of which mean the button moved, and all of which make the match fail.

The hub already knows a better way and was not using it here. PC control reads
the accessibility tree - every element with its name, control type and window -
and `ui` routines match against that. Pixel routines never did.

So: **identity first, picture second.**

1. Ask the tree where "the Export button in Notepad" is. Robust to moving,
   resizing, re-theming and DPI, because none of those change what it is.
2. Only if the tree cannot answer, fall back to matching the recorded crop.

The second half is the part a demonstration cannot tell you: which of those two
will keep working. So each replay records which one found the target, and the
step learns. A step whose tree lookup has worked the last ten times stops paying
for a screen grab; one whose identity has vanished leans on the picture and says
so. A routine recorded once gets better at being replayed, instead of staying
exactly as fragile as the day it was taught.
"""
from __future__ import annotations

import json
import time

from ..config import logger

# How a step was found, in the order we prefer to find it.
BY_TREE = "tree"
BY_PIXELS = "pixels"

# A tree hit is worth more than a pixel hit at the same nominal score: it matched
# what the thing IS. This is the number that lets a routine's confidence mean
# something across both paths.
TREE_SCORE = 0.97


def identity(element: dict) -> dict:
    """What a step should remember about its target, besides where it was.

    Deliberately not coordinates: a position is the one property guaranteed to be
    wrong later. Name, control type and window survive a window being dragged.
    """
    return {"name": element.get("name", ""),
            "control": (element.get("control") or "").lower(),
            "window": element.get("window", "")}


def learned(target: dict) -> dict:
    """What this step has learned about finding itself."""
    got = target.get("sight") or {}
    return {"prefer": got.get("prefer") or BY_TREE,
            "tree_hits": int(got.get("tree_hits") or 0),
            "tree_misses": int(got.get("tree_misses") or 0),
            "pixel_hits": int(got.get("pixel_hits") or 0),
            "pixel_misses": int(got.get("pixel_misses") or 0)}


def confidence(target: dict) -> float:
    """How often this step has been found at all, by either route.

    What a person wants to know before trusting a routine is simply: does this
    still work? Not which mechanism answered.
    """
    s = learned(target)
    hits = s["tree_hits"] + s["pixel_hits"]
    tries = hits + s["tree_misses"] + s["pixel_misses"]
    return round(hits / tries, 2) if tries else 0.0


def remember(target: dict, by: str, found: bool) -> dict:
    """Fold one replay into what the step knows, and return the new target.

    The preference flips only on evidence, not on a single bad day: a route has
    to have failed more than it has worked before the other one is preferred.
    """
    s = learned(target)
    key = f"{'tree' if by == BY_TREE else 'pixel'}_{'hits' if found else 'misses'}"
    s[key] += 1
    tree_ok = s["tree_hits"] - s["tree_misses"]
    pixel_ok = s["pixel_hits"] - s["pixel_misses"]
    s["prefer"] = BY_TREE if tree_ok >= pixel_ok else BY_PIXELS
    return {**target, "sight": s}


async def find(target: dict, snapshot=None) -> "dict | None":
    """Where this step's target is now, by identity. None if the tree cannot say.

    `snapshot` is injectable so this can be exercised without a desktop.
    """
    want = target.get("identity") or {}
    if not want.get("name") and not want.get("control"):
        return None                      # recorded before identities were kept
    try:
        from . import pc_control as PC
        elements = await (snapshot or PC._snapshot)()
        hit = PC._match(elements, want)
    except Exception as exc:
        logger.info("routine_sight: tree lookup failed: %s", exc)
        return None
    if not hit:
        return None
    return {"x": hit["x"], "y": hit["y"], "score": TREE_SCORE, "by": BY_TREE,
            "what": f"{hit.get('control', '')} {hit.get('name', '')}".strip()}


def element_at(elements: "list[dict]", x: int, y: int, within: int = 60) -> "dict | None":
    """The listed element nearest a point, if anything is near enough.

    `within` keeps a click on empty canvas from adopting whatever button happened
    to be closest - a wrong identity is worse than none, because the step would
    then confidently click the wrong thing.
    """
    best, best_d = None, None
    for e in elements:
        try:
            d = abs(int(e["x"]) - int(x)) + abs(int(e["y"]) - int(y))
        except (KeyError, TypeError, ValueError):
            continue
        if best_d is None or d < best_d:
            best, best_d = e, d
    return best if best is not None and best_d is not None and best_d <= within else None


async def adopt(target: dict, x: int, y: int, snapshot=None) -> dict:
    """Learn what a step clicks, from a replay that found it by pixels.

    The recorder cannot do this - its hook must return immediately - but a replay
    can: the pixels have just told us where the thing is, so this is the one
    moment we know which element that is. A routine that works once becomes a
    routine that keeps working.
    """
    try:
        from . import pc_control as PC
        elements = await (snapshot or PC._snapshot)()
        hit = element_at(elements, x, y)
    except Exception as exc:
        logger.info("routine_sight: could not learn an identity: %s", exc)
        return target
    if not hit:
        return target
    logger.info("routine_sight: step learned it clicks %s %r", hit.get("control"), hit.get("name"))
    return {**target, "identity": identity(hit)}


def describe(target: dict) -> str:
    """One line about how this step finds itself, for a person reading a routine."""
    s = learned(target)
    ident = target.get("identity") or {}
    what = (f"{ident.get('control', '')} “{ident.get('name', '')}”".strip()
            if ident.get("name") else "a picture of the screen")
    tries = s["tree_hits"] + s["tree_misses"] + s["pixel_hits"] + s["pixel_misses"]
    if not tries:
        return f"finds {what}; never replayed"
    return (f"finds {what}; {confidence(target):.0%} over {tries} "
            f"replay{'s' if tries != 1 else ''}, prefers the "
            f"{'accessibility tree' if s['prefer'] == BY_TREE else 'recorded picture'}")


def generalise(steps: "list[dict]") -> "list[dict]":
    """Turn one demonstration into something reusable.

    A recording is a transcript: it types exactly what was typed. Most of the
    value in a routine is doing the same thing with *different* text, so typed
    input becomes a named value the routine asks for - the same `needs` an
    automation step uses, so one answer serves both.

    Clicks are not touched. What was clicked is the routine; what was typed is
    usually the subject.
    """
    out, seen = [], set()
    for i, step in enumerate(steps):
        args = step.get("args") or {}
        text = str(args.get("text") or "")
        if step.get("tool") in ("Type", "type", "SendKeys") and text.strip():
            key = f"text{len(seen) + 1}"
            seen.add(key)
            out.append({**step,
                        "args": {**args, "text": "{{" + key + "}}"},
                        "needs": [{"key": key, "label": f"text for step {i + 1}",
                                   "why": f"recorded as {text[:40]!r}"}],
                        "recorded_text": text})
        else:
            out.append(step)
    return out


def to_json(target: dict) -> str:
    return json.dumps({**target, "seen": time.time()})
