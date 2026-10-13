"""TALK PC-control router: a small, auditable routine store over Windows MCP."""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from ..runtime import STATE
from . import mcp as MCP

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

# Words that end up glued to an app name when somebody is being polite.
_TRAILING = __import__("re").compile(
    r"\s*\b(?:for me|please|now|again|up|app|application|program)\b\s*$", __import__("re").I)


def classify_request(text: str) -> dict | None:
    """Classify a spoken or typed request into a task, before any routine is looked up.

    Returns the app to open and, when the sentence carried on, what was asked
    *after* it - "play the ADHD playlist" is a second step, not part of the name.
    """
    import re
    t = " ".join((text or "").casefold().split())
    m = _OPEN_RX.search(t)
    if not m:
        return None
    name = m.group(1)
    for _ in range(3):                       # "apple music for me please" -> "apple music"
        trimmed = _TRAILING.sub("", name)
        if trimmed == name:
            break
        name = trimmed
    app = canonical_app_name(name)
    # "open the" must not resolve to an application called "the".
    if len(app) < 2 or app in _NOT_A_NAME:
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
        status = "trusted" if successes >= 2 else "candidate"
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
        if "level" not in {c[1] for c in db.execute("PRAGMA table_info(pc_runs)")}:
            db.execute("ALTER TABLE pc_runs ADD COLUMN level TEXT NOT NULL DEFAULT ''")
        _consolidate_launch_routines(db)
        db.execute("UPDATE pc_routines SET status='trusted', updated=? WHERE status='candidate' AND successes>=2", (time.time(),))
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


async def launch_app(app: str, request: str, then: str = "") -> dict:
    """Open an installed application, say truthfully whether it opened, and only
    then remember it.

    `then` is the rest of the sentence - "and play the ADHD playlist". See `after`
    for why that is either replayed, asked about, or offered to be learned, but
    never silently dropped.
    """
    heard = canonical_app_name(app)
    if len(heard) < 2:
        return {"ok": False, "say": "Tell me which application to open."}

    corrected = False
    names = await start_app_names()
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

    key = canonical_app_name(target)
    known = _routine(_intent(key))
    args = json.loads(known["args_json"]) if known else {"mode": "launch", "name": target}
    route = "routine" if known else "discovery"
    try:
        result = await MCP.call_tool("windows", "App", args)
    except Exception as exc:
        _record_run(request, route, "failed", str(exc))
        return {"ok": False, "say": f"I could not open {target}: {str(exc)[:150]}."}

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
    if then:
        got = await after(key, then, request)
        return {**got, "routine": got.get("routine") or tag}
    return {"ok": True, "say": said, "routine": tag}


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


def parse_snapshot(text: str) -> "list[dict]":
    """Every element with a position - what a routine can actually click.

    Kept to the shape the rest of the hub already expects (window, control, name,
    x, y), so routine replay and identity matching did not have to change; they
    were correct, and simply never received anything to work on.
    """
    return [{"window": n["window"], "control": n["control"], "name": n["name"],
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for n in parse_tree(text) if "x" in n]


def ui_signature(elements: "list[dict]", window: str) -> dict:
    """What this screen looked like, in a form that survives it being moved or resized.

    Names and control types only - never coordinates, so dragging the window does
    not invalidate the routine, while the dialog changing underneath it does.
    """
    same = sorted(f"{e['control']}|{e['name']}" for e in elements if e["window"] == window)
    digest = hashlib.sha256(chr(10).join(same).encode("utf-8")).hexdigest()[:16]
    return {"kind": "ui", "window": window, "controls": len(same), "fingerprint": digest}


async def _raw_tree(app: str = "") -> "list[dict]":
    """The tree, with the app brought to the front first if one was named.

    A snapshot of an unfocused window is empty. Measured on this machine: with
    Apple Music open but behind, the tree held 499 `word` nodes belonging to the
    focused application and nothing at all from Apple Music; after an App/switch
    it held 72 buttons, 8 links and the playlist. Reading the screen without
    focusing first does not return less, it returns somebody else's window.
    """
    if app:
        try:
            await MCP.call_tool("windows", "App", {"mode": "switch", "name": display_app_name(app)})
            await asyncio.sleep(1.0)               # the window has to finish coming forward
        except Exception as exc:
            logger.info("pc_control: could not focus %s: %s", app, exc)
    result = await MCP.call_tool("windows", "Snapshot", {"use_vision": False})
    return parse_tree(snapshot_text(result))


async def _snapshot(app: str = "") -> "list[dict]":
    return [{"window": n["window"], "control": n["control"], "name": n["name"],
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for n in await _raw_tree(app) if "x" in n]


def _match(elements: list[dict], target: dict) -> dict | None:
    """Find the element a step was recorded against, in a fresh snapshot.

    Exact window+control+name first; then the same control+name in any window,
    because a document title changes far more often than a button's label.
    """
    name, control = target.get("name", ""), (target.get("control") or "").lower()
    window = target.get("window", "")
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
    return ""


async def replay_ui_routine(routine: dict, request: str = "") -> dict:
    """Run a stored step sequence, but only onto the screen it was recorded against.

    Every refusal here is deliberate: a routine that cannot see what it expects
    must stop, never fall back to clicking where the control used to be.
    """
    stored = json.loads(routine["signature_json"] or "{}")
    steps = _steps(routine["id"])
    if not steps:
        return {"ok": False, "route": "fall-through", "say": "That routine has no steps saved."}

    # Focus first: an unfocused window contributes nothing to the tree, so a
    # routine replayed while something else is in front would see an empty
    # screen and conclude its target had vanished.
    elements = await _snapshot(stored.get("window", ""))
    live = ui_signature(elements, stored.get("window", ""))
    if live["fingerprint"] != stored.get("fingerprint"):
        _record_run(request, "fall-through", "skipped",
                    f"signature mismatch: expected {stored.get('fingerprint')}, saw {live['fingerprint']}")
        _remember_outcome(routine["id"], False)
        return {"ok": False, "route": "fall-through",
                "say": f"{routine['title']} was recorded on a different screen, so I did not touch it."}

    window = stored.get("window", "")
    before = live                      # the signature just taken, reused as the baseline
    for step in steps:
        target = json.loads(step["target_json"] or "{}")
        args = dict(json.loads(step["args_json"] or "{}"))
        if target:
            found = _match(elements, target)
            if not found:
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
        try:
            await MCP.call_tool("windows", step["tool"], args)
        except Exception as exc:
            _record_run(request, "routine", "failed", f"step {step['ordinal']}: {exc}")
            _remember_outcome(routine["id"], False)
            return {"ok": False, "route": "routine", "say": f"{routine['title']} failed: {str(exc)[:150]}"}
        # The screen moved; anything resolved from the old snapshot is now a guess.
        # No re-focus: we are the ones driving this window, so it is still in
        # front, and focusing again would cost a second of waiting per step.
        elements = await _snapshot()

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


def _remember_outcome(routine_id: str, success: bool) -> dict:
    """Same promotion rule as launches: two clean runs earn trust, a failure disables."""
    with _db() as db:
        db.execute("UPDATE pc_routines SET successes=successes+?, failures=failures+?, updated=? WHERE id=?",
                   (int(success), int(not success), time.time(), routine_id))
        if not success:
            db.execute("UPDATE pc_routines SET status='disabled', updated=? WHERE id=? AND status='candidate'",
                       (time.time(), routine_id))
        else:
            # Promote in the same transaction. _db() also does this on open, but that
            # would not run until the next call, so the status handed back to the
            # caller would describe the run before this one.
            db.execute("UPDATE pc_routines SET status='trusted', updated=? "
                       "WHERE id=? AND status='candidate' AND successes>=2", (time.time(), routine_id))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (routine_id,)).fetchone())


@routes.get("/api/pc/routines")
async def api_routines(request: web.Request) -> web.Response:
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT id,intent,title,tool,kind,args_json,status,successes,failures,created,updated FROM pc_routines ORDER BY updated DESC")]
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
    if routine["tool"] != "ui":
        raise ValueError("only recorded routines can be replayed from here; launches go through TALK")
    return await replay_ui_routine(routine, request=request)


@routes.post("/api/pc/routines/{id}/run")
async def api_run_routine(request: web.Request) -> web.Response:
    try:
        return web.json_response(await run_routine(request.match_info["id"]))
    except KeyError as exc:
        raise web.HTTPNotFound(text=str(exc))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))


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
    """Disable a routine, or put it back to candidate. Never promotes to trusted -
    that is earned by clean runs, not by a button."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = str(body.get("status", ""))
    if status not in ("disabled", "candidate"):
        raise web.HTTPBadRequest(text="status must be 'disabled' or 'candidate'")
    with _db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE id=?", (request.match_info["id"],)).fetchone()
        if not row:
            raise web.HTTPNotFound(text="no such routine")
        db.execute("UPDATE pc_routines SET status=?, updated=? WHERE id=?",
                   (status, time.time(), row["id"]))
        return web.json_response({"ok": True, "routine": dict(
            db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())})


@routes.get("/api/pc/routines/{id}/steps")
async def api_routine_steps(request: web.Request) -> web.Response:
    steps = _steps(request.match_info["id"])
    return web.json_response({"steps": [
        {"ordinal": s["ordinal"], "tool": s["tool"],
         "args": json.loads(s["args_json"] or "{}"),
         "target": json.loads(s["target_json"] or "{}")} for s in steps]})


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
    return "do:" + canonical_app_name(app) + ":" + " ".join(sorted(content_words(then)))


def _ask(say: str, action: str, args: dict, label: str) -> dict:
    """An answer that ends in a question the caller can say yes to."""
    return {"ok": True, "say": say, "confirm": True,
            "action": {"id": action, "args": args, "label": label}}


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
    return [{"window": n["window"], "control": n["control"], "name": n["name"],
             "x": n["x"], "y": n["y"], "action": "click" if n["clickable"] else ""}
            for n in nodes if "x" in n]


def window_state(nodes: "list[dict]", window: str) -> dict:
    """A fingerprint of one window, for comparing before and after.

    Deliberately the same construction as a routine's stored signature, so "the
    screen changed" and "the screen is not the one this was recorded on" are
    measured the same way and cannot disagree.
    """
    return ui_signature(flatten(nodes), window)


async def effect_of(window: str, before: dict, settle: float = 1.2) -> dict:
    """Whether the window visibly changed, after giving it a moment to react.

    `settle` exists because a press is not instantaneous: a view redraws, a track
    starts, a dialog opens. Reading too early reports no effect for an action
    that was about to have one. Reading cannot be retried forever either, so this
    is one short wait and one look.
    """
    try:
        await asyncio.sleep(settle)
        after = window_state(await _raw_tree(), window)
    except Exception as exc:
        logger.info("pc_control: could not check what changed in %r: %s", window, exc)
        return {"known": False, "changed": False, "why": "I could not read the window afterwards"}
    changed = after["fingerprint"] != before.get("fingerprint")
    return {"known": True, "changed": changed, "before": before, "after": after,
            "why": "" if changed else "nothing in the window changed"}


async def after(app: str, then: str, request: str, tree=None) -> dict:
    """Deal with the rest of the sentence, once the app is open.

    `tree` is injectable so every branch is testable against a captured snapshot
    rather than a desktop - and the captured ones are real, because every branch
    here was written against an invented format and none of it worked.
    """
    name = display_app_name(app)
    taught = _routine(do_intent(app, then))
    if taught and taught["tool"] == "ui" and _steps(taught["id"]):
        got = await replay_ui_routine(taught, request)
        if got.get("ok"):
            return {"ok": True, "say": f"Opened {name} and {then}.", "routine": got.get("routine")}
        return {"ok": False, "say": f"Opened {name}. {got.get('say') or 'The rest did not run.'}"}

    try:
        nodes = await (tree(app) if tree else _raw_tree(app))
    except Exception as exc:
        logger.info("pc_control: could not read %s's window: %s", app, exc)
        nodes = []

    got = locate(nodes, then, app) if nodes else {}

    if got.get("target"):
        t = got["target"]
        where = (f" inside “{got['container']['name']}”"
                 if got.get("container") else "")
        return _ask(f"Opened {name}. I can see {t['control']} “{t['name']}”{where}. "
                    f"Shall I press it? I will remember it, so next time this is one step.",
                    "pc_do", {"app": app, "then": then, "request": request,
                              "name": t["name"], "control": t.get("control", ""),
                              "window": t.get("window", "")},
                    f"Press “{t['name']}” in {name}")

    if got.get("choices"):
        choices = ", ".join(f"“{c['name']}”" for c in got["choices"])
        return _ask(f"Opened {name}. More than one thing matches that: {choices}. Which one?",
                    "pc_pick", {"app": app, "then": then, "request": request},
                    f"Choose what to press in {name}")

    if got.get("found"):
        return _ask(f"Opened {name}. I can see “{got['found']['name']}” but nothing inside "
                    f"it that I can press. Shall I record it while you do it once?",
                    "pc_record", {"app": app, "then": then}, f"Record how to {then}")

    why = "nothing in its window is named that" if nodes else "I cannot read its window"
    seen = _visible_names(nodes)
    sees = f" I can see: {', '.join(seen)}." if seen else ""
    return _ask(f"Opened {name}. I cannot {then} myself: {why}.{sees} Shall I record it while you do it "
                f"once? After that I can do it on my own.",
                "pc_record", {"app": app, "then": then}, f"Record how to {then}")


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
