"""The fitness report: how well each part of the Hub is doing, against what, on how much evidence. Read-only; it changes nothing.

Two rules keep it honest. (1) Only rows from after the FRESH START count, so the routines you had already checked are not training samples.
(2) A third of the labelled route rows (picked by a fixed hash of the sentence) are held out: a learner never trains on them, and a copy is kept in
data/yard/frozen/ so the log's rotation cannot take them away. They are what a new version is judged on, because a real PC cannot repeat a test.

Score per part: a win rate with its 95 % interval (Wilson), or for the confidence a Brier score, the mean of (confidence - what you said)^2, lower is better.
"""
from __future__ import annotations

import json
import zlib

from aiohttp import web

from ..runtime import STATE
from . import gate

routes = web.RouteTableDef()

DIR = STATE / "data" / "yard" / "frozen"
HELD_OUT = 3           # of every 10 sentences


def held_out(text: str) -> bool:
    """A fixed split by the sentence itself: the same sentence is always held out or always trained on, whatever else changes."""
    from . import knobs as K
    return zlib.crc32(" ".join(str(text or "").casefold().split()).encode()) % 10 < K.get("held_out_tenths")


def _frozen_rows() -> "list[dict]":
    try:
        return [json.loads(l) for l in (DIR / "route.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def sync() -> "list[dict]":
    """Copy every exact-labelled, held-out route row into the frozen file once. Returns the frozen rows."""
    from ..features import binning as BIN, learning as LRN
    have = {r.get("at") for r in _frozen_rows()}
    texts = {r.get("at"): str(r.get("text") or "") for r in BIN._rows() if r.get("kind") not in ("outcome", "verdict") and r.get("at")}
    new = []
    for e in LRN.events():
        if e["kind"] != "route" or e["ok"] is None or e.get("at") in have:
            continue
        text = texts.get(e.get("at"), "")
        if text and held_out(text):
            new.append({"at": e["at"], "text": text[:200], "chosen": e["chosen"], "ok": e["ok"]})
    if new:
        DIR.mkdir(parents=True, exist_ok=True)
        with (DIR / "route.jsonl").open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return _frozen_rows()


def _rate(k: int, n: int) -> dict:
    lo, hi = gate.wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "lower95": round(lo, 3), "upper95": round(hi, 3)}


def report() -> dict:
    from ..features import learning as LRN
    from . import evidence as EV, settings as YS
    rows = LRN.events()
    frozen = sync()
    out = {"fresh_since": YS.fresh_since(), "before_fresh_start": LRN.status()["before_fresh_start"], "heads": []}

    route = [e for e in rows if e["kind"] == "route" and e["ok"] is not None]
    fz_ok = sum(1 for r in frozen if r["ok"])
    out["heads"].append({"head": "Route", "what": "the bin chosen was right (exact labels)", "train": _rate(sum(1 for e in route if e["ok"]), len(route)),
                         "frozen": _rate(fz_ok, len(frozen)), "needs": f"{__import__('hub.yard.knobs', fromlist=['get']).get('min_frozen')} frozen rows to judge a new version; {len(frozen)} now",
                         "baseline": "rules + tev as they are today"})
    for kind, what in (("model", "the mission or task worked"), ("rung", "the way chosen worked")):
        per: dict = {}
        for e in rows:
            if e["kind"] == kind and e["ok"] is not None:
                c = per.setdefault(str(e["chosen"]), [0, 0])
                c[0] += 1 if e["ok"] else 0
                c[1] += 1
        out["heads"].append({"head": kind.capitalize(), "what": what, "options": {k: _rate(*v) for k, v in per.items()}, "needs": "two options, three exact results each", "baseline": "your own pick"})

    graded = [(r["confidence"], 1.0 if (EV._labels().get(r["id"]) or {}).get("grade") == "right" else 0.0) for r in EV._rows()
              if (EV._labels().get(r["id"]) or {}).get("grade") in ("right", "wrong") and not r.get("attested")]
    brier = round(sum((p - y) ** 2 for p, y in graded) / len(graded), 4) if graded else None
    out["heads"].append({"head": "Task confidence", "what": "how sure the Hub is that a PC task worked, against what you said", "graded": len(graded), "brier": brier,
                         "mean_confidence": round(sum(p for p, _ in graded) / len(graded), 3) if graded else None, "bands": EV.calibration(),
                         "needs": "about 30 graded tasks before the weights are fitted", "baseline": "always 0.5 scores a Brier of 0.25"})
    try:
        rep = json.loads((STATE / "data" / "yard" / "report.json").read_text(encoding="utf-8"))
        from . import candidates as CD
        lr = CD._learner()
        safety = CD.breaches(lr, 60) if lr is not None else None
        out["heads"].append({"head": "Control (yard)", "what": "win rate on pretend apps it never saw", "means": rep.get("means"), "safety": safety, "attested": rep.get("attested_agreement"),
                             "needs": "beat the rule of thumb on live shadow first", "baseline": "random and the rule of thumb"})
    except (OSError, ValueError):
        out["heads"].append({"head": "Control (yard)", "what": "win rate on pretend apps it never saw", "means": None, "needs": "run one practice session", "baseline": "random and the rule of thumb"})
    from . import learners as LN, router_challenger as RC
    try:
        out["challengers"] = {"selected": LN.selected(), "model": LN.compare(rows, "model"), "rung": LN.compare(rows, "rung"), "router_knn": RC.loo_accuracy(RC.examples()), "router_classifier": __import__("hub.yard.route_classifier", fromlist=["x"]).kfold_accuracy(RC.examples())}
    except Exception as exc:  # noqa: BLE001 - a challenger must never break the report
        out["challengers"] = {"error": str(exc)[:120]}
    out["heads"].append(live_shadow())
    from . import knobs as K
    out["gate"] = {"min_frozen": K.get("min_frozen"), "shadow_n": K.get("shadow_n"), "shadow_agree": K.get("shadow_agree")}
    return out


def live_shadow() -> dict:
    """Join each live shadow line to the PC task it belongs to (same goal, inside the task's time) so the control learner can be scored on real tasks:
    how often it would have pressed what the live agent pressed, in tasks that worked and in tasks that did not."""
    from . import evidence as EV
    try:
        steps = [json.loads(l) for l in (STATE / "data" / "yard" / "shadow.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        steps = []
    steps = [s for s in steps if s.get("kind") == "step"]
    ok_n = ok_agree = bad_n = bad_agree = tasks = 0
    for r in EV._rows():
        if r.get("way") != "agent" or r.get("attested"):
            continue
        mine = [s for s in steps if r["at"] - r["seconds"] - 10 <= s["at"] <= r["at"] + 5 and str(s.get("goal", "")).casefold() == str(r["goal"])[:80].casefold()]
        if not mine:
            continue
        tasks += 1
        a = sum(1 for s in mine if s.get("agree"))
        if r["ok"] and r["confidence"] >= 0.75:
            ok_n, ok_agree = ok_n + len(mine), ok_agree + a
        else:
            bad_n, bad_agree = bad_n + len(mine), bad_agree + a
    return {"head": "Control (live shadow)", "what": "how often the learner would have pressed what the live agent pressed", "tasks": tasks,
            "in_good_tasks": _rate(ok_agree, ok_n), "in_other_tasks": _rate(bad_agree, bad_n), "needs": f"{gate_shadow_n()} watched choices before promotion", "baseline": "the live agent"}


def gate_shadow_n() -> int:
    from . import knobs as K
    return K.get("shadow_n")


@routes.get("/api/yard/fitness")
async def api_fitness(request: web.Request) -> web.Response:
    return web.json_response(report())


@routes.get("/api/yard/learners")
async def api_learners(request: web.Request) -> web.Response:
    """Every learner that can sit behind a head, which one is being watched, and how each scores on the logged choices (off-policy, see ope.py)."""
    from . import learners as LN
    rows = LRN_events()
    return web.json_response({"selected": LN.selected(), "heads": {h: LN.compare(rows, h) for h in LN.HEADS}})


@routes.post("/api/yard/learners")
async def api_learner_select(request: web.Request) -> web.Response:
    """{"head": "model", "learner": "thompson"}: choose which learner is watched for a head. It changes no live choice."""
    from . import learners as LN
    try:
        b = await request.json()
        return web.json_response(LN.select(str(b["head"]), str(b["learner"])))
    except (KeyError, TypeError, ValueError):
        raise web.HTTPBadRequest(text='send {"head": "model"|"rung", "learner": a name from GET /api/yard/learners}')


def LRN_events():
    from ..features import learning as LRN
    return LRN.events()


@routes.post("/api/yard/gate")
async def api_gate(request: web.Request) -> web.Response:
    """A dry run of the gate on numbers you send: {"candidate": {"k", "n"}, "baseline": {"p"}, "breaches", "shadow": {"n", "agree"}, "user_yes"}."""
    try:
        b = await request.json()
        return web.json_response(gate.evaluate(b.get("candidate") or {}, b.get("baseline") or {}, b.get("breaches"), b.get("shadow"), b.get("user_yes")))
    except (TypeError, ValueError, AttributeError):
        raise web.HTTPBadRequest(text='send {"candidate": {"k": 0, "n": 0}, "baseline": {"p": 0.5}}')
