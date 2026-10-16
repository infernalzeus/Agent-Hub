"""Questions the hub can answer without being asked to change anything.

TALK used to have exactly two ways to answer a question that was not about the
hub itself: a handful of hard-coded phrases, or a small local model that has to
be running. Ask it the weather and it could not say; worse, it could not ever
*learn* to.

This is the rung between "I know it" and "start a mission":

    0  know it        facts the person told it          (user_facts)
    2  routine        a *procedure* it has used before   <- here, deterministic
    3  chat answer    an agent looks it up and answers   <- here, researcher

**A routine remembers how, never what.** The weather routine stores the steps
(geocode the place, ask the forecast service, say it in this shape) and a short
dated record that a lookup happened. It does not store "it is 15 degrees". The
number is fetched every time it is asked, because it is only true for a
moment.

**Confidence is earned from verified results, the same way a PC routine is.**
A routine is `candidate` until it has produced a result that parsed and passed
its own checks twice; a failure twice in a row disables it, and the question
falls through to an agent. Once a routine is trusted the model is not involved
at all, which is what lets the local model stay stopped.

Nothing here writes anywhere but its own small file and the person's facts, and
a fact is only written when the person answered a question the hub asked.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime
from urllib.parse import quote

from aiohttp import web

from ..config import logger
from ..runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "info_routines.json"

PROMOTE_AFTER = 2          # verified results before a candidate is trusted
DISABLE_AFTER = 2          # failures in a row before it is set aside
LOG_KEEP = 20
PENDING_TTL = 300.0        # how long a question stays open
INGEST_WAIT = 10.0         # reading a large app takes minutes; answer inside the turn, finish in the background
AGENT_WAIT = 35.0          # voice.js gives one request 45 s; stay inside it
AGENT_TIMEOUT = 240.0

_WMO = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog",
    48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "heavy freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


# -- what the hub ships knowing how to do --------------------------------------
# Defined in code so a fix reaches everyone; what each has *earned* (status,
# counts, the log) lives in the file and survives an update.
SEEDS: "list[dict]" = [
    {"id": "weather", "title": "Weather", "intent": "weather",
     "match": [r"\b(?:weather|forecast)\b", r"\bhow (?:hot|cold|warm)\b",
               r"\bis it (?:raining|snowing|sunny|cold|hot|warm|windy)\b",
               r"\bwill it rain\b", r"\bwhat(?:'s| is) it like outside\b"],
     "slots": {"location": r"\b(?:in|for|at|near|around)\s+(?P<v>[A-Za-z][A-Za-z' .,-]{1,60}?)"
                           r"(?=\s+(?:today|tomorrow|tonight|now|right now|please|this|later|at)\b|[?.!]|$)"},
     "needs": ["location"], "procedure": {"kind": "weather"}},
    {"id": "time", "title": "Time and date", "intent": "time",
     "match": [r"\bwhat(?:'s| is)? the time\b", r"\bwhat time is it\b", r"\bcurrent time\b",
               r"\bwhat(?:'s| is) the date\b", r"\bwhat day is it\b"],
     "slots": {}, "needs": [], "procedure": {"kind": "clock"}},
]


class ProcedureError(Exception):
    """The procedure ran but did not produce a result it can stand behind."""


class Ambiguous(Exception):
    """More than one thing fits, and guessing would be a confident wrong answer."""

    def __init__(self, options: "list[dict]", why: str = ""):
        super().__init__(why or "more than one place fits")
        self.options = options


# -- the store -------------------------------------------------------------------
def load() -> "list[dict]":
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        saved = {r["id"]: r for r in data if isinstance(r, dict) and r.get("id")}
    except (OSError, ValueError, TypeError):
        saved = {}
    out = []
    for seed in SEEDS:
        old = saved.pop(seed["id"], {})
        row = {**seed, "kind": "seed",
               "status": old.get("status") or "candidate",
               "successes": int(old.get("successes") or 0),
               "failures": int(old.get("failures") or 0),
               "streak_fail": int(old.get("streak_fail") or 0),
               "log": list(old.get("log") or [])[-LOG_KEEP:]}
        out.append(row)
    out.extend(saved.values())
    return out


def _save(rows: "list[dict]") -> None:
    write_json(FILE, rows)


def get(rid: str) -> "dict | None":
    return next((r for r in load() if r["id"] == rid), None)


def _update(rid: str, fn) -> None:
    rows = load()
    for r in rows:
        if r["id"] == rid:
            fn(r)
    _save(rows)


def record_success(rid: str, inputs: dict, said: str) -> None:
    def go(r):
        r["successes"] = int(r.get("successes", 0)) + 1
        r["streak_fail"] = 0
        if r.get("status") == "candidate" and r["successes"] >= PROMOTE_AFTER:
            r["status"] = "trusted"
        r.setdefault("log", []).append({"at": datetime.now().isoformat(timespec="seconds"),
                                        "inputs": inputs, "said": said[:200]})
        r["log"] = r["log"][-LOG_KEEP:]
    _update(rid, go)


def record_failure(rid: str, why: str) -> None:
    def go(r):
        r["failures"] = int(r.get("failures", 0)) + 1
        r["streak_fail"] = int(r.get("streak_fail", 0)) + 1
        r.setdefault("log", []).append({"at": datetime.now().isoformat(timespec="seconds"),
                                        "failed": why[:200]})
        r["log"] = r["log"][-LOG_KEEP:]
        if r["streak_fail"] >= DISABLE_AFTER:
            r["status"] = "disabled"
    _update(rid, go)


# -- reading a sentence ----------------------------------------------------------
def match(text: str) -> "dict | None":
    for r in load():
        for rx in r.get("match", []):
            if re.search(rx, text or "", re.I):
                return r
    return None


def slot(routine: dict, key: str, text: str) -> "str | None":
    """A value the sentence itself carries ("weather IN LEEDS"), for this one ask.

    Not remembered: saying where you want the weather once is not the same as
    telling the hub where you live.
    """
    rx = (routine.get("slots") or {}).get(key)
    if not rx:
        return None
    m = re.search(rx, text or "", re.I)
    v = (m.group("v") if m else "") or ""
    v = v.strip(" ,.")
    return v or None


_QUESTION = re.compile(
    r"^(?:what|what's|whats|who|who's|whos|when|where|which|how (?:many|much|tall|old|long|far|big|do|does|did|can|to)|"
    r"why|is|are|does|do|did|can|tell me|look up|search for|find out|find me|google)\b", re.I)
_HUB_WORDS = re.compile(
    r"\b(?:ask|asks|mission|missions|project|projects|agent|agents|hub|pipeline|automation|automations|"
    r"routine|routines|review|apply|discard|pause|resume|plan|waiting|status|skill|skills|model|models|talk|"
    r"tile|tiles|ingest|download|upload|schedule|folder|file|files|repo|code|branch|team|teams|persona|"
    r"personas|orchestrator|worktree|commit|git|settings|setup|install|update|version|release|"
    r"you|your)\b", re.I)

# A turn that starts like an instruction is an instruction, even when it is short.
_COMMANDISH = re.compile(
    r"^(?:open|launch|start|play|stop|pause|resume|show|run|go|turn|switch|enable|disable|set|make|"
    r"create|new|ask|tell|find|search|download|upload|close|apply|discard|status|help|yes|yeah|"
    r"what|who|when|where|why|how|is|are|do|does|can)\b", re.I)


def looks_like_lookup(text: str) -> bool:
    """An outward-facing question: not about the hub, not a command, not chit-chat."""
    t = (text or "").strip()
    return len(t.split()) >= 3 and bool(_QUESTION.match(t)) and not _HUB_WORDS.search(t)


_WRONG = re.compile(r"^(?:no,? )?(?:not that one|wrong (?:one|place)|other one|another one|"
                    r"different (?:one|place)|that'?s not (?:it|right|the one)|not (?:there|that place))\b", re.I)
_FOLLOW_UP = re.compile(
    r"^(?:so |ok |okay |hey )?(?:what did you (?:find|get|see)|any luck|did you find (?:it|anything|out)|"
    r"is it done|are you done|have you (?:got|found)|what(?:'s| is) the answer)\b", re.I)


# -- the procedures --------------------------------------------------------------
async def fetch_json(url: str, timeout: float = 8.0) -> dict:
    import aiohttp
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get(url, headers={"User-Agent": "AgentHub"}) as r:
                if r.status != 200:
                    raise ProcedureError(f"{host} answered {r.status}")
                return await r.json(content_type=None)
    except ProcedureError:
        raise
    except Exception as exc:
        raise ProcedureError(f"could not reach {host}: {str(exc)[:80]}")


_ALIAS = {"uk": "gb", "u.k.": "gb", "britain": "gb", "great britain": "gb",
          "us": "us", "usa": "us", "u.s.": "us", "america": "us"}


def _label(r: dict) -> str:
    return ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)


def _qualifies(r: dict, quals: "list[str]") -> bool:
    hay = " ".join(str(r.get(k) or "") for k in ("admin1", "admin2", "country", "country_code")).lower()
    tokens = set(re.findall(r"[a-z]+", hay))
    for q in quals:
        ql = q.lower().strip()
        want = _ALIAS.get(ql)
        if ql in hay or (want and want in tokens):
            continue
        return False
    return True


def _temp_unit(units: str) -> "tuple[str, str]":
    u = (units or "").lower()
    return ("fahrenheit", "°F") if ("fahr" in u or re.search(r"\bf\b", u)) else ("celsius", "°C")


def _machine_offset() -> "float | None":
    """This PC's current UTC offset in hours, or None if it cannot be told."""
    try:
        return datetime.now().astimezone().utcoffset().total_seconds() / 3600.0
    except Exception:
        return None


def _place_offset(r: dict) -> "float | None":
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(str(r.get("timezone"))).utcoffset(datetime.now()).total_seconds() / 3600.0
    except Exception:
        return None


_SWAPS = (("ea", "ai"), ("ai", "ea"), ("ee", "ea"), ("ea", "ee"), ("ie", "ei"), ("ei", "ie"), ("oo", "ou"), ("ou", "oo"),
          ("ay", "ai"), ("ai", "ay"), ("ade", "aid"), ("a", "e"), ("e", "a"), ("e", "i"), ("i", "e"), ("i", "y"), ("y", "i"), ("o", "ou"), ("c", "k"), ("k", "c"), ("ph", "f"))


def _vowel_variants(name: str, limit: int = 8) -> "list[str]":
    """Spellings a speech recogniser may have confused with this one, most likely first."""
    n, out = name.strip(), []
    low = n.lower()
    for a, b in _SWAPS:
        i = low.find(a)
        while i != -1 and len(out) < limit * 3:
            cand = n[:i] + b + n[i + len(a):]
            cand = cand[:1].upper() + cand[1:]
            if cand.lower() != low and cand not in out:
                out.append(cand)
            i = low.find(a, i + 1)
    return out[:limit]


def rank_places(found: "list[dict]", here: "float | None" = None) -> "list[dict]":
    """Order candidate places so the one most likely meant comes first.

    A name is rarely unique, and asking every time is worse than being usually
    right and saying which one it was. Nearest to this machine's own clock first
    - "Canterbury" from a PC on UK time is Kent, not New Hampshire - then the
    larger place, then the service's own order.
    """
    here = _machine_offset() if here is None else here

    def key(item):
        i, r = item
        off = _place_offset(r)
        gap = abs(off - here) if (off is not None and here is not None) else 99.0
        return (round(gap, 1), -(r.get("population") or 0), i)

    return [r for _, r in sorted(enumerate(found), key=key)]


async def _forecast(r: dict, inputs: dict, fetch) -> str:
    unit, sym = _temp_unit(str(inputs.get("units") or ""))
    wx = await fetch("https://api.open-meteo.com/v1/forecast?"
                     f"latitude={r['latitude']}&longitude={r['longitude']}"
                     f"&current=temperature_2m,weather_code,wind_speed_10m&temperature_unit={unit}")
    cur = wx.get("current") or {}
    try:
        temp, code, wind = cur["temperature_2m"], int(cur["weather_code"]), cur["wind_speed_10m"]
    except (KeyError, TypeError, ValueError):
        raise ProcedureError("the forecast service answered, but not in the shape expected")
    return f"{_label(r)}: {round(float(temp))}{sym}, {_WMO.get(code, 'unsettled')}, wind {round(float(wind))} km/h."


async def _weather(inputs: dict, fetch, skip: int = 0) -> "tuple[str, dict]":
    """Where, then what it is like there now. Returns the sentence and what it resolved.

    It answers with the best match and says which place that was. It does not
    ask: the first version asked whenever a name had several matches, and a reply
    of just "Maidstone" matched all of them, so it asked again, indefinitely.
    """
    where = str(inputs.get("location") or "").strip()
    parts = [p.strip() for p in where.split(",") if p.strip()]
    if not parts:
        raise ProcedureError("no place was given")
    name, quals = parts[0], parts[1:]
    geo = await fetch("https://geocoding-api.open-meteo.com/v1/search?name="
                      f"{quote(name)}&count=10&language=en&format=json")
    found = list(geo.get("results") or [])
    if quals:
        found = [r for r in found if _qualifies(r, quals)]
    guessed = ""
    if not found:
        # A speech recogniser swaps vowels ("Meadstone" for Maidstone). Try the usual swaps and say which one was taken.
        for alt in _vowel_variants(name):
            geo2 = await fetch("https://geocoding-api.open-meteo.com/v1/search?name="
                               f"{quote(alt)}&count=10&language=en&format=json")
            found = list(geo2.get("results") or [])
            if quals:
                found = [r for r in found if _qualifies(r, quals)]
            if found and str(found[0].get("name", "")).lower() == alt.lower():
                guessed = name
                break
            found = []
    if not found:
        raise ProcedureError(f"I could not find a place called {where!r}")
    ranked = rank_places(found)
    # Only places with the same name are real alternatives to each other.
    first_name = str(ranked[0].get("name", "")).lower()
    options = [r for r in ranked if str(r.get("name", "")).lower() == first_name]
    pick = options[min(skip, len(options) - 1)]
    say = await _forecast(pick, inputs, fetch)
    if guessed:
        say = f"I couldn't find \"{guessed}\", so I took it as {pick.get('name')}. " + say
    others = [o for o in options if o is not pick]
    if others and not quals:
        say += f" That's the one in {pick.get('admin1') or pick.get('country')}; say \"not that one\" for another."
    return say, {"label": _label(pick),
                 "options": [{"label": _label(o), "latitude": o.get("latitude"),
                              "longitude": o.get("longitude")} for o in options],
                 "index": min(skip, len(options) - 1)}


def _clock() -> str:
    now = datetime.now()
    return f"It's {now:%H:%M} on {now:%A} {now.day} {now:%B}."


async def execute(routine: dict, inputs: dict, fetch=None) -> "tuple[str, dict]":
    """Run a routine's procedure. Returns (what to say, what it resolved)."""
    kind = (routine.get("procedure") or {}).get("kind")
    if kind == "clock":
        return _clock(), {}
    if kind == "weather":
        return await _weather(inputs, fetch or fetch_json)
    raise ProcedureError(f"no procedure called {kind!r}")


# -- a question left open between turns ------------------------------------------
_PENDING: dict = {}


def _open(**kw) -> None:
    _PENDING.clear()
    _PENDING.update(kw, expires=time.time() + PENDING_TTL)


def _pending() -> "dict | None":
    if _PENDING and _PENDING.get("expires", 0) > time.time():
        return _PENDING
    _PENDING.clear()
    return None


def clear_pending() -> None:
    _PENDING.clear()


_LEAD = re.compile(r"^(?:it'?s|it is|i'?m in|i am in|i'?m at|in|at|my \w+ is|the one in|near)\s+", re.I)
_NEVER = re.compile(r"^(?:no|nope|nah|cancel|never ?mind|forget it|skip|stop)\b", re.I)


def _route(rung: int, name: str, routine: "str | None" = None, text: str = "") -> dict:
    try:
        from . import routing
        when = routing.read_trigger(text)
        when = when.get("kind", "manual") if isinstance(when, dict) else "manual"
    except Exception:
        when = "manual"
    return {"rung": rung, "name": name, "routine": routine, "when": when}


# -- the answer rung -------------------------------------------------------------
_JOBS: "dict[str, dict]" = {}
_LAST_JOB: "list[str]" = []


async def _agent(brief: str) -> str:
    """Hand a question to the researcher in the scratch workspace.

    No project, no worktree, no review: nothing is changed, so there is nothing
    to apply. A function of its own so tests can stand in for it.
    """
    from . import missions as M
    return await M.ask_scratch("researcher", brief, timeout=AGENT_TIMEOUT)


def _voice(text: str, limit: int = 560) -> str:
    """What reads well aloud: no markdown, no links' addresses, a bounded length."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    t = re.sub(r"[#*_`>]+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > 120 else cut.rstrip()) + " …"


def _brief(question: str, facts: dict) -> str:
    known = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items() if v)
    return ("Answer this question using the web if you need to. Reply with the answer only: at most "
            "three plain sentences, then one line 'Source: <address>'. Do not write any files and do "
            "not change anything.\n\nQuestion: " + question.strip()
            + (f"\n\nWhat the user has told the hub about themselves: {known}" if known else ""))


async def _answer_with_agent(text: str) -> dict:
    from . import user_facts as F
    jid = uuid.uuid4().hex[:6]
    task = asyncio.ensure_future(_agent(_brief(text, {k: v["value"] for k, v in F.load().items()
                                                       if isinstance(v, dict)})))
    _JOBS[jid] = {"question": text, "task": task, "started": time.time()}
    _LAST_JOB[:] = [jid]
    try:
        got = await asyncio.wait_for(asyncio.shield(task), AGENT_WAIT)
    except asyncio.TimeoutError:
        return {"say": "I've handed that to a research agent and it's still working. Ask me "
                       "\"what did you find\" in a moment.", "route": _route(3, "chat answer", None, text)}
    except Exception as exc:
        return {"say": f"I couldn't get an answer for that: {str(exc)[:120]}.",
                "route": _route(3, "chat answer", None, text)}
    return {"say": _voice(got) or "The research agent finished but had nothing to say.",
            "route": _route(3, "chat answer", None, text)}


def _follow_up() -> "dict | None":
    if not _LAST_JOB:
        return None
    job = _JOBS.get(_LAST_JOB[0])
    if not job:
        return None
    t = job["task"]
    if not t.done():
        return {"say": f"Still working on \"{job['question'][:60]}\" — "
                       f"{int(time.time() - job['started'])} seconds so far.",
                "route": _route(3, "chat answer")}
    try:
        return {"say": _voice(t.result()) or "It finished with nothing to say.",
                "route": _route(3, "chat answer")}
    except Exception as exc:
        return {"say": f"That didn't work: {str(exc)[:120]}.", "route": _route(3, "chat answer")}


# -- the one entry ---------------------------------------------------------------
_LAST: dict = {}          # the last place answered, so "not that one" has something to move off


async def _run(routine: dict, text: str, fetch=None, override: "dict | None" = None, skip: int = 0,
               quiet: bool = False) -> dict:
    from . import user_facts as F
    inputs: dict = {}
    polluted = False
    for key in routine.get("needs") or []:
        v = (override or {}).get(key) or slot(routine, key, text) or F.get(key)
        if v and key == "location":
            cleaned = F.clean_place(v) or v
            if cleaned != v and not (override or {}).get("location") and not slot(routine, key, text):
                polluted = True                            # the stored value was a sentence, not a place
            v = cleaned
        if not v:
            _open(kind="need", key=key, routine=routine["id"], text=text)
            return {"say": f"I need to know {F.KNOWN.get(key, {}).get('label', key)} for that. "
                           f"{F.question_for(key)} I'll remember it so I don't have to ask again.",
                    "route": _route(2, routine["title"], routine["id"], text), "asked": key}
        inputs[key] = v
    units = F.get("units")
    if units:
        inputs["units"] = units
    try:
        if (routine.get("procedure") or {}).get("kind") == "weather":
            say, resolved = await _weather(inputs, fetch or fetch_json, skip)
        else:
            say, resolved = await execute(routine, inputs, fetch)
    except ProcedureError as exc:
        if not quiet and "could not find a place" not in str(exc) and "no place was given" not in str(exc):
            record_failure(routine["id"], str(exc))
        return {"say": "", "failed": str(exc), "route": _route(2, routine["title"], routine["id"], text)}
    if polluted and resolved and resolved.get("label"):
        try:                                           # a remembered sentence that only worked after clean-up is stored clean
            F.remember("location", resolved["label"], how="asked")
        except Exception:
            pass
    shown = {k: v for k, v in inputs.items() if k != "units"}
    record_success(routine["id"], {**shown, **({"resolved": resolved["label"]} if resolved else {})}, say)
    if resolved and resolved.get("options"):
        _LAST.clear()
        _LAST.update(routine=routine["id"], text=text, options=resolved["options"],
                     index=resolved.get("index", 0), expires=time.time() + PENDING_TTL)
    return {"say": say, "route": _route(2, routine["title"], routine["id"], text),
            "routine": routine["id"], "resolved": (resolved or {}).get("label")}


_FOLLOW_LEAD = re.compile(r"^(?:and|so|what about|how about|what of|then|ok(?:ay)?|in|for|at)\s+", re.I)


async def _follow_place(text: str, fetch=None) -> "dict | None":
    if not _LAST or _LAST.get("expires", 0) < time.time():
        return None
    t = (text or "").strip(" .!?,")
    for _ in range(3):
        trimmed = _FOLLOW_LEAD.sub("", t)
        if trimmed == t:
            break
        t = trimmed
    words = t.split()
    if not 1 <= len(words) <= 4 or "?" in text and len(words) > 3:
        return None
    # An instruction is an instruction, whatever follows it.
    if _COMMANDISH.match(t) or re.search(
            r"\b(?:open|launch|start|play|stop|show|run|status|help|weather|time|yes|no|cancel|pause|resume|"
            r"apply|discard|retry|switch|enable|disable|turn|mission|ask|agent|automation|hub)\b", t, re.I):
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z' .,-]{1,40}", t):
        return None
    # Anything the hub already has a rule for is that rule's, not a place name.
    try:
        from . import voice as _V
        if _V.match_rules(text):
            return None
    except Exception:
        pass
    routine = get(_LAST["routine"])
    if not routine or not routine.get("needs"):
        return None
    # `quiet`: a short phrase that turns out not to be a place must not count
    # against the weather routine.
    got = await _run(routine, _LAST["text"], fetch, override={routine["needs"][0]: t}, quiet=True)
    return None if got.get("failed") else got


async def not_that_one(fetch=None) -> "dict | None":
    """"No, not that one": move to the next place with that name."""
    if not _LAST or _LAST.get("expires", 0) < time.time():
        return None
    routine = get(_LAST["routine"])
    if not routine:
        return None
    nxt = _LAST["index"] + 1
    if nxt >= len(_LAST["options"]):
        _LAST.clear()
        return {"say": "That was the last place I found with that name. Tell me the county or country.",
                "route": _route(2, routine["title"], routine["id"])}
    from . import user_facts as F
    pick = _LAST["options"][nxt]
    got = await _run(routine, _LAST["text"], fetch, override={"location": pick["label"]}, skip=0)
    if got.get("failed"):
        return got
    F.remember("location", pick["label"], how="asked")
    return got


def _pick(p: dict, text: str) -> "dict | None":
    """Which of the offered options this reply names - by number or by name."""
    t = (text or "").lower().strip(" .!?")
    opts = p.get("options") or []
    m = re.search(r"\b([1-9])\b", t) or re.search(r"\b(first|second|third)\b", t)
    if m:
        idx = {"first": 1, "second": 2, "third": 3}.get(m.group(1)) or int(m.group(1))
        if 1 <= idx <= len(opts):
            return opts[idx - 1]
    hits = [o for o in opts if t and t in o["label"].lower()]
    return hits[0] if len(hits) == 1 else None


async def find_place_in(text: str, fetch=None) -> "str | None":
    """The town a sentence names: "I'm basically in Kent these days" -> "Kent".

    Candidates are the phrases in the sentence, longest first; the first one a
    geocoder knows is the place. A mis-heard vowel gets the usual swaps once.
    """
    from . import user_facts as F
    fetch = fetch or fetch_json
    cleaned = F.clean_place(text)
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", cleaned)
    skip = {"i", "im", "i'm", "am", "in", "at", "the", "a", "an", "these", "days", "now", "basically", "currently",
            "live", "living", "near", "around", "from", "my", "is", "location", "it", "its", "it's", "town", "city", "please",
            "over", "there", "here", "somewhere", "about", "just", "still", "based", "up", "down", "out", "back"}
    single = len(words) == 1
    cands, seen = [], set()
    for n in (3, 2, 1):
        for i in range(0, len(words) - n + 1):
            chunk = words[i:i + n]
            if all(w.lower() in skip for w in chunk) or chunk[0].lower() in skip or chunk[-1].lower() in skip:
                continue
            c = " ".join(chunk)
            # A place is written with a capital. Without that, "over" in "over in Maidstone" is a town (Over).
            if not single and not chunk[0][:1].isupper():
                continue
            if c.lower() not in seen:
                seen.add(c.lower())
                cands.append(c)
    for c in cands[:8]:
        try:
            geo = await fetch("https://geocoding-api.open-meteo.com/v1/search?name="
                              f"{quote(c)}&count=3&language=en&format=json")
        except Exception:
            continue
        for r in (geo.get("results") or []):
            if str(r.get("name", "")).lower() == c.lower():
                return str(r["name"])
    if len(cands) == 1 or (cands and len(cands[-1].split()) == 1):
        for alt in _vowel_variants(cands[-1] if cands else cleaned)[:6]:
            try:
                geo = await fetch("https://geocoding-api.open-meteo.com/v1/search?name="
                                  f"{quote(alt)}&count=3&language=en&format=json")
            except Exception:
                continue
            for r in (geo.get("results") or []):
                if str(r.get("name", "")).lower() == alt.lower():
                    return str(r["name"])
    return None


async def ingest_by_name(name: str) -> dict:
    """Read an installed app's own files. A short answer: what it exposes, or why it cannot be read."""
    from . import rea_inspect as REA
    name = re.sub(r"^(?:the|an?)\s+|\s+(?:app|application)$", "", (name or "").strip(), flags=re.I).strip()
    if not name:
        return {"say": "Which app?", "route": _route(0, "know it")}
    async def work():
        return (await REA.ingest_installed(name))["summary"]
    jid = uuid.uuid4().hex[:6]
    task = asyncio.ensure_future(work())
    _JOBS[jid] = {"question": f"reading {name}", "task": task, "started": time.time()}
    _LAST_JOB[:] = [jid]
    try:
        said = await asyncio.wait_for(asyncio.shield(task), INGEST_WAIT)
    except asyncio.TimeoutError:
        return {"say": f"Still reading {name}. Ask me \"what did you find\" in a minute.",
                "route": _route(1, "ingest", None, name)}
    except ValueError as exc:
        return {"say": str(exc) + ".", "route": _route(0, "know it")}
    except RuntimeError as exc:
        return {"say": f"I could not read it: {str(exc)[:120]}", "route": _route(0, "know it")}
    return {"say": said, "route": _route(1, "ingest", None, name)}


async def answer_pending(text: str, fetch=None) -> "dict | None":
    """The reply to a question the hub left open, if that is what this is."""
    live = _pending()
    if not live:
        return None
    p = dict(live)                            # clear_pending() empties the original
    words = (text or "").split()
    if _NEVER.match((text or "").strip()):
        clear_pending()
        return {"say": "Okay, never mind.", "route": _route(0, "know it")}
    # Something that is itself a question is a new request, not the answer. The
    # first version took "what's the weather like today?", asked straight after
    # "where are you?", as the place - and stored it as the person's location.
    picked = _pick(p, text) if p.get("kind") == "choose" else None
    command = bool(_COMMANDISH.match((text or "").strip())) and picked is None
    if not command and picked is None:
        try:
            from . import pc_control as PC
            command = PC.classify_request(text) is not None
        except Exception:
            command = False
    if picked is None and (len(words) > 6 or "?" in (text or "") or command
                           or match(text) or looks_like_lookup(text)):
        clear_pending()
        return None
    from . import user_facts as F
    if p.get("kind") == "app":                       # an app was asked for and not named: the next words are the app
        clear_pending()
        then = p.get("then") or "ingest"
        name = re.sub(r"^(?:the|an?)\s+|\s+(?:app|application)$", "", (text or "").strip(" .!?,"), flags=re.I).strip()
        if then == "ingest":
            return await ingest_by_name(name)
        if then == "address":
            return {"say": f"Opening {name}.", "action": ("open_address", {"name": name}), "route": _route(1, "open", None, name)}
        return {"say": f"Opening {name}.", "action": ("pc_app", {"app": name, "request": text, "then": ""}),
                "route": _route(1, "open", None, name)}
    if p.get("kind") == "fact":                      # "which town?" was asked: the answer is the place
        clear_pending()
        place = await find_place_in(text) or F.clean_place(text)
        if not place:
            return {"say": "I didn't catch the town.", "route": _route(0, "know it")}
        return {"say": f"Save {place} as your location?", "action": ("remember_fact", {"key": "location", "value": place}),
                "route": _route(0, "know it")}
    routine = get(p.get("routine"))
    if not routine:
        clear_pending()
        return None
    if p["kind"] == "need":
        value = (text or "").strip()
        for _ in range(3):
            trimmed = _LEAD.sub("", value)
            if trimmed == value:
                break
            value = trimmed
        value = value.strip(" .!?,")
        if p["key"] == "location":
            value = F.clean_place(value)
        if not value:
            return None
        clear_pending()
        # Look it up *before* remembering anything. The first version stored the
        # bare typed name, so a place that matched several things was kept in its
        # ambiguous form and asked about on every later request.
        got = await _run(routine, p["text"], fetch, override={p["key"]: value})
        if got.get("failed"):
            return await _after_failure(routine, p["text"], got)
        try:
            F.remember(p["key"], got.get("resolved") or value, how="asked")
        except ValueError as exc:
            return {"say": str(exc), "route": _route(0, "know it")}
        got["say"] = f"Noted \u2014 {p['key'].replace('_', ' ')}: {got.get('resolved') or value}. " + got["say"]
        return got
    if p["kind"] == "choose":
        if picked is None:
            return {"say": "Say the number, or part of the name.",
                    "route": _route(2, routine["title"], routine["id"])}
        F.remember(p["key"], picked["label"], how="asked")
        clear_pending()
        got = await _run(routine, p["text"], fetch)
        if got.get("failed"):
            return await _after_failure(routine, p["text"], got)
        return got
    clear_pending()
    return None


async def _after_failure(routine: dict, text: str, got: dict, allow_agent: bool = True) -> dict:
    """The procedure failed. Say so, and let an agent try - never a silent gap."""
    failed = str(got.get("failed", ""))
    if "could not find a place" in failed or "no place was given" in failed:
        import re as _re
        said = _re.search(r"called '(.+?)'", failed)
        _open(kind="need", key="location", routine=routine["id"], text=text)
        return {"say": (f"I couldn't find \"{said.group(1)}\". Which town?" if said else "Which town?"),
                "route": got.get("route"), "asked": "location"}
    if allow_agent and (looks_like_lookup(text) or routine.get("intent")):
        out = await _answer_with_agent(text)
        out["say"] = f"My {routine['title'].lower()} routine failed ({got.get('failed', '')[:80]}). " + out["say"]
        return out
    return {"say": f"That didn't work: {got.get('failed', '')[:120]}.", "route": got.get("route")}


async def handle(text: str, fetch=None, allow_agent: bool = True) -> "dict | None":
    """Answer, ask, or return None to leave it to the model.

    Order is the point: a routine that can do it deterministically always beats
    asking an agent, and an agent always beats an open model call.
    `allow_agent=False` is "no model, no agent" - used by tests and by anything
    that must stay deterministic.
    """
    t = (text or "").strip()
    if not t:
        return None
    follow = _FOLLOW_UP.match(t)
    if follow:
        return _follow_up()
    if _WRONG.match(t):
        moved = await not_that_one(fetch)
        if moved:
            return moved
    # Straight after an answer about a place, a bare place - "Leeds", "and in
    # York?" - means the same question for that place. Without this the reply
    # was "I did not catch a command", which read as the hub getting stuck.
    followed = await _follow_place(t, fetch)
    if followed:
        return followed
    routine = match(t)
    if routine:
        if routine.get("status") == "disabled":
            if not allow_agent:
                return {"say": f"My {routine['title'].lower()} routine is switched off after failing.",
                        "route": _route(2, routine["title"], routine["id"], t)}
            out = await _answer_with_agent(t)
            out["say"] = f"My {routine['title'].lower()} routine is switched off after failing. " + out["say"]
            return out
        got = await _run(routine, t, fetch)
        if got.get("failed"):
            return await _after_failure(routine, t, got, allow_agent)
        trig = (got.get("route") or {}).get("when")
        if trig and trig != "manual" and got.get("say") and not got.get("asked"):
            got["say"] += " (You asked for that on a schedule — I've answered once. Keeping it as a recurring automation is done from the Automations page.)"
        return got
    if allow_agent and looks_like_lookup(t):
        return await _answer_with_agent(t)
    return None


# -- the local model is not left running for nothing -----------------------------
async def _idle_loop() -> None:
    """Stop the Ollama this hub started once nothing has needed it for a while.

    Open conversation still works with it - it is started again on demand - but
    a routine that has earned trust answers without it, so there is no reason to
    keep a model resident on a machine that is also used to play games.
    """
    from . import missions as M
    while True:
        await asyncio.sleep(60)
        try:
            await M.stop_ollama_if_idle()
        except Exception as exc:
            logger.info("converse: idle check failed: %s", exc)


def setup(app: web.Application) -> None:
    async def _start(a):
        a["ollama_idle_task"] = asyncio.create_task(_idle_loop())

    async def _stop(a):
        t = a.get("ollama_idle_task")
        if t:
            t.cancel()

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)


# -- http ------------------------------------------------------------------------
@routes.post("/api/converse/ask")
async def api_ask(request: web.Request) -> web.Response:
    """Put a question to the router directly. TALK and the Missions thread reach
    the same code through `voice.chat`; this is for tests and automations."""
    try:
        b = await request.json()
    except Exception:
        b = {}
    text = str(b.get("text") or "").strip()[:500]
    if not text:
        raise web.HTTPBadRequest(text="no text")
    got = (await answer_pending(text)) or (await handle(text))
    return web.json_response({"say": (got or {}).get("say"), "route": (got or {}).get("route"),
                              "answered": got is not None})


@routes.get("/api/info-routines")
async def api_list(request: web.Request) -> web.Response:
    """What the hub knows how to look up, how well it has gone, and when."""
    return web.json_response({"routines": [
        {k: r.get(k) for k in ("id", "title", "intent", "kind", "status", "successes",
                               "failures", "needs", "log")} for r in load()]})


@routes.post("/api/info-routines/{id}/status")
async def api_status(request: web.Request) -> web.Response:
    """Switch one off, or put a disabled one back to candidate. Never to trusted:
    trust is earned from results, not granted by a button."""
    try:
        b = await request.json()
    except Exception:
        b = {}
    status = str(b.get("status") or "")
    if status not in ("disabled", "candidate"):
        raise web.HTTPBadRequest(text="status must be 'disabled' or 'candidate'")
    if not get(request.match_info["id"]):
        raise web.HTTPNotFound(text="no such routine")

    def go(r):
        r["status"] = status
        r["streak_fail"] = 0
        if status == "candidate":
            r["successes"] = 0
    _update(request.match_info["id"], go)
    return web.json_response({"ok": True})
