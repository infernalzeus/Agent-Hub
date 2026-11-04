"""A bandit: the smallest learner there is. One choice, a few options, a tally of how often each option worked.

It is not an agent like Smith or the Doctor (those talk and act). It is a lookup table with arithmetic: for a given kind of choice
(which model for a small brief; replay a saved routine or let the agent try) it keeps, for every option, how many times that option
was labelled a success and how many times a failure. It prefers the option with the better record, but only once the record is long
enough to mean something. Until then it has no opinion, and says so.

Only EXACT labels count (a real outcome or the person's own verdict). Weak hints from follow-ups never feed it.

Nothing live calls this yet. `replay` runs it against the log, in order, asking at every decision "what would a bandit that had only
seen the earlier ones have chosen?", and counts how often that differs from what was really chosen. That is shadow mode for choices:
zero cost on the live path, and the numbers the person needs before promoting it.
"""
from __future__ import annotations

MIN_N = 3                # an option needs this many labelled results before the bandit trusts its record


def mean(c: dict) -> float:
    """Success rate with a gentle prior (one pretend win and one pretend loss), so 1 of 1 does not look perfect."""
    return (c["ok"] + 1) / (c["ok"] + c["failed"] + 2)


def advise(table: "dict[str, dict]", options: "list[str] | None" = None, min_n: int = MIN_N) -> "dict":
    """{"would": option or None, "why": text}. `table` is {option: {"ok": n, "failed": n}}. No opinion unless at least two options have a trusted record."""
    pool = {o: c for o, c in table.items() if (options is None or o in options) and c["ok"] + c["failed"] >= min_n}
    if len(pool) < 2:
        return {"would": None, "why": f"no opinion yet: needs at least two options with {min_n} labelled results each"}
    best = max(pool, key=lambda o: (mean(pool[o]), pool[o]["ok"] + pool[o]["failed"]))
    return {"would": best, "why": f"{best} has worked {pool[best]['ok']} of {pool[best]['ok'] + pool[best]['failed']} times"}


def replay(events: "list[dict]", kind: str) -> dict:
    """Online evaluation against the log. Events must be oldest first. A decision is judged only by what came before it."""
    seen: "dict[str, dict[str, dict]]" = {}
    decided = opinion = agreed = 0
    for e in events:
        if e.get("kind") != kind:
            continue
        ctx = seen.setdefault(str(e.get("context")), {})
        decided += 1
        adv = advise(ctx)
        if adv["would"] is not None:
            opinion += 1
            agreed += adv["would"] == str(e.get("chosen"))
        if e.get("ok") is not None:                      # only an exact label teaches it
            c = ctx.setdefault(str(e.get("chosen")), {"ok": 0, "failed": 0})
            c["ok" if e["ok"] else "failed"] += 1
    return {"decided": decided, "had_an_opinion": opinion, "agreed": agreed, "differed": opinion - agreed}
