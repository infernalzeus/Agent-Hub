"""Replay keeps a record (each step, its time, a picture), opens the app first when it is closed, can be stopped, and is what the routines panel shows before you approve."""
import asyncio
import json

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import pc_control as PC, run_record as RR

WIN = "Apple Music"
SCREEN = [{"window": WIN, "control": "window", "name": "Apple Music", "path": "", "x": 0, "y": 0, "action": ""},
          {"window": WIN, "control": "button", "name": "Home", "path": "", "x": 10, "y": 10, "action": "click"},
          {"window": WIN, "control": "button", "name": "Play", "path": "", "x": 20, "y": 20, "action": "click"}]


def _routine(tmp_path, monkeypatch):
    monkeypatch.setattr(RR, "STATE", tmp_path)
    sig = PC.ui_signature(SCREEN, WIN)
    steps = [{"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": "Home", "control": "button", "window": WIN, "path": ""}},
             {"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": "Play", "control": "button", "window": WIN, "path": ""}}]
    row = PC.save_ui_routine("do:apple music:play my adhd playlist", "Apple Music: play my adhd playlist", WIN, steps, sig)
    with PC._db() as db:
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (row["id"],)).fetchone())


def test_a_replay_opens_the_app_first_when_it_is_closed_and_keeps_every_step(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    opened = []
    state = {"open": False}

    async def snapshot(app=""):
        return [dict(e) for e in SCREEN] if state["open"] else []

    async def launch(app, request, then=""):
        opened.append(app)
        state["open"] = True
        return {"ok": True, "say": "opened"}
    calls = []

    async def call_tool(name, tool, args, timeout=90):
        calls.append((tool, args.get("loc")))
        return {"text": []}

    async def effect(window, before):
        return {"known": True, "changed": True, "why": ""}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC, "launch_app", launch)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    monkeypatch.setattr(PC, "effect_of", effect)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda s: _real_sleep(0))
    res = asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert opened == ["Apple Music"] and res["ok"] and res["rid"] and "ms" in res
    assert calls == [("Click", [10, 10]), ("Click", [20, 20])]
    row = json.loads((tmp_path / "data" / "runs" / res["rid"] / "run.json").read_text(encoding="utf-8"))
    assert [t["do"] for t in row["trace"]] == ["open", "click", "click"] and row["kind"] == "replay" and row["routine"] == routine["id"]
    assert RR.latest_for(routine["id"])["id"] == res["rid"]                                            # what the routines panel shows


def test_an_app_that_cannot_be_opened_stops_the_replay_and_says_so(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)

    async def snapshot(app=""):
        return []

    async def launch(app, request, then=""):
        return {"ok": False, "say": "no such app"}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC, "launch_app", launch)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda s: _real_sleep(0))
    res = asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert res["ok"] is False and "could not open" in res["say"]
    row = json.loads((tmp_path / "data" / "runs" / res["rid"] / "run.json").read_text(encoding="utf-8"))
    assert row["trace"][0]["do"] == "open" and row["trace"][0].get("error")


def test_stop_ends_a_replay_before_the_next_step(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    calls = []

    async def snapshot(app=""):
        return [dict(e) for e in SCREEN]

    async def call_tool(name, tool, args, timeout=90):
        calls.append(tool)
        PC.stop_all()                                                                                   # the STOP button, pressed during the first step
        return {"text": []}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    res = asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert res["route"] == "stopped" and len(calls) == 1


def test_the_stop_and_last_run_endpoints(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    rec = RR.Recorder("replay", "play", "apple music", routine=routine["id"])
    asyncio.run(rec.step("click", "Home", 800))
    rid = rec.finish(True, "Ran it.")
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            g0 = PC.stop_gen()
            j = await (await c.post("/api/pc/stop")).json()
            assert j["ok"] and PC.stop_gen() == g0 + 1
            last = await (await c.get(f"/api/pc/routines/{routine['id']}/last-run")).json()
            assert last["run"]["id"] == rid and last["run"]["trace"][0]["control"] == "Home"
            none = await (await c.get("/api/pc/routines/nothing/last-run")).json()
            assert none["run"] is None
    asyncio.run(go())


def test_a_replay_in_shadow_mode_leaves_a_demonstration(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    seen = []
    from hub.yard import shadow as SH
    monkeypatch.setattr(SH, "enabled", lambda: True)
    monkeypatch.setattr(SH, "note", lambda goal, app, prompt, act, step: seen.append((goal, act["do"], act["control"]["id"], "Home" in prompt)))
    raw = [{"control": "window", "name": "Apple Music", "window": WIN, "x": 0, "y": 0, "clickable": False},
           {"control": "button", "name": "Home", "window": WIN, "x": 10, "y": 10, "clickable": True},
           {"control": "button", "name": "Play", "window": WIN, "x": 20, "y": 20, "clickable": True}]

    async def snapshot(app=""):
        PC._LAST_RAW["nodes"] = raw
        return [dict(e) for e in SCREEN]

    async def call_tool(name, tool, args, timeout=90):
        return {"text": []}

    async def effect(window, before):
        return {"known": True, "changed": True, "why": ""}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    monkeypatch.setattr(PC, "effect_of", effect)
    asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert [s[1] for s in seen] == ["click", "click"] and all(s[3] for s in seen)                    # each step: the screen it saw and the control it pressed


def _launch_routine(tmp_path, monkeypatch, status="trusted"):
    monkeypatch.setattr(RR, "STATE", tmp_path)
    with PC._db() as db:
        db.execute("INSERT INTO pc_routines (id,intent,title,tool,kind,args_json,signature_json,status,successes,failures,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   ("l1", "open:apple music", "Open Apple Music", "App", "mcp", json.dumps({"mode": "launch", "name": "Apple Music"}), json.dumps({"kind": "start_menu_app", "name": "Apple Music"}), status, 20, 0, 1.0, 1.0))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id='l1'").fetchone())


def test_replaying_a_launch_routine_opens_the_app_checks_its_window_and_keeps_the_step(tmp_path, monkeypatch):
    """The trusted routine 'Open Apple Music' answered REPLAY with 'launches go through TALK': a trusted routine that did nothing."""
    routine = _launch_routine(tmp_path, monkeypatch)
    opened, windows = [], iter([False, False, True])

    async def launch(app, request, then=""):
        opened.append(app)
        return {"ok": True, "say": "Opened Apple Music."}

    async def window_for(name):
        return next(windows)
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(PC, "launch_app", launch)
    monkeypatch.setattr(PC, "_window_for", window_for)
    monkeypatch.setattr(asyncio, "sleep", lambda s: _real_sleep(0))
    res = asyncio.run(PC.run_routine("l1"))
    assert opened == ["Apple Music"] and res["ok"] and res["rid"]
    row = json.loads((tmp_path / "data" / "runs" / res["rid"] / "run.json").read_text(encoding="utf-8"))
    assert [t["do"] for t in row["trace"]] == ["open"] and row["ok"]


def test_a_launch_that_never_shows_a_window_is_a_failed_replay_not_a_silent_one(tmp_path, monkeypatch):
    routine = _launch_routine(tmp_path, monkeypatch)

    async def launch(app, request, then=""):
        return {"ok": True, "say": "launched"}

    async def window_for(name):
        return False
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(PC, "launch_app", launch)
    monkeypatch.setattr(PC, "_window_for", window_for)
    monkeypatch.setattr(asyncio, "sleep", lambda s: _real_sleep(0))
    res = asyncio.run(PC.run_routine("l1"))
    assert res["ok"] is False and "no window came up" in res["say"]


def test_a_routine_goes_on_when_the_app_shows_another_page_but_its_first_control_is_there(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    other = [dict(e) for e in SCREEN] + [{"window": WIN, "control": "tab", "name": "Radio", "path": "", "x": 30, "y": 30, "action": "click"}]    # another page: one more tab than when recorded
    calls = []

    async def snapshot(app=""):
        return [dict(e) for e in other]

    async def call_tool(name, tool, args, timeout=90):
        calls.append(args.get("loc"))
        return {"text": []}

    async def effect(window, before):
        return {"known": True, "changed": True, "why": ""}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    monkeypatch.setattr(PC, "effect_of", effect)
    res = asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert res["ok"] and calls == [[10, 10], [20, 20]]


def test_a_routine_whose_first_control_is_missing_presses_nothing_and_names_what_it_looked_for(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    calls = []

    async def snapshot(app=""):
        return [{"window": WIN, "control": "button", "name": "Sign in", "path": "", "x": 1, "y": 1, "action": "click"}]

    async def call_tool(name, tool, args, timeout=90):
        calls.append(tool)
        return {"text": []}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    res = asyncio.run(PC.replay_ui_routine(routine, "test"))
    assert res["ok"] is False and "Home" in res["say"] and "did not press anything" in res["say"] and calls == []


def test_a_trusted_routine_that_fails_two_replays_in_a_row_is_no_longer_listed_as_trusted(tmp_path, monkeypatch):
    _launch_routine(tmp_path, monkeypatch)

    async def failing(rid, request="manual run"):
        return {"ok": False, "route": "routine", "say": "No window came up."}
    monkeypatch.setattr(PC, "run_routine", failing)
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            first = await (await c.post("/api/pc/routines/l1/run?test=1")).json()
            assert not first.get("demoted")
            rows = (await (await c.get("/api/pc/routines")).json())["routines"]
            assert rows[0]["status"] == "trusted" and rows[0]["replay_failures"] == 1               # still trusted, and the list says its last replay failed
            second = await (await c.post("/api/pc/routines/l1/run?test=1")).json()
            assert second["demoted"] is True and "no longer trusted" in second["say"]
            rows = (await (await c.get("/api/pc/routines")).json())["routines"]
            assert rows[0]["status"] == "candidate"
    asyncio.run(go())
