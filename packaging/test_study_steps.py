"""Studying a routine: a note on it and on each step, the model's confidence kept with each step, one step (or from a step on) replayed on its own, and ATTEMPT AGAIN that does the task or
says why it did not. All of it with fake screens and fake models: nothing here touches this PC."""
import asyncio
import json

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import desktop_agent as DA, pc_control as PC, run_record as RR
from test_replay_record import SCREEN, WIN, _routine


def test_the_models_confidence_is_read_clamped_and_never_invented():
    shown = [{"id": 1, "node": {"name": "Home", "control": "button", "window": WIN, "x": 1, "y": 1}, "path": ""}]
    assert DA.parse_action({"do": "click", "id": 1, "confidence": 0.85}, shown)["confidence"] == 0.85
    assert DA.parse_action({"do": "click", "id": 1, "confidence": 90}, shown)["confidence"] == 0.9            # a model that says 90 means 90 %
    assert DA.parse_action({"do": "click", "id": 1, "confidence": "high"}, shown)["confidence"] is None       # words are not a number: none is recorded
    assert DA.parse_action({"do": "done", "say": "ok"}, shown)["confidence"] is None
    assert "confidence" in DA._SCHEMA["properties"]


def test_a_confidence_that_differs_does_not_make_a_repeated_press_look_like_a_new_step():
    a = {"tool": "Click", "target": {"name": "Playlists", "control": "list item", "confidence": 0.9}, "_changed": True}
    b = {"tool": "Click", "target": {"name": "Playlists", "control": "list item", "confidence": 0.4}, "_changed": True}
    c = {"tool": "Click", "target": {"name": "ADHD", "control": "list item", "confidence": 0.8}, "_changed": True}
    assert [s["target"]["name"] for s in DA._trim([a, c, b])] == ["Playlists"]                                 # coming back to a control already pressed cuts the detour, whatever the confidence


def test_the_agent_starts_ollama_when_it_is_off_and_says_so_when_it_cannot(monkeypatch):
    """12 Nov 11:53: both models failed with 'connection refused' because nothing had started Ollama; the failure then looked like success."""
    from hub.features import missions as M
    state = {"started": 0}

    async def ensure(wait=30.0):
        state["started"] += 1
        return state["started"] > 1                                                                          # the first ask finds it off and cannot start it; the second finds it up
    monkeypatch.setattr(M, "_ensure_ollama", ensure)
    monkeypatch.setattr(M, "touch_ollama", lambda: state.update(touched=True))
    from hub import decide as DEC

    async def raw(body):
        return {"message": {"content": json.dumps({"do": "done"})}}
    monkeypatch.setattr(DEC, "_ollama_raw", raw)
    decide = DA.ollama_decider("m")
    try:
        asyncio.run(decide("s", "u"))
        assert False, "should have refused"
    except RuntimeError as exc:
        assert "Ollama is not running" in str(exc)
    assert json.loads(asyncio.run(decide("s", "u")))["do"] == "done" and state["touched"]


def test_attempt_again_that_could_not_do_the_task_says_so_and_does_not_ask_or_claim_success(monkeypatch):
    async def agent(then, app, **kw):
        return {"ok": False, "say": "The model did not answer: Ollama is not running.", "tries": [{"model": "m", "trace": []}]}
    monkeypatch.setattr(DA, "run", agent)

    async def snap():
        return None

    async def evidence(*a, **k):
        return None
    monkeypatch.setattr(PC, "_snap", snap)
    monkeypatch.setattr(PC, "_learn", lambda *a, **k: None)
    monkeypatch.setattr(PC, "_evidence", evidence)
    monkeypatch.setattr(PC, "_record_run", lambda *a, **k: None)
    got = asyncio.run(PC.after("apple music", "play something from the adhd playlist", "q", fresh=True))
    assert got["ok"] is False and "could not do it" in got["say"] and "Ollama is not running" in got["say"] and "confirm" not in got
    again = asyncio.run(PC.after("apple music", "play something", "q", fresh=True))                            # 'something' alone would normally make it ask: not when trying again
    assert "confirm" not in again


def test_a_question_from_the_pipeline_is_not_reported_as_the_attempt_working(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)

    async def launch(app, request, then="", fresh=False):
        return PC._ask("Apple Music is open. Shall I shuffle your library?", "desktop_task", {}, "Shuffle")
    monkeypatch.setattr(PC, "launch_app", launch)
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            j = await (await c.post(f"/api/pc/routines/{routine['id']}/reattempt")).json()
            assert j["ok"] is False and "nothing was done" in j["say"]
    asyncio.run(go())


def test_a_note_on_a_routine_and_on_a_step_is_kept_listed_and_does_not_change_how_it_runs(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    with PC._db() as db:
        db.execute("UPDATE pc_routines SET status='trusted', approved=1 WHERE id=?", (routine["id"],))
    seen = []
    from hub.features import learning as LRN
    monkeypatch.setattr(LRN, "note", lambda kind, context, chosen, *a, **k: seen.append((kind, context, chosen, k.get("text"), k.get("step"))))
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.post(f"/api/pc/routines/{routine['id']}/note", json={"note": "Playlists is the sidebar entry; ADHD is under it"})).status == 200
            assert (await c.post(f"/api/pc/routines/{routine['id']}/steps/1", json={"note": "the Play next to the playlist title, not the player bar"})).status == 200
            rows = (await (await c.get("/api/pc/routines")).json())["routines"]
            assert rows[0]["note"].startswith("Playlists is the sidebar") and rows[0]["status"] == "trusted"   # a note is not an edit: the approval stands
            steps = (await (await c.get(f"/api/pc/routines/{routine['id']}/steps")).json())["steps"]
            assert steps[1]["note"].startswith("the Play next to") and steps[0]["note"] == ""
            assert (await c.post("/api/pc/routines/nope/note", json={"note": "x"})).status == 404
    asyncio.run(go())
    assert [(s[0], s[1], s[4]) for s in seen] == [("note", "routine", None), ("note", "step", 1)] and "ADHD is under it" in seen[0][3]


def test_one_step_or_the_steps_from_there_run_on_their_own_and_leave_the_routines_record_alone(tmp_path, monkeypatch):
    routine = _routine(tmp_path, monkeypatch)
    pressed = []

    async def snapshot(app=""):
        return [dict(e) for e in SCREEN]

    async def call_tool(name, tool, args, timeout=90):
        pressed.append(args.get("loc"))
        return {"text": []}
    monkeypatch.setattr(PC, "_snapshot", snapshot)
    monkeypatch.setattr(PC.MCP, "call_tool", call_tool)
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            one = await (await c.post(f"/api/pc/routines/{routine['id']}/steps/1/run", json={"mode": "one"})).json()
            assert one["ok"] and pressed == [[20, 20]] and "step 2" in one["say"]                              # only the second step: the Play
            pressed.clear()
            rest = await (await c.post(f"/api/pc/routines/{routine['id']}/steps/0/run", json={"mode": "from"})).json()
            assert rest["ok"] and pressed == [[10, 10], [20, 20]] and "steps 1 to 2" in rest["say"]
            last = await (await c.get(f"/api/pc/routines/{routine['id']}/last-run")).json()
            assert [t["ordinal"] for t in last["run"]["trace"]] == [0, 1]                                      # each step of the record knows which step of the routine it was
            none = await (await c.post(f"/api/pc/routines/{routine['id']}/steps/9/run", json={"mode": "one"})).json()
            assert none["ok"] is False and "no such step" in none["say"]
    asyncio.run(go())
    with PC._db() as db:
        r = db.execute("SELECT status, successes, failures FROM pc_routines WHERE id=?", (routine["id"],)).fetchone()
    assert (r["status"], r["successes"], r["failures"]) == ("candidate", 0, 0)                                 # two part-runs earned and cost the routine nothing
