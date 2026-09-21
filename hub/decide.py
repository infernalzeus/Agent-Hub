"""decide(state, questions) — the hub's closed-question judge.

A writer LLM generates; this answers small typed questions ABOUT what was written ("did the checks pass?", "ship / changes-needed /
blocked?", "is every claim supported by the brief?") with a probability, so the hub can route unsure cases to the user instead of
trusting an agent's opinion of its own work.

One call shape, three interchangeable backends:
  rules  deterministic, free, instant — plain functions over the mission state (registered with @rule)
  local  an Ollama model, JSON constrained to the options by a schema; confidence = token log-probabilities of the answer
  jev    hosted decision model — an adapter SLOT only; it answers "not configured" until TypeSafe API access is wired in

Every question is a choice over `options` (yes/no and scores are choices too), so every result has the same shape:
  {id, answer, p, dist, backend, note}      answer None + p 0.0 = "abstain" (no rule / backend unavailable) — never a guess.
Shadow mode: `record()` appends what a backend decided to one jsonl, `record_outcome()` appends what the user then did
(APPLY / DISCARD), so agreement can be measured before any backend is trusted to gate anything.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

# ── question constructors ────────────────────────────────────────────────────────────────────────────────────────────
def q_yes_no(qid: str, text: str) -> dict:
    return {"id": qid, "text": text, "options": ["yes", "no"]}


def q_choice(qid: str, text: str, options: list[str]) -> dict:
    return {"id": qid, "text": text, "options": list(options)}


def q_score(qid: str, text: str, scale: int = 5) -> dict:
    return {"id": qid, "text": text, "options": [str(i) for i in range(1, scale + 1)]}


# ── backend 1: rules ─────────────────────────────────────────────────────────────────────────────────────────────────
RULES: dict[str, Callable[[dict], "tuple[str, float] | None"]] = {}


def rule(qid: str):
    """Register a deterministic answer for question `qid`: fn(state) -> (answer, p) or None to abstain."""
    def deco(fn):
        RULES[qid] = fn
        return fn
    return deco


@rule("checks_ok")
def _r_checks_ok(state: dict):
    v = state.get("verify")
    return None if not v else (("yes" if v.get("ok") else "no"), 1.0)


@rule("has_output")
def _r_has_output(state: dict):
    n = state.get("changed")
    return None if n is None else (("yes" if n else "no"), 1.0)


@rule("reviewer_verdict")
def _r_verdict(state: dict):
    v = state.get("verdict")
    return (v, 1.0) if v in ("ship", "changes-needed", "blocked") else None


def _decide_rules(state: dict, questions: list[dict]) -> list[dict]:
    out = []
    for q in questions:
        fn, hit = RULES.get(q["id"]), None
        if fn:
            try:
                hit = fn(state)
            except Exception:
                hit = None
        if hit and hit[0] in q["options"]:
            out.append({"id": q["id"], "answer": hit[0], "p": float(hit[1]), "dist": {hit[0]: float(hit[1])},
                        "backend": "rules", "note": ""})
        else:
            out.append({"id": q["id"], "answer": None, "p": 0.0, "dist": None, "backend": "rules", "note": "no rule for this question"})
    return out


# ── backend 2: local model (Ollama) ──────────────────────────────────────────────────────────────────────────────────
ChatFn = Callable[[dict], Awaitable[dict]]


async def _ollama_raw(body: dict) -> dict:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
        async with sess.post("http://127.0.0.1:11434/api/chat", json=body) as r:
            if r.status != 200:
                raise RuntimeError(f"ollama {r.status}: {(await r.text())[:160]}")
            return await r.json()


_SYSTEM = ("You judge ONE closed question about the STATE below. Answer only from the STATE; if it does not contain enough to "
           "decide, pick the most cautious option. Reply with JSON only.")


def dist_from_logprobs(logprobs: list[dict], options: list[str]) -> "dict[str, float] | None":
    """Probability of each option at the token where the JSON answer value begins. None when the runtime gave no log-probs
    (older Ollama) or the answer token cannot be located — the caller then reports p=None instead of inventing one."""
    if not logprobs:
        return None
    toks = [str(t.get("token", "")) for t in logprobs]
    full = "".join(toks)
    m = re.search(r'"answer"\s*:\s*"', full)
    if not m:
        return None
    pos, cands = 0, None
    for i, t in enumerate(toks):                       # the token that contains the first character of the answer value
        if pos <= m.end() < pos + len(t):
            cands = logprobs[i].get("top_logprobs") or [{"token": t, "logprob": logprobs[i].get("logprob", 0.0)}]
            break
        pos += len(t)
    if cands is None:
        return None
    mass = {o: 0.0 for o in options}
    for c in cands:
        s = str(c.get("token", "")).lstrip(' "').lower()
        if not s:
            continue
        hits = [o for o in options if o.lower().startswith(s) or s.startswith(o.lower())]
        if len(hits) == 1:                         # a token shared by several options says nothing about WHICH one: skip it, never guess
            mass[hits[0]] += math.exp(float(c.get("logprob", -99.0)))
    tot = sum(mass.values())
    return {o: v / tot for o, v in mass.items()} if tot > 0 else None


async def _decide_local(state: dict, questions: list[dict], model: str, chat: ChatFn) -> list[dict]:
    state_text = json.dumps(state, ensure_ascii=False, default=str)[:24000]
    name = model.split("/", 1)[1] if model.startswith("ollama/") else model

    async def one(q: dict) -> dict:
        schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": q["options"]}}, "required": ["answer"]}
        body = {"model": name, "stream": False, "format": schema, "logprobs": True, "top_logprobs": 10,
                "options": {"temperature": 0, "num_predict": 24, "num_ctx": 16384},
                "messages": [{"role": "system", "content": _SYSTEM},
                             {"role": "user", "content": f"STATE:\n{state_text}\n\nQUESTION: {q['text']}\nOPTIONS: {', '.join(q['options'])}"}]}
        try:
            d = await chat(body)
            ans = str(json.loads(((d.get("message") or {}).get("content") or "{}")).get("answer", ""))
        except Exception as exc:
            return {"id": q["id"], "answer": None, "p": 0.0, "dist": None, "backend": "local", "note": f"unavailable: {str(exc)[:90]}"}
        if ans not in q["options"]:
            return {"id": q["id"], "answer": None, "p": 0.0, "dist": None, "backend": "local", "note": f"off-schema answer {ans[:30]!r}"}
        lp = d.get("logprobs") or (d.get("message") or {}).get("logprobs") or []
        dist = dist_from_logprobs(lp, q["options"])
        return {"id": q["id"], "answer": ans, "p": (dist or {}).get(ans), "dist": dist, "backend": "local",
                "note": "" if dist else "no log-probs from this Ollama/model: confidence unknown"}

    gate = asyncio.Semaphore(1)                     # one local model, one call at a time: the same rule as pipeline calls

    async def metered(q):
        async with gate:
            return await one(q)
    return list(await asyncio.gather(*(metered(q) for q in questions)))


# ── backend 3: Jev (adapter slot) ────────────────────────────────────────────────────────────────────────────────────
def _decide_jev(state: dict, questions: list[dict]) -> list[dict]:
    return [{"id": q["id"], "answer": None, "p": 0.0, "dist": None, "backend": "jev",
             "note": "not configured: needs TypeSafe API access (adapter slot only)"} for q in questions]


# ── the one entry point ──────────────────────────────────────────────────────────────────────────────────────────────
async def decide(state: dict, questions: list[dict], *, backend: str = "rules", model: str = "ollama/nemotron-3-super:cloud",
                 chat: "ChatFn | None" = None) -> list[dict]:
    if backend == "rules":
        return _decide_rules(state, questions)
    if backend == "local":
        return await _decide_local(state, questions, model, chat or _ollama_raw)
    if backend == "jev":
        return _decide_jev(state, questions)
    raise ValueError(f"unknown backend {backend!r}")


def route(results: list[dict], min_p: float = 0.9) -> dict:
    """auto only when every question was answered with confidence >= min_p; otherwise a human decides, with the reasons."""
    why = []
    for r in results:
        if r["answer"] is None:
            why.append(f"{r['id']}: no answer ({r.get('note') or 'abstained'})")
        elif r["p"] is None:
            why.append(f"{r['id']}: confidence unknown")
        elif r["p"] < min_p:
            why.append(f"{r['id']}: {r['answer']} at p={r['p']:.2f} < {min_p}")
    return {"route": "human" if why else "auto", "reasons": why}


# ── shadow log ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _append(path: Path, rec: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass                                          # a log must never break a mission


def record(path: Path, mission_id: str, stage: str, results: list[dict]) -> None:
    _append(path, {"t": time.time(), "mission": mission_id, "kind": "decision", "stage": stage, "results": results,
                   **route(results)})


def record_outcome(path: Path, mission_id: str, outcome: str) -> None:
    _append(path, {"t": time.time(), "mission": mission_id, "kind": "outcome", "outcome": outcome})


def agreement(path: Path) -> dict:
    """How often the judge's verdict matched what the user then did. verdict ship <-> applied, changes-needed/blocked <-> discarded."""
    by: dict[str, dict] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {"missions": 0, "agree": 0, "rate": None}
    for l in lines:
        try:
            e = json.loads(l)
        except Exception:
            continue
        rec = by.setdefault(e.get("mission", "?"), {})
        if e.get("kind") == "outcome":
            rec["outcome"] = e.get("outcome")
        elif e.get("kind") == "decision":
            for r in e.get("results", []):
                if r["id"] == "reviewer_verdict" and r.get("answer"):
                    rec["verdict"] = r["answer"]
    n = a = 0
    for r in by.values():
        if r.get("verdict") and r.get("outcome"):
            n += 1
            a += int((r["verdict"] == "ship") == (r["outcome"] == "applied"))
    return {"missions": n, "agree": a, "rate": (a / n) if n else None}


# the questions asked about every finished mission (rules answer the first three today; `claims_supported` needs the local backend)
REVIEW_QUESTIONS = [
    q_yes_no("checks_ok", "Did the hub's compile / test / content checks pass?"),
    q_yes_no("has_output", "Did the run produce files?"),
    q_choice("reviewer_verdict", "What was the reviewer's verdict?", ["ship", "changes-needed", "blocked"]),
    q_yes_no("claims_supported", "Is every factual claim in OUTPUT supported by BRIEF or REFERENCE?"),
]
