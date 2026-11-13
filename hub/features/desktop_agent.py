"""Desktop task agent: the loop a person runs on an app they have not used before - look, press one thing, look again, check.

Why it exists. The rule layer in `pc_control` knows a few sentence shapes ("open X and open the Y playlist") and can open
things. Everything else ended in "Which app?" or a small model saying "I cannot control Apple Music", because the model was
given a menu of fixed actions and no view of the app. This gives a model what Claude has when it is handed the same job: the
app's real controls, numbered, what it did last and what that changed, and a way to check the outcome (for music: the
Windows media session says *Playing* and names the track).

One loop, any model. `run()` takes the model as a function, so the same loop is tried with a small local model first and a
stronger one after it, and what each of them did is kept (`trace`). A run that works is saved as an ordinary routine, so
the second time the same sentence is replayed with no model at all.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess
import sys
import time

from ..config import logger
from ..runtime import STATE
from . import mcp as MCP
from . import pc_control as PC

MAX_STEPS = 9
MAX_SECONDS = 150                # a whole try, however slow the model is
SETTLE = 1.3                     # seconds for a press to show on screen
_CHROME = {"minimize", "maximize", "close", "restore", "system"}      # the window's own buttons, never a way to the goal
_CAP = 70                        # controls shown to the model
_PER_GROUP = 10                  # at most this many alike controls from one group (a 300-song list is not 300 choices)
_KEYS = re.compile(r"^(?:enter|escape|esc|tab|space|up|down|left|right|ctrl\+f|ctrl\+l|ctrl\+k|f3)$", re.I)
_PLAY_GOAL = re.compile(r"\b(?:play|resume|listen to|put on|shuffle)\b", re.I)

# ── what the model is shown ─────────────────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You operate ONE Windows app for the user, one step at a time. You see the app's controls as a numbered list. Each line is: "
    "number, control type, name, then where it sits: 'in X' is the group it belongs to and 'on the row of X' is the item it is "
    "level with. Same-named controls differ by that: to play a PLAYLIST press the Play that is in the playlist's own group, not "
    "a song's Play and not the Play in the player bar. If the playlist or page you need is not listed, press the button that "
    "opens the navigation or the search first. Press ONE control per step. Do only what the GOAL says - if it is to open something, stop once it is open; do not press Play. Say done only when the "
    "screen or NOW PLAYING shows the goal has happened. Say stuck if nothing listed gets you closer. Never buy, subscribe, delete, sign out or send. "
    "Add \"confidence\": a number from 0 to 1 for how sure you are that this step moves toward the goal. "
    "Answer with JSON only.")

_SCHEMA = {"type": "object", "required": ["do"], "properties": {
    "do": {"type": "string", "enum": ["click", "type", "key", "done", "stuck"]},
    "id": {"type": "integer"}, "text": {"type": "string"}, "say": {"type": "string"}, "confidence": {"type": "number"}}}


def _conf(v) -> "float | None":
    """The model's own confidence in a step, 0 to 1, or None when it gave none. It is the model's word, not a measurement: it is kept beside each step so it can be calibrated against what happened (R9b)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, x / 100 if x > 1 else x)), 2)


def _clip(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


container_of = PC.container_of


def _row_of(nodes: "list[dict]", i: int, items: "list[int]") -> str:
    """The list entry level with this control (a song's own buttons sit on the song's row)."""
    y = nodes[i].get("y")
    if y is None:
        return ""
    for j in items:
        if j != i and abs((nodes[j].get("y") or -999) - y) <= 14 and nodes[j]["control"] == "list item":
            return nodes[j]["name"]
    return ""


def controls(nodes: "list[dict]", app: str, goal: str = "") -> "list[dict]":
    """The pressable controls of the app's window, numbered from 1, ready to show a model or to press.

    Window chrome is left out; alike controls from one group are capped; what the goal's own words hit comes first.
    """
    appl = PC.canonical_app_name(app)
    try:                                                          # experimental, off by default: forbidden controls are never offered (policy before the model call)
        from ..yard import knobs as _K
        hide = bool(_K.get("hide_forbidden"))
    except Exception:  # noqa: BLE001
        hide = False
    scope = [i for i, n in enumerate(nodes) if (not appl or appl in (n.get("window") or "").casefold())
             and "x" in n and (n.get("name") or "").strip() and n["control"] != "window"
             and (n["name"].strip().casefold() not in _CHROME) and not (hide and PC.never_press(n["name"]))]
    items = [i for i in scope if nodes[i]["control"] == "list item"]
    want = PC.target_words(goal)
    seen, per, out = set(), {}, []
    for i in scope:
        n = nodes[i]
        path = container_of(nodes, i)
        key = (n["control"], n["name"], path, n["y"])
        group = (n["control"], path)
        hit = sum(1 for w in want if w in (n["name"] + " " + path).casefold())
        if key in seen or (per.get(group, 0) >= _PER_GROUP and not hit):      # the cap is for alike controls the goal does not name: the one it names is always kept
            continue
        seen.add(key)
        per[group] = per.get(group, 0) + 1
        out.append({"hit": hit, "order": len(out), "node": n, "path": path, "row": _row_of(nodes, i, items)})
    out.sort(key=lambda c: (-min(c["hit"], 2), c["order"]))
    out = out[:_CAP]
    for k, c in enumerate(out, 1):
        c["id"] = k
    return out


def describe(c: dict) -> str:
    n = c["node"]
    state = re.findall(r"\[(toggle:\w+|focused)\]", n.get("flags") or "")
    where = (f' in "{_clip(c["path"], 40)}"' if c["path"] else "") + (f' on the row of "{_clip(c["row"], 40)}"' if c["row"] else "")
    return f'{c["id"]}. {n["control"]} "{_clip(n["name"], 60)}"{where}' + (f' [{", ".join(state)}]' if state else "")


def brief(goal: str, app: str, shown: "list[dict]", media: "list[dict]", history: "list[str]", step: int) -> str:
    playing = next((m for m in media if m.get("status") == "Playing"), None)
    now = (f'NOW PLAYING: "{playing.get("title")}" by {playing.get("artist")}' if playing else "NOW PLAYING: nothing")
    done = "\n".join(history[-6:]) or "(nothing yet)"
    return (f"GOAL: {goal}\nAPP: {app}\nSTEP {step + 1} of {MAX_STEPS}\n{now}\n\nSO FAR:\n{done}\n\nCONTROLS:\n"
            + "\n".join(describe(c) for c in shown))


def parse_action(raw: "str | dict", shown: "list[dict]") -> dict:
    """The model's answer as {do, control?, text?, say?}, or {do:"invalid", why} - never raises."""
    try:
        j = raw if isinstance(raw, dict) else json.loads(raw)
    except Exception:
        return {"do": "invalid", "why": "the answer was not JSON"}
    if not isinstance(j, dict):
        return {"do": "invalid", "why": "the answer was not an object"}
    # Models that ignore the requested field names still say the same thing ("action": "press", "control": 8).
    do = str(j.get("do") or j.get("action") or j.get("type") or "").strip().lower()
    do = {"press": "click", "tap": "click", "select": "click", "choose": "click", "finish": "done", "complete": "done",
          "give_up": "stuck", "fail": "stuck"}.get(do, do)
    if "id" not in j:
        j = {**j, "id": next((j[k] for k in ("control", "target", "element", "number", "index") if k in j), None)}
    conf = _conf(j.get("confidence"))
    if do in ("done", "stuck"):
        return {"do": do, "say": _clip(j.get("say") or "", 160), "confidence": conf}
    if do in ("click", "type"):
        try:
            cid = int(j.get("id"))
        except (TypeError, ValueError):
            return {"do": "invalid", "why": f"{do} needs the number of a control"}
        c = next((x for x in shown if x["id"] == cid), None)
        if not c:
            return {"do": "invalid", "why": f"there is no control number {cid}"}
        if do == "type" and not str(j.get("text") or "").strip():
            return {"do": "invalid", "why": "type needs text"}
        return {"do": do, "control": c, "text": str(j.get("text") or "")[:200], "confidence": conf}
    if do == "key":
        k = str(j.get("text") or j.get("say") or "").strip().lower()
        return {"do": "key", "text": k, "confidence": conf} if _KEYS.match(k) else {"do": "invalid", "why": f"key {k!r} is not one I press"}
    return {"do": "invalid", "why": f"unknown action {do!r}"}


# ── checking the outcome ────────────────────────────────────────────────────────────────────────────────────────────

_SMTC = r"""
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$out = @()
foreach ($s in $mgr.GetSessions()) {
  #CMD#
  $p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
  $out += [pscustomobject]@{ app = $s.SourceAppUserModelId; status = "$($s.GetPlaybackInfo().PlaybackStatus)"; title = $p.Title; artist = $p.Artist }
}
ConvertTo-Json -Compress -InputObject @($out)
"""


_MEDIA_CMDS = {
    "pause": "if ($s.GetPlaybackInfo().PlaybackStatus -eq 'Playing') { [void](Await ($s.TryPauseAsync()) ([bool])) }",
    "play": "if ($s.GetPlaybackInfo().PlaybackStatus -ne 'Playing') { [void](Await ($s.TryPlayAsync()) ([bool])) }",
    "next": "[void](Await ($s.TrySkipNextAsync()) ([bool]))",
    "previous": "[void](Await ($s.TrySkipPreviousAsync()) ([bool]))",
}


async def media_sessions(command: str = "") -> "list[dict]":
    """What Windows says is playing: [{app, status, title, artist}]. Empty off Windows or when nothing has a media session."""
    if sys.platform != "win32":
        return []

    def run() -> str:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # -EncodedCommand, not "-Command -": a script read from stdin runs line by line and printed nothing here.
        enc = base64.b64encode(_SMTC.replace("#CMD#", _MEDIA_CMDS.get(command, "")).encode("utf-16-le")).decode()
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=20, creationflags=flags)
        return r.stdout.strip()
    try:
        out = await asyncio.get_running_loop().run_in_executor(None, run)
        got = json.loads(out) if out else []
        return got if isinstance(got, list) else [got]
    except Exception as exc:  # noqa: BLE001
        logger.info("desktop_agent: could not read the media session: %s", exc)
        return []


_VOLUME_KEYS = {"volume_down": 174, "volume_up": 175, "mute": 173}


async def _press_media_key(code: int, times: int) -> None:
    script = "$s = New-Object -ComObject WScript.Shell; 1.." + str(times) + " | ForEach-Object { $s.SendKeys([char]" + str(code) + ") }"
    enc = base64.b64encode(script.encode("utf-16-le")).decode()

    def run() -> None:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], capture_output=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    await asyncio.get_running_loop().run_in_executor(None, run)


async def media_control(command: str) -> dict:
    """Pause, resume, skip or go back through the Windows media session - no screen driving needed - or change the volume with the
    keyboard's own volume keys. Says what it found."""
    if command in _VOLUME_KEYS:
        if sys.platform != "win32":
            return {"ok": False, "say": "I can only change the volume on Windows."}
        await _press_media_key(_VOLUME_KEYS[command], 1 if command == "mute" else 5)         # five presses is about ten per cent
        return {"ok": True, "say": {"volume_up": "Turned up.", "volume_down": "Turned down.", "mute": "Mute toggled."}[command]}
    if command not in _MEDIA_CMDS:
        return {"ok": False, "say": "I can pause, resume, skip to the next song, go back, or change the volume."}
    before = await media_sessions()
    if not before:
        return {"ok": False, "say": "Nothing is open that I can control: no player has a media session."}
    await media_sessions(command)
    await asyncio.sleep(1.0 if command in ("pause", "play") else 2.0)
    now = await media_sessions()
    top = next((m for m in now if m.get("status") == "Playing"), now[0] if now else {})
    song = f' “{top.get("title")}”' if top.get("title") else ""
    if command == "pause":
        return {"ok": top.get("status") != "Playing", "say": ("Paused" + song + ".") if top.get("status") != "Playing" else "It is still playing."}
    if command == "play":
        return {"ok": top.get("status") == "Playing", "say": ("Playing" + song + ".") if top.get("status") == "Playing" else "It did not start."}
    was = (next((m for m in before if m.get("status") == "Playing"), before[0])).get("title")
    changed = top.get("title") != was
    return {"ok": changed, "say": (f"Now playing{song}." if changed else "It stayed on the same song.")}


def wants_music(goal: str) -> bool:
    return bool(_PLAY_GOAL.search(goal or ""))


def playing_now(media: "list[dict]", app: str = "") -> "dict | None":
    """The session that is playing, preferring the app that was driven."""
    hits = [m for m in media if m.get("status") == "Playing"]
    mine = [m for m in hits if PC.canonical_app_name(app).replace(" ", "") in (m.get("app") or "").casefold()]
    return (mine or hits or [None])[0]


# ── the loop ────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _click(x: int, y: int) -> None:
    await MCP.call_tool("windows", "Click", {"loc": [x, y], "button": "left", "clicks": 1})


async def _type(text: str, loc: "list[int] | None") -> None:
    args = {"text": text, "clear": True}
    if loc:
        args["loc"] = loc
    await MCP.call_tool("windows", "Type", args)


async def _key(k: str) -> None:
    await MCP.call_tool("windows", "Shortcut", {"shortcut": k})


async def attempt(goal: str, app: str, decide, *, shadow: bool = True, **kw) -> dict:
    """`_attempt`, plus shadow mode: beside each choice the model makes, the yard's trained policy says what it would have pressed (record only)."""
    res = await _attempt(goal, app, decide, shadow=shadow, **kw)
    if shadow:
        try:
            from ..yard import shadow as SH
            SH.note_result(goal, app, bool(res.get("ok")), len(res.get("trace") or []))
        except Exception:  # noqa: BLE001 - recording must never touch the result
            pass
    return res


async def _attempt(goal: str, app: str, decide, *, tree=None, media=None, click=None, type_=None, key=None,
                   settle: float = SETTLE, max_steps: int = MAX_STEPS, shadow: bool = False, shot=None, rid: str = "") -> dict:
    """One model's try at the goal. `decide(system, user)` returns the model's raw answer.

    Returns {ok, say, steps, trace, saved} - `steps` are the presses that worked, in the shape a routine stores.
    Every press is checked first (present, enabled, not on the never-press list) and afterwards (did the window change,
    and for music: is something playing now that was not before).
    """
    tree = tree or (lambda: PC._raw_tree(app))
    media = media or media_sessions
    click, type_, key = click or _click, type_ or _type, key or _key
    trace, steps, history = [], [], []
    first = None
    g0, deadline = PC.stop_gen(), time.time() + MAX_SECONDS
    last_press, same = None, 0
    music = wants_music(goal)
    opening = bool(PC._OPEN_ONLY.match(goal or "")) and not music
    pressed_play = False
    unusable = 0                       # answers refused in a row: a model that cannot follow the format is not worth 9 steps
    before_media = now_media = await media() if music else []
    for step in range(max_steps):
        if PC.stop_gen() != g0:
            return {"ok": False, "say": "Stopped.", "steps": steps, "trace": trace, "stopped": True}
        if time.time() > deadline:
            return {"ok": False, "say": f"It ran out of time ({MAX_SECONDS} s) without reaching the goal.", "steps": steps, "trace": trace}
        nodes = await tree()
        if first is None:
            first = nodes
        if opening and _page_open(nodes, goal, app):
            # "Open the ADHD playlist" is met when the ADHD page is showing; a small model went on to press Play, which was not asked.
            return {"ok": True, "verified": True, "say": "It is open." if steps else "It is already showing.", "steps": steps,
                    "trace": trace, "first": first, "playing": None}
        shown = controls(nodes, app, goal)
        if not shown:
            return {"ok": False, "say": f"I cannot read {PC.display_app_name(app)}'s window. " + PC.read_problem(app), "steps": steps, "trace": trace}
        prompt = brief(goal, app, shown, now_media, history, step)
        t0 = time.time()
        try:
            raw = await decide(_SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001
            trace.append({"step": step, "error": str(exc)[:160], "ms": int((time.time() - t0) * 1000)})
            return {"ok": False, "say": f"The model did not answer: {str(exc)[:100]}", "steps": steps, "trace": trace}
        act = parse_action(raw, shown)
        if shadow:
            try:
                from ..yard import shadow as SH
                SH.note(goal, app, prompt, act, step)
            except Exception:  # noqa: BLE001
                pass
        trace.append({"step": step, "ms": int((time.time() - t0) * 1000), "raw": str(raw)[:300],
                      "do": act["do"], "control": describe(act["control"]) if act.get("control") else "", "why": act.get("why", ""), "confidence": act.get("confidence")})
        if act["do"] == "invalid":
            unusable += 1
        elif act["do"] in ("click", "type", "key"):
            unusable = 0
        if unusable >= 3:
            return {"ok": False, "say": "The model kept giving answers I could not use.", "steps": steps, "trace": trace}
        if act["do"] == "invalid":
            history.append(f'step {step + 1}: your answer was refused: {act["why"]}')
            continue
        if act["do"] == "stuck":
            return {"ok": False, "say": act.get("say") or "It could not find a way.", "steps": steps, "trace": trace}
        if act["do"] == "done":
            ok = _outcome(goal, app, before_media, now_media, pressed_play)
            if ok is False:
                unusable += 1                                                  # "done" with no music is as useless as a refused answer
                if unusable >= 3:
                    return {"ok": False, "say": "The model kept saying it was done when nothing was playing.", "steps": steps, "trace": trace}
                history.append(f"step {step + 1}: you said done, but nothing is playing yet. Keep going.")
                continue
            return {"ok": True, "verified": ok, "say": act.get("say") or "Done.", "steps": steps, "trace": trace,
                    "first": first, "playing": playing_now(now_media, app)}
        if act["do"] == "key":
            await key(act["text"])
            history.append(f"step {step + 1}: pressed the key {act['text']}")
            steps.append({"tool": "Shortcut", "args": {"shortcut": act["text"]}, "target": {}})
            trace[-1]["press"] = len(steps) - 1
            await asyncio.sleep(settle)
            if shot:
                trace[-1]["shot"] = await shot(rid, step) or ""
            continue
        c = act["control"]
        node = c["node"]
        why = PC.step_blocker(node)
        if why:
            history.append(f"step {step + 1}: you may not press {c['id']} (“{node['name']}”): {why}")
            continue
        sig = (node["control"], node["name"], c["path"])
        same = same + 1 if sig == last_press else 0
        last_press = sig
        if same >= 2:
            return {"ok": False, "say": f"It kept pressing “{node['name']}” without anything changing.", "steps": steps, "trace": trace}
        if PC.stop_gen() != g0:                                             # the model took a while to answer: nothing is pressed after a stop
            return {"ok": False, "say": "Stopped.", "steps": steps, "trace": trace, "stopped": True}
        window_before = PC.window_state(nodes, node["window"])
        tp = time.time()
        if act["do"] == "type":
            await type_(act["text"], [node["x"], node["y"]])
        else:
            await click(node["x"], node["y"])
        await asyncio.sleep(settle)
        after_nodes = await tree()
        changed = PC.window_state(after_nodes, node["window"])["fingerprint"] != window_before["fingerprint"]
        history.append(f'step {step + 1}: {"typed " + repr(act["text"]) + " into" if act["do"] == "type" else "pressed"} {c["id"]} '
                       f'{node["control"]} “{_clip(node["name"], 40)}”{(" in " + chr(34) + c["path"] + chr(34)) if c["path"] else ""} '
                       f'- {"the screen changed" if changed else "NOTHING on screen changed"}')
        trace[-1]["changed"] = changed
        trace[-1]["press_ms"] = int((time.time() - tp) * 1000)                 # from the press to the screen settling
        if shot:
            trace[-1]["shot"] = await shot(rid, step) or ""                        # what the window looked like after it
        pressed_play = pressed_play or bool(re.search(r"\bplay\b", node["name"], re.I))
        if changed or music:
            ident = {"name": node["name"], "control": node["control"], "window": node["window"], "path": c["path"], **({"confidence": act["confidence"]} if act.get("confidence") is not None else {})}
            steps.append({"tool": "Type" if act["do"] == "type" else "Click",
                          "args": {"text": act["text"], "clear": True} if act["do"] == "type" else {"button": "left", "clicks": 1},
                          "target": ident, "_changed": changed})
            trace[-1]["press"] = len(steps) - 1
        if music:
            # The evidence decides, not the model: a small model read "NOW PLAYING" and pressed Play twice more.
            now_media = await media()
            if _outcome(goal, app, before_media, now_media, pressed_play):
                trace[-1]["verified"] = True
                playing = playing_now(now_media, app)
                missing = _unfound_target(goal, steps, playing)
                if missing:
                    # 5 Nov: "play the robelec speedplay list" clicked DarkSynth, then an artist, pressed Play and called it Done (and saved that as a routine).
                    # Something played, but not what was asked for: say so, and do not keep it as a way to do this.
                    trace[-1]["verified"] = False
                    return {"ok": True, "verified": False, "say": f"I could not find “{missing}” in {PC.display_app_name(app)}, so I played something else instead.",
                            "steps": steps, "trace": trace, "first": first, "playing": playing, "unfound": missing}
                return {"ok": True, "verified": True, "say": "Done.", "steps": steps, "trace": trace, "first": first, "playing": playing}
    return {"ok": False, "say": f"It used all {max_steps} steps without reaching the goal.", "steps": steps, "trace": trace}


def _outcome(goal: str, app: str, before: "list[dict]", now: "list[dict]", pressed_play: bool = False) -> "bool | None":
    """Did the goal happen? For music the media session is the evidence: playing now, and a different track from what was
    playing before - or the same one after a Play was pressed. None when nothing can check it."""
    if not wants_music(goal):
        return None
    after, was = playing_now(now, app), playing_now(before, app)
    if not after:
        return False
    if was and was.get("title") == after.get("title") and not pressed_play:
        return None                                       # it was already playing that track: nothing shows our press did it
    return True


def _page_open(nodes: "list[dict]", goal: str, app: str) -> bool:
    """Is the page the goal names showing? A page is a group or heading carrying its name (a sidebar entry is a list item)."""
    want = PC.target_words(goal)
    appl = PC.canonical_app_name(app)
    if not want:
        return False
    return any(n["control"] in ("group", "heading", "document") and "x" not in n
               and (not appl or appl in (n.get("window") or "").casefold())
               and all(w in (n.get("name") or "").casefold() for w in want) for n in nodes)


MODEL_FILE = STATE / "desktop_agent_model.json"


def chosen_model() -> str:
    """The model you picked for the desktop agent on the Agency page, or '' to follow the Hub's own order."""
    try:
        return str(json.loads(MODEL_FILE.read_text(encoding="utf-8")).get("model") or "")[:80]
    except (OSError, ValueError, AttributeError):
        return ""


def set_chosen_model(name: str) -> None:
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(json.dumps({"model": (name or "")[:80]}), encoding="utf-8")


def ladder() -> "list[str]":
    """Models to try, quickest first: the ones on this PC that load fast."""
    from .. import agent_knowledge
    chain = [m.split("/", 1)[1] for m in agent_knowledge.model_chain(None, None) if m.startswith("ollama/")]
    chain = [m for m in chain if not re.search(r"embed|^tev|nomic", m)]          # classifiers and embedders cannot chat
    chain.sort(key=lambda m: "32k" not in m and "e4b" not in m and "e2b" not in m)
    mine = chosen_model()
    if mine:
        chain = [mine] + [m for m in chain if m != mine]        # your pick goes first; the rest stay as the fall-back order
    return chain


def ollama_decider(model: str, ctx: int = 6144):
    async def decide(system: str, user: str):
        from .. import decide as DEC
        from . import missions as M
        if not await M._ensure_ollama():                          # the Hub starts Ollama when a task needs it (and stops it when idle); this path had never asked
            raise RuntimeError("Ollama is not running and could not be started")
        M.touch_ollama()
        body = {"model": model, "stream": False, "format": _SCHEMA,
                "options": {"temperature": 0, "num_predict": 140, "num_ctx": ctx},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        d = await asyncio.wait_for(DEC._ollama_raw(body), 30)         # a step is seconds; a model that needs a minute has hung
        return (d.get("message") or {}).get("content") or "{}"
    return decide


async def run(goal: str, app: str, *, models: "list[str] | None" = None, decider=None, remember: bool = True, **fakes) -> dict:
    """Try the goal with each model in turn; keep the first success as a routine. Always reports what each model did."""
    t0 = time.time()
    tries = []
    chain = ladder()
    # One model that is quick on this PC. Not every model on disk: a 24 GB one on a 12 GB card takes minutes per step.
    pool = models if models is not None else chain[:1]
    deciders = [(m, ollama_decider(m)) for m in pool] if decider is None else [("injected", decider)]
    g0 = PC.stop_gen()
    for name, dec in deciders:
        if PC.stop_gen() != g0:
            break
        ta = time.time()
        rid = "%x" % int(ta * 1000)
        extra = {"rid": rid}
        if not fakes:                                                         # the real thing: keep a picture per step. A test that injects its own screen gets none.
            extra["shot"] = _make_shot(app)
        got = await attempt(goal, app, dec, **extra, **fakes)
        try:
            from . import run_record as RR
            RR.write(rid, goal, app, name, got, (time.time() - ta) * 1000)
        except Exception as exc:  # noqa: BLE001
            logger.info("desktop_agent: could not keep the run record: %s", exc)
        tries.append({"model": name, "ok": got["ok"], "say": got["say"], "trace": got["trace"], "pressed": len(got["steps"]), "rid": rid})
        _log_run(goal, app, tries[-1])
        try:                                     # R1: which model did the task, and did the checked result agree
            from . import learning as LRN
            LRN.note("model", "desktop_task", name, chain, got["ok"], (time.time() - ta) * 1000, p=1.0, ctx={"goal_words": len(goal.split()), "music": bool(wants_music(goal)), "models": len(chain)},
                     sampling={"temperature": 0, "num_predict": 140, "num_ctx": 6144})
        except Exception:  # noqa: BLE001
            pass
        if got["ok"]:
            saved = None
            if remember and got["steps"] and got.get("verified") is not False:
                saved = _save(goal, app, got)
            who = (got.get("playing") or {})
            heard = f' Now playing “{who.get("title")}” by {who.get("artist")}.' if who else ""
            return {"ok": True, "say": f"{got['say'].rstrip('.')}.{heard}".strip(), "tries": tries, "routine": saved,
                    "seconds": round(time.time() - t0, 1)}
    return {"ok": False, "say": tries[-1]["say"] if tries else "No model is available to do this.", "tries": tries,
            "seconds": round(time.time() - t0, 1)}


def _make_shot(app: str):
    """A picture of the app's window after each step, kept with the run (about 40 KB each, on this PC only), so a person can see what the agent saw. Never raises, never blocks a step."""
    async def shot(rid: str, step: int) -> str:
        try:
            from . import run_record as RR, window_mirror as WM
            win = await asyncio.to_thread(WM.find_window, PC.display_app_name(app))
            if not win:
                return ""
            got = await asyncio.to_thread(WM.capture, int(win["id"]), 720, 60)
            return RR.keep_shot(rid, step, got[0]) if got else ""
        except Exception as exc:  # noqa: BLE001
            logger.info("desktop_agent: no picture of step %s: %s", step, exc)
            return ""
    return shot


def _log_run(goal: str, app: str, tried: dict) -> None:
    """Every model's try, kept: what it was shown to choose from is the only way to see why a small model went wrong."""
    try:
        path = STATE / "data" / "desktop_agent_runs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.time(), "goal": goal, "app": app, **tried}, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.info("desktop_agent: could not log the run: %s", exc)


_GOAL_FILLER = {"play", "something", "some", "from", "the", "playlist", "list", "music", "song", "songs", "open", "apple", "a", "an", "my", "on", "in", "to", "and",
                "me", "please", "can", "you", "i", "of", "for", "with", "by", "track", "tracks", "album", "radio", "station", "start", "put", "listen", "app"}


def _unfound_target(goal: str, steps: "list[dict]", playing: "dict | None") -> str:
    """The words in the goal that name a thing (a playlist, an artist) when NONE of them shows up in anything that was pressed or is now playing.
    Empty when the goal names nothing, or when at least one of its words was found. Matching is on whole-word prefixes, so 'adhd' finds 'ADHD'."""
    words = [w for w in re.findall(r"[\w']+", goal.casefold()) if w not in _GOAL_FILLER and len(w) > 1]
    if not words:
        return ""
    seen = " ".join(str(v) for st in steps for v in (st.get("target") or {}).values()).casefold()
    seen += " " + " ".join(str(v) for v in (playing or {}).values()).casefold()
    if any(re.search(r"\b" + re.escape(w[:max(3, len(w) - 1)]), seen) for w in words):
        return ""
    return " ".join(words)


def _trim(steps: "list[dict]") -> "list[dict]":
    """What is worth replaying: the last step always (the Play), steps that changed the screen, and no loops. A detour that comes back to a control
    already pressed is cut out, so a way that wandered (Playlists, a Home tile, Playlists again) replays as the short way."""
    keep = [s for i, s in enumerate(steps) if s.get("_changed", True) or i == len(steps) - 1]
    key = lambda s: json.dumps({k: v for k, v in (s.get("target") or {}).items() if k != "confidence"}, sort_keys=True)
    out: "list[dict]" = []
    for s in keep:
        k = key(s)
        for j, o in enumerate(out):
            if key(o) == k:
                out = out[:j]                                          # came back to a control it had pressed before: everything since was a detour
                break
        out.append(s)
    return [{k: v for k, v in s.items() if not k.startswith("_")} for s in out]


def _save(goal: str, app: str, got: dict) -> "dict | None":
    first = got.get("first") or []
    window = next((n["window"] for n in first if n["control"] == "window" and PC.canonical_app_name(app) in n["name"].casefold()), "")
    if not window:
        return None
    steps = _trim([s for s in got["steps"] if s["tool"] in ("Click", "Type", "Shortcut")])
    try:
        old = PC.routine_for_do(app, goal)                    # keep the routine this wording already has, whatever key it was stored under
        row = PC.save_ui_routine(old["intent"] if old else PC.do_intent(app, goal), f"{PC.display_app_name(app)}: {goal}".strip(), window, steps,
                                 PC.ui_signature(PC.flatten(first), window))
    except Exception as exc:  # noqa: BLE001
        logger.info("desktop_agent: could not save the routine: %s", exc)
        return None
    return {"id": row["id"], "status": row["status"], "successes": row["successes"], "tag": "ROUTINE"}
