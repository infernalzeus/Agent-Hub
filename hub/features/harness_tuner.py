"""The Hub reads its own logs and proposes how to behave better. You say yes.

Everything the Hub does is logged - every spoken request with how it was routed, every mission
with how it ended - and until now nothing read those logs. This does, with plain counting and
no model: a pattern that repeats is a candidate, and each candidate becomes a *proposal* that
carries the evidence behind it. Accepting one writes a procedural rule (see `memory_tiers`),
which is versioned, starts on probation and can be rolled back. The tuner is allowed to be
clever; only you are allowed to install.

Three patterns, because three are all the logs can honestly support today:

* the same request keeps going to a model although it could be a fixed command;
* the same request keeps coming back unsure (low confidence);
* the same mission error keeps happening.
"""
from __future__ import annotations

import collections
import json
import re

from aiohttp import web

from ..config import logger

routes = web.RouteTableDef()

MIN_REPEATS = 2
LOW_CONFIDENCE = 0.6


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", str(text).lower()))[:120]


def _decisions() -> "list[dict]":
    from . import binning as B
    try:
        return [json.loads(x) for x in B.LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _mission_errors() -> "list[dict]":
    try:
        from . import missions as M
        return [{"id": m.id, "project": m.project_name, "error": m.error} for m in M.S.m.values()
                if m.status in ("failed", "timed_out") and m.error]
    except Exception:  # noqa: BLE001
        return []


def candidates(decisions: "list[dict] | None" = None, errors: "list[dict] | None" = None) -> "list[dict]":
    rows = _decisions() if decisions is None else decisions
    errs = _mission_errors() if errors is None else errors
    out: "list[dict]" = []

    by_model = collections.Counter(_norm(r["text"]) for r in rows if r.get("by") not in (None, "rules") and r.get("text"))
    for text, n in by_model.items():
        if n >= MIN_REPEATS and text:
            out.append({"rule_id": "fixed_" + re.sub(r"\W+", "_", text)[:30],
                        "name": f'Answer "{text[:40]}" without a model',
                        "why": f"You said this {n} times and a model answered every time.",
                        "text": f'When asked "{text}", use the same fixed answer or action instead of asking a model.',
                        "evidence": {"pattern": "model-for-repeat", "count": n}, "confidence": min(0.9, 0.5 + 0.1 * n)})

    unsure = collections.Counter(_norm(r["text"]) for r in rows if isinstance(r.get("confidence"), (int, float)) and r["confidence"] < LOW_CONFIDENCE and r.get("text"))
    for text, n in unsure.items():
        if n >= MIN_REPEATS and text:
            out.append({"rule_id": "ask_" + re.sub(r"\W+", "_", text)[:30],
                        "name": f'Ask what "{text[:40]}" means',
                        "why": f"The router was unsure {n} times about this request.",
                        "text": f'When asked "{text}", ask one short question before acting.',
                        "evidence": {"pattern": "unsure-repeat", "count": n}, "confidence": 0.6})

    by_error = collections.Counter(_norm(e["error"])[:80] for e in errs)
    for text, n in by_error.items():
        if n >= MIN_REPEATS and text:
            out.append({"rule_id": "err_" + re.sub(r"\W+", "_", text)[:30],
                        "name": f"Missions keep failing: {text[:40]}",
                        "why": f"{n} missions ended with the same error.",
                        "text": f"Before starting a mission, check for this known failure: {text}.",
                        "evidence": {"pattern": "same-error", "count": n}, "confidence": 0.7})
    return out


def tune(decisions=None, errors=None) -> "list[dict]":
    """Turn the candidates into proposals, once each. Returns the proposals created."""
    from . import memory_tiers as MT
    from . import proposals as P
    have = {(p.get("wiring") or {}).get("rule_id") for p in P.load()} | set(MT.rules())
    made = []
    for c in candidates(decisions, errors):
        if c["rule_id"] in have:
            continue
        made.append(P.propose({"kind": "harness_edit", "name": c["name"], "why": c["why"], "from": "harness tuner",
                               "confidence": c["confidence"],
                               "wiring": {"rule_id": c["rule_id"], "text": c["text"], "evidence": c["evidence"]}}))
        have.add(c["rule_id"])
    if made:
        logger.info("harness tuner: %d proposals from the logs", len(made))
    return made


@routes.get("/api/harness/candidates")
async def api_candidates(request: web.Request) -> web.Response:
    return web.json_response({"candidates": candidates()})


@routes.post("/api/harness/tune")
async def api_tune(request: web.Request) -> web.Response:
    return web.json_response({"proposed": tune()})
