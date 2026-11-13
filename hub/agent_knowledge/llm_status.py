"""What every way of reaching a model is doing right now: checked, not assumed.

Why this exists (13 Nov 2026): Ollama's cloud Nemotron, the Hub's fast default for two months, started answering "Add usage credits or subscribe",
and one of the Zen free models it fell back to (`mimo-v2.5-free`) had been withdrawn. Nothing said so: every run just tried the dead model first and
failed over. This module asks each route once, on demand, keeps the answer for a day, and lets `model_chain` leave out what is known to be dead.

Four routes are looked at:
  Ollama           the server on this PC (up or not), the models installed, and for a *cloud* model one tiny call (it may need credits)
  OpenCode Zen     the free `opencode/*` models: still offered? does a one-word call come back?
  Claude Code      `claude auth status`: signed in, and on which plan (what the Doctor works through)
  API keys         whether a paid provider key is set in the environment (names only, never values)

Nothing here loads a local model into the graphics card unless `deep` is asked for.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from ..runtime import STATE, write_json

FILE = STATE / "llm_status.json"
DEAD_TTL = 24 * 3600                      # a failed check keeps a model out of the chain for a day; run CHECK again to clear it
OLLAMA = "http://127.0.0.1:11434"
KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ---- what the last check found
def _read() -> dict:
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def dead(model: str) -> str:
    """Why this model is known not to work (from a check in the last day), or "" if it is not known to be dead."""
    row = (_read().get("models") or {}).get(model)
    if row and row.get("ok") is False and time.time() - row.get("at", 0) < DEAD_TTL:
        return str(row.get("why") or "failed its last check")
    return ""


def _remember(rows: dict) -> None:
    cur = _read()
    cur.setdefault("models", {}).update(rows)
    cur["checked_at"] = time.time()
    try:
        write_json(FILE, cur)
    except OSError:
        pass


# ---- Claude Code: signed in or not (the Doctor works through it)
_CLAUDE: dict = {"at": 0.0, "row": None, "busy": False}


def _claude_now() -> "dict | None":
    exe = shutil.which("claude")
    if not exe:
        return {"installed": False, "signed_in": False, "why": "Claude Code is not installed on this PC."}
    try:
        r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL)
        j = json.loads(r.stdout)
    except Exception:  # noqa: BLE001 - a missing answer is "unknown", never "signed out"
        return None
    if not isinstance(j, dict):
        return None
    return {"installed": True, "signed_in": bool(j.get("loggedIn")), "plan": j.get("subscriptionType") or "", "how": j.get("authMethod") or "",
            "why": "" if j.get("loggedIn") else "Claude Code is signed out. Open a terminal, run claude, then type /login."}


def claude_status(max_age: float = 60.0) -> "dict | None":
    """{installed, signed_in, plan, how, why}, or None when it cannot be told. Cached for a minute; a stale answer is refreshed in the background."""
    now = time.time()
    if _CLAUDE["row"] is not None and now - _CLAUDE["at"] < max_age:
        return _CLAUDE["row"]
    if _CLAUDE["row"] is None:                                 # the first ask waits for the answer (about a second)
        _CLAUDE["row"], _CLAUDE["at"] = _claude_now(), now
        return _CLAUDE["row"]
    if not _CLAUDE["busy"]:
        _CLAUDE["busy"] = True

        def go():
            try:
                row = _claude_now()
                if row is not None:
                    _CLAUDE["row"], _CLAUDE["at"] = row, time.time()
            finally:
                _CLAUDE["busy"] = False
        threading.Thread(target=go, daemon=True).start()
    return _CLAUDE["row"]


# ---- Ollama
async def _get(path: str, timeout: float = 3.0):
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        async with s.get(OLLAMA + path) as r:
            return r.status, await r.json()


async def _tiny_chat(name: str, timeout: float, keep_alive=None) -> "tuple[bool, str, float]":
    """One-word chat with an Ollama model. Returns (ok, why, seconds). A cloud model that wants credits answers at once with a plain sentence about them."""
    import aiohttp
    body = {"model": name, "stream": False, "think": False, "options": {"num_predict": 12}, "messages": [{"role": "user", "content": "Reply with the single word: ok"}]}
    if keep_alive is not None:
        body["keep_alive"] = keep_alive                         # 0: unload the model again straight away
    t0 = time.time()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.post(OLLAMA + "/api/chat", json=body) as r:
                text = await r.text()
                if r.status == 200:
                    return True, "", time.time() - t0
    except Exception as exc:  # noqa: BLE001
        return False, f"no answer ({exc.__class__.__name__})", time.time() - t0
    low = text.lower()
    if r.status in (401, 402, 403) or "credits" in low or "subscribe" in low:
        return False, "needs usage credits or a subscription on ollama.com", time.time() - t0
    return False, f"error {r.status}: {text[:120]}", time.time() - t0


# ---- OpenCode Zen free models
async def _opencode(args: list, timeout: float) -> "tuple[int, str]":
    from ..features import opencode as OC
    env = {**os.environ, "OPENCODE_CONFIG": OC.OPENCODE_CONFIG, "NO_COLOR": "1"}
    work = tempfile.mkdtemp(prefix="llm-check-")                 # a throw-away folder: the check must not touch anything
    try:
        p = await asyncio.create_subprocess_exec(OC.OPENCODE_EXE, *args, cwd=work, env=env, stdin=asyncio.subprocess.DEVNULL,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
        return p.returncode or 0, _ANSI.sub("", out.decode("utf-8", "replace"))
    except asyncio.TimeoutError:
        try:
            p.kill()
        except Exception:  # noqa: BLE001
            pass
        return 124, "timed out"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def _zen(model: str, offered: "set[str]") -> dict:
    if offered and model not in offered:
        return {"model": model, "ok": False, "why": "no longer offered by OpenCode Zen"}
    t0 = time.time()
    rc, out = await _opencode(["run", "-m", model, "Reply with the single word: ok"], 80)
    secs = round(time.time() - t0, 1)
    if rc == 0 and "ok" in out.lower() and "error" not in out.lower()[:200]:
        return {"model": model, "ok": True, "why": "", "secs": secs}
    why = "timed out" if rc == 124 else (re.search(r'"message":\s*"([^"]{3,140})', out) or re.search(r"(Unexpected[^\n]{0,100}|[A-Za-z ]*[Ee]rror[^\n]{0,100})", out) or [None, "no answer"])[1]
    return {"model": model, "ok": False, "why": str(why).strip()[:140], "secs": secs}


def _zen_ids() -> "list[str]":
    from .. import agent_knowledge as AK
    ids = [m for m in dict.fromkeys([AK.FAST_FREE_MODEL, *AK.MODEL_FALLBACKS]) if m.startswith("opencode/")]
    return ids


# ---- the whole picture
async def snapshot(*, check: bool = False, deep: bool = False) -> dict:
    """What each route is doing. `check` makes the calls that tell (a tiny call to each cloud model, a one-word run of each free model); without it this reads the last
    answers and only asks the cheap things live (is Ollama up, what is installed, is Claude Code signed in). `deep` also loads the default local model once."""
    from .. import agent_knowledge as AK
    out: dict = {"checked_at": _read().get("checked_at"), "default": AK.resolved_default_model(), "local_model": AK.LOCAL_MODEL, "policy": AK.model_policy()}
    cache = _read().get("models") or {}
    # Ollama
    oll: dict = {"up": False, "local": [], "cloud": []}
    try:
        st, tags = await _get("/api/tags")
        oll["up"] = st == 200
        for m in tags.get("models", []):
            name = m.get("name", "")
            if m.get("remote_host"):
                oll["cloud"].append({"model": name})
            elif "embedding" not in (m.get("capabilities") or []):
                oll["local"].append(name)
    except Exception:  # noqa: BLE001
        pass
    todo = []
    for c in oll["cloud"]:
        key = "ollama/" + c["model"]
        if check and oll["up"]:
            todo.append((key, _tiny_chat(c["model"], 30)))
        else:
            row = cache.get(key) or {}
            c.update({"ok": row.get("ok"), "why": row.get("why", ""), "checked": row.get("at")})
    if check and deep and oll["up"]:
        todo.append((AK.LOCAL_MODEL, _tiny_chat(AK.LOCAL_MODEL.split("/", 1)[1], 150, keep_alive=0)))
    # Zen
    zen: list = []
    offered: set = set()
    if check:
        rc, listing = await _opencode(["models"], 40)
        offered = {ln.strip() for ln in listing.splitlines() if ln.strip().startswith("opencode/")} if rc == 0 else set()
    for m in _zen_ids():
        if check:
            todo.append((m, _zen(m, offered)))
        else:
            row = cache.get(m) or {}
            zen.append({"model": m, "ok": row.get("ok"), "why": row.get("why", ""), "checked": row.get("at")})
    if todo:
        got = await asyncio.gather(*[c for _, c in todo])
        rows = {}
        for (key, _), r in zip(todo, got):
            if isinstance(r, dict):                                     # a Zen row
                zen.append(r)
                rows[key] = {"ok": r["ok"], "why": r["why"], "at": time.time(), "secs": r.get("secs")}
            else:                                                       # an Ollama (ok, why, secs)
                ok, why, secs = r
                rows[key] = {"ok": ok, "why": why, "at": time.time(), "secs": round(secs, 1)}
                for c in oll["cloud"]:
                    if "ollama/" + c["model"] == key:
                        c.update({"ok": ok, "why": why, "checked": time.time()})
                if key == AK.LOCAL_MODEL:
                    oll["local_probe"] = {"ok": ok, "why": why, "secs": round(secs, 1)}
        _remember(rows)
        out["checked_at"] = time.time()
    out["ollama"], out["zen"] = oll, zen
    cl = claude_status()
    out["claude"] = cl
    out["keys"] = {k: bool(os.environ.get(k)) for k in KEYS}
    out["lines"] = _lines(out)
    return out


def _lines(s: dict) -> "list[dict]":
    """One short plain line per route: {"what", "state": ok|bad|unknown, "say"}."""
    rows = []
    o = s["ollama"]
    rows.append({"what": "Ollama on this PC", "state": "ok" if o["up"] else "bad",
                 "say": (f"running, {len(o['local'])} local model{'s' if len(o['local']) != 1 else ''} installed; the default is {s['local_model']}") if o["up"] else "not running (the Hub starts it when a run needs it)"})
    for c in o["cloud"]:
        say = "answers" if c.get("ok") else ((c.get("why") or "failed its check") if c.get("ok") is False else "not checked yet; press CHECK")
        rows.append({"what": "Ollama cloud: " + c["model"], "state": "ok" if c.get("ok") else ("bad" if c.get("ok") is False else "unknown"), "say": say})
    if s["zen"]:
        good = [z for z in s["zen"] if z.get("ok")]
        bad = [z for z in s["zen"] if z.get("ok") is False]
        if good or bad:
            say = f"{len(good)} of {len(s['zen'])} answer" + (("; out: " + ", ".join(z["model"].split("/", 1)[1] + " (" + (z.get("why") or "failed") + ")" for z in bad)) if bad else "")
        else:
            say = "not checked yet; press CHECK"
        rows.append({"what": "OpenCode Zen free models", "state": ("ok" if good else "bad") if (good or bad) else "unknown", "say": say})
    cl = s.get("claude")
    if cl is None:
        rows.append({"what": "Claude Code (the Doctor)", "state": "unknown", "say": "could not tell"})
    elif not cl.get("installed", True):
        rows.append({"what": "Claude Code (the Doctor)", "state": "bad", "say": cl["why"]})
    else:
        rows.append({"what": "Claude Code (the Doctor)", "state": "ok" if cl["signed_in"] else "bad",
                     "say": (f"signed in ({cl.get('plan') or 'plan unknown'}, through {cl.get('how') or 'sign-in'}); repairs use this, not an API key") if cl["signed_in"] else cl["why"]})
    have = [k.split("_")[0].title() for k, v in s["keys"].items() if v]
    rows.append({"what": "Paid API keys", "state": "ok", "say": ("set: " + ", ".join(have)) if have else "none set; nothing here needs one"})
    return rows
