"""R1 of the learning plan: every choice the Hub makes, in one shape, with what happened afterwards. Nothing here learns yet.

Three places in the Hub choose between options. Each already wrote something; this module reads all three as one list of events
and adds one small log for the choice that wrote nothing (how a PC task was done). It adds NO model call, NO background thread
and NO training: the answer path pays one appended line (`note`, measured under 1 ms) and everything else is computed when asked.

    kind   who chooses                         options                          log it comes from
    route  binning.decide / refine             the bins (launch_app, mission_ask…)  utterance_decisions.jsonl (+ outcome and verdict lines)
    model  missions, the desktop task agent    local and cloud models              model_outcomes.json, and `note` for desktop tasks
    rung   pc_control.after                    saved routine, local agent, cloud    `note`  (choices.jsonl)

An event: {kind, context, chosen, options, by, ok, ms, at}. `ok` is True only on evidence (the project's checks passed, Windows says it
is playing, the person said thanks), False only on evidence (a failed check, a correction), None otherwise: an unlabelled event is
never counted as a success.

What reads this later, all pure functions over `counters()`: R3 picks the model and R4 the rung (a bandit: shadow first, only
recording what it would choose), R5 fits the router's confidence against `route` events that have an `ok`. See `status()` for how
much data each of them has and what it still needs.
"""
from __future__ import annotations

import json
import os
import re
import time

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()

CHOICES = STATE / "choices.jsonl"
MAX_BYTES = 5 * 1024 * 1024
KINDS = ("route", "model", "rung")
NEEDS = {"R3": ("model", 30, "labelled model events, across at least two models"),
         "R4": ("rung", 30, "labelled rung events, across at least two ways"),
         "R5": ("route", 100, "labelled route decisions")}
_STATS = {"calls": 0, "spent_s": 0.0, "worst_s": 0.0, "since": time.time()}
_FH: dict = {"f": None, "path": None}      # the log stays open: opening a file for every line cost about 0.3 ms on Windows, a write to an open one about 15 us


def _close() -> None:
    try:
        if _FH["f"] is not None:
            _FH["f"].close()
    except OSError:
        pass
    _FH.update(f=None, path=None)


def _handle():
    if _FH["f"] is None or _FH["path"] != CHOICES or _FH["f"].closed:
        _close()
        CHOICES.parent.mkdir(parents=True, exist_ok=True)
        _FH.update(f=CHOICES.open("a", encoding="utf-8", buffering=1), path=CHOICES)
    return _FH["f"]


def enabled() -> bool:
    if os.environ.get("HUB_LEARNING_LOG", "1") == "0":
        return False
    from ..yard import settings as YS            # the switch on the practice page
    return YS.flag("learning")


def note(kind: str, context: str, chosen: str, options: "list | None" = None, ok: "bool | None" = None,
         ms: "float | None" = None, by: str = "rules", **extra) -> None:
    """One line: a choice that was made and, when it is already known, how it turned out. Never raises, never waits on anything but a file append."""
    if not enabled():
        return
    t0 = time.perf_counter()
    try:
        row = {"kind": kind, "context": str(context)[:80], "chosen": str(chosen)[:80], "options": [str(o)[:80] for o in (options or [])][:8],
               "by": by, "ok": ok if isinstance(ok, bool) else None, "ms": None if ms is None else int(ms), "at": round(time.time(), 1), **extra}
        if _STATS["calls"] % 200 == 0 and CHOICES.exists() and CHOICES.stat().st_size > MAX_BYTES:
            _close()
            os.replace(CHOICES, CHOICES.with_suffix(".jsonl.1"))          # keep one older file, never grow without bound
        _handle().write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 - recording a choice must never break making it
        logger.info("learning: could not note a choice: %s", exc)
    finally:
        dt = time.perf_counter() - t0
        _STATS["calls"] += 1
        _STATS["spent_s"] += dt
        _STATS["worst_s"] = max(_STATS["worst_s"], dt)


def _jsonl(path) -> "list[dict]":
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


_CORRECTION = re.compile(r"^\s*(?:no\b|nope\b|not that\b|that'?s (?:not|wrong)\b|i meant\b|i said\b|wrong\b|cancel\b|undo\b)", re.I)
WEAK_WINDOW_S = 90


def _words(t: str) -> "set[str]":
    return set(re.findall(r"[a-z0-9']+", (t or "").lower()))


def weak_labels(rows: "list[tuple[dict, str, float]]") -> None:
    """WEAK evidence from what the person did next, for choices that have no exact label. Written to e["weak"] as False (it probably did not work) or True
    (they carried on to something else), and counted apart from exact labels: a repeat or a correction within 90 s is a likely failure, a different
    request soon after is only a hint of success. Weak evidence never fills e["ok"], so nothing that needs exact labels is fooled by it."""
    rows = sorted(rows, key=lambda r: r[2] or 0)
    for i, (e, text, at) in enumerate(rows):
        if e.get("ok") is not None or not at or i + 1 >= len(rows):
            continue
        n_e, n_text, n_at = rows[i + 1]
        if not n_at or n_at - at > WEAK_WINDOW_S:
            continue
        a, b = _words(text), _words(n_text)
        if _CORRECTION.match(n_text or "") or (a and b and len(a & b) / len(a | b) >= 0.7):
            e["weak"] = False
        else:
            e["weak"] = True


def _route_events() -> "list[dict]":
    """The router's decisions, each with the outcome and the person's verdict that came after it."""
    from . import binning as BIN
    out: "list[dict]" = []
    texts: "list[tuple[dict, str, float]]" = []
    last_by_action: "dict[str, dict]" = {}
    by_at: "dict[float, dict]" = {}
    for r in BIN._rows():
        k = r.get("kind")
        if k == "outcome":
            e = last_by_action.get(str(r.get("action")))
            if e is not None and e["ok"] is None and isinstance(r.get("ok"), bool):
                e["ok"] = r["ok"]
            continue
        if k == "verdict":
            e = by_at.get(r.get("of"))
            if e is not None and isinstance(r.get("ok"), bool) and (e["ok"] is None or r["ok"] is False):      # a correction beats a run that finished
                e["ok"] = r["ok"]
            continue
        asked = [a for a in (r.get("asked") or []) if isinstance(a, dict)]
        e = {"kind": "route", "context": "bin", "chosen": str(r.get("bin")), "options": [str(r.get("bin"))] + [str(a.get("answer")) for a in asked if a.get("answer")],
             "by": str(r.get("by") or "rules"), "ok": None, "ms": r.get("ms"), "at": r.get("at"), "confidence": r.get("confidence"), "escalated": bool(asked)}
        out.append(e)
        texts.append((e, str(r.get("text") or ""), r.get("at")))
        by_at[r.get("at")] = e
        if r.get("action"):
            last_by_action[str(r["action"])] = e
    weak_labels(texts)
    return out


def mission_verdicts() -> "dict[str, bool]":
    """What the person decided about a mission, by id: APPLY is a yes, DISCARD is a no, and a tap on the TEACH page says it directly (the tap wins).
    This beats the project's own checks, which only say whether the tests passed."""
    out: "dict[str, bool]" = {}
    try:
        from . import missions as M
        for m in M.S.m.values():
            if m.status == "applied":
                out[m.id] = True
            elif m.status == "discarded":
                out[m.id] = False
    except Exception:  # noqa: BLE001
        pass
    out.update({k: v["ok"] for k, v in _jsonl_dict(MISSION_LABELS).items() if isinstance(v, dict) and isinstance(v.get("ok"), bool)})
    return out


MISSION_LABELS = STATE / "mission_labels.json"


def _jsonl_dict(path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _model_events() -> "list[dict]":
    from ..agent_knowledge import model_stats as MS
    from ..agent_knowledge.model_stats import SMALL_BRIEF_CHARS
    human = mission_verdicts()
    out = []
    for r in MS._outcomes():
        ok = r.get("ok") if isinstance(r.get("ok"), bool) else None
        mid = str(r.get("mission") or "")
        if mid in human:
            ok = human[mid]                                  # your decision beats the project's checks
        out.append({"kind": "model", "context": "mission:" + ("small" if int(r.get("chars") or 0) <= SMALL_BRIEF_CHARS else "large"), "chosen": r.get("model"), "options": [],
                    "by": "rules", "ok": ok, "ms": int(float(r.get("secs") or 0) * 1000), "at": r.get("at"), "mission": mid})
    return out


def events(limit: int = 5000) -> "list[dict]":
    """Every recorded choice, oldest first, from the three places that make them."""
    rows = _route_events() + _model_events() + _jsonl(CHOICES)
    rows.sort(key=lambda e: e.get("at") or 0)
    return rows[-limit:]


def counters(rows: "list[dict] | None" = None) -> dict:
    """{kind: {context: {option: {n, ok, failed, unknown, ms}}}}: the table a bandit would read. Computed when asked, never kept."""
    out: dict = {}
    for e in rows if rows is not None else events():
        c = out.setdefault(e["kind"], {}).setdefault(e["context"], {}).setdefault(str(e["chosen"]), {"n": 0, "ok": 0, "failed": 0, "unknown": 0, "weak_ok": 0, "weak_failed": 0, "ms": 0})
        c["n"] += 1
        c["ok" if e["ok"] is True else "failed" if e["ok"] is False else "unknown"] += 1
        if e["ok"] is None and e.get("weak") is not None:
            c["weak_ok" if e["weak"] else "weak_failed"] += 1                 # a hint, counted apart from exact labels
        c["ms"] += int(e.get("ms") or 0)
    for ctx in out.values():
        for opts in ctx.values():
            for c in opts.values():
                c["ms"] = round(c["ms"] / c["n"]) if c["n"] else 0
    return out


def status() -> dict:
    """How much the Hub has to learn from, and what each later step still needs. Read-only."""
    rows = events()
    per: dict = {}
    for k in KINDS:
        mine = [e for e in rows if e["kind"] == k]
        per[k] = {"events": len(mine), "labelled": sum(1 for e in mine if e["ok"] is not None),
                  "weak": sum(1 for e in mine if e["ok"] is None and e.get("weak") is not None), "options": len({e["chosen"] for e in mine if e["ok"] is not None})}
    needs = {}
    for step, (kind, n, what) in NEEDS.items():
        have = per[kind]["labelled"]
        needs[step] = {"needs": what, "want": n, "have": have, "ready": have >= n and (per[kind]["options"] >= 2 or kind == "route")}
    calls = _STATS["calls"]
    from . import bandit as BD
    bandits = {"R3 model choice": BD.replay(rows, "model"), "R4 PC-task way": BD.replay(rows, "rung")}
    return {"logging": enabled(), "per_kind": per, "needs": needs, "bandits": bandits,
            "cost": {"notes": calls, "spent_ms": round(_STATS["spent_s"] * 1000, 2), "mean_us": round(_STATS["spent_s"] / calls * 1e6) if calls else 0, "worst_us": round(_STATS["worst_s"] * 1e6)},
            "learning": "nothing learns yet: R1 only records"}


@routes.get("/api/learning/status")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(status())
