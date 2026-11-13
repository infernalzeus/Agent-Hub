"""Sampling settings for a language model call: named presets, a reward that needs no label, and a tally over the presets per agent role.

The eight settings are temperature, top_k, top_p, min_p, presence penalty, frequency penalty, max tokens and stop sequences. Five presets cover the usual choices; the Hub
records which preset a call used and how the answer scored, and a tally (the same Thompson or tally learner used elsewhere) learns which preset suits which role.

The reward needs no grading from you: the answer was valid, it was not cut off, it did not repeat itself, the checks passed, and it used few tokens. The size of each part is
adjustable (KNOBS, "Sampling presets"). Your own approval of a mission always outranks it.

LIVE (since 13 Nov), in three modes you choose in the settings ("What presets do"): OFF records nothing. SHADOW (the default) scores every finished mission step with the reward above, writes
the preset the tally would pick for that role next time, and changes nothing. APPLY lets an agent use that preset's temperature and top p (a setting you set yourself on the agent always wins).
The tally is a Thompson draw over wins and losses per preset, after each preset has been tried `min_n` times (until then the least tried is picked, so every preset gets its turn).
In shadow the calls were made with the agent's own settings, so a call counts for a preset only when its temperature and top p are close to that preset (otherwise it counts for "own", which no arm learns from).
"""
from __future__ import annotations

import json
import random
import re
import time

PRESETS = {
    "precise": {"temperature": 0.0, "top_k": 20, "top_p": 0.8, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.0, "max_tokens": 1024},
    "balanced": {"temperature": 0.4, "top_k": 40, "top_p": 0.9, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.1, "max_tokens": 2048},
    "varied": {"temperature": 0.9, "top_k": 80, "top_p": 0.95, "min_p": 0.02, "presence_penalty": 0.3, "frequency_penalty": 0.3, "max_tokens": 2048},
    "terse": {"temperature": 0.2, "top_k": 30, "top_p": 0.85, "min_p": 0.05, "presence_penalty": 0.0, "frequency_penalty": 0.2, "max_tokens": 256},
    "long": {"temperature": 0.5, "top_k": 50, "top_p": 0.92, "min_p": 0.03, "presence_penalty": 0.1, "frequency_penalty": 0.1, "max_tokens": 8192},
}


def repeat_ratio(text: str, n: int = 4) -> float:
    """The share of word n-grams that already appeared: 0 for varied text, near 1 for a loop."""
    w = re.findall(r"\w+", (text or "").casefold())
    grams = [tuple(w[i:i + n]) for i in range(len(w) - n + 1)]
    return 1.0 - len(set(grams)) / len(grams) if grams else 0.0


def label_free_reward(text: str, finish_reason: str = "stop", tokens: int = 0, max_tokens: int = 2048, checks_passed: "bool | None" = None, expect_json: bool = False) -> dict:
    """{"reward", "parts"}. Higher is better. The parts are returned so you can see why."""
    from . import knobs as K
    valid = 1.0
    if expect_json:
        try:
            json.loads(text)
        except (ValueError, TypeError):
            valid = 0.0
    parts = {"valid": K.get("rw_valid_json") * valid,
             "not_cut_off": K.get("rw_not_truncated") * (0.0 if finish_reason in ("length", "max_tokens") else 1.0),
             "no_repeat": K.get("rw_no_repeat") * (1.0 - repeat_ratio(text)),
             "checks": K.get("rw_checks") * (1.0 if checks_passed else 0.0 if checks_passed is False else 0.5),
             "tokens": -K.get("rw_tokens") * min(1.0, tokens / max(1, max_tokens))}
    return {"reward": round(sum(parts.values()), 4), "parts": {k: round(v, 4) for k, v in parts.items()}}


def rows_for_tally(calls: "list[dict]", role: str) -> "list[dict]":
    """calls: [{"role", "preset", "reward" (0..1 scaled by you), ...}] -> rows the tally learners read (ok when the reward is above the role's median, or all are alike)."""
    mine = [c for c in calls if c.get("role") == role and c.get("preset") in PRESETS and isinstance(c.get("reward"), (int, float))]
    if not mine:
        return []
    rewards = sorted(c["reward"] for c in mine)
    med, top = rewards[len(rewards) // 2], rewards[-1]
    return [{"kind": "preset", "context": role, "chosen": c["preset"], "ok": c["reward"] > med or (c["reward"] == med == top), "at": c.get("at", i), "p": 1.0} for i, c in enumerate(mine)]       # a win is above the middle; when all are alike they all win


# ---- live: record, tally, pick
def _dir():
    from ..runtime import STATE
    return STATE / "data" / "yard"


def mode() -> str:
    from . import knobs as K
    return str(K.get("preset_mode"))


def nearest(sampling: dict) -> str:
    """The preset whose temperature and top p are closest to what a call used, or "own" when none is close (then no arm learns from the call)."""
    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    t, p = num(sampling.get("temperature")), num(sampling.get("top_p"))
    if t is None:
        return "own"
    best, dist = min(((n, abs(v["temperature"] - t) + (abs(v["top_p"] - p) if p is not None else 0.0)) for n, v in PRESETS.items()), key=lambda x: x[1])
    return best if dist <= 0.15 else "own"


def calls() -> "list[dict]":
    try:
        return [json.loads(l) for l in (_dir() / "preset_calls.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _picks() -> dict:
    try:
        d = json.loads((_dir() / "preset_picks.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def tally(role: str) -> "dict[str, dict]":
    """{preset: {"n": tries, "ok": results above the role's median}} from the recorded calls."""
    out = {n: {"n": 0, "ok": 0} for n in PRESETS}
    for r in rows_for_tally(calls(), role):
        out[r["chosen"]]["n"] += 1
        out[r["chosen"]]["ok"] += 1 if r["ok"] else 0
    return out


def suggest(role: str, rng: "random.Random | None" = None) -> dict:
    """The preset the tally would use next for a role: the least tried until each has `min_n` tries, then a Thompson draw (a Beta over wins and losses with one pretend of each)."""
    from . import knobs as K
    rng = rng or random.Random()
    t = tally(role)
    need = K.get("min_n")
    short = [n for n, v in t.items() if v["n"] < need]
    if short:
        fewest = min(t[n]["n"] for n in short)
        pick, why = rng.choice([n for n in short if t[n]["n"] == fewest]), f"trying each preset {need} times first"
    else:
        draws = {n: rng.betavariate(1 + v["ok"], 1 + v["n"] - v["ok"]) for n, v in t.items()}
        pick, why = max(draws, key=draws.get), "the highest Thompson draw"
    return {"role": role, "pick": pick, "why": why, "tally": t}


def note_mission(m) -> "list[dict]":
    """Score what a finished mission produced, per role, and choose the preset for next time. Never raises (a log line must not stop a mission)."""
    try:
        if mode() == "off":
            return []
        from .. import agent_knowledge as AK
        items = []
        if getattr(m, "kind", "") == "orchestrator" and getattr(m, "plan", None):
            items = [(st["agent"], str(st.get("summary") or "")) for st in m.plan if st.get("agent") and st.get("status") in ("done", "complete") and st.get("summary")]
        elif getattr(m, "answer", ""):
            items = [(m.agent or "coder", str(m.answer))]
        verify = getattr(m, "verify", None)
        checks = bool(verify.get("ok")) if isinstance(verify, dict) and "ok" in verify else None
        rows = []
        picks = _picks()
        for role, text in items:
            smp = AK.sampling_of(role)
            applied = mode() == "apply" and (picks.get(role) or {}).get("applied")
            name = picks[role]["name"] if applied else nearest(smp)
            toks = max(1, len(text) // 4)
            r = label_free_reward(text, "stop", toks, int(smp.get("num_predict") or smp.get("max_tokens") or 2048), checks)
            rows.append({"at": time.time(), "role": role, "mission": getattr(m, "id", ""), "preset": name, "applied": bool(applied), "sampling": smp, "reward": r["reward"], "parts": r["parts"]})
        if rows:
            _dir().mkdir(parents=True, exist_ok=True)
            with open(_dir() / "preset_calls.jsonl", "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(x) + "\n" for x in rows))
            for role in {x["role"] for x in rows}:
                sg = suggest(role)
                picks[role] = {"name": sg["pick"], "why": sg["why"], "at": time.time(), "applied": mode() == "apply"}
            (_dir() / "preset_picks.json").write_text(json.dumps(picks), encoding="utf-8")
        return rows
    except Exception:  # noqa: BLE001
        return []


def applied(role: str) -> "dict | None":
    """What an agent should use now, only in APPLY mode and only once a pick exists: {"name", "temperature", "top_p"}."""
    try:
        if mode() != "apply":
            return None
        p = _picks().get(role)
        if not p or p.get("name") not in PRESETS:
            return None
        v = PRESETS[p["name"]]
        return {"name": p["name"], "temperature": v["temperature"], "top_p": v["top_p"]}
    except Exception:  # noqa: BLE001
        return None


def summary() -> dict:
    """For the panel: the mode, and for each role that has calls: how many, the tally, what it would pick (shadow) or uses (apply), and the last reward."""
    cs = calls()
    roles = sorted({c["role"] for c in cs})
    picks = _picks()
    return {"mode": mode(), "calls": len(cs), "roles": [{"role": r, "calls": sum(1 for c in cs if c["role"] == r), "tally": tally(r), "pick": picks.get(r),
                                                         "last_reward": next((c["reward"] for c in reversed(cs) if c["role"] == r), None)} for r in roles]}
