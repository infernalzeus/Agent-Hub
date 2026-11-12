"""TALK PC-control router: a small, auditable routine store over Windows MCP."""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from ..runtime import STATE
from . import mcp as MCP

# One stop signal for everything that acts on this PC (the desktop agent, a routine being replayed, an app being opened). A task remembers the
# number when it starts and ends itself the moment the number has moved: STOP in Talk, closing the Talk panel, and switching PC control off all move it.
_STOP = {"gen": 0, "at": 0.0}


def stop_all() -> int:
    _STOP["gen"] += 1
    _STOP["at"] = time.time()
    logger.info("pc_control: stop requested; running PC tasks will end at their next step")
    return _STOP["gen"]


def stop_gen() -> int:
    return _STOP["gen"]


STOPPED = {"ok": False, "route": "stopped", "say": "Stopped."}

routes = web.RouteTableDef()
# Learned routines are per-machine state, not part of the program.
DB_PATH = STATE / "data" / "pc_control.sqlite"


def canonical_app_name(value: str) -> str:
    """Normalise spoken app names before they become routine parameters or keys."""
    app = " ".join((value or "").casefold().split())
    app = __import__("re").sub(r"^(?:the )|(?: for me| please| app| application)$", "", app).strip()
    return app[:80]


def display_app_name(app: str) -> str:
    return " ".join(part.capitalize() for part in canonical_app_name(app).split())


# People do not speak in commands. "Can you open Apple Music for me and play the
# ADHD playlist?" is the same request as "open apple music", and a fullmatch on
# the whole sentence recognises only the second - so the first fell through to a
# model, which returned nothing, and the hub said it could not help. The pattern
# finds the verb anywhere, takes the name after it, and stops at whatever the
# sentence does next.
_OPEN_RX = __import__("re").compile(
    r"\b(?:open|launch|start|fire up|bring up|put on)\s+(?:up\s+)?(?:the\s+)?"
    r"([a-z0-9][a-z0-9 '&.+-]{1,60}?)"
    r"(?=\s*(?:$|[,.;!?]|\band\b|\bthen\b|\bfor me\b|\bplease\b|\bso\b|\bto\b|\bwith\b))",
    __import__("re").I)

# Politeness and conjunctions that sit between the app name and the real
# second request: "open X FOR ME AND play Y" -> the ask is "play Y".
_LEADING = __import__("re").compile(
    r"^(?:for me|please|and|then|to|so that|so|can you|could you|would you)\b\s*",
    __import__("re").I)

# Left over when somebody trails off: not applications.
_NOT_A_NAME = {"the", "a", "an", "it", "that", "this", "one", "up", "something", "anything"}

# "Open their latest video" is not an application. Sending it to the launcher costs a read of the whole Start
# menu to find that out, and ends in "I can't find an app called 'their latest video'". Not "our" or "my": "open
# our music" is the recogniser's way of writing "Apple Music".
_NOT_AN_APP = __import__("re").compile(
    r"^(?:(?:their|his|her|its|that|this|those|these|the same)\b|"
    r"(?:the\s+)?(?:latest|newest|first|second|third|next|previous|last|top)\b.*\b"
    r"(?:video|song|track|playlist|album|episode|file|tab|link|page|message|email|result)s?\b)",
    __import__("re").I)

# Words that end up glued to an app name when somebody is being polite.
_TRAILING = __import__("re").compile(
    r"\s*\b(?:for me|please|now|again|up|app|application|program)\b\s*$", __import__("re").I)


# "Play some songs from my Apple Music" has no "open" in it, and "open the playlist ADHD on Apple Music" has the app at the
# END: read as one name it became an app called "playlist adhd on apple music" that the launcher fuzzily matched to Apple
# Music, and the playlist was dropped (the 2 Nov transcript). The app is the last "on/in/from X"; what comes before it is the ask.
_ACT_ON_RX = __import__("re").compile(
    r"\b((?:play|put on|shuffle|queue|search for|search|find|pause|skip|add|download|show)\b[^,.;!?]*?)\s+"
    r"(?:on|in|from|using|through|via|inside)\s+(?:my\s+|the\s+)?([a-z0-9][a-z0-9 '&.+-]{1,40}?)\s*[.?!]*$",
    __import__("re").I)
_THING_FIRST = __import__("re").compile(
    r"^(?:(?:the|my)\s+)?(?:playlist|song|track|album|artist|folder|file|document|tab|channel|video|page|project|chat|library|music)s?\b"
    r"|^(?:some|any)\s+\w+",
    __import__("re").I)
_ON_APP_RX = __import__("re").compile(
    r"^(.+?)\s+(?:on|in|from|using|through|via|inside)\s+(?:my\s+|the\s+)?([a-z0-9][a-z0-9 '&.+-]{1,40})$", __import__("re").I)


def _trim_name(name: str) -> str:
    for _ in range(3):                       # "apple music for me please" -> "apple music"
        trimmed = _TRAILING.sub("", name)
        if trimmed == name:
            break
        name = trimmed
    return name


_TEACH_RX = __import__("re").compile(
    r"^(?:(?:hey )?smith[, ]*)?(?:(?:can|could|would) you |please )*(?:record|learn|teach yourself|teach you|remember|save)\s+"
    r"(?:(?:a|the|this)\s+)?(?:routine\s+|macro\s+|way\s+|how\s+)?(?:for|to|of)?\s*(.+?)[.?!]*$", __import__("re").I)
_GERUND = {"playing": "play", "opening": "open", "searching": "search", "finding": "find", "starting": "start", "shuffling": "shuffle",
           "pausing": "pause", "queueing": "queue", "downloading": "download", "showing": "show", "adding": "add"}


def untaught(text: str) -> str:
    """"record a routine for playing the ADHD playlist" -> "play the ADHD playlist". The Hub learns a task by doing it once
    and checking it worked, so asking it to learn one is asking it to do it. Returns the text unchanged when it is not that."""
    m = _TEACH_RX.match(" ".join((text or "").split()))
    if not m:
        return text
    inner = m.group(1).strip()
    first, _, rest = inner.partition(" ")
    inner = (_GERUND.get(first.casefold(), first) + (" " + rest if rest else "")).strip()
    return inner if len(inner) >= 4 else text


def classify_request(text: str) -> dict | None:
    """Classify a spoken or typed request into a task, before any routine is looked up.

    Returns the app to open and, when the sentence carried on, what was asked
    *after* it - "play the ADHD playlist" is a second step, not part of the name.
    """
    import re
    t = " ".join((text or "").casefold().split())
    m = _OPEN_RX.search(t)
    if m and (on := _ON_APP_RX.match(m.group(1))) and _THING_FIRST.match(on.group(1)):
        app = canonical_app_name(_trim_name(on.group(2)))
        if len(app) >= 2 and app not in _NOT_A_NAME:
            then = t[m.start():m.start(1) + len(on.group(1))].strip()          # "open the playlist adhd", "put on some music"
            more = _LEADING.sub("", t[m.end():].strip(" ,.;!?")).strip()
            more = _TRAILING.sub("", more).strip()
            if len(more) >= 3:                                                # "... and shuffle it": the rest of the sentence goes with it
                then += " and " + more
            return {"kind": "launch_app", "app": app, "intent": _intent(app), "then": then, "explicit": True}
    if not m:
        act = _ACT_ON_RX.search(t)
        if not act:
            return None
        app = canonical_app_name(_trim_name(act.group(2)))
        if len(app) < 2 or app in _NOT_A_NAME or _NOT_AN_APP.search(act.group(2)):
            return None
        return {"kind": "launch_app", "app": app, "intent": _intent(app), "then": act.group(1).strip(), "explicit": True}
    name = m.group(1)
    name = _trim_name(name)
    app = canonical_app_name(name)
    # "open the" must not resolve to an application called "the".
    if len(app) < 2 or app in _NOT_A_NAME or _NOT_AN_APP.search(name):
        return None
    rest = t[m.end():].strip(" ,.;!?")
    for _ in range(3):                   # "for me and play X" -> "play X"
        shorter = _LEADING.sub("", rest).strip()
        if shorter == rest:
            break
        rest = shorter
    rest = _TRAILING.sub("", rest).strip()
    return {"kind": "launch_app", "app": app, "intent": _intent(app),
            "then": rest if len(rest) >= 3 else ""}


# Words that are also installed apps' names ("Photos", "Mail", "Clock"): a sentence is not about those unless it says "open".
_COMMON_APP_WORDS = {"photos", "mail", "clock", "calendar", "camera", "maps", "weather", "news", "store", "settings", "movies", "calculator",
                     "files", "music", "video", "paint", "notes", "people", "phone", "tips", "help", "edge", "chrome", "browser", "google",
                     "youtube", "firefox", "terminal", "windows", "search", "voice", "recorder", "sound", "games", "xbox", "teams"}
_ACTION_START = re.compile(r"^(?:(?:hey )?smith[, ]*)?(?:(?:can|could|would) you |please |i want you to |i'd like you to )*"
                           r"(?:play|put on|shuffle|queue|search|find|look up|show|add|download|pause|skip|open|press|click|type|select|start)\b", re.I)
_MUSIC_APP = re.compile(r"music|spotify|itunes|vlc|foobar|winamp|tidal|deezer|groove|musicbee|aimp", re.I)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").casefold())


def mentioned_app(text: str, names: "list[str]") -> str:
    """The installed app a sentence is about, by name ("search Apple Music for Daft Punk" -> "apple music"), or "".

    Longest name wins. Names that are also everyday words are left out (see _COMMON_APP_WORDS)."""
    t = " " + re.sub(r"[^a-z0-9&+.' -]+", " ", (text or "").casefold()) + " "
    best = ""
    for n in names or []:
        k = canonical_app_name(n)
        if len(k) < 5 or k in _COMMON_APP_WORDS or len(k) <= len(best):
            continue
        if f" {k} " in t or f" {k}'s " in t:
            best = k
    return best


def default_music_app(names: "list[str]", playing: "list[dict] | None" = None) -> str:
    """Which app "play the ADHD playlist" means when it does not say: the one playing or paused right now, else the music app
    that has been opened most often."""
    for m in playing or []:
        sq = _squash(m.get("app"))
        for n in names or []:
            if _squash(n) and _squash(n) in sq:
                return canonical_app_name(n)
    best, top = "", 0
    for app, n in _launch_history().items():
        if _MUSIC_APP.search(app) and n > top:
            best, top = app, n
    return canonical_app_name(best)


def strip_mention(text: str, app: str) -> str:
    """The ask without the app and the politeness around it: "can you search Apple Music for Daft Punk?" -> "search for daft punk"."""
    t = " ".join((text or "").casefold().split())
    t = re.sub(r"\b(?:on|in|from|using|with|through|inside|within|at|via)?\s*(?:my\s+|the\s+)?" + re.escape(app) + r"(?:'s)?\b", " ", t, count=1)
    t = re.sub(r"^(?:(?:hey )?smith[, ]*)?(?:(?:can|could|would) you |please |i want you to |i'd like you to )+", "", t.strip())
    t = re.sub(r"\b(?:for me|please)\b", " ", t)
    return " ".join(t.strip(" ,.;!?").split())


async def mention_task(text: str, playing: "list[dict] | None" = None) -> "dict | None":
    """A task for a sentence that names an installed app without the "open ... on ..." shape, or an app-less "play ..." (the app is then
    the one already playing, or the most-used music app). None when the sentence is about neither."""
    if not _ACTION_START.match(" ".join((text or "").casefold().split())):
        return None
    names = await start_app_names()
    if not names:
        return None
    app = mentioned_app(text, names)
    why = "mentioned"
    if not app and re.match(r"^(?:(?:can|could|would) you |please )*(?:play|put on|shuffle|queue)\b", " ".join(text.casefold().split())):
        app, why = default_music_app(names, playing), "default music app"
    if not app:
        return None
    then = strip_mention(text, app) if why == "mentioned" else " ".join(text.casefold().split()).strip(" ?.!")
    then = re.sub(r"^(?:(?:can|could|would) you |please )+", "", then)
    if len(then) < 3:
        return None
    return {"kind": "launch_app", "app": app, "intent": _intent(app), "then": then, "why": why}


def _consolidate_launch_routines(db: sqlite3.Connection) -> None:
    """Merge pre-classifier routine keys such as 'open:outlook for me' into 'open:outlook'."""
    rows = list(db.execute("SELECT * FROM pc_routines WHERE tool='App'"))
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        try:
            app = canonical_app_name(json.loads(row["args_json"]).get("name", ""))
        except Exception:
            continue
        if app:
            groups.setdefault(_intent(app), []).append(row)
    for intent, same in groups.items():
        if len(same) == 1 and same[0]["intent"] == intent:
            continue
        same.sort(key=lambda r: (r["intent"] != intent, r["created"]))
        keep, rest = same[0], same[1:]
        app = intent.split(":", 1)[1]
        successes = sum(int(r["successes"]) for r in same)
        failures = sum(int(r["failures"]) for r in same)
        status = "trusted" if any(r["status"] == "trusted" for r in same) else "candidate"      # merging duplicates never promotes; it keeps what a person decided
        args = json.dumps({"mode": "launch", "name": display_app_name(app)})
        signature = json.dumps({"kind": "start_menu_app", "name": display_app_name(app)})
        for row in rest:
            db.execute("DELETE FROM pc_routines WHERE id=?", (row["id"],))
        db.execute("UPDATE pc_routines SET intent=?,title=?,args_json=?,signature_json=?,status=?,successes=?,failures=?,updated=? WHERE id=?", (intent, f"Open {display_app_name(app)}", args, signature, status, successes, failures, time.time(), keep["id"]))


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS pc_runs (
              id INTEGER PRIMARY KEY, created REAL NOT NULL, request TEXT NOT NULL,
              route TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pc_routines (
              id TEXT PRIMARY KEY, intent TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
              tool TEXT NOT NULL, args_json TEXT NOT NULL, signature_json TEXT NOT NULL,
              status TEXT NOT NULL, successes INTEGER NOT NULL DEFAULT 0,
              failures INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pc_steps (
              id INTEGER PRIMARY KEY, routine_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
              tool TEXT NOT NULL, args_json TEXT NOT NULL, target_json TEXT NOT NULL,
              created REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pc_steps_routine ON pc_steps(routine_id, ordinal);
        """)
        # 'mcp' = driven through Windows MCP and resolved semantically.
        # 'machine' = recorded from the screen surface (Phase 3); not written yet.
        if "kind" not in {c[1] for c in db.execute("PRAGMA table_info(pc_routines)")}:
            db.execute("ALTER TABLE pc_routines ADD COLUMN kind TEXT NOT NULL DEFAULT 'mcp'")
        if "approved" not in {c[1] for c in db.execute("PRAGMA table_info(pc_routines)")}:
            # 12 Nov: every routine that had two clean runs was promoted to trusted by this file itself, on every open. Trust is a person's decision (PROMOTE / DEMOTE in the routines
            # panel), so the promotion is gone, and what it had granted is withdrawn once: every routine starts again as a candidate.
            db.execute("ALTER TABLE pc_routines ADD COLUMN approved INTEGER NOT NULL DEFAULT 0")
            db.execute("UPDATE pc_routines SET status='candidate' WHERE status='trusted'")
        if "note" not in {c[1] for c in db.execute("PRAGMA table_info(pc_routines)")}:
            db.execute("ALTER TABLE pc_routines ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        if "level" not in {c[1] for c in db.execute("PRAGMA table_info(pc_runs)")}:
            db.execute("ALTER TABLE pc_runs ADD COLUMN level TEXT NOT NULL DEFAULT ''")
        _consolidate_launch_routines(db)
        yield db
        db.commit()
    finally:
        db.close()


def _intent(app: str) -> str:
    return "open:" + canonical_app_name(app)


# The lowest level that did the job, recorded with each run. Order of preference:
#   api      the application's own entry point (a Start-menu launch, a URI scheme)
#   ui-tree  a named control found in the UI Automation tree and pressed
#   pointer  a recorded position inside a window
#   vision   an image matched on screen
LEVELS = ("api", "ui-tree", "pointer", "vision")


def _record_run(request: str, route: str, status: str, detail: str, level: str = "") -> None:
    with _db() as db:
        db.execute("INSERT INTO pc_runs(created,request,route,status,detail,level) VALUES(?,?,?,?,?,?)",
                   (time.time(), request, route, status, detail[:1000], level if level in LEVELS else ""))


def _remember_launch(app: str, success: bool) -> dict:
    intent = _intent(app); now = time.time()
    rid = hashlib.sha256(intent.encode()).hexdigest()[:16]
    args = {"mode": "launch", "name": display_app_name(app)}
    signature = {"kind": "start_menu_app", "name": display_app_name(app)}
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, updated=? WHERE id=?", (int(success), int(not success), now, row["id"]))
            return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())
        if not success:
            return None
        db.execute("INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,successes,failures,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (rid, intent, f"Open {display_app_name(app)}", "App", json.dumps(args), json.dumps(signature), "candidate", 1, 0, now, now))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


def _routine(intent: str) -> dict | None:
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE intent=? AND status!='disabled'", (intent,)).fetchone()
    return dict(row) if row else None


# ── knowing what is installed, and what was meant ──────────────────────────────────────────────────────────────────────
# "Open Apple Music" arrived as "open our music". Windows answered
# `Our Music not found in start menu.` as an ordinary return value - not an
# error - and the launcher below treated "no exception" as "it worked": it said
# "Opened Our Music", recorded the run as done, and created a routine for an
# application that does not exist. Three separate faults, all in the same
# place: the name was never checked against what is installed, the answer was
# never read, and success was inferred from the absence of an error.
#
# So: the heard name is resolved against the Start menu first (deterministic,
# local, no model); Windows' own answer is read; and nothing is remembered
# until a window for the thing has actually been seen.

_START_APPS: dict = {"at": 0.0, "names": []}
_START_TTL = 600.0
# Entries in the Start menu that are not what anyone means by "open X".
_JUNK_NAME = re.compile(r"\b(uninstall|reset preferences|release notes|readme|license|documentation|"
                        r"help|website|web site|manual|changelog)\b", re.I)


async def start_app_names(force: bool = False) -> "list[str]":
    """What can be launched by name on this PC. Cached for ten minutes.

    Empty off Windows or when the listing fails; callers then fall back to
    passing the name through, which is what happened before this existed.
    """
    now = time.time()
    if not force and _START_APPS["names"] and now - _START_APPS["at"] < _START_TTL:
        return _START_APPS["names"]
    if os.name != "nt":
        return []
    cmd = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
           "Get-StartApps | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress")
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        raw = json.loads(out.decode("utf-8", "replace").strip() or "[]")
        names = [raw] if isinstance(raw, str) else [str(n) for n in raw]
    except Exception as exc:
        logger.info("pc_control: could not list Start menu apps: %s", exc)
        return _START_APPS["names"]
    seen, clean = set(), []
    for n in names:
        key = n.casefold().strip()
        if key and key not in seen and not _JUNK_NAME.search(n):
            seen.add(key)
            clean.append(n.strip())
    _START_APPS.update(at=now, names=clean)
    return clean


def _words(text: str) -> "list[str]":
    return re.findall(r"[a-z0-9]+", (text or "").casefold())


def _token_sim(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def score_name(heard: str, name: str) -> float:
    """How well a spoken name fits one installed name, 0..1.

    Whole words first, because a transcription error usually damages one word and
    leaves the others intact: "our music" is wrong in "our" and exact in "music".
    """
    h, n = _words(heard), _words(name)
    if not h or not n:
        return 0.0
    if h == n:
        return 1.0
    if all(w in n for w in h):                       # "outlook" -> "Outlook (classic)"
        return 0.92 - 0.02 * max(0, len(n) - len(h))
    if all(w in h for w in n):                       # "open the calculator app"
        return 0.88
    total, weight = 0.0, 0
    for w in h:
        best = max(_token_sim(w, x) for x in n)
        total += best * len(w)
        weight += len(w)
    sim = total / max(weight, 1)
    # Unmatched words in the installed name count against it, lightly.
    missed = sum(1 for x in n if max(_token_sim(x, w) for w in h) < 0.6)
    # A transcription error damages one word and leaves the distinctive one
    # alone, so a whole-word hit on a real word is strong evidence by itself.
    exact = sum(1 for w in h if len(w) >= 4 and w in n)
    return min(0.97, max(0.0, sim - 0.05 * missed) + 0.15 * min(exact, 1))


def _launch_history() -> "dict[str, int]":
    """How often each application has actually been launched, from the run log.

    A tie-breaker only: a name you have opened thirty times is more likely to be
    what a garbled "our music" meant than one you have never opened.
    """
    out: "dict[str, int]" = {}
    try:
        with _db() as db:
            for r in db.execute("SELECT detail, COUNT(*) AS n FROM pc_runs WHERE status='done' "
                                "AND detail LIKE '% launched.' GROUP BY detail"):
                out[re.sub(r"\s+launched\.$", "", r["detail"]).casefold()] = int(r["n"])
    except Exception:
        pass
    return out


def resolve_app(heard: str, names: "list[str]", usage: "dict | None" = None) -> dict:
    """Decide what an installed-app name was meant, and how sure that is.

    status: exact   - it is installed under that name
            likely  - one clear winner; launch it and say the corrected name
            ask     - a plausible guess, not safe to act on unconfirmed
            unknown - nothing installed fits; do not launch anything
    """
    usage = usage or {}
    scored = []
    for name in names:
        s = score_name(heard, name)
        if s <= 0:
            continue
        s = min(1.0, s + 0.05 * min(usage.get(name.casefold(), 0), 5) / 5)
        scored.append((s, name))
    scored.sort(key=lambda t: (-t[0], len(t[1])))
    if not scored:
        return {"status": "unknown", "heard": heard, "options": []}
    top, name = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    options = [n for _, n in scored[:3]]
    if top >= 0.98:
        return {"status": "exact", "name": name, "score": top, "heard": heard, "options": options}
    if top >= 0.60 and top - second >= 0.15:
        return {"status": "likely", "name": name, "score": top, "heard": heard, "options": options}
    if top >= 0.55:
        return {"status": "ask", "name": name, "score": top, "heard": heard, "options": options}
    return {"status": "unknown", "heard": heard, "options": [n for s, n in scored[:3] if s >= 0.3]}


def vocabulary_prompt(limit: int = 60) -> str:
    """Words to bias speech recognition toward, so "Apple Music" is not "our music".

    Whisper takes a prompt of expected vocabulary; giving it the names actually
    installed is the cheapest accuracy gain there is.
    """
    names = _START_APPS.get("names") or []
    used = _launch_history()
    ranked = sorted(names, key=lambda n: (-used.get(n.casefold(), 0), len(n)))
    return ", ".join(ranked[:limit])


def _opened_windows(snapshot_text: str) -> "list[str]":
    """Window titles from the 'Opened Windows' table at the top of a Snapshot."""
    head = (snapshot_text or "").split("UI Tree:")[0]
    out = []
    for line in head.splitlines():
        m = re.match(r"^\s*(.+?)\s{2,}\d+\s+(?:Normal|Minimized|Maximized)\b", line)
        if m:
            out.append(m.group(1).strip())
    return out


async def _window_for(name: str) -> bool:
    """Is there a window for this application right now? Reads, never clicks."""
    try:
        res = await MCP.call_tool("windows", "Snapshot", {"use_vision": False, "use_ui_tree": False})
        titles = _opened_windows(snapshot_text(res))
    except Exception as exc:
        logger.info("pc_control: could not list windows: %s", exc)
        return False
    want = _words(name)
    return any(all(w in _words(t) for w in want) or name.casefold() in t.casefold() for t in titles)


def clean_then(then: str, app: str = "") -> str:
    """The rest of the sentence after the app name, without leftover punctuation, and nothing at all when it only says open the app again.

    "Open Notepad, please. Open Notepad." used to leave ". open notepad" as a task INSIDE Notepad: the agent spent 38 s clicking in a window it could not read."""
    rest = re.sub(r"^[\s.,;:!?-]+", "", then or "").strip()
    name = re.escape(canonical_app_name(app))
    if re.fullmatch(r"(?:please[ ,.]*)?(?:(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?" + name + r"(?:\s+app)?)?[ ,.!]*(?:please)?[ .!]*", rest, re.I):
        return ""
    return rest


def _start_ids_file():
    return STATE / "data" / "start_ids.json"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").casefold())


def _start_id(name: str) -> str:
    """The Start menu's own id for an app ("AppleInc.AppleMusicWin_...!App"): what Windows itself launches when you click its tile. Read once with Get-StartApps (a second or two), kept on disk."""
    key = _norm(name)
    try:
        cache = json.loads(_start_ids_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if cache.get(key):
        return cache[key]
    import subprocess
    env = {**os.environ, "HUB_APP_NAME": name}
    script = ("$n=$env:HUB_APP_NAME; $m=@(Get-StartApps | Where-Object { $_.Name -eq $n }); if($m.Count -eq 0){ $m=@(Get-StartApps | Where-Object { $_.Name -like \"*$n*\" }) }; "
              "if($m.Count -ge 1){ $m[0].AppID }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=20, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return ""
    sid = out[0].strip() if out else ""
    if sid:
        try:
            _start_ids_file().parent.mkdir(parents=True, exist_ok=True)
            cache[key] = sid
            _start_ids_file().write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except OSError:
            pass
    return sid


def _is_window_of(win: dict, name: str) -> bool:
    """Is this open window that app's? Its program is named like the app, or its whole title is the app's name, or starts with it as a heading, or ends with it after a dash
    ("Document - Notepad"). Not merely a title that mentions it."""
    want = _norm(name)
    if not want:
        return False
    if _norm((win.get("exe") or "").casefold().replace(".exe", "")) == want:
        return True
    raw = (win.get("title") or "").strip()
    n = re.escape(name.strip())
    return bool(re.fullmatch(n, raw, re.I) or re.match(n + r"\s*(?:[-–—|:]|$)", raw, re.I) or re.search(r"[-–—|]\s*" + n + r"$", raw, re.I))


async def _fast_open(name: str) -> "dict | None":
    """Open an app the way a person's click does, without the 14 s the Windows tool took for Apple Music: if its window is already open, bring it forward (instant); else start it by its
    Start-menu id and wait on the window itself (so the wait is the app's own start-up, not ours). Returns what was done, or None when this cannot be done (not Windows, id unknown,
    window never came up) and the old way should run."""
    if sys.platform != "win32":
        return None
    from . import window_mirror as WM

    async def window():
        for w in await asyncio.to_thread(WM.list_windows):
            if _is_window_of(w, name):
                return w
        return None
    t0 = time.time()
    w = await window()
    if w:
        await asyncio.to_thread(WM.focus, int(w["id"]))
        return {"how": "its window was already open: brought it forward", "ms": int((time.time() - t0) * 1000), "id": ""}
    sid = await asyncio.to_thread(_start_id, name)
    if not sid:
        return None
    try:
        os.startfile(f"shell:AppsFolder\\{sid}")                      # noqa: S606 - Windows: what the Start menu tile does
    except OSError as exc:
        logger.info("pc_control: could not start %r by its Start-menu id: %s", name, exc)
        return None
    g0 = stop_gen()
    for _ in range(100):                                              # up to 25 s for a cold start; Apple Music needs a few seconds of its own
        await asyncio.sleep(0.25)
        if stop_gen() != g0:
            return None
        w = await window()
        if w:
            await asyncio.to_thread(WM.focus, int(w["id"]))
            return {"how": f"started it by its Start-menu id and its window came up after {time.time() - t0:.1f} s", "ms": int((time.time() - t0) * 1000), "id": sid}
    return None


async def launch_app(app: str, request: str, then: str = "", fresh: bool = False) -> dict:
    """Open an installed application, say truthfully whether it opened, and only
    then remember it.

    `then` is the rest of the sentence - "and play the ADHD playlist". See `after`
    for why that is either replayed, asked about, or offered to be learned, but
    never silently dropped.
    """
    heard = canonical_app_name(app)
    then = clean_then(then, heard)
    if len(heard) < 2:
        return {"ok": False, "say": "Tell me which application to open."}

    corrected = False
    t0 = time.time()
    # An app that has already been opened and verified once is a routine: its exact Start-menu name is known, so the (slow, cached) listing of every
    # installed app is not needed. The first open after a restart used to wait several seconds for that listing.
    fast = _routine(_intent(canonical_app_name(heard)))
    names = [] if fast else await start_app_names()
    t_list = time.time() - t0
    if names:
        res = resolve_app(heard, names, _launch_history())
        if res["status"] == "unknown":
            _record_run(request, "discovery", "failed", f"no installed app called {heard!r}")
            near = ", ".join(res["options"][:3])
            return {"ok": False, "say": f"I can't find an app called “{heard}” on this PC."
                                        + (f" The closest are {near}." if near else "")}
        if res["status"] == "ask":
            return _ask(f"I'm not sure which app you meant by “{heard}”. Did you mean "
                        f"{res['name']}?" + (f" Or {', '.join(res['options'][1:3])}." if len(res["options"]) > 1 else ""),
                        "pc_app", {"app": res["name"], "request": request, "then": then},
                        f"Open {res['name']}")
        target = res["name"]
        corrected = res["status"] == "likely"
    else:
        target = heard                       # no listing available: pass it through
        if fast:
            try:
                target = str(json.loads(fast["args_json"]).get("name") or heard)    # the exact name that opened it before
            except Exception:
                pass

    key = canonical_app_name(target)
    known = _routine(_intent(key))
    args = json.loads(known["args_json"]) if known else {"mode": "launch", "name": target}
    route = "routine" if known else "discovery"
    t1 = time.time()
    fast = None
    try:
        fast = await _fast_open(target)
    except Exception as exc:  # noqa: BLE001 - the fast way is an optimisation: any trouble means the old way runs
        logger.info("pc_control: fast open of %r did not work: %s", target, exc)
    if fast:
        result = {"text": [f"{target} launched."]}
    else:
        try:
            result = await MCP.call_tool("windows", "App", args)
        except Exception as exc:
            _record_run(request, route, "failed", str(exc))
            return {"ok": False, "say": f"I could not open {target}: {str(exc)[:150]}."}
    logger.info("pc_control: open %r took %.1f s (listing apps %.1f s, %s; opening %.1f s)", target, time.time() - t0, t_list, "skipped, routine known" if fast else "listed", time.time() - t1)

    # Windows reports "<name> launched.", or "<name> not found in start menu.", or
    # "Launching <name> sent, but window not detected yet." - all as ordinary text.
    text = " ".join(result.get("text") or []).strip()
    low = text.lower()
    if "not found" in low or "could not" in low or "failed" in low:
        _record_run(request, route, "failed", text)
        return {"ok": False, "say": f"I tried to open {target}, but Windows said: {text[:140]}"}
    verified = low.rstrip(". ").endswith("launched") or await _window_for(target)
    if not verified:
        _record_run(request, route, "unverified", text or "no window seen")
        return {"ok": False, "say": f"I asked Windows to open {target}, but I can't see its window, "
                                    f"so I haven't counted that as done."}

    routine = _remember_launch(key, True)
    _record_run(request, route, "done", f"{target} launched.", level="api")
    tag = {"id": routine["id"], "status": routine["status"], "successes": routine["successes"], "tag": "ROUTINE"}
    said = f"Opened {target}." if not corrected else f"Opened {target} — I heard “{heard}”."
    how = fast["how"] if fast else "by the Windows tool (windows.App launch)"
    open_ms = int((time.time() - t0) * 1000)                       # the opening alone: the rest of the sentence is timed by what it does
    if then:
        got = await after(key, then, request, fresh=fresh)
        _record_second_half(request, then, got)
        return {**got, "routine": got.get("routine") or tag, "how": how, "open_ms": open_ms}
    return {"ok": True, "say": said, "routine": tag, "how": how}


def _record_second_half(request: str, then: str, got: dict) -> None:
    """The run row above is the launch. The rest of the sentence gets its own row, so a
    request that opened the app but never did the rest does not look finished.

    The detail never ends in " launched.", which `_launch_history` counts as a launch.
    """
    if got.get("confirm"):
        status = "asked"                       # waiting on a yes: nothing has been done yet
    elif got.get("ok"):
        status = "done"
    else:
        status = "failed"
    detail = f"rest of request: {then} - {str(got.get('say') or '')[:160]} [second half]"
    try:
        _record_run(request, "second-half", status, detail, level="ui-tree" if status == "done" else "")
    except Exception as exc:
        logger.info("pc_control: could not log the second half: %s", exc)


# ── routines learned from an app's own evidence ───────────────────────────────────────────────────────────────────
# Ingesting an installed app (rea_inspect) finds the URL schemes Windows has registered to it. Each becomes a
# routine here, so what was learned about the app is kept with the other routines and shows in the routines
# list: it can be disabled or forgotten like any other. Running one first checks the address is still
# registered to that app, so an app that has been removed is reported as removed, not "opened".

def _open_uri(uri: str) -> None:
    """Hand an address to the operating system, on whichever one this is."""
    if hasattr(os, "startfile"):
        os.startfile(uri)                                    # noqa: S606  - Windows
        return
    import subprocess
    import sys
    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", uri],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def learn_address_routines(app: str, protocols: "list[dict]", sha: str = "") -> "list[dict]":
    made = []
    now = time.time()
    with _db() as db:
        for pr in protocols or []:
            scheme = str(pr.get("scheme") or "").strip()
            if not scheme:
                continue
            intent = f"open-address:{canonical_app_name(app)}:{scheme.casefold()}"
            rid = hashlib.sha256(intent.encode()).hexdigest()[:16]
            args = json.dumps({"mode": "address", "uri": f"{scheme}://"})
            sig = json.dumps({"kind": "address", "app": canonical_app_name(app), "scheme": scheme, "sha256": sha})
            row = db.execute("SELECT id FROM pc_routines WHERE intent=?", (intent,)).fetchone()
            if row:
                db.execute("UPDATE pc_routines SET args_json=?, signature_json=?, updated=? WHERE id=?",
                           (args, sig, now, row["id"]))
            else:
                db.execute("INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,successes,failures,created,updated,kind) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (rid, intent, f"Open {display_app_name(app)} by its address ({scheme}://)", "Uri", args, sig,
                            "candidate", 0, 0, now, now, "mcp"))
            made.append({"id": rid, "intent": intent, "uri": f"{scheme}://"})
    return made


def _address_routine(app: str) -> "dict | None":
    want = canonical_app_name(app)
    with _db() as db:
        for r in db.execute("SELECT * FROM pc_routines WHERE tool='Uri' AND status!='disabled' ORDER BY successes DESC"):
            try:
                if json.loads(r["signature_json"]).get("app") == want:
                    return dict(r)
            except ValueError:
                continue
    return None


async def open_address(app: str, request: str = "", tail: str = "") -> dict:
    """Open an app through the address Windows has registered for it, and check a window came up.

    A bare scheme ("antigravity://") is not an instruction: an app may treat it as "open
    nothing" and quit, which is what Antigravity did. Without a path to go to, this opens
    the app the ordinary way and says so.
    """
    routine = _address_routine(app)
    name = display_app_name(app)
    if not routine:
        # Not read before. Windows already knows the app's address, so there is nothing to wait for:
        # look it up, keep it as a routine, and carry on.
        try:
            from . import rea_inspect as REA
            found = REA.discover_address(app)
            if found:
                routine = _address_routine(app)
        except Exception as exc:
            logger.info("pc_control: address discovery for %s failed: %s", app, exc)
    if routine and not str(tail or "").strip():
        got = await launch_app(app, request or f"open {name}")
        if got.get("ok"):
            got["say"] = f"Opened {name}. Its address needs a path to do more than that."
        return got
    if not routine:
        return {"ok": False, "say": f"I haven't learned an address for {name}. Say \"ingest the {name} app\" first."}
    sig = json.loads(routine["signature_json"])
    uri = json.loads(routine["args_json"]).get("uri", "")
    from . import rea_inspect as REA
    ev = REA.saved_evidence(app) or {}
    still = [p for p in REA.protocols_for(ev.get("path", "")) if p["scheme"].casefold() == str(sig.get("scheme", "")).casefold()] \
        if ev.get("path") else []
    if not still:
        hint = ev.get("reinstall") or {}
        how = f" I kept what I learned about it. To get it back: winget install {hint['winget']}." if hint.get("winget") else \
              " I kept what I learned about it."
        _record_run(request or f"open {name} by address", "routine", "failed", f"{sig.get('scheme')}:// is not registered", level="api")
        _remember_outcome(routine["id"], False)
        return {"ok": False, "say": f"{name} doesn't seem to be installed: Windows no longer routes {uri} to it.{how}"}
    try:
        _open_uri(uri + str(tail).lstrip("/"))               # the address, exactly as the OS registered it
    except Exception as exc:
        _record_run(request or f"open {name} by address", "routine", "failed", str(exc)[:200], level="api")
        _remember_outcome(routine["id"], False)
        return {"ok": False, "say": f"I tried {uri} but Windows refused: {str(exc)[:120]}"}
    seen = False
    for _ in range(12):                                      # up to about 6 s for a window to appear
        await asyncio.sleep(0.5)
        if await _window_for(name):
            seen = True
            break
    if not seen:
        _record_run(request or f"open {name} by address", "routine", "unverified", f"{uri} sent, no window seen", level="api")
        return {"ok": False, "say": f"I sent {uri}, but I can't see {name}'s window, so I haven't counted that as done."}
    updated = _remember_outcome(routine["id"], True)
    _record_run(request or f"open {name} by address", "routine", "done", f"{uri} opened {name}", level="api")
    return {"ok": True, "say": f"Opened {name} through {uri}.",
            "routine": {"id": routine["id"], "status": updated["status"], "successes": updated["successes"], "tag": "ROUTINE"}}


# ── reading the screen ───────────────────────────────────────────────────────────────────────────────────────────────
# Windows MCP returns its accessibility tree as an indented tree, and every
# assumption the first version of this parser made about that was wrong. The
# corrected format, captured from a real snapshot (tools/fixtures/):
#
#     UI Tree:
#     desktop
#     ├── window "Apple Music"
#     │   ├── (743,381) list item "Playlists"  [action: click]
#     │   ├── (858,143) button "Shuffle"  [action: click]  [toggle:off]
#     │   ├── group "ADHD 7 items · 27 minutes"
#     │   │   └── group "ADHD 7 items · 27 minutes"
#     │   │       ├── (1167,517) button "Play"  [action: click]
#
# Four things that broke, each of which silently produced an empty or wrong
# answer rather than an error:
#
# 1. The payload arrives JSON-encoded, so the whole 31KB is ONE line whose
#    newlines are the two characters backslash-n. `splitlines()` found nothing.
# 2. Node lines carry box-drawing prefixes, so a `^\s*window "..."` anchor never
#    matched a window and every element was attributed to window "".
# 3. Control types are not one word. `list item` and `app bar button` failed the
#    match outright, which quietly dropped every navigation row and transport
#    button - the only things worth clicking.
# 4. The name and the clickable control are DIFFERENT NODES. "ADHD" is on a
#    structural group with no coordinates; the Play button is its child and does
#    not contain the word "ADHD". A flat list cannot say "the Play button inside
#    the ADHD group", so the hierarchy has to survive parsing.

# Indentation is built from box-drawing glyphs, four columns per level.
_INDENT_RX = re.compile(r"^[\s│├└─]*")
# Optional coordinates, a control type of one or more lowercase words, a quoted
# name, then any number of bracketed flags: [action: click] [toggle:off] [focused]
_NODE_RX = re.compile(
    r'^(?:\((\d+)\s*,\s*(\d+)\)\s+)?([a-z][a-z ]*?)\s+"(.*)"\s*((?:\[[^\]]*\]\s*)*)$')


def snapshot_text(result: dict) -> str:
    """The tree as text, whatever shape the MCP server wrapped it in.

    The server returns a list of content chunks; here that list has arrived both
    as real chunks and as a single JSON-encoded array of them, and the second
    case is the one that silently yielded zero elements for months.
    """
    # Joined on newlines, not spaces: a chunk boundary is a line boundary, and
    # one node per line is the whole structure. Joining with a space collapses
    # a multi-chunk tree into one unparseable line.
    chunks = result.get("text") or []
    text = chr(10).join(c if isinstance(c, str) else str(c) for c in chunks)
    if text.lstrip()[:1] in ("[", '"'):
        try:
            got = json.loads(text)
        except ValueError:
            return text
        if isinstance(got, list):
            return chr(10).join(str(c) for c in got)
        return str(got)
    return text


def parse_tree(text: str) -> "list[dict]":
    """Every node in the snapshot, keeping depth, window and parentage.

    Structural nodes (a group or pane with a name but no coordinates) are kept,
    because they are where the names live. `clickable` says whether this node can
    be pressed; `parent` indexes into this same list.
    """
    out: "list[dict]" = []
    stack: "list[tuple[int, int]]" = []            # (depth, index) of open ancestors
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        indent = _INDENT_RX.match(line).end()
        body = line[indent:]
        m = _NODE_RX.match(body)
        if not m:
            continue
        x, y, control, name, flags = m.groups()
        depth = indent // 4
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else None
        window = ""
        control = " ".join(control.split()).lower()
        if control == "window":
            window = name
        elif parent is not None:
            window = out[parent]["window"]
        node = {"depth": depth, "control": control, "name": name, "window": window,
                "flags": (flags or "").strip(), "parent": parent,
                "clickable": "action:" in (flags or "")}
        if x is not None:
            node["x"], node["y"] = int(x), int(y)
        stack.append((depth, len(out)))
        out.append(node)
    return out


def container_of(nodes: "list[dict]", i: int) -> str:
    """The name of the nearest named group a node sits in ("" at the top of its window).

    Two controls can share a name ("Play" in the player bar, "Play" on a playlist, "Play" on a song); the group they sit in
    is what tells them apart, so a routine stores it and a model is shown it.
    """
    own = (nodes[i].get("name") or "").strip()
    p = nodes[i].get("parent")
    while p is not None:
        n = nodes[p]
        nm = (n.get("name") or "").strip()
        if n["control"] != "window" and nm and nm != own:
            return nm
        p = n.get("parent")
    return ""


def parse_snapshot(text: str) -> "list[dict]":
    """Every element with a position - what a routine can actually click.

    Kept to the shape the rest of the hub already expects (window, control, name,
    x, y), so routine replay and identity matching did not have to change; they
    were correct, and simply never received anything to work on.
    """
    nodes = parse_tree(text)
    return [{"window": n["window"], "control": n["control"], "name": n["name"], "path": container_of(nodes, i),
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for i, n in enumerate(nodes) if "x" in n]


_STABLE_CONTROLS = {"button", "tab item", "menu item", "toggle button"}


def ui_signature(elements: "list[dict]", window: str) -> dict:
    """What this screen looked like, in a form that survives it being moved or resized.

    Names and control types only - never coordinates, so dragging the window does
    not invalidate the routine, while the dialog changing underneath it does.

    `fingerprint` covers every control and is kept for routines saved before `stable` existed. `stable` covers
    only the short-named buttons and tabs without digits (the app's own chrome), because the content of a home
    page changes between visits: on 30 Oct the same Apple Music start screen differed by what had just been
    played, the full fingerprint no longer matched, and a good routine was refused and disabled.
    """
    same = sorted(f"{e['control']}|{e['name']}" for e in elements if e["window"] == window)
    digest = hashlib.sha256(chr(10).join(same).encode("utf-8")).hexdigest()[:16]
    chrome = sorted({f"{e['control']}|{e['name']}" for e in elements if e["window"] == window
                     and e["control"] in _STABLE_CONTROLS and e["name"] and len(e["name"]) <= 24
                     and not any(ch.isdigit() for ch in e["name"])})
    stable = hashlib.sha256(chr(10).join(chrome).encode("utf-8")).hexdigest()[:16]
    return {"kind": "ui", "window": window, "controls": len(same), "fingerprint": digest, "stable": stable}


_READ_DIAG: dict = {}


async def _bring_forward(app: str) -> dict:
    """Make the app's own window the one in front, as far as Windows allows, and say what happened. Every read of a window depends on this: the Windows tool reads the window in front, and
    a window that is behind, minimised, on a locked screen or refused the front reads as EMPTY. Never raises."""
    diag = {"app": app, "window": None, "minimised": None, "foreground": None, "locked": None}
    if sys.platform != "win32":
        return diag
    try:
        from . import window_mirror as WM
        diag["locked"] = await asyncio.to_thread(WM.desktop_locked)
        win = next((w for w in await asyncio.to_thread(WM.list_windows) if _is_window_of(w, display_app_name(app))), None)
        if win:
            diag.update(window=win["title"], minimised=bool(win.get("minimised")), foreground=False)
            for _ in range(6):
                await asyncio.to_thread(WM.focus, int(win["id"]))
                await asyncio.sleep(0.2)
                if await asyncio.to_thread(WM.foreground) == int(win["id"]):
                    diag["foreground"] = True
                    break
    except Exception as exc:  # noqa: BLE001
        logger.info("pc_control: could not bring %s forward: %s", app, exc)
    return diag


def read_problem(app: str) -> str:
    """Why the last read of this app's window gave no controls, in a sentence a person can act on. Written from what was measured, not guessed."""
    d = _READ_DIAG if _READ_DIAG.get("app") == app else {}
    name = display_app_name(app) or "that app"
    if d.get("locked"):
        return "The screen of this PC is locked (or showing a secure screen), and Windows gives a program nothing to read then. Unlock the PC and try again."
    if d and d.get("window") is None:
        return f"I cannot see an open {name} window to read."
    if d and d.get("minimised"):
        return f"The {name} window is minimised and would not come back, so I could not read it."
    if d and d.get("foreground") is False:
        return f"Windows would not let me bring the {name} window to the front (something else holds it), so I could not read its controls."
    if d:
        return (f"The {name} window is in front, but Windows gave back no controls from it ({d.get('nodes', 0)} nodes in all, none from {name}). "
                "Some apps only expose their controls once something asks for them; try again in a few seconds.")
    return ""


async def _raw_tree(app: str = "") -> "list[dict]":
    """The tree, with the app brought to the front first if one was named.

    A snapshot of an unfocused window is empty. Measured on this machine: with
    Apple Music open but behind, the tree held 499 `word` nodes belonging to the
    focused application and nothing at all from Apple Music; after an App/switch
    it held 72 buttons, 8 links and the playlist. Reading the screen without
    focusing first does not return less, it returns somebody else's window.

    12 Nov: the Windows tool's own switch is not enough when something else holds the front (a person was driving the Hub from a phone, with other windows in front): the window is
    brought forward here first and checked, a read with nothing from the app in it is retried, and what was measured is kept (`read_problem`) so a failure says why.
    """
    diag: dict = {}
    if app:
        diag = await _bring_forward(app)
        try:
            await MCP.call_tool("windows", "App", {"mode": "switch", "name": display_app_name(app)})
            await asyncio.sleep(1.0)               # the window has to finish coming forward
        except Exception as exc:
            logger.info("pc_control: could not focus %s: %s", app, exc)
    result = await MCP.call_tool("windows", "Snapshot", {"use_vision": False})
    nodes = parse_tree(snapshot_text(result))
    if app:
        want = canonical_app_name(app)
        mine = lambda ns: sum(1 for n in ns if want and want in (n.get("window") or "").casefold())      # noqa: E731
        for _ in range(2):
            if mine(nodes) or diag.get("locked"):
                break
            diag = await _bring_forward(app)
            await asyncio.sleep(1.0)
            nodes = parse_tree(snapshot_text(await MCP.call_tool("windows", "Snapshot", {"use_vision": False})))
        diag.update(nodes=len(nodes), app_nodes=mine(nodes))
        _READ_DIAG.clear()
        _READ_DIAG.update(diag)
    return nodes


_LAST_RAW: dict = {"nodes": []}


async def _snapshot(app: str = "") -> "list[dict]":
    nodes = await _raw_tree(app)
    _LAST_RAW["nodes"] = nodes                                   # the replay hands these to shadow mode as a demonstration of what a person-approved routine presses
    return [{"window": n["window"], "control": n["control"], "name": n["name"], "path": container_of(nodes, i),
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for i, n in enumerate(nodes) if "x" in n]


def _match(elements: list[dict], target: dict) -> dict | None:
    """Find the element a step was recorded against, in a fresh snapshot.

    Exact window+control+name first; then the same control+name in any window,
    because a document title changes far more often than a button's label.
    """
    name, control = target.get("name", ""), (target.get("control") or "").lower()
    window = target.get("window", "")
    if target.get("path"):                 # same name AND the same group: the playlist's Play, not the player bar's
        for e in elements:
            if e["name"] == name and e["control"] == control and e["window"] == window and e.get("path") == target["path"]:
                return e
    for e in elements:
        if e["name"] == name and e["control"] == control and e["window"] == window:
            return e
    for e in elements:
        if e["name"] == name and e["control"] == control:
            return e
    return None


# ── multi-step routines ──────────────────────────────────────────────────────────────────────────────────────────────
def _steps(routine_id: str) -> list[dict]:
    with _db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM pc_steps WHERE routine_id=? ORDER BY ordinal", (routine_id,))]


def save_ui_routine(intent: str, title: str, window: str, steps: list[dict],
                    signature: dict) -> dict:
    """Store a step sequence as a candidate routine. Replaces any steps it had."""
    now = time.time()
    rid = hashlib.sha256(intent.encode()).hexdigest()[:16]
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            rid = row["id"]
            db.execute("UPDATE pc_routines SET title=?,tool=?,signature_json=?,updated=? WHERE id=?",
                       (title, "ui", json.dumps(signature), now, rid))
            db.execute("DELETE FROM pc_steps WHERE routine_id=?", (rid,))
        else:
            db.execute(
                "INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,"
                "successes,failures,created,updated,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, intent, title, "ui", json.dumps({"window": window}),
                 json.dumps(signature), "candidate", 0, 0, now, now, "mcp"))
        for i, st in enumerate(steps):
            db.execute("INSERT INTO pc_steps(routine_id,ordinal,tool,args_json,target_json,created) "
                       "VALUES(?,?,?,?,?,?)",
                       (rid, i, st["tool"], json.dumps(st.get("args") or {}),
                        json.dumps(st.get("target") or {}), now))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


# Controls the Hub never presses on its own, whatever a routine or a request says: they spend money, destroy
# something, or send something out. The Hub stops and tells the person instead of pressing.
_NEVER_PRESS = re.compile(
    r"\b(?:buy|purchase|subscribe|pay|checkout|check out|delete|remove|erase|uninstall|format|sign out|log out|logout|send)\b",
    re.I)


def never_press(name: str) -> str:
    """The word that puts a control on the never-press list, or "" if it is not on it."""
    m = _NEVER_PRESS.search(name or "")
    return m.group(0).lower() if m else ""


_BLOCKING_FLAGS = ("disabled", "unavailable", "offscreen", "off-screen", "hidden", "collapsed", "read-only")


def step_blocker(node: "dict | None", tool: str = "Click") -> str:
    """Why a step must not run against this element, or "" if it may.

    Checked before every step, not only before the first: a routine that found
    its screen at the start can still be looking at a greyed-out button three
    steps later. Taken from how UFO2 verifies a control (present, enabled,
    visible) before acting.
    """
    if not node:
        return "it is not on screen"
    flags = str(node.get("flags") or "").lower()
    for f in _BLOCKING_FLAGS:
        if re.search(rf"\[\s*{re.escape(f)}\b", flags) or re.search(rf"\b{re.escape(f)}\s*:\s*true", flags):
            return f"it is {f}"
    if tool == "Click" and node.get("x") is None:
        return "it has no position on screen"
    word = never_press(str(node.get("name") or "")) if tool == "Click" else ""
    if word:
        return f"its name is on the never-press list ({word})"
    return ""


def _app_of(routine: dict) -> str:
    """The app a routine belongs to: the words before the colon in its title ("Apple Music: play my ADHD playlist"), else the window it was recorded in."""
    title = routine.get("title") or ""
    if ":" in title:
        return title.split(":", 1)[0].strip()
    try:
        return json.loads(routine.get("signature_json") or "{}").get("window", "")
    except ValueError:
        return ""


def _goal_of(routine: dict) -> str:
    title = routine.get("title") or ""
    return title.split(":", 1)[1].strip() if ":" in title else title


async def replay_ui_routine(routine: dict, request: str = "", record: bool = True, only: "tuple | None" = None) -> dict:
    """Replay a routine and keep what happened: every step (the app being opened first, if it was not open), how long it took, and a picture of the window after it.
    The record is what a person looks at to say whether the routine is right; it also names the newest replay of this routine for the routines panel."""
    rec = None
    if record:
        try:
            from . import run_record as RR
            stored = json.loads(routine.get("signature_json") or "{}")
            rec = RR.Recorder("replay", _goal_of(routine), _app_of(routine), routine=routine["id"], window=stored.get("window", ""))
        except Exception as exc:  # noqa: BLE001
            logger.info("pc_control: no replay record: %s", exc)
    t0 = time.time()
    res = await _replay_core(routine, request, rec, only)
    res["ms"] = int((time.time() - t0) * 1000)
    if rec:
        res["rid"] = rec.finish(bool(res.get("ok")), res.get("say", ""))
    return res


async def _open_if_closed(routine: dict, window: str, request: str, rec) -> "dict | None":
    """A replay starts from an open app, as a person would: when the window is not there, open the app (its own trusted launch routine, if it has one), wait for the window,
    and count that as step 1. Returns a result to stop with, or None to carry on."""
    app = _app_of(routine) or window
    if not app:
        return None
    g0 = stop_gen()
    t0 = time.time()
    got = await launch_app(app, request or "replay")
    if not got.get("ok"):
        if rec:
            await rec.step("open", app, (time.time() - t0) * 1000, False, got.get("say", ""))
        return {"ok": False, "route": "routine", "say": f"The app was not open, and I could not open {display_app_name(app)}: {got.get('say', '')}"}
    for _ in range(24):                                               # up to about 12 s for its window to draw
        if stop_gen() != g0:
            return dict(STOPPED)
        if await _snapshot(window):
            break
        await asyncio.sleep(0.5)
    if rec:
        await rec.step("open", display_app_name(app), (time.time() - t0) * 1000, True, "was not open; opened first")
    return None


async def _replay_core(routine: dict, request: str, rec, only: "tuple | None" = None) -> dict:
    """Run a stored step sequence, but only onto the screen it was recorded against.

    Every refusal here is deliberate: a routine that cannot see what it expects
    must stop, never fall back to clicking where the control used to be.
    """
    stored = json.loads(routine["signature_json"] or "{}")
    steps = _steps(routine["id"])
    if not steps:
        return {"ok": False, "route": "fall-through", "say": "That routine has no steps saved."}
    if only is not None:                                              # one step, or from a step on: the screen is wherever the person left it, so it is not held to the recorded one
        steps = [s for s in steps if only[0] <= s["ordinal"] <= only[1]]
        if not steps:
            return {"ok": False, "route": "fall-through", "say": "There is no such step."}

    # Focus first: an unfocused window contributes nothing to the tree, so a
    # routine replayed while something else is in front would see an empty
    # screen and conclude its target had vanished.
    elements = await _snapshot(stored.get("window", ""))
    # An empty tree is a window that has not drawn yet (5 Nov: the ADHD routine fell through three times because the tree was read the instant the app
    # came forward, signature e3b0c442... = nothing). Look again a few times before deciding the screen is a different one.
    for _ in range(4):
        if elements:
            break
        await asyncio.sleep(0.6)
        elements = await _snapshot(stored.get("window", ""))
    if not elements:                       # still nothing after looking again: the app is not open. Open it, as the first step, and read its screen.
        opened = await _open_if_closed(routine, stored.get("window", ""), request, rec)
        if opened:
            return opened
        elements = await _snapshot(stored.get("window", ""))
    live = ui_signature(elements, stored.get("window", ""))
    key = "stable" if stored.get("stable") else "fingerprint"
    if only is None and live[key] != stored.get(key):
        # The app is not showing the page the routine was recorded on (it came up on another page, or its content moved). That alone is not a reason to refuse: every step below finds its own
        # control on the live screen and stops if it is missing. So the routine goes on when the control of its FIRST step is there, and says that it did; it stops, saying exactly what it
        # looked for, when it is not. Before 12 Nov any difference stopped it, so a replay after the app had just been opened did nothing at all.
        first_target = json.loads(steps[0]["target_json"] or "{}")
        if not (first_target and _match(elements, first_target)):
            why_empty = read_problem(_app_of(routine) or stored.get("window", "")) if not elements else ""
            _record_run(request, "fall-through", "skipped",
                        f"signature mismatch ({key}): expected {stored.get(key)}, saw {live[key]}; first control not on screen")
            if rec:
                await rec.step("check", first_target.get("name", "")[:60], 0, False, why_empty or "the screen is not the one it was recorded on, and its first control is not on it")
            return {"ok": False, "route": "fall-through",
                    "say": (why_empty + " " if why_empty else "") + f"{routine['title']} starts from “{(first_target.get('name') or 'a control')[:50]}”, which is not on the screen ({live.get('controls', 0)} controls seen). I did not press anything."}
        _record_run(request, "routine", "note", f"screen differs ({key}) but the first control is on it: going on")

    window = stored.get("window", "")
    before = live                      # the signature just taken, reused as the baseline
    g0 = stop_gen()
    history: "list[str]" = []
    for step in steps:
        if stop_gen() != g0:
            return dict(STOPPED)
        ts = time.time()
        target = json.loads(step["target_json"] or "{}")
        args = dict(json.loads(step["args_json"] or "{}"))
        if target:
            found = _match(elements, target)
            if not found:
                if rec:
                    await rec.step(step["tool"].lower(), target.get("name", ""), (time.time() - ts) * 1000, False, "not on screen", ordinal=step["ordinal"])
                _record_run(request, "fall-through", "skipped",
                            f"step {step['ordinal']}: no element {target.get('control')} \"{target.get('name')}\"")
                _remember_outcome(routine["id"], False)
                return {"ok": False, "route": "fall-through",
                        "say": f"I could not find \"{target.get('name')}\" on screen, so I stopped."}
            why = step_blocker(found, step["tool"])
            if why:
                _record_run(request, "fall-through", "skipped",
                            f"step {step['ordinal']}: \"{target.get('name')}\" {why}")
                _remember_outcome(routine["id"], False)
                return {"ok": False, "route": "fall-through",
                        "say": f"I stopped at step {step['ordinal'] + 1}: \"{target.get('name')}\" is there but {why}."}
            args["loc"] = [found["x"], found["y"]]
            _shadow_demo(routine, found, step, args, history)
        try:
            await MCP.call_tool("windows", step["tool"], args)
        except Exception as exc:
            if rec:
                await rec.step(step["tool"].lower(), target.get("name", ""), (time.time() - ts) * 1000, False, str(exc)[:120], ordinal=step["ordinal"])
            _record_run(request, "routine", "failed", f"step {step['ordinal']}: {exc}")
            _remember_outcome(routine["id"], False)
            return {"ok": False, "route": "routine", "say": f"{routine['title']} failed: {str(exc)[:150]}"}
        # The screen moved; anything resolved from the old snapshot is now a guess.
        # No re-focus: we are the ones driving this window, so it is still in
        # front, and focusing again would cost a second of waiting per step.
        elements = await _snapshot()
        history.append(f"step {len(history) + 1}: {step['tool'].lower()} {target.get('name', '')}")
        if rec:
            await rec.step(step["tool"].lower(), target.get("name", ""), (time.time() - ts) * 1000, True, ordinal=step["ordinal"])

    if only is not None:                                              # a part of a routine: say what ran, and leave its record alone
        return {"ok": True, "route": "routine", "say": f"Ran {'step ' + str(steps[0]['ordinal'] + 1) if len(steps) == 1 else 'steps ' + str(steps[0]['ordinal'] + 1) + ' to ' + str(steps[-1]['ordinal'] + 1)}. It did not change the routine."}

    # Every step ran without raising. That is not the same as having worked, and
    # counting it as a success is how a routine that does nothing becomes
    # `trusted`: promotion needs evidence, so a replay that leaves the window
    # untouched is recorded as a failure and says so.
    did = await effect_of(window, before)
    if did["known"] and not did["changed"]:
        # Neither promoted nor demoted. "I cannot tell" is not the same as "it
        # failed": a refresh that redraws identical content changes nothing and
        # is still working, so counting this as a failure would disable routines
        # that are fine. An unverifiable run simply earns no credit.
        _record_run(request, "routine", "no-effect", f"{len(steps)} step(s), window unchanged")
        return {"ok": False, "route": "routine",
                "say": f"I ran {routine['title']} and {did['why']}, so I cannot say it worked.",
                "routine": {"id": routine["id"], "status": routine["status"],
                            "successes": routine["successes"], "tag": "ROUTINE"}}
    updated = _remember_outcome(routine["id"], True)
    _record_run(request, "routine", "done", f"{len(steps)} step(s), window changed", level="ui-tree")
    return {"ok": True, "route": "routine", "say": f"Ran {routine['title']}.",
            "routine": {"id": routine["id"], "status": updated["status"],
                        "successes": updated["successes"], "tag": "ROUTINE"}}


def _shadow_demo(routine: dict, found: dict, step: dict, args: dict, history: "list[str]") -> None:
    """With shadow mode on, a replay is a demonstration: this screen, and the control the routine presses on it. It goes where the live agent's own choices go (the live memory), so a
    learner can later be fitted to what a person-approved routine does, not only to what a model chose. Never raises, never slows the replay by more than a millisecond or two."""
    try:
        from ..yard import shadow as SH
        if not SH.enabled():
            return
        from . import desktop_agent as DA
        shown = DA.controls(_LAST_RAW["nodes"], _app_of(routine), _goal_of(routine))
        hit = next((c for c in shown if c["node"].get("name") == found["name"] and c["node"].get("x") == found["x"] and c["node"].get("y") == found["y"]), None)
        if hit is None:
            return
        prompt = DA.brief(_goal_of(routine), _app_of(routine), shown, [], history, len(history))
        SH.note(_goal_of(routine), _app_of(routine), prompt, {"do": "type" if step["tool"] == "Type" else "click", "control": {"id": hit["id"]}, "text": args.get("text", "")}, len(history))
    except Exception as exc:  # noqa: BLE001
        logger.info("pc_control: no shadow sample from this replay step: %s", exc)


def _remember_outcome(routine_id: str, success: bool) -> dict:
    """Same promotion rule as launches: two clean runs earn trust, a failure disables."""
    with _db() as db:
        db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, updated=? WHERE id=?",
                   (int(success), int(not success), time.time(), routine_id))
        if not success:
            db.execute("UPDATE pc_routines SET status='disabled', updated=? WHERE id=? AND status='candidate'",
                       (time.time(), routine_id))
        # A clean run adds to the count; it never promotes. Only PROMOTE does.
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (routine_id,)).fetchone())


@routes.get("/api/pc/routines")
async def api_routines(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT id,intent,title,tool,kind,args_json,status,successes,failures,created,updated,note FROM pc_routines ORDER BY updated DESC")]
        counts = {r["routine_id"]: r["n"] for r in db.execute(
            "SELECT routine_id, COUNT(*) AS n FROM pc_steps GROUP BY routine_id")}
        scores = {}
        for s in db.execute("SELECT routine_id, target_json FROM pc_steps"):
            try:
                v = json.loads(s["target_json"] or "{}").get("last_score")
            except ValueError:
                v = None
            if v is not None:
                scores.setdefault(s["routine_id"], []).append(float(v))
        for r in rows:
            r["steps"] = counts.get(r["id"], 0)
            try:
                r["profile"] = json.loads(r.pop("args_json", "") or "{}").get("profile")
            except ValueError:
                r["profile"] = None
            seen = scores.get(r["id"]) or []
            r["lowest_match"] = min(seen) if seen else None
            r["matched"] = len(seen)
    try:
        from . import run_record as RR
        for r in rows:
            last = RR.latest_for(r["id"])
            r["last_replay"] = {"ok": last.get("ok"), "at": last.get("at"), "ms": last.get("ms"), "kind": last.get("kind", "run"), "say": last.get("say", "")} if last else None
            r["replay_failures"] = RR.trailing_failures(r["id"])
    except Exception:  # noqa: BLE001
        pass
    return web.json_response({"routines": rows})


@routes.get("/api/pc/runs")
async def api_runs(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM pc_runs ORDER BY id DESC LIMIT 30")]
    return web.json_response({"runs": rows})


@routes.get("/api/pc/snapshot")
async def api_snapshot(request: web.Request) -> web.Response:
    """What is on screen right now, parsed. Reads; clicks nothing."""
    try:
        elements = await _snapshot()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"Snapshot failed: {str(exc)[:200]}")
    windows = sorted({e["window"] for e in elements if e["window"]})
    return web.json_response({"elements": elements, "windows": windows,
                              "signatures": {w: ui_signature(elements, w) for w in windows}})


@routes.post("/api/pc/routines")
async def api_save_routine(request: web.Request) -> web.Response:
    """Record a UI routine: {intent, title, window, steps:[{tool,args,target}]}.

    The signature is taken from the screen as it is NOW, which is the screen the
    caller just drove - that is what makes the replay check meaningful.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    intent = " ".join(str(body.get("intent", "")).split())[:120]
    title = " ".join(str(body.get("title", "")).split())[:120] or intent
    window = str(body.get("window", ""))
    steps = body.get("steps") or []
    if not intent or not steps:
        raise web.HTTPBadRequest(text="intent and at least one step are required")
    allowed = {"Click", "Type", "Shortcut", "Scroll", "Wait", "App"}
    for st in steps:
        if not isinstance(st, dict) or st.get("tool") not in allowed:
            raise web.HTTPBadRequest(text=f"each step needs a tool from {sorted(allowed)}")
    try:
        elements = await _snapshot()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"Snapshot failed: {str(exc)[:200]}")
    if window and window not in {e["window"] for e in elements}:
        raise web.HTTPBadRequest(text=f"no window named {window!r} is on screen to record against")
    saved = save_ui_routine(intent, title, window, steps, ui_signature(elements, window))
    return web.json_response({"ok": True, "routine": saved, "steps": len(steps)})


async def run_routine(rid: str, request: str = "manual run") -> dict:
    """Replay one stored routine by id, whichever kind it is.

    Lifted out of the endpoint so a tile's button can press a routine through
    exactly the same path a person pressing it on the routines panel does -
    one way for a routine to run, not two that can drift apart.
    """
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone()
    if not row:
        raise KeyError("no such routine")
    routine = dict(row)
    if routine["status"] == "disabled":
        raise ValueError("that routine is disabled")
    if routine["tool"] == "surface":
        from . import machine_routines as MR
        return await MR.replay_machine_routine(routine, request=request)
    if routine["tool"] in ("App", "Uri"):
        return await replay_launch_routine(routine, request=request)
    if routine["tool"] != "ui":
        raise ValueError(f"I cannot replay a routine of kind {routine['tool']!r} from here")
    return await replay_ui_routine(routine, request=request)


def launch_command(routine: dict) -> dict:
    """What a launch routine runs, in words a person can check: the tool, its arguments, and where the app's name comes from."""
    try:
        args = json.loads(routine.get("args_json") or "{}")
    except ValueError:
        args = {}
    if routine.get("tool") == "Uri":
        uri = (json.loads(routine.get("signature_json") or "{}") or {}).get("uri") or ""
        return {"tool": "Uri", "args": {"uri": uri}, "text": f"open the address {uri or '(registered by the app)'} through Windows", "source": "an address Windows has registered for the app"}
    name = args.get("name") or ""
    try:
        sid = json.loads(_start_ids_file().read_text(encoding="utf-8")).get(_norm(name), "")
    except (OSError, ValueError):
        sid = ""
    first = (f"if its window is open, bring it forward; otherwise start it by its Start-menu id {sid}" if sid else "if its window is open, bring it forward; otherwise look up its Start-menu id (Get-StartApps) and start it by that")
    return {"tool": "App", "args": args, "text": f"{first}, then wait for its window. If that is not possible: windows.App {json.dumps(args)}",
            "source": f"the Start-menu entry “{name}”, remembered from {routine.get('successes', 0)} earlier successful opens"}


async def replay_launch_routine(routine: dict, request: str = "") -> dict:
    """REPLAY on "Open Apple Music" (or an address routine): do exactly what Talk does for that sentence and keep the step, the exact command, its time and a picture.
    `launch_app` itself checks that the window came up (that check is the slow part of a cold start: Windows took 14 s for Apple Music), so it is not repeated here."""
    from . import run_record as RR
    cmd = launch_command(routine)
    name = str((cmd["args"] or {}).get("name") or "")
    if not name:
        name = (routine.get("title") or "").removeprefix("Open ").split(" by its address")[0].strip()
    if not name and ":" in (routine.get("intent") or ""):
        name = routine["intent"].split(":", 1)[1].split(":")[0]
    rec = RR.Recorder("replay", routine.get("title") or name, name, routine=routine["id"], window=name)
    t0 = time.time()
    g0 = stop_gen()
    got = await (open_address(name, request or "replay") if routine["tool"] == "Uri" else launch_app(name, request or "replay"))
    ms = (time.time() - t0) * 1000
    if stop_gen() != g0:
        res = {**STOPPED, "say": f"Stopped by you after {ms / 1000:.0f} s. That is not a result: the routine is unchanged."}
        await rec.step("open", display_app_name(name), ms, False, cmd["text"] + " (stopped)")
    else:
        ok = bool(got.get("ok"))
        await rec.step("open", display_app_name(name), ms, ok, (got.get("how") + ". " if got.get("how") else "") + cmd["text"] + (f" — {got.get('say', '')}" if not ok else ""))
        res = {"ok": ok, "route": "routine", "say": (got.get("say") or ("Opened " + display_app_name(name) + "." if ok else "It did not open.")) + (f" Took {ms / 1000:.1f} s." if ok else "")}
    res["ms"] = int(ms)
    res["command"] = cmd
    res["rid"] = rec.finish(bool(res.get("ok")), res["say"])
    return res


@routes.post("/api/pc/stop")
async def api_stop(request: web.Request) -> web.Response:
    """STOP: whatever the Hub is doing on this PC (a replay, the desktop agent, an app being opened) ends at its next step."""
    return web.json_response({"ok": True, "gen": stop_all()})


@routes.get("/api/pc/routines/{id}/last-run")
async def api_last_run(request: web.Request) -> web.Response:
    """The newest replay or attempt of this routine, with its steps, times and pictures (what you look at before approving it)."""
    from . import run_record as RR
    row = RR.latest_for(request.match_info["id"])
    return web.json_response({"run": row})


@routes.post("/api/pc/routines/{id}/reattempt")
async def api_reattempt(request: web.Request) -> web.Response:
    """ATTEMPT AGAIN: say the routine's own sentence to the Hub again ("open Apple Music and play something from the adhd playlist") and let it follow the pipeline Smith follows: open the app (a step
    of its own, by the fast way), then do the task fresh with the desktop agent and check the result. The old recording is not replayed. A good attempt replaces a candidate's steps; the pictures
    of the attempt are the ones shown for this routine. A trusted routine is left alone, so an attempt cannot replace what you approved."""
    from . import run_record as RR
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
    if not row:
        raise web.HTTPNotFound(text="no such routine")
    routine = dict(row)
    if routine["status"] == "trusted":
        return web.json_response({"ok": False, "say": "That routine is trusted. Demote it first, so a new attempt cannot replace what you approved."})
    if routine["tool"] != "ui":
        return web.json_response({"ok": False, "say": "ATTEMPT AGAIN is for routines that press things inside an app. This one only opens an app: use REPLAY."})
    app, goal = _app_of(routine), _goal_of(routine)
    if not app or not goal:
        return web.json_response({"ok": False, "say": "This routine has no app and task I can read from its name."})
    sentence = f"open {display_app_name(app)} and {goal}"
    t0 = time.time()
    got = await launch_app(app, sentence, then=goal, fresh=True)
    if got.get("confirm") or got.get("action"):                          # a question is not a result: nothing was done
        got = {"ok": False, "say": "It stopped to ask you something instead of doing the task, so nothing was done: " + str(got.get("say") or "")[:200]}
    if got.get("ok") and not (got.get("confirm") or got.get("action")):
        try:
            RR.note_outcome(routine["id"], True)                      # a good attempt ends a run of failed replays
        except Exception:  # noqa: BLE001
            pass
    rid = ((got.get("tries") or [{}])[-1] or {}).get("rid", "")
    if rid:
        try:
            RR.annotate(rid, sentence=sentence, opened={"how": got.get("how", ""), "ms": got.get("open_ms")})
            latest = RR._latest()
            latest[routine["id"]] = rid
            (RR._root() / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
        except OSError:
            pass
    return web.json_response({"ok": bool(got.get("ok")), "say": got.get("say", ""), "rid": rid, "ms": int((time.time() - t0) * 1000), "sentence": sentence, "how": got.get("how", ""), "routine": got.get("routine")})


@routes.post("/api/pc/routines/{id}/run")
async def api_run_routine(request: web.Request) -> web.Response:
    t0 = time.time()
    before = await _snap()                                        # EXPERIMENTAL shadow mode only: a picture before, evidence after
    rid = request.match_info["id"]
    keep = None
    if request.query.get("test") == "1":                                  # a tester's replay: it must not promote the routine, or disable it
        with _db() as db:
            r0 = db.execute("SELECT status, successes, failures FROM pc_routines WHERE id=?", (rid,)).fetchone()
        keep = dict(r0) if r0 else None
    try:
        try:
            got = await run_routine(request.match_info["id"])
        finally:
            if keep:
                with _db() as db:
                    db.execute("UPDATE pc_routines SET status=?, successes=?, failures=? WHERE id=?", (keep["status"], keep["successes"], keep["failures"], rid))
        if request.query.get("test") == "1" and got.get("route") != "stopped" and keep:
            try:
                from . import run_record as RR
                RR.note_outcome(rid, bool(got.get("ok")))
                if keep["status"] == "trusted" and not got.get("ok") and RR.trailing_failures(rid) >= 2:
                    with _db() as db:                       # two replays in a row failed: it is not a routine a person can rely on, so it is not listed as trusted
                        db.execute("UPDATE pc_routines SET status='candidate', approved=0, successes=0, updated=? WHERE id=?", (time.time(), rid))
                    got = {**got, "demoted": True, "say": (got.get("say") or "") + " It failed its last two replays, so it is no longer trusted: it is a candidate again."}
            except Exception as exc:  # noqa: BLE001
                logger.info("pc_control: could not note the replay outcome: %s", exc)
        try:
            with _db() as db:
                row = db.execute("SELECT title FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
            await _evidence("manual routine", (row["title"] if row else request.match_info["id"]), "", bool(got.get("ok")), t0, before, {"routine_clean": bool(got.get("ok"))}, request.match_info["id"])
        except Exception:  # noqa: BLE001
            pass
        return web.json_response(got)
    except KeyError as exc:
        raise web.HTTPNotFound(text=str(exc))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


def rename_routine(rid: str, title: str) -> bool:
    """Change what a routine is called. The intent it is looked up by is unchanged, so it still runs."""
    title = " ".join(str(title or "").split())[:80]
    if not title:
        return False
    with _db() as db:
        n = db.execute("UPDATE pc_routines SET title=?, updated=? WHERE id=?", (title, time.time(), rid)).rowcount
    return bool(n)


def forget_routine(rid: str) -> bool:
    """Remove a learned routine for good: its row, its steps, and its anchors.

    Until now a routine could only be disabled, which hides it but keeps it in
    the store forever. Something learned by accident - a mis-click during a
    test, a launch recorded under a name you never meant - had no way out.
    Anchor images are deleted with it, because a surface routine's screenshots
    of your desktop should not outlive the routine that needed them.
    """
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE id=?", (rid,)).fetchone()
        if not row:
            return False
        db.execute("DELETE FROM pc_steps WHERE routine_id=?", (rid,))
        db.execute("DELETE FROM pc_routines WHERE id=?", (rid,))
    try:
        from . import machine_routines as MR
        shots = MR.ANCHORS / rid
        if shots.is_dir():
            import shutil
            shutil.rmtree(shots, ignore_errors=True)
    except Exception as exc:
        logger.info("pc_control: could not remove anchors for %s: %s", rid, exc)
    logger.info("pc_control: forgot routine %s", rid)
    return True


@routes.delete("/api/pc/routines/{id}")
async def api_forget_routine(request: web.Request) -> web.Response:
    if not forget_routine(request.match_info["id"]):
        raise web.HTTPNotFound(text="no such routine")
    return web.json_response({"ok": True})


@routes.post("/api/pc/routines/{id}/status")
async def api_set_status(request: web.Request) -> web.Response:
    """Set a routine's status: trusted (PROMOTE), candidate (DEMOTE) or disabled. Nothing else changes it to trusted: no count of clean runs does."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = str(body.get("status", ""))
    if status not in ("disabled", "candidate", "trusted"):
        raise web.HTTPBadRequest(text="status must be 'trusted', 'candidate' or 'disabled'")
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
        if not row:
            raise web.HTTPNotFound(text="no such routine")
        db.execute("UPDATE pc_routines SET status=?, approved=?, updated=? WHERE id=?",
                   (status, int(status == "trusted"), time.time(), row["id"]))
        if status == "trusted":                                   # you looked at it and approved it: failures from before that decision are not held against it
            try:
                from . import run_record as RR
                RR.clear_failures(row["id"])
            except Exception:  # noqa: BLE001
                pass
        try:                                                      # who decided, recorded with the routine
            from . import learning as LRN
            LRN.note("trust", "routine", status, ["trusted", "candidate", "disabled"], status == "trusted", by="you", routine=row["id"])
        except Exception:  # noqa: BLE001
            pass
        return web.json_response({"ok": True, "routine": dict(
            db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())})


@routes.post("/api/pc/routines/{id}/approve")
async def api_approve_routine(request: web.Request) -> web.Response:
    """The person reads the steps and says it is right: it becomes trusted without waiting for two clean replays. Only this button does that."""
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
        if not row:
            raise web.HTTPNotFound(text="no such routine")
        db.execute("UPDATE pc_routines SET status='trusted', approved=1, updated=? WHERE id=?", (time.time(), row["id"]))
        try:                                                      # R1: you read the steps and trusted it; recorded with the routine and who decided
            from . import learning as LRN
            LRN.note("trust", "routine", "trusted", ["trusted", "candidate"], True, by="you", routine=row["id"])
        except Exception:  # noqa: BLE001
            pass
        return web.json_response({"ok": True, "routine": dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())})


# ── editing a routine's steps ───────────────────────────────────────────────────────────────────
# A routine recorded from an agent run can carry detours (6 steps where 3 are needed). The person who reads it can drop a step, move one, or change the name of the control it presses.
# Editing a trusted routine makes it a candidate again: it is not the routine that was approved any more, so it earns trust again (an approval, or two clean replays).
def _steps_changed(db, rid: str) -> None:
    for i, row in enumerate(db.execute("SELECT id FROM pc_steps WHERE routine_id=? ORDER BY ordinal, id", (rid,)).fetchall()):
        db.execute("UPDATE pc_steps SET ordinal=? WHERE id=?", (i, row["id"]))
    db.execute("UPDATE pc_routines SET status=CASE WHEN status='disabled' THEN status ELSE 'candidate' END, approved=0, successes=0, failures=0, updated=? WHERE id=?", (time.time(), rid))      # it has to earn trust again


def delete_step(rid: str, ordinal: int) -> bool:
    with _db() as db:
        n = db.execute("DELETE FROM pc_steps WHERE routine_id=? AND ordinal=?", (rid, int(ordinal))).rowcount
        if n:
            _steps_changed(db, rid)
    return bool(n)


def move_step(rid: str, ordinal: int, to: int) -> bool:
    with _db() as db:
        rows = [r["id"] for r in db.execute("SELECT id FROM pc_steps WHERE routine_id=? ORDER BY ordinal, id", (rid,)).fetchall()]
        ordinal, to = int(ordinal), int(to)
        if not (0 <= ordinal < len(rows) and 0 <= to < len(rows)) or ordinal == to:
            return False
        moved = rows.pop(ordinal)
        rows.insert(to, moved)
        for i, sid in enumerate(rows):
            db.execute("UPDATE pc_steps SET ordinal=? WHERE id=?", (i, sid))
        _steps_changed(db, rid)
    return True


def edit_step(rid: str, ordinal: int, name: str) -> bool:
    """Change the name of the control a step presses. A routine can only press a control that is on the screen, so a name that is not there makes the step stop, never click elsewhere."""
    name = " ".join(str(name or "").split())[:200]
    if not name:
        return False
    with _db() as db:
        row = db.execute("SELECT id, target_json FROM pc_steps WHERE routine_id=? AND ordinal=?", (rid, int(ordinal))).fetchone()
        if not row:
            return False
        target = json.loads(row["target_json"] or "{}")
        target["name"] = name
        db.execute("UPDATE pc_steps SET target_json=? WHERE id=?", (json.dumps(target), row["id"]))
        _steps_changed(db, rid)
    return True


@routes.delete("/api/pc/routines/{id}/steps/{ordinal}")
async def api_delete_step(request: web.Request) -> web.Response:
    if not delete_step(request.match_info["id"], int(request.match_info["ordinal"])):
        raise web.HTTPNotFound(text="no such step")
    return web.json_response({"ok": True})


@routes.post("/api/pc/routines/{id}/steps/{ordinal}")
async def api_edit_step(request: web.Request) -> web.Response:
    """{"name": "ADHD"} renames the control the step presses; {"to": 1} moves the step to that position (counting from 0)."""
    body = await request.json()
    rid, ordinal = request.match_info["id"], int(request.match_info["ordinal"])
    if "note" in body:
        ok = set_step_note(rid, ordinal, body.get("note"))
    else:
        ok = move_step(rid, ordinal, body["to"]) if "to" in body else edit_step(rid, ordinal, body.get("name"))
    if not ok:
        raise web.HTTPBadRequest(text="nothing changed: check the step number and the new name")
    return web.json_response({"ok": True})


def set_routine_note(rid: str, note: str) -> bool:
    """A person's own words about a routine: why it works, why it does not, what to change. It is kept with the routine and written to the learning record. Changing it never changes how the routine runs."""
    note = str(note or "").strip()[:1500]
    with _db() as db:
        n = db.execute("UPDATE pc_routines SET note=? WHERE id=?", (note, rid)).rowcount
    if n:
        _note_event("routine", rid, None, note)
    return bool(n)


def set_step_note(rid: str, ordinal: int, note: str) -> bool:
    """The same for one step. It rides in the step's own record and is NOT an edit: it does not make a trusted routine a candidate."""
    note = str(note or "").strip()[:600]
    with _db() as db:
        row = db.execute("SELECT id, target_json FROM pc_steps WHERE routine_id=? AND ordinal=?", (rid, int(ordinal))).fetchone()
        if not row:
            return False
        target = json.loads(row["target_json"] or "{}")
        if note:
            target["note"] = note
        else:
            target.pop("note", None)
        db.execute("UPDATE pc_steps SET target_json=? WHERE id=?", (json.dumps(target), row["id"]))
    _note_event("step", rid, int(ordinal), note)
    return True


def _note_event(scope: str, rid: str, ordinal: "int | None", note: str) -> None:
    try:
        from . import learning as LRN
        LRN.note("note", scope, note[:80], by="you", routine=rid, **({"step": ordinal} if ordinal is not None else {}), text=note)
    except Exception:  # noqa: BLE001
        pass


@routes.post("/api/pc/routines/{id}/note")
async def api_routine_note(request: web.Request) -> web.Response:
    body = await request.json()
    if not set_routine_note(request.match_info["id"], body.get("note", "")):
        raise web.HTTPNotFound(text="no such routine")
    return web.json_response({"ok": True})


@routes.post("/api/pc/routines/{id}/steps/{ordinal}/run")
async def api_run_step(request: web.Request) -> web.Response:
    """Replay ONE step ({"mode": "one"}) or the steps from there to the end ({"mode": "from"}) against the screen as it is now. This is how a routine is studied step by step: put the app where the
    step expects it, run the step, look at the picture. It does not change the routine's record (a part of a routine proves nothing about the whole)."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    rid, ordinal = request.match_info["id"], int(request.match_info["ordinal"])
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone()
    if not row:
        raise web.HTTPNotFound(text="no such routine")
    routine = dict(row)
    if routine["tool"] != "ui":
        raise web.HTTPBadRequest(text="only a routine that presses things inside an app has steps to run one by one")
    only = (ordinal, ordinal) if body.get("mode", "one") == "one" else (ordinal, 10 ** 6)
    got = await replay_ui_routine(routine, "step run", only=only)
    return web.json_response(got)


@routes.get("/api/pc/routines/{id}/steps")
async def api_routine_steps(request: web.Request) -> web.Response:
    with _db() as db:
        row = db.execute("SELECT * FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
    if row and row["tool"] in ("App", "Uri"):                                 # a launch routine is one step, and it is not editable: say what it runs and where the name comes from
        cmd = launch_command(dict(row))
        name = str((cmd["args"] or {}).get("name") or row["title"])
        return web.json_response({"steps": [{"ordinal": 0, "tool": cmd["tool"], "args": cmd["args"], "target": {"name": name, "control": "app"}, "command": cmd["text"], "source": cmd["source"], "fixed": True}]})
    steps = _steps(request.match_info["id"])
    return web.json_response({"steps": [
        {"ordinal": s["ordinal"], "tool": s["tool"],
         "args": json.loads(s["args_json"] or "{}"),
         "target": json.loads(s["target_json"] or "{}"),
         "note": json.loads(s["target_json"] or "{}").get("note", ""), "confidence": json.loads(s["target_json"] or "{}").get("confidence")} for s in steps]})


# ── the second half of a sentence ────────────────────────────────────────────────────────────────────────────────────
# "Open Apple Music and play the ADHD playlist" is two requests. Opening is a
# deterministic MCP call and always worked; the hub then dropped the rest of the
# sentence without a word, which is the worst thing it could do - the person has
# no way to tell the difference between "done" and "ignored".
#
# What comes after the open lives inside somebody else's window, so there are
# exactly three honest outcomes, and this picks between them:
#
#   1. a routine we were taught for this - replay it, deterministically;
#   2. nothing taught, but the thing is named on screen - say so and ASK;
#   3. nothing taught and nothing found - say so and offer to be shown once.
#
# It never clicks on a guess. Every branch either replays something learned or
# ends in a question, because a wrong click on a real desktop is not made better
# by apologising afterwards.

# Words that carry no target: the verbs of asking, and the politeness around them.
_FILLER = {
    "play", "put", "start", "open", "launch", "run", "go", "set", "show", "give", "get", "make",
    "the", "a", "an", "my", "me", "it", "that", "this", "some", "any", "on", "in", "to", "for",
    "of", "and", "then", "please", "now", "up", "off", "again", "next", "from", "with", "at",
    "can", "could", "would", "you", "want", "like", "let", "us", "we", "do", "does",
}


def content_words(then: str) -> "list[str]":
    """The words in a follow-on request that could name something on screen.

    "play the ADHD playlist" -> ["adhd", "playlist"]. The verb is how it was
    asked, not what was asked for, so it cannot help find the target.
    """
    out = []
    for w in re.findall(r"[a-z0-9]+", (then or "").casefold()):
        if w not in _FILLER and len(w) > 1 and w not in out:
            out.append(w)
    return out


def candidates(elements: "list[dict]", then: str, app: str = "") -> "list[dict]":
    """Screen elements that might be what a follow-on request meant, best first.

    Scored on how much of the *name* the request accounts for, not on how many
    words happen to collide. Counting collisions picks the wrong thing: for "play
    the ADHD playlist", a sidebar entry called "ADHD and other focus playlists"
    collides twice and "ADHD" only once, yet "ADHD" is plainly what was meant.
    A name the request explains entirely is the better answer; coverage of the
    request only breaks ties, so "ADHD playlist" still beats "ADHD".
    """
    want = content_words(then)
    if not want:
        return []
    appl = canonical_app_name(app)
    found = []
    for e in elements:
        name = (e.get("name") or "").casefold()
        if not name:
            continue
        hits = [w for w in want if w in name]
        if not hits:
            continue
        words = len(re.findall(r"[a-z0-9]+", name)) or 1
        found.append({**e, "score": round(len(hits) / words, 3), "covers": len(hits),
                      "in_app": bool(appl) and appl in (e.get("window") or "").casefold(),
                      "matched": hits})
    found.sort(key=lambda e: (not e["in_app"], -e["score"], -e["covers"], len(e.get("name") or "")))
    return found


# Nouns that name a KIND of thing rather than a thing. "Play the ADHD playlist"
# identifies its target with "ADHD"; "playlist" only tells you what sort of
# object that is, and on a real screen it is also the name of a navigation row.
# Measured against the captured snapshot: scoring "playlist" as evidence makes
# `list item "Playlists"` the best match at 1.00, beating the actual playlist's
# group at 0.20 - so the hub would confidently click the wrong thing.
_CATEGORY = {
    "playlist", "playlists", "song", "songs", "track", "tracks", "album", "albums",
    "artist", "artists", "station", "radio", "queue", "library", "file", "files",
    "folder", "document", "documents", "tab", "window", "page", "list", "item",
    "items", "mix", "podcast", "episode", "video", "channel",
}


def target_words(then: str) -> "list[str]":
    """The words that identify WHICH thing was meant.

    Falls back to keeping the category nouns when removing them would leave
    nothing to look for, because "open playlists" really is about the playlists.
    """
    words = content_words(then)
    sharp = [w for w in words if w not in _CATEGORY]
    return sharp or words


def _descendants(nodes: "list[dict]", i: int) -> "list[dict]":
    """The subtree under node `i`, in document order."""
    depth = nodes[i]["depth"]
    out = []
    for n in nodes[i + 1:]:
        if n["depth"] <= depth:
            break
        out.append(n)
    return out


def locate(nodes: "list[dict]", then: str, app: str = "") -> dict:
    """Work out what on screen a follow-on request meant, and what to press.

    Two separate questions, which the first version of this conflated into one:
    *which thing* was meant, and *what to press* to act on it. On a real screen
    they are usually different nodes - the name sits on a structural group and
    the buttons are its children - so this finds the thing by name, then picks
    the control inside it using the verb that was asked.

    Returns {"target": node} when there is one answer, {"choices": [...]} when
    the screen genuinely offers more than one, or {} when nothing matched.
    """
    want = target_words(then)
    if not want or not nodes:
        return {}
    appl = canonical_app_name(app)
    scope = [i for i, n in enumerate(nodes)
             if not appl or appl in (n.get("window") or "").casefold()]
    if not scope:
        # No fallback to searching every window. Measured on this machine: with
        # Apple Music open but behind, the tree was the focused app's prose, and
        # the word "ADHD" was in it - so "look anywhere" means offering to click
        # text in an unrelated program and saving that as a music routine. If the
        # app we just opened is not in the tree, the honest answer is that we
        # cannot see it.
        return {}

    scored = []
    for i in scope:
        name = (nodes[i].get("name") or "").casefold()
        if not name or nodes[i]["control"] == "window":
            continue
        hits = [w for w in want if w in name]
        if not hits:
            continue
        words = len(re.findall(r"[a-z0-9]+", name)) or 1
        scored.append((round(len(hits) / words, 3), len(hits), i))
    if not scored:
        return {}
    scored.sort(key=lambda s: (-s[0], -s[1], nodes[s[2]]["depth"]))
    best_score, best_covers, i = scored[0]

    # A pane and the group inside it often carry the same name; the inner one is
    # the one holding the buttons.
    for j in range(i + 1, len(nodes)):
        if nodes[j]["depth"] <= nodes[i]["depth"]:
            break
        if nodes[j]["name"] == nodes[i]["name"]:
            i = j

    even = [k for sc, cv, k in scored[1:]
            if sc == best_score and cv == best_covers and nodes[k]["name"] != nodes[i]["name"]]
    if even:
        return {"choices": [nodes[i]] + [nodes[k] for k in even[:2]]}

    node = nodes[i]
    if "x" in node and node["clickable"]:
        return {"target": node, "via": "direct"}

    # The name was on something structural, so the thing to press is inside it.
    # The verb chooses which: "play" the ADHD playlist means its Play button,
    # not its Edit or More button. This is why the verb cannot just be filler.
    inside = [n for n in _descendants(nodes, i) if "x" in n and n["clickable"]]
    if not inside:
        return {"found": node}                      # seen, but nothing to press
    asked = set(re.findall(r"[a-z0-9]+", (then or "").casefold()))
    named = [n for n in inside
             if asked & set(re.findall(r"[a-z0-9]+", (n.get("name") or "").casefold()))]
    if len(named) == 1:
        return {"target": named[0], "via": "inside", "container": node}
    if len(named) > 1:
        return {"choices": named[:3], "container": node}
    if len(inside) == 1:
        return {"target": inside[0], "via": "inside", "container": node}
    return {"choices": inside[:3], "container": node}


def do_intent(app: str, then: str) -> str:
    """The key a taught follow-on is stored under, stable across wordings."""
    # "play the ADHD playlist" and "open the ADHD playlist" name the same thing but are different jobs: the first must not be
    # answered by a routine that only opens the page.
    verb = "play:" if re.match(r"^\s*(?:play|resume|shuffle|put on)\b", then or "", re.I) else ""
    return "do:" + canonical_app_name(app) + ":" + verb + " ".join(_key_words(then, verb))


# Words that say how a play request was phrased, not what to play: "play something from the ADHD playlist", "play music from ADHD" and "play the ADHD list" are one job.
# Left in the key they made each wording a different job, so a routine that worked was never found again and the slow, step-by-step agent ran every time.
_PHRASING = {"play", "resume", "shuffle", "put", "something", "anything", "music", "song", "songs", "track", "tracks", "tunes", "stuff", "random", "whatever", "good", "nice", "playlist", "playlists", "list"}


def _key_words(then: str, verb: str = "play:") -> "list[str]":
    words = sorted(content_words(then))
    if not verb:
        return words
    core = [w for w in words if w not in _PHRASING]
    return core or words


def routine_for_do(app: str, then: str) -> "dict | None":
    """The taught follow-on for this request: the one stored under today's key, or one stored under an older key (before the wording was ignored) that means the same.
    A trusted one wins over a candidate."""
    row = _routine(do_intent(app, then))
    if row:
        return row
    if not re.match(r"^\s*(?:play|resume|shuffle|put on)\b", then or "", re.I):
        return None
    prefix = "do:" + canonical_app_name(app) + ":play:"
    want = set(_key_words(then))
    best = None
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM pc_routines WHERE intent LIKE ? AND status!='disabled'", (prefix + "%",)).fetchall()]
    for r in rows:
        words = set(r["intent"][len(prefix):].split())
        words = {w for w in words if w not in _PHRASING} or words
        if words == want and (best is None or (r["status"] == "trusted", r["successes"]) > (best["status"] == "trusted", best["successes"])):
            best = r
    return best


def _ask(say: str, action: str, args: dict, label: str, detail: str = "") -> dict:
    """An answer that ends in a question the caller can say yes to.

    `say` is what is spoken, and is short. `detail` is for reading in the log.
    """
    out = {"ok": True, "say": say, "confirm": True,
           "action": {"id": action, "args": args, "label": label}}
    if detail:
        out["detail"] = detail
    return out


# ── did it actually do anything ───────────────────────────────────────────────────────────────────────────────────────
# The hub used to call a click "done" because `MCP.call_tool` returned without
# raising, and then counted that towards promoting the routine to `trusted`. A
# click on a disabled button, on a control that had moved, or on empty space all
# return perfectly well. So a routine could reach `trusted` having never once had
# an effect, and the hub would report success in good faith.
#
# It is also what made a live test worthless: pressing Play while music is
# already playing produces a reply saying it worked, whether or not the press did
# anything at all, and nothing in the system could tell the difference.
#
# The accessibility tree is the evidence. Take the window's fingerprint before
# acting and again after: the names and control types of everything in it. If
# nothing in that window changed, the press had no visible effect, and that is
# reported as what it is rather than dressed up as success.


def flatten(nodes: "list[dict]") -> "list[dict]":
    """The positioned elements of a tree, in the shape ui_signature expects."""
    return [{"window": n["window"], "control": n["control"], "name": n["name"], "path": container_of(nodes, i),
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for i, n in enumerate(nodes) if "x" in n]


def window_state(nodes: "list[dict]", window: str) -> dict:
    """A fingerprint of one window, for comparing before and after.

    Deliberately the same construction as a routine's stored signature, so "the
    screen changed" and "the screen is not the one this was recorded on" are
    measured the same way and cannot disagree.
    """
    return ui_signature(flatten(nodes), window)


async def effect_of(window: str, before: dict, settle: float = 1.2, retries: int = 3) -> dict:
    """Whether the window visibly changed, after giving it a moment to react.

    `settle` exists because a press is not instantaneous: a view redraws, a track
    starts, a dialog opens. Reading too early reports no effect for an action
    that was about to have one - and it got worse when a read dropped from 5 s to 1 s (the kept-open control
    session, 30 Oct): the navigation panel was still sliding open at the first look, so a press that worked was
    reported as doing nothing. So it looks again, a few times, until something changed; "nothing changed" is
    only said after the last look.
    """
    after = None
    for attempt in range(retries + 1):
        try:
            await asyncio.sleep(settle if attempt == 0 else 1.0)
            after = window_state(await _raw_tree(), window)
        except Exception as exc:
            logger.info("pc_control: could not check what changed in %r: %s", window, exc)
            return {"known": False, "changed": False, "why": "I could not read the window afterwards"}
        if after["fingerprint"] != before.get("fingerprint"):
            break
    changed = after["fingerprint"] != before.get("fingerprint")
    return {"known": True, "changed": changed, "before": before, "after": after,
            "why": "" if changed else "nothing in the window changed"}


async def _snap() -> "bytes | None":
    """EXPERIMENTAL shadow mode: a small picture of the screen before a task, or None when the switch is off. Never raises."""
    try:
        from ..yard import evidence as EV
        return await EV.snap()
    except Exception:  # noqa: BLE001
        return None


async def _evidence(way: str, goal: str, app: str, ok: bool, t0: float, before: "bytes | None", markers: dict, routine: "str | None" = None) -> None:
    """EXPERIMENTAL shadow mode: keep what was asked, how it was done, what proved it and a before/after picture. Never raises, never changes a result."""
    try:
        from ..yard import evidence as EV
        if EV.enabled():
            EV.record(way, goal, display_app_name(app), ok, markers, time.time() - t0, routine, before, await EV.snap())
    except Exception:  # noqa: BLE001
        pass


def _learn(chosen: str, ok: bool, t0: float, app: str) -> None:
    """R1: how this task was done (a saved routine, or the agent) and whether it worked, for the learning log. Never raises."""
    try:
        from . import learning as LRN
        LRN.note("rung", canonical_app_name(app), chosen, ["replay", "agent"], ok, (time.time() - t0) * 1000, p=1.0, ctx={"app": canonical_app_name(app)})       # the order is fixed in code, so the chance of this choice was 1
    except Exception:  # noqa: BLE001
        pass


_GENERIC_PLAY = {"play", "put", "on", "some", "any", "something", "anything", "music", "song", "songs", "track", "tracks", "random", "whatever", "good", "nice",
                 "a", "an", "the", "my", "me", "for", "please", "from", "in", "of", "to", "start", "tunes", "stuff", "can", "you", "could", "something"}


def _open_ended_play(then: str, app: str = "") -> bool:
    """A request to play that names nothing to play ("play some music", "put something on")."""
    words = re.findall(r"[a-z0-9']+", (then or "").casefold())
    appw = set(canonical_app_name(app).split())
    return bool(words) and bool(re.search(r"\b(?:play|put|start)\b", then or "", re.I)) and all(w in _GENERIC_PLAY or w in appw for w in words)


async def after(app: str, then: str, request: str, tree=None, fresh: bool = False) -> dict:
    """Deal with the rest of the sentence, once the app is open.

    `tree` is injectable so every branch is testable against a captured snapshot
    rather than a desktop - and the captured ones are real, because every branch
    here was written against an invented format and none of it worked.
    """
    name = display_app_name(app)
    t0 = time.time()
    before = await _snap() if tree is None else None
    if tree is None and not fresh and _open_ended_play(then, app):
        # "play some music" names nothing. Guessing wastes a minute on a library full of choices; one short question does not.
        return _ask(f"{name} is open. You did not name anything, so I can shuffle your whole library, or start a radio station. Shall I shuffle your library?",
                    "desktop_task", {"app": app, "goal": "shuffle all songs in my library"}, "Shuffle my library")
    taught = None if fresh else routine_for_do(app, then)          # "try again" is the sentence said again, not the old recording played again
    if taught and taught["tool"] == "surface" and taught["status"] != "disabled":
        from . import machine_routines as MR
        got = await MR.replay_machine_routine(taught, request=request)
        if tree is None:
            await _evidence("recorded routine", then, app, bool(got.get("ok")), t0, before, {"routine_clean": bool(got.get("ok")), "nothing_changed": not got.get("ok")}, taught.get("id"))
        if got.get("ok"):
            return {"ok": True, "say": f"Done: {then}.", "routine": got.get("routine")}
        return {"ok": False, "say": f"Opened {name}. {got.get('say') or 'The recording did not run.'}"}
    if taught and taught["tool"] == "ui" and _steps(taught["id"]):
        got = await replay_ui_routine(taught, request)
        heard = None
        if got.get("ok") and tree is None and os.environ.get("HUB_DESKTOP_AGENT", "1") != "0":
            # A replay that changed the window is not a replay that played music: Windows says whether something is playing.
            from . import desktop_agent as DA
            heard = None
            for _ in range(3 if DA.wants_music(then) else 0):       # a track takes a moment to start
                heard = DA.playing_now(await DA.media_sessions(), app)
                if heard:
                    break
                await asyncio.sleep(1.5)
            if DA.wants_music(then) and not heard:
                _remember_outcome(taught["id"], False)
                got = {"ok": False, "route": "fall-through", "say": "It ran, but nothing is playing."}
        if tree is None:
            _learn("replay", bool(got.get("ok")), t0, app)
            await _evidence("saved routine", then, app, bool(got.get("ok")), t0, before,
                            {"routine_clean": bool(got.get("ok")), "windows_confirms": bool(got.get("ok") and heard), "nothing_changed": not got.get("ok")}, taught.get("id"))
        if got.get("ok"):
            return {"ok": True, "say": f"Opened {name} and {then}.", "routine": got.get("routine")}
        if got.get("route") != "fall-through":
            return {"ok": False, "say": f"Opened {name}. {got.get('say') or 'The rest did not run.'}"}
        # "Recorded on a different screen": nothing was pressed, so look at this screen afresh below.

    # Nothing taught for this. A model that can see the app's controls does it step by step, and the outcome is
    # checked (for music: Windows says it is playing). This used to stop at "Press X?" or "Record it?" for every ask.
    if tree is None and os.environ.get("HUB_DESKTOP_AGENT", "1") != "0":
        from . import desktop_agent as DA
        t1 = time.time()
        got = await DA.run(then, app)
        _learn("agent", bool(got["ok"]), t1, app)
        try:
            from ..yard import evidence as EV
            last = (got.get("tries") or [{}])[-1]
            await _evidence("agent", then, app, bool(got["ok"]), t1, before, EV.markers_from_trace(last.get("trace") or [], bool(got["ok"]), got.get("say") or "", DA.wants_music(then)))
        except Exception:  # noqa: BLE001
            pass
        _record_run(request, "agent", "done" if got["ok"] else "failed",
                    f"{then}: {got['say'][:140]} [{', '.join(t['model'] for t in got['tries'])}]", level="ui-tree" if got["ok"] else "")
        if got["ok"]:
            return {"ok": True, "say": f"Opened {name}. {got['say']}", "routine": got.get("routine"), "tries": got["tries"]}
        logger.info("pc_control: the desktop agent could not %r in %s: %s", then, app, got["say"])
        if fresh:                                                     # an attempt again has nobody to answer a question: it says what stopped it, plainly
            return {"ok": False, "say": f"I opened {name}, but could not do it: {got['say']}", "tries": got["tries"]}

    try:
        nodes = await (tree(app) if tree else _raw_tree(app))
    except Exception as exc:
        logger.info("pc_control: could not read %s's window: %s", app, exc)
        nodes = []

    got = locate(nodes, then, app) if nodes else {}

    # "Open the ADHD playlist" while the ADHD playlist's own page is showing: the thing named is the page
    # itself (a heading with controls inside it), and "open" matches none of those controls. It is already
    # done; offering "which one: Shuffle, Play, Downloaded?" would be nonsense.
    box = got.get("container")
    if box and not got.get("target") and _OPEN_ONLY.match(then or "") and "x" not in box:
        return {"ok": True, "say": f"“{box['name']}” is already showing in {name}."}

    if got.get("target"):
        t = got["target"]
        where = (f" inside “{got['container']['name']}”"
                 if got.get("container") else "")
        inside = f" in “{got['container']['name']}”" if got.get("container") else ""
        return _ask(f"Press “{t['name']}”{inside}?",
                    "pc_do", {"app": app, "then": then, "request": request,
                              "name": t["name"], "control": t.get("control", ""),
                              "window": t.get("window", "")},
                    f"Press “{t['name']}” in {name}",
                    detail=f"Opened {name}. I can see {t['control']} “{t['name']}”{where}.")

    if got.get("choices"):
        choices = ", ".join(f"“{c['name']}”" for c in got["choices"])
        return _ask("Which one?", "pc_pick", {"app": app, "then": then, "request": request},
                    f"Choose what to press in {name}", detail=f"More than one thing matches: {choices}.")

    if got.get("found"):
        return _ask(f"I can't {then} yet. Record it?", "pc_record", {"app": app, "then": then}, f"Record how to {then}",
                    detail=f"I can see “{got['found']['name']}” but nothing inside it that I can press.")

    opener = nav_opener(nodes, app) if nodes else None
    if opener:
        want = " ".join(target_words(then)) or then
        ident = {"name": opener["name"], "control": opener["control"], "window": opener.get("window", "")}
        return _ask(f"I can't see “{want}” yet. Path: press “{opener['name']}”, then press the item named like “{want}”. Go?",
                    "pc_path", {"app": app, "then": then, "request": request, "steps": [ident]},
                    f"Open the navigation, then press “{want}” in {name}",
                    detail=f"“{want}” is not in the window, but “{opener['name']}” is, and the item may appear once it is open.")

    why = "nothing in its window is named that" if nodes else "I cannot read its window"
    seen = _visible_names(nodes)
    sees = f" I can see: {', '.join(seen)}." if seen else ""
    short = "I cannot read its window" if not nodes else f"I can't {then} yet"
    return _ask(f"Opened {name}. {short}. Record it?", "pc_record", {"app": app, "then": then}, f"Record how to {then}",
                detail=f"I cannot {then} myself: {why}.{sees}")


_OPEN_ONLY = re.compile(r"^\s*(?:open|show|go to|view|see|display|bring up)\b", re.I)
_NAV_OPENER = re.compile(r"^open\s+(?:the\s+)?(?:navigation(?: pane| menu)?|sidebar|side bar|side menu|main menu|menu)$", re.I)


def nav_opener(nodes: "list[dict]", app: str = "") -> "dict | None":
    """The control that opens an app's navigation, when it is closed ("Open Navigation").

    Only an *open* control counts: once the navigation is showing, the same button reads "Close Navigation"
    and this returns nothing, so the Hub cannot toggle it shut again.
    """
    appl = canonical_app_name(app)
    for n in nodes or []:
        if appl and appl not in (n.get("window") or "").casefold():
            continue
        if "x" in n and _NAV_OPENER.match((n.get("name") or "").strip()):
            return n
    return None


def _find_by_identity(nodes: "list[dict]", ident: dict, app: str = "") -> "dict | None":
    """The node a step names, by name and control, inside the app's window."""
    appl = canonical_app_name(app)
    name, control = str(ident.get("name") or ""), str(ident.get("control") or "").lower()
    for n in nodes or []:
        if appl and appl not in (n.get("window") or "").casefold():
            continue
        if (n.get("name") or "") == name and (n.get("control") or "").lower() == control and "x" in n:
            return n
    return None


def goal_met(then: str, nodes: "list[dict]") -> "bool | None":
    """Whether what was asked now shows on screen; None when this kind of ask cannot be checked from the tree.

    "play ..." is met when a Pause or Stop control appears. "open ..." has no reliable marker, so it is left
    unverified rather than guessed.
    """
    if re.match(r"^\s*(?:play|resume)\b", then or "", re.I):
        return any((n.get("control") == "button" and re.fullmatch(r"(?:pause|stop)", (n.get("name") or "").strip(), re.I))
                   for n in nodes or [])
    return None


async def do_path(app: str, then: str, request: str, steps: "list[dict]", tree=None) -> dict:
    """Press the path that was shown, then the thing that was asked for. One YES covers the shown steps.

    Each step is found again by name and control (never by where it used to be), checked (present, enabled,
    not on the never-press list), pressed, and checked for effect. After the shown steps the screen is read
    again and the request is located afresh: that last press is only made when there is exactly one answer.
    Anything unclear stops with what the screen offers, never a guess.
    """
    name = display_app_name(app)
    read = (lambda: tree(app)) if tree else (lambda: _raw_tree(app))
    saved: "list[dict]" = []
    first_nodes = None
    window = ""
    plan = list(steps or [])

    async def press(node: dict) -> "dict | None":
        """Press one node. Returns a failure reply, or None when it worked."""
        why = step_blocker(node)
        if why:
            _record_run(request, "path", "skipped", f"“{node['name']}” {why}")
            return {"ok": False, "say": f"I stopped: “{node['name']}” {why}."}
        before = window_state(nodes_now, node["window"])
        try:
            await MCP.call_tool("windows", "Click", {"loc": [node["x"], node["y"]], "button": "left", "clicks": 1})
        except Exception as exc:
            _record_run(request, "path", "failed", f"“{node['name']}”: {exc}")
            return {"ok": False, "say": f"I could not press “{node['name']}”: {str(exc)[:150]}."}
        did = await effect_of(node["window"], before)
        if did["known"] and not did["changed"]:
            _record_run(request, "path", "no-effect", f"pressed {node['control']} {node['name']}")
            return {"ok": False, "say": f"I pressed “{node['name']}” in {name}, but {did['why']}, so I stopped "
                                        f"and saved nothing."}
        saved.append({"tool": "Click", "args": {"button": "left", "clicks": 1},
                      "target": {"name": node["name"], "control": node["control"], "window": node["window"]}})
        return None

    for st in plan:
        nodes_now = await read()
        if first_nodes is None:
            first_nodes = nodes_now
        node = _find_by_identity(nodes_now, st, app)
        if not node:
            _record_run(request, "path", "skipped", f"gone: {st.get('name')}")
            return {"ok": False, "say": f"“{st.get('name')}” is not on screen any more, so I pressed nothing."}
        window = node["window"]
        bad = await press(node)
        if bad:
            return bad

    nodes_now = await read()
    if first_nodes is None:
        first_nodes = nodes_now
    got = locate(nodes_now, then, app)
    t = got.get("target")
    want = " ".join(target_words(then)) or then
    if not t:
        seen = _visible_names(nodes_now)
        sees = f" I can see: {', '.join(seen)}." if seen else ""
        _record_run(request, "path", "failed", f"after the shown steps, no single match for {want!r}")
        if got.get("choices"):
            opts = ", ".join(f"“{c['name']}”" for c in got["choices"])
            return {"ok": False, "say": f"Opened it, but more than one thing matches “{want}”: {opts}. Say which one."}
        return {"ok": False, "say": f"Pressed the shown steps, but I still can't find “{want}”.{sees}"}
    window = t["window"] or window
    bad = await press(t)
    if bad:
        return bad
    after_nodes = await read()
    goal = goal_met(then, after_nodes)
    if goal is False:
        _record_run(request, "path", "unverified", f"pressed {t['name']}; the result of {then!r} is not showing")
        return {"ok": False, "say": f"I pressed “{t['name']}”, but I can't see that it worked, so I have not saved it."}
    saved_routine = save_ui_routine(do_intent(app, then), f"{name}: {then}".strip(), window, saved,
                                    ui_signature(flatten(first_nodes), window))
    _record_run(request, "path", "done", f"{len(saved)} step(s) ending at {t['control']} {t['name']}", level="ui-tree")
    verified = " I could see it working." if goal else ""
    return {"ok": True,
            "say": f"Pressed {' then '.join('“' + s_['target']['name'] + '”' for s_ in saved)} in {name}.{verified} "
                   f"Saved as a routine to check, so next time “{then}” is one request.",
            "routine": {"id": saved_routine["id"], "status": saved_routine["status"],
                        "successes": saved_routine["successes"], "tag": "ROUTINE"}}


def _visible_names(nodes: "list[dict]", limit: int = 6) -> "list[str]":
    """A few things actually on screen, so "I can't find it" says what it *could* see."""
    out, seen = [], set()
    for n in nodes or []:
        nm = str(n.get("name") or "").strip()
        if (n.get("control") in ("button", "tabitem", "listitem", "hyperlink", "menuitem", "treeitem", "group")
                and 2 < len(nm) < 36 and nm.casefold() not in seen):
            seen.add(nm.casefold())
            out.append(nm)
        if len(out) >= limit:
            break
    return out


async def do_on_screen(app: str, then: str, request: str, target: dict, tree=None) -> dict:
    """Press the thing that was offered, and keep it as a routine if it worked.

    The screen is read again and the request resolved again, rather than trusting
    the coordinate in the offer: between the question and the yes there is a
    person deciding, and a window can scroll, close or change in that time. If
    the answer has moved on, this refuses instead of pressing where the thing
    used to be - that refusal is the only reason this is safe to point at a real
    desktop at all.
    """
    name = display_app_name(app)
    offered = str(target.get("name") or "")
    try:
        nodes = await (tree(app) if tree else _raw_tree(app))
    except Exception as exc:
        _record_run(request, "discovery", "failed", f"snapshot: {exc}")
        return {"ok": False, "say": f"I lost sight of {name}'s window, so I pressed nothing."}

    got = locate(nodes, then, app)
    t = got.get("target")
    if not t:
        _record_run(request, "discovery", "skipped", f"gone: {offered}")
        return {"ok": False, "say": f"“{offered}” is not there any more, so I pressed "
                                    f"nothing. Ask again and I will look afresh."}
    if offered and t["name"] != offered:
        _record_run(request, "discovery", "skipped", f"changed: {offered} -> {t['name']}")
        return {"ok": False, "say": f"The window changed: I offered “{offered}” but now "
                                    f"find “{t['name']}”. Ask again so you can agree to "
                                    f"the right one."}
    word = never_press(t["name"])
    if word:
        _record_run(request, "discovery", "skipped", f"never-press: {t['name']} ({word})")
        return {"ok": False, "say": f"I will not press “{t['name']}” on my own: it is on the never-press list ({word}). "
                                    f"Do that one yourself."}
    before = window_state(nodes, t["window"])
    try:
        await MCP.call_tool("windows", "Click",
                            {"loc": [t["x"], t["y"]], "button": "left", "clicks": 1})
    except Exception as exc:
        _record_run(request, "discovery", "failed", str(exc))
        return {"ok": False, "say": f"I could not press “{t['name']}”: {str(exc)[:150]}."}

    # The press returning without error says nothing about whether it worked.
    did = await effect_of(t["window"], before)
    if did["known"] and not did["changed"]:
        _record_run(request, "discovery", "no-effect", f"pressed {t['control']} {t['name']}")
        return {"ok": False, "say": f"I pressed “{t['name']}” in {name}, but {did['why']}, "
                                    f"so I cannot tell you it worked and I have not saved it as a "
                                    f"routine. Shall I record it while you do it once?",
                "confirm": True,
                "action": {"id": "pc_record", "args": {"app": app, "then": then},
                           "label": f"Record how to {then}"}}

    ident = {"name": t["name"], "control": t["control"], "window": t["window"]}
    flat = flatten(nodes)
    saved = save_ui_routine(do_intent(app, then), f"{name}: {then}".strip(),
                            t["window"], [{"tool": "Click",
                                           "args": {"button": "left", "clicks": 1},
                                           "target": ident}],
                            ui_signature(flat, t["window"]))
    _record_run(request, "discovery", "done", f"pressed {t['control']} {t['name']}, window changed", level="ui-tree")
    seen = "" if not did["known"] else " The window changed, so it took effect."
    return {"ok": True,
            "say": f"Pressed “{t['name']}” in {name}.{seen} Saved, so next time "
                   f"“{then}” is one step.",
            "routine": {"id": saved["id"], "status": saved["status"],
                        "successes": saved["successes"], "tag": "ROUTINE"}}
