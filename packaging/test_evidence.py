"""EXPERIMENTAL shadow mode: off by default; a PC task is kept with its evidence, picture and confidence only while it is on; your taps grade the confidence."""
import asyncio
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import desktop_agent as DA
from hub.features import learning as LRN
from hub.features import pc_control as PC
from hub.yard import evidence as EV
from hub.yard import settings as YS

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


@pytest.fixture()
def state(tmp_path, monkeypatch):
    """Everything this feature writes goes to a temporary folder; the real data folder is never touched."""
    d = tmp_path / "yard"
    monkeypatch.setattr(YS, "FILE", d / "settings.json")
    monkeypatch.setattr(YS, "_CACHE", {"at": 0.0, "data": {}, "file": None})
    monkeypatch.setattr(EV, "DIR", d)
    monkeypatch.setattr(EV, "FILE", d / "evidence.jsonl")
    monkeypatch.setattr(EV, "SHOTS", d / "evidence")
    monkeypatch.setattr(EV, "LABELS", d / "evidence_labels.json")
    monkeypatch.setattr(LRN, "CHOICES", tmp_path / "choices.jsonl")
    LRN._close()
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)
    monkeypatch.delenv("HUB_LEARNING_LOG", raising=False)
    yield d
    LRN._close()


def test_shadow_and_learning_are_off_until_you_switch_them_on(state):
    assert YS.flag("shadow") is False and YS.flag("learning") is False
    assert EV.record("agent", "play x", "apple music", True, {"agent_done": True}, 3.0) is None      # nothing is kept while off
    assert not (state / "evidence.jsonl").exists()
    YS.update({"shadow": True, "learning": True})
    assert YS.flag("shadow") is True and YS.flag("learning") is True


def test_the_environment_switch_still_forces_it_off(state, monkeypatch):
    YS.update({"shadow": True})
    monkeypatch.setenv("HUB_YARD_SHADOW", "0")
    assert YS.flag("shadow") is False


@pytest.mark.parametrize("markers,p,capped", [
    ({"windows_confirms": True}, 0.85, False),                                           # Windows said so: strong on its own
    ({"agent_done": True}, 0.25, False),                                                 # the agent's word alone is weak
    ({"routine_clean": True, "screen_changed": True}, 0.6425, False),                   # 1 - 0.55 x 0.65
    ({"routine_clean": True, "screen_changed": True, "agent_done": True, "few_steps": True}, 0.75, True),   # 0.759 but nothing independent checked it
    ({"windows_confirms": True, "screen_changed": True, "agent_done": True}, 0.927, False),                 # 1 - 0.15 x 0.65 x 0.75; with Windows' word there is no cap
    ({"windows_confirms": True, "nothing_changed": True}, 0.425, False),                 # a warning sign halves it
    ({"windows_confirms": True, "stopped": True}, 0.0, False),                           # you pressed stop
    ({}, 0.0, False)])
def test_the_confidence_arithmetic(markers, p, capped):
    got = EV.confidence(markers)
    assert got["p"] == pytest.approx(p, abs=0.001) and got["capped"] is capped


def test_markers_are_read_from_the_agents_own_trace():
    trace = [{"do": "click", "changed": True}, {"do": "invalid"}, {"do": "click", "changed": True}, {"do": "done"}]
    m = EV.markers_from_trace(trace, True, "Done. Now playing Song by Band.", music=True)
    assert m["agent_done"] and m["screen_changed"] and m["invalid"] and m["few_steps"] and m["windows_confirms"] and not m["false_done"]
    bad = EV.markers_from_trace([{"do": "click", "changed": False}, {"do": "done"}], False, "stuck", music=True)
    assert bad["nothing_changed"] and bad["false_done"] and not bad["windows_confirms"]


def _run(coro):
    return asyncio.run(coro)


def test_a_real_pc_task_is_kept_with_evidence_only_while_shadow_is_on(state, monkeypatch):
    """The journey: Talk's request reaches PC.after; the (fake) desktop agent does it; the record, picture and confidence appear."""
    async def fake_run(goal, app, **kw):
        return {"ok": True, "say": "Pressed Play. Now playing Song by Band.", "routine": None,
                "tries": [{"model": "m", "ok": True, "say": "x", "trace": [{"do": "click", "changed": True}, {"do": "done"}], "pressed": 1}]}
    monkeypatch.setattr(DA, "run", fake_run)
    monkeypatch.setattr(PC, "_routine", lambda *a, **k: None)
    monkeypatch.setattr(EV, "_grab_jpeg", lambda: JPEG)

    _run(PC.after("apple music", "play the ADHD playlist", "play the ADHD playlist"))
    assert EV._rows() == []                                                              # shadow is off: nothing kept

    YS.update({"shadow": True, "learning": True})
    done = _run(PC.after("apple music", "play the ADHD playlist", "play the ADHD playlist"))
    assert done["ok"]
    rows = EV._rows()
    assert len(rows) == 1
    r = rows[0]
    assert r["way"] == "agent" and r["ok"] and r["goal"] == "play the ADHD playlist" and r["pics"] == ["before", "after"]
    assert r["markers"]["windows_confirms"] and r["confidence"] >= 0.9 and not r["capped"]
    assert (state / "evidence" / f"{r['id']}-before.jpg").read_bytes() == JPEG


def test_the_api_lists_shows_grades_and_calibrates(state):
    YS.update({"shadow": True})
    a = EV.record("agent", "play a", "apple music", True, {"windows_confirms": True}, 4.0, before=JPEG, after=JPEG)
    b = EV.record("saved routine", "play b", "apple music", True, {"routine_clean": True}, 9.0, routine="r1")
    assert a and b

    async def go():
        app = web.Application()
        app.add_routes(EV.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/yard/evidence")).json()
            assert j["on"] and [i["goal"] for i in j["items"]] == ["play b", "play a"] and j["weights"]["cap"] == 0.75
            pic = await c.get(f"/api/yard/evidence/{a}/before.jpg")
            assert pic.status == 200 and await pic.read() == JPEG
            assert (await c.get(f"/api/yard/evidence/{b}/before.jpg")).status == 404           # no picture was kept for it
            assert (await c.get("/api/yard/evidence/../../x/before.jpg")).status == 404
            assert (await c.post(f"/api/yard/evidence/{a}/label", json={"grade": "maybe"})).status == 400
            assert (await c.post(f"/api/yard/evidence/{a}/label", json={"grade": "right"})).status == 200
            assert (await c.post(f"/api/yard/evidence/{b}/label", json={"grade": "wrong", "note": "it opened the wrong list"})).status == 200
            cal = {x["band"]: x for x in (await (await c.get("/api/yard/evidence")).json())["calibration"]}
            assert cal["75-90 %"]["graded"] == 1 and cal["75-90 %"]["right"] == 1       # a: 0.85, you said right
            assert cal["0-50 %"]["graded"] == 1 and cal["0-50 %"]["right"] == 0         # b: 0.45, you said wrong
    _run(go())
    labels = json.loads((state / "evidence_labels.json").read_text(encoding="utf-8"))
    assert labels[a]["grade"] == "right" and labels[b]["note"] == "it opened the wrong list"


def test_replay_needs_a_confirm_and_a_saved_routine(state, monkeypatch):
    YS.update({"shadow": True})
    agent = EV.record("agent", "play a", "apple music", True, {"agent_done": True}, 4.0)
    routine = EV.record("saved routine", "play b", "apple music", True, {"routine_clean": True}, 9.0, routine="r1")
    ran = []

    async def fake_run_routine(rid, request="manual run"):
        ran.append((rid, request))
        return {"ok": True, "say": "ran"}
    monkeypatch.setattr(PC, "run_routine", fake_run_routine)

    async def go():
        app = web.Application()
        app.add_routes(EV.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post(f"/api/yard/evidence/{routine}/replay", json={})).status == 400          # it presses things: must be confirmed
            assert (await c.post(f"/api/yard/evidence/{agent}/replay", json={"confirm": True})).status == 409   # the agent did it: no routine
            assert ran == []
            got = await c.post(f"/api/yard/evidence/{routine}/replay", json={"confirm": True})
            assert got.status == 200 and (await got.json())["ok"] and ran == [("r1", "teach replay")]
    _run(go())


def test_only_the_newest_records_are_kept_and_clear_removes_everything(state):
    from hub.yard import knobs as K
    YS.update({"shadow": True})
    K.set_many({"evidence_keep": 20})                                                   # the KNOBS tab's number; 20 is its smallest
    ids = [EV.record("agent", f"task {i}", "app", True, {"agent_done": True}, 1.0, before=JPEG) for i in range(23)]
    rows = EV._rows()
    assert [r["goal"] for r in rows] == [f"task {i}" for i in range(3, 23)]
    assert not (state / "evidence" / f"{ids[0]}-before.jpg").exists() and (state / "evidence" / f"{ids[22]}-before.jpg").exists()

    async def go():
        app = web.Application()
        app.add_routes(EV.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.delete("/api/yard/evidence")).status == 400
            assert (await c.delete("/api/yard/evidence?confirm=1")).status == 200
    _run(go())
    assert EV._rows() == [] and not (state / "evidence").exists()
