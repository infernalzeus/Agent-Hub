"""Three things for the router's small local model (tev), none of which trains anything.

R9a  EXAMPLES. When the router asks tev about a sentence the rules were unsure of, it also shows the nearest sentences you have already settled (the ones you graded, and the request each
     routine you trusted answers) with the bin that was right for each. Few-shot examples are the cheapest learning there is: no training, and a wrong answer you corrected stops repeating.
     How many are shown is the setting "Settled sentences shown to the router model" (0 turns it off). It only matters when local decisions are switched on.
R8b  REPLAY. Ask tev the same stored sentences again with different settings (temperature, with and without examples) and count how often the bin it names is the right one. It calls the
     local model, so it runs only when you ask (the REPLAY button, or POST /api/yard/router-replay) and says how many calls it made. A setting the endpoint ignores shows as identical rows.
R9b  CUT-OFFS. The router acts on the rules' answer at 0.75 and on tev's at 0.8. These are guesses. With enough settled decisions this works out, for each possible cut-off, how many it
     would have got right and how many it would have had to ask about, and names the cut-off that costs least. It only SUGGESTS: the live cut-offs are not changed by it.
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()
MIN_FOR_CUTOFFS = 20


def pool() -> "list[dict]":
    """Every settled sentence: {"text", "label", "source", "confidence"?}: the ones you graded, and the request each trusted routine answers."""
    from . import router_challenger as RC, routine_data as RD
    out = [{"text": e["text"], "label": e["label"], "source": "graded", "confidence": e.get("confidence")} for e in RC.examples()]
    return out + [{**r} for r in RD.router_rows()]


def nearest(text: str, k: "int | None" = None, rows: "list[dict] | None" = None) -> "list[dict]":
    """The k settled sentences most like this one, most alike first: [{"sentence", "bin", "alike"}]. The sentence itself and ones with nothing in common are left out."""
    from . import knobs as K, router_challenger as RC
    k = K.get("router_examples") if k is None else k
    if not k:
        return []
    g = RC._grams(text)
    scored = []
    for r in (pool() if rows is None else rows):
        if " ".join(r["text"].casefold().split()) == " ".join(str(text).casefold().split()):
            continue
        s = RC._cos(g, RC._grams(r["text"]))
        if s >= 0.25:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [{"sentence": r["text"], "bin": r["label"], "alike": round(s, 2)} for s, r in scored[:k]]


def state_for(text: str) -> dict:
    """What tev is shown: the sentence, and (R9a) the nearest settled sentences with their right bin when there are any."""
    st = {"utterance": text}
    ex = nearest(text)
    if ex:
        st["examples"] = [{"sentence": e["sentence"], "bin": e["bin"]} for e in ex]
    return st


async def replay(post=None, temperatures: "tuple" = (0.0, 0.3, 0.7), shots: "tuple" = (0, 3), limit: int = 40) -> dict:
    """R8b. For each setting, ask tev each settled sentence (the sentence itself is never among its own examples) and count the right bins."""
    from .. import decide as DEC
    from ..features import binning as BIN
    rows = [r for r in pool()][:limit]
    q = DEC.q_choice("bin", "Which kind of request is this?", list(BIN.BINS), BIN._BIN_DESC)
    model = BIN.settings()["local"]["model"]
    out, calls = [], 0
    for t in temperatures:
        for k in shots:
            right = asked = 0
            for r in rows:
                st = {"utterance": r["text"]}
                ex = nearest(r["text"], k, rows) if k else []
                if ex:
                    st["examples"] = [{"sentence": e["sentence"], "bin": e["bin"]} for e in ex]
                got = await DEC._decide_systemone(st, [q], model, post, options={"temperature": t})
                calls += 1
                a = (got or [{}])[0].get("answer")
                asked += a is not None
                right += a == r["label"]
            out.append({"temperature": t, "examples": k, "sentences": len(rows), "answered": asked, "right": right, "rate": round(right / len(rows), 3) if rows else None})
    return {"model": model, "calls": calls, "rows": out, "note": "a temperature the endpoint ignores gives the same row each time" if len({(r["answered"], r["right"]) for r in out if r["examples"] == 0}) == 1 and len(temperatures) > 1 else ""}


def cutoffs(pairs: "list[tuple[float, bool]]", cost_wrong: float = 5.0, cost_ask: float = 1.0) -> dict:
    """R9b. pairs: (how sure the router said it was, whether it was right). For each cut-off from 0.5 to 0.95: the share acted on, how many of those were right, and the cost
    (a wrong action costs `cost_wrong`, a question you are asked costs `cost_ask`). Names the cheapest. Suggests only."""
    from . import calibrate as CAL
    n = len(pairs)
    if n < MIN_FOR_CUTOFFS:
        return {"n": n, "ready": False, "needs": MIN_FOR_CUTOFFS, "note": f"{n} settled decisions with a stated confidence; {MIN_FOR_CUTOFFS} are needed before a cut-off can be suggested"}
    table = []
    for c in [round(0.5 + 0.05 * i, 2) for i in range(10)]:
        acted = [ok for p, ok in pairs if p >= c]
        wrong = sum(1 for ok in acted if not ok)
        asked = n - len(acted)
        table.append({"cutoff": c, "acted": len(acted), "right": len(acted) - wrong, "asked": asked, "cost": round(wrong * cost_wrong + asked * cost_ask, 2)})
    best = min(table, key=lambda r: (r["cost"], -r["cutoff"]))
    cal = [(float(p), 1.0 if ok else 0.0) for p, ok in pairs]
    return {"n": n, "ready": True, "table": table, "suggested": best["cutoff"], "now": 0.75, "calibration_error": CAL.ece(cal), "cost_wrong": cost_wrong, "cost_ask": cost_ask,
            "note": "a suggestion only: the live cut-offs are not changed by this"}


def graded_pairs() -> "list[tuple[float, bool]]":
    from ..features import binning as BIN
    from . import settings as YS
    rows, since = BIN._rows(), YS.fresh_since()
    verdicts = {r.get("of"): r for r in rows if r.get("kind") == "verdict" and isinstance(r.get("ok"), bool)}
    return [(float(r["confidence"]), bool(verdicts[r["at"]]["ok"])) for r in rows
            if r.get("kind") not in ("outcome", "verdict") and r.get("at") in verdicts and isinstance(r.get("confidence"), (int, float)) and not (since and r["at"] < since)]


@routes.get("/api/yard/router-tuning")
async def api_tuning(request: web.Request) -> web.Response:
    text = request.query.get("text", "")
    return web.json_response({"pool": len(pool()), "examples_shown": nearest(text) if text else [], "cutoffs": cutoffs(graded_pairs())})


@routes.post("/api/yard/router-replay")
async def api_replay(request: web.Request) -> web.Response:
    """Runs the local model, so only on request. Nothing is written."""
    return web.json_response(await replay())
