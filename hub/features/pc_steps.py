"""Do a task on a web page or in an app from discrete instructions, by looking at the screen.

This is not a scraper and it does not guess. A person (or a mission agent asking for desktop control) gives the
steps; the Hub shows the whole path, asks once, then does each step against what is actually on screen:

    go to wikipedia.org; click the search box; type "Ada Lovelace" in the search box; press enter; expect "Analytical Engine"

Each step is looked up in the live UI tree (the same tree and the same never-press list the app-navigation path
uses), done, and given a moment to settle. The first step that cannot be done stops the run and says what was on
screen instead. A run that works is remembered as a recipe (trusted after two clean runs, like every other
routine); nothing here runs without a YES, and never against a control on the never-press list or into a field
that looks like a password or a card.

    POST /api/pc/steps   {text|steps, run?, approved?}   run false (default) = parse and show the path; run true needs
                         approved true, which the caller sets only after the user said yes (a mission agent asks them first)
    GET  /api/pc/recipes
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time

from aiohttp import web

from ..config import logger
from ..runtime import STATE, write_json
from . import mcp as MCP
from . import pc_control as PC

routes = web.RouteTableDef()
RECIPES = STATE / "pc_step_recipes.json"
BROWSER = "edge"                    # the window steps are looked up in (a part of its title)
BROWSER_APP = "Microsoft Edge"      # what to bring to the front before reading it; opening a page uses the default browser
SETTLE = 1.3
EXPECT_WAIT = 8.0
TRUST_AFTER = 2

_KEYS = {"enter", "return", "tab", "escape", "esc", "backspace", "delete", "space", "up", "down", "left", "right",
         "pagedown", "pageup", "home", "end", "f5"}
_KEY_COMBO = re.compile(r"^(?:(?:ctrl|alt|shift|win)\+)+[a-z0-9]$|^(?:ctrl|alt|shift|win)\+(?:" + "|".join(sorted(_KEYS)) + r")$", re.I)
_NEVER_TYPE = re.compile(r"\b(?:password|passcode|pin|cvv|cvc|card number|security code|ssn|social security|secret)\b", re.I)
_QUOTED = re.compile(r"[\"“”]([^\"“”]*)[\"“”]")
_SPLIT = re.compile(r"\s*(?:;|\n|\band then\b|\bthen\b|(?:^|\s)\d{1,2}[.)]\s+)\s*", re.I)
_URL = r"(?:https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?)"

_GRAMMAR = [
    ("open", re.compile(rf"^(?:go to|open|visit|navigate to|browse to)\s+(?P<url>{_URL})\s*$", re.I)),
    ("type", re.compile(r"^(?:type|enter|write|search for|fill in)\s+(?P<text>@@Q\d+@@)(?:\s+(?:in|into|in to)\s+(?:the\s+)?(?P<field>.+))?\s*$", re.I)),
    ("expect", re.compile(r"^(?:wait for|expect|check that|make sure|verify|confirm)\s+(?:that\s+)?(?:the\s+)?(?:page|window|screen)?\s*(?:shows?|has|says|contains)?\s*(?P<text>@@Q\d+@@)\s*$", re.I)),
    ("key", re.compile(r"^(?:press|hit)\s+(?:the\s+)?(?P<key>[a-z0-9+]+?)(?:\s+key)?\s*$", re.I)),
    ("click", re.compile(r"^(?:click|press|select|choose|tap|open)(?:\s+on)?\s+(?:the\s+)?(?P<name>.+)$", re.I)),
]


def parse(text: str) -> dict:
    """{"steps": [...]} or {"error": "..."} naming the first piece that was not understood."""
    quotes: list[str] = []

    def hold(m):
        quotes.append(m.group(1))
        return f"@@Q{len(quotes) - 1}@@"
    body = _QUOTED.sub(hold, (text or "").strip())
    body = re.sub(r"^(?:please\s+)?(?:follow these steps|do these steps|steps)\s*[:\-]?\s*", "", body, flags=re.I)
    pieces = [p.strip(" .,") for p in _SPLIT.split(body) if p and p.strip(" .,")]
    steps = []
    for piece in pieces:
        got = None
        for kind, rx in _GRAMMAR:
            m = rx.match(piece)
            if not m:
                continue
            d = {k: v for k, v in m.groupdict().items() if v is not None}
            if kind == "key":
                k = d["key"].lower()
                if k not in _KEYS and not _KEY_COMBO.match(k):
                    continue                       # "press the Search button" is a click, not a key
                d["key"] = k
            if "text" in d:
                d["text"] = quotes[int(re.search(r"\d+", d["text"]).group())]
            if kind == "open" and not d["url"].lower().startswith("http"):
                d["url"] = "https://" + d["url"]
            got = {"do": kind, **d}
            break
        if not got:
            return {"error": f"I did not understand step {len(steps) + 1}: “{piece[:80]}”. "
                             "Each step is one of: go to <site>, click <name>, type “text” [in <field>], press <key>, expect “text”."}
        steps.append(got)
    if not steps:
        return {"error": "No steps found."}
    return {"steps": steps}


def describe(step: dict) -> str:
    d = step["do"]
    if d == "open":
        return f"go to {step['url']}"
    if d == "click":
        return f"press “{step['name']}”"
    if d == "type":
        return f"type “{step['text']}”" + (f" in “{step['field']}”" if step.get("field") else "")
    if d == "key":
        return f"press {step['key']}"
    return f"check the page shows “{step['text']}”"


def path_text(steps: "list[dict]") -> str:
    return "; ".join(f"{i + 1}. {describe(s)}" for i, s in enumerate(steps))


# -- recipes: a run that worked is kept, trusted after two clean runs ---------------------------------------------
def _rid(steps: "list[dict]") -> str:
    return hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()[:12]


def recipes() -> "list[dict]":
    try:
        return json.loads(RECIPES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _remember(steps: "list[dict]", ok: bool) -> dict:
    rows = recipes()
    rid = _rid(steps)
    row = next((r for r in rows if r["id"] == rid), None)
    if not row:
        row = {"id": rid, "title": describe(steps[0]) + (f" … {describe(steps[-1])}" if len(steps) > 1 else ""),
               "steps": steps, "status": "candidate", "successes": 0, "failures": 0, "created": time.time()}
        rows.append(row)
    if ok:
        row["successes"] += 1
        row["failures"] = 0
        if row["successes"] >= TRUST_AFTER and row["status"] == "candidate":
            row["status"] = "trusted"
    else:
        row["failures"] += 1
        if row["failures"] >= TRUST_AFTER:
            row["status"] = "disabled"
    row["updated"] = time.time()
    write_json(RECIPES, rows)
    return row


# -- doing it --------------------------------------------------------------------------------------------------------
def _flags(node: dict) -> str:
    return PC.step_blocker(node, "Click")


async def _find(name: str, nodes: "list[dict]") -> dict:
    # A control whose whole name is what was asked for beats any word-by-word match ("Search" the link over
    # "Search" the word inside a heading); only when there is no such control does the looser lookup run.
    want = " ".join(name.casefold().split())
    exact = [n for n in nodes if BROWSER in (n.get("window") or "").casefold() and n.get("x") is not None
             and n.get("clickable") and " ".join((n.get("name") or "").casefold().split()) == want]
    if len(exact) == 1:
        return {"target": exact[0]}
    got = PC.locate(nodes, name, app=BROWSER)
    if got.get("target"):
        return got
    if got.get("choices"):
        return {"stop": f"“{name}” matches more than one thing: " + ", ".join(f"“{c['name']}”" for c in got["choices"]) + "."}
    seen = PC._visible_names(nodes, 8)
    return {"stop": f"I can't see “{name}” on screen." + (f" I can see: {', '.join(seen)}." if seen else "")}


async def _tree() -> "list[dict]":
    return await PC._raw_tree(BROWSER_APP)


def _browser_unreadable(nodes: "list[dict]") -> str:
    """"" when the browser window is in the tree, else what is in the way.

    Measured 30 Oct: with a game client in front, "switch to Edge" reports success, the focused window stays the
    game, and the tree holds the taskbar only. Pressing anything from that tree would be pressing something else.
    """
    if any(BROWSER in (n.get("window") or "").casefold() for n in nodes):
        return ""
    return "I can't read the browser window; something else is in front of it, so I pressed nothing"


async def run(steps: "list[dict]", request: str = "steps") -> dict:
    """Do the steps in order. Stops at the first one that cannot be done and says why."""
    done: list[str] = []
    t0 = time.time()

    def fail(i: int, why: str) -> dict:
        PC._record_run(request, "steps", "failed", f"step {i + 1} ({describe(steps[i])}): {why}")
        _remember(steps, False)
        return {"ok": False, "done": len(done), "say": f"Stopped at step {i + 1}, {describe(steps[i])}: {why}", "log": done}

    for i, st in enumerate(steps):
        d = st["do"]
        try:
            if d == "open":
                PC._open_uri(st["url"])
                await asyncio.sleep(3.0)
            elif d == "key":
                await MCP.call_tool("windows", "Shortcut", {"shortcut": st["key"]})
                await asyncio.sleep(SETTLE)
            elif d == "expect":
                want = st["text"].casefold()
                end = time.time() + EXPECT_WAIT
                seen = False
                while True:
                    nodes = await _tree()
                    blocked = _browser_unreadable(nodes)
                    if blocked and time.time() > end:
                        return fail(i, blocked)
                    if any(want in (n.get("name") or "").casefold() for n in nodes):
                        seen = True
                        break
                    if time.time() > end:
                        break
                    await asyncio.sleep(1.0)
                if not seen:
                    return fail(i, f"the page does not show “{st['text']}”" + (f"; it shows: {', '.join(PC._visible_names(nodes, 6))}" if nodes else ""))
            elif d in ("click", "type"):
                field = st.get("name") if d == "click" else st.get("field")
                loc = None
                if d == "type" and not field:
                    # No field named: type only into a text field the page itself has focused. Typing at "wherever
                    # the cursor is" is how text lands in the wrong place without anyone knowing.
                    nodes = await _tree()
                    blocked = _browser_unreadable(nodes)
                    if blocked:
                        return fail(i, blocked)
                    focused = [n for n in nodes if BROWSER in (n.get("window") or "").casefold() and n.get("x") is not None
                               and n.get("control") in ("edit", "combo box", "text box", "document")
                               and "focused" in str(n.get("flags") or "").lower() and n.get("control") != "document"]
                    if len(focused) != 1:
                        return fail(i, "no single text field is focused on the page; name the field, as in type “…” in <field>")
                    if _NEVER_TYPE.search(str(focused[0].get("name") or "")):
                        return fail(i, f"“{focused[0].get('name')}” looks like a password or card field, so I won't type into it; do that one yourself")
                    loc = [focused[0]["x"], focused[0]["y"]]
                if field:
                    nodes = await _tree()
                    blocked = _browser_unreadable(nodes)
                    if blocked:
                        return fail(i, blocked)
                    got = await _find(field, nodes)
                    if got.get("stop"):
                        return fail(i, got["stop"])
                    node = got["target"]
                    why = PC.step_blocker(node, "Click")
                    if why:
                        return fail(i, f"“{node.get('name')}” {why}" if not why.startswith("its name") else f"I won't press it: {why}")
                    if d == "type" and _NEVER_TYPE.search(str(node.get("name") or "") + " " + field):
                        return fail(i, f"“{node.get('name')}” looks like a password or card field, so I won't type into it; do that one yourself")
                    loc = [node["x"], node["y"]]
                if d == "click":
                    await MCP.call_tool("windows", "Click", {"loc": loc, "button": "left", "clicks": 1})
                else:
                    args = {"text": st["text"], "clear": True}
                    if loc:
                        args["loc"] = loc
                    await MCP.call_tool("windows", "Type", args)
                await asyncio.sleep(SETTLE)
        except Exception as exc:  # noqa: BLE001
            logger.info("pc_steps: step %s failed: %s", i + 1, exc)
            return fail(i, str(exc)[:160])
        done.append(describe(st))
    row = _remember(steps, True)
    PC._record_run(request, "steps", "done", f"{len(steps)} step(s) in {time.time() - t0:.0f}s [{row['status']}]", level="ui-tree")
    return {"ok": True, "done": len(done), "say": f"Done: {len(done)} steps in {time.time() - t0:.0f} s.", "log": done,
            "recipe": {"id": row["id"], "status": row["status"], "successes": row["successes"]}}


def plan_reply(text: str) -> "dict | None":
    """The TALK reply for 'steps: ...': the whole path, asked once. None when this is not a steps request."""
    if not re.match(r"^\s*(?:please\s+)?(?:follow these steps|do these steps|steps)\b\s*[:\-]", text or "", re.I):
        return None
    got = parse(text)
    if got.get("error"):
        return {"say": got["error"], "action": None}
    steps = got["steps"]
    return {"say": f"Path: {path_text(steps)}. Go?", "action": ("pc_steps", {"steps": steps, "request": text[:200]})}


def pc_ready() -> str:
    """"" when PC control can be used, else why not."""
    win = next((x for x in MCP.servers() if x["name"] == "windows"), None)
    if not win or not win["installed"]:
        return "PC control is not installed."
    if not win["enabled"]:
        return "PC control is off. Switch on the wireframe PC button, then ask again."
    return ""


@routes.post("/api/pc/steps")
async def api_steps(request: web.Request) -> web.Response:
    """Do a web or app task from discrete steps on screen (go to, click, type, press, expect). Send run false first to get the path to show the user; run true only with approved true after they said yes."""
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    steps = b.get("steps")
    if isinstance(steps, list) and steps and all(isinstance(s, dict) and s.get("do") for s in steps):
        got = {"steps": steps}
    else:
        got = parse(str(b.get("text") or steps or ""))
    if got.get("error"):
        raise web.HTTPBadRequest(text=got["error"])
    out = {"steps": got["steps"], "path": path_text(got["steps"])}
    if not b.get("run"):
        return web.json_response({**out, "ran": False})
    if not b.get("approved"):
        raise web.HTTPConflict(text="Show this path to the user and ask once; send approved true only after they say yes.")
    why = pc_ready()
    if why:
        raise web.HTTPConflict(text=why)
    return web.json_response({**out, "ran": True, **(await run(got["steps"], str(b.get("request") or "api steps")))})


@routes.get("/api/pc/recipes")
async def api_recipes(request: web.Request) -> web.Response:
    return web.json_response({"recipes": recipes()})
