"""Memory in three tiers, each with its own write rule, and a test that shows whether memory helps.

The Hub already remembers three different kinds of thing, but they were stored in three
places under no stated rules. Mixing the rules is how a memory goes wrong: a fact gets
appended and the old one is still there, an event gets edited and the record is false, a
rule gets searched for and is not found when it matters.

* **semantic** - what is true of you now (`user_facts`). Writing is an *upsert*: a new value
  replaces the one it contradicts. Nothing is inferred; this module never writes it.
* **episodic** - what happened (decisions, missions, events). *Append-only*: a past event is
  never edited, so the record of what the Hub did cannot be made kinder than it was.
* **procedural** - how the Hub should behave (rules). *Replaced with a version*: one rule is
  swapped, its number goes up, and the old text is kept so it can be rolled back. It is never
  searched; every rule that is on is simply in the prompt.

`ablate` switches one tier off at a time and scores whether the needed fact still reaches the
prompt. It measures what the Hub *hands the model*, not what the model then says; a model's
answer is a separate, slower test. A tier whose removal changes no score is a tier doing
nothing for the cases you gave it.
"""
from __future__ import annotations

import json
import re
import time

from aiohttp import web

from ..runtime import STATE, write_json

routes = web.RouteTableDef()

TIERS = ("semantic", "episodic", "procedural")
PROCEDURAL = STATE / "memory_procedural.json"
EPISODIC = STATE / "memory_episodic.jsonl"
PROBATION_NEEDS = 2          # a new rule is kept after this many wins, undone after this many losses


# --- procedural: versioned, rollback, never searched ----------------------------------------------------
def _rules() -> dict:
    try:
        d = json.loads(PROCEDURAL.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def rules() -> dict:
    return _rules()


def set_rule(rule_id: str, text: str, source: str = "you", probation: bool = False) -> dict:
    """Replace one rule. Its version goes up and the old text stays in `history`."""
    rid = re.sub(r"[^a-z0-9_]+", "_", str(rule_id).lower()).strip("_")[:40]
    text = " ".join(str(text or "").split())[:400]
    if not rid or not text:
        raise ValueError("a rule needs an id and some text")
    data = _rules()
    old = data.get(rid)
    row = {"id": rid, "text": text, "version": (old["version"] + 1) if old else 1, "source": source,
           "at": time.time(), "history": ((old.get("history") or []) + [{"version": old["version"], "text": old["text"], "source": old.get("source"), "at": old.get("at")}]) if old else [],
           "probation": {"needs": PROBATION_NEEDS, "wins": 0, "losses": 0} if probation else None}
    data[rid] = row
    write_json(PROCEDURAL, data)
    return row


def rollback(rule_id: str) -> "dict | None":
    """Put the previous text back as a new version. A rule with no history is removed."""
    data = _rules()
    row = data.get(rule_id)
    if not row:
        return None
    if not row["history"]:
        del data[rule_id]
        write_json(PROCEDURAL, data)
        return None
    prev = row["history"][-1]
    restored = {**row, "text": prev["text"], "version": row["version"] + 1, "source": "rollback",
                "at": time.time(), "history": row["history"] + [{"version": row["version"], "text": row["text"], "source": row.get("source"), "at": row.get("at")}],
                "probation": None}
    data[rule_id] = restored
    write_json(PROCEDURAL, data)
    return restored


def record_outcome(rule_id: str, ok: bool) -> str:
    """A rule on probation is confirmed after enough wins and rolled back after enough losses."""
    data = _rules()
    row = data.get(rule_id)
    if not row or not row.get("probation"):
        return "none"
    pr = row["probation"]
    pr["wins" if ok else "losses"] += 1
    if pr["wins"] >= pr["needs"]:
        row["probation"] = None
        write_json(PROCEDURAL, data)
        return "kept"
    if pr["losses"] >= pr["needs"]:
        rollback(rule_id)
        return "rolled_back"
    write_json(PROCEDURAL, data)
    return "pending"


def prompt_block() -> str:
    """Every rule that is on, in a fixed order. This is how procedural memory reaches the model."""
    return "\n".join(f"- {r['text']}" for _, r in sorted(_rules().items()))


# --- episodic: append only ------------------------------------------------------------------------------
def note_event(text: str, kind: str = "event") -> None:
    line = json.dumps({"at": time.time(), "kind": kind, "text": " ".join(str(text).split())[:300]}, ensure_ascii=False)
    EPISODIC.parent.mkdir(parents=True, exist_ok=True)
    with EPISODIC.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def events(limit: int = 200) -> "list[dict]":
    try:
        rows = [json.loads(x) for x in EPISODIC.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        rows = []
    return rows[-limit:]


# --- recall -------------------------------------------------------------------------------------------
def _words(text: str) -> "set[str]":
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 2}


def recall(query: str, tiers: "tuple[str, ...]" = TIERS, k: int = 4) -> str:
    """What reaches the prompt for this question, from the tiers that are on."""
    parts = []
    if "procedural" in tiers:
        block = prompt_block()
        if block:
            parts.append("Rules:\n" + block)
    q = _words(query)
    if "semantic" in tiers:
        from . import user_facts as UF
        facts = UF.load()
        hits = [f"{key}: {v.get('value')}" for key, v in facts.items() if q & (_words(key) | _words(v.get("value", "")))]
        if hits:
            parts.append("Facts:\n" + "\n".join(hits[:k]))
    if "episodic" in tiers:
        scored = sorted(((len(q & _words(e["text"])), e) for e in events()), key=lambda s: (-s[0], -s[1]["at"]))
        hits = [e["text"] for n, e in scored if n][:k]
        if hits:
            parts.append("Earlier:\n" + "\n".join(hits))
    return "\n\n".join(parts)


def ablate(cases: "list[dict]") -> dict:
    """Score the cases with every tier on, with each tier off in turn, and with all off.

    A case is `{"q": question, "expect": text that must reach the prompt, "tier": which tier should supply it}`.
    """
    def score(tiers: "tuple[str, ...]") -> float:
        if not cases:
            return 0.0
        return round(sum(1 for c in cases if str(c["expect"]).lower() in recall(c["q"], tiers).lower()) / len(cases), 3)

    full = score(TIERS)
    out = {"cases": len(cases), "all_on": full, "all_off": score(()), "without": {}, "verdict": {}}
    for t in TIERS:
        s = score(tuple(x for x in TIERS if x != t))
        out["without"][t] = s
        needed = sum(1 for c in cases if c.get("tier") == t)
        out["verdict"][t] = ("no case depends on it" if not needed else
                             "helps: removing it lowers the score" if s < full else "cases expect it, but another tier already supplies them")
    return out


def status() -> dict:
    from . import user_facts as UF
    r = _rules()
    return {
        "tiers": {
            "semantic": {"rule": "upsert: a new value replaces the one it contradicts; never inferred", "count": len(UF.load())},
            "episodic": {"rule": "append-only: a past event is never edited", "count": len(events(100000))},
            "procedural": {"rule": "replace with a version, keep the old text, roll back; never searched, always in the prompt", "count": len(r),
                           "on_probation": [k for k, v in r.items() if v.get("probation")]},
        },
    }


@routes.get("/api/memory/tiers")
async def api_tiers(request: web.Request) -> web.Response:
    return web.json_response({**status(), "rules": [{k: v for k, v in r.items() if k != "history"} | {"versions": len(r["history"]) + 1} for r in _rules().values()]})
