"""The run record: each step of a desktop-agent run is kept with its times and a picture; the person ticks the right ones and saves them as a routine."""
import asyncio
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import desktop_agent as DA, pc_control as PC, run_record as RR


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(RR, "STATE", tmp_path)
    return tmp_path


def _got():
    return {"ok": True, "verified": True, "say": "Done.", "first": [{"control": "window", "name": "apple music", "window": "Apple Music"}],
            "trace": [{"step": 0, "ms": 4100, "do": "click", "control": "Search box", "why": "find the list", "changed": False, "press": 0, "press_ms": 900, "shot": "000.jpg"},
                      {"step": 1, "ms": 5200, "do": "click", "control": "Home", "why": "", "changed": True, "press": 1, "press_ms": 700, "shot": "001.jpg"},
                      {"step": 2, "ms": 3900, "do": "invalid", "why": "refused"},
                      {"step": 3, "ms": 4400, "do": "click", "control": "ADHD", "why": "the list", "changed": True, "verified": True, "press": 2, "press_ms": 800}],
            "steps": [{"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": "Search box", "control": "Edit", "window": "Apple Music", "path": ""}, "_changed": False},
                      {"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": "Home", "control": "Button", "window": "Apple Music", "path": ""}, "_changed": True},
                      {"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": "ADHD", "control": "ListItem", "window": "Apple Music", "path": ""}, "_changed": True}]}


def test_a_run_is_kept_with_times_pictures_and_what_was_pressed(store, monkeypatch):
    monkeypatch.setattr(PC, "ui_signature", lambda flat, window: {"window": window})
    monkeypatch.setattr(PC, "flatten", lambda nodes: nodes)
    assert RR.keep_shot("abc123", 1, b"\xff\xd8jpeg") == "001.jpg"
    RR.write("abc123", "play my adhd playlist", "apple music", "m1", _got(), 70500)
    row = json.loads((store / "data" / "runs" / "abc123" / "run.json").read_text(encoding="utf-8"))
    assert row["ms"] == 70500 and len(row["trace"]) == 4 and row["window"] == "Apple Music" and len(row["presses"]) == 3
    assert (store / "data" / "runs" / "abc123" / "001.jpg").read_bytes() == b"\xff\xd8jpeg"
    assert RR.summary(row)["useful"] == 2 and RR.summary(row)["steps"] == 4


def test_an_id_that_is_not_a_run_id_cannot_reach_other_files(store):
    assert RR.keep_shot("../x", 0, b"a") == ""
    with pytest.raises(web.HTTPNotFound):
        RR._dir("../../etc")


def test_ticking_the_right_steps_saves_only_those_as_a_routine(store, monkeypatch):
    monkeypatch.setattr(PC, "ui_signature", lambda flat, window: {"window": window})
    monkeypatch.setattr(PC, "flatten", lambda nodes: nodes)
    RR.write("abc123", "play my adhd playlist", "apple music", "m1", _got(), 70500)
    saved = {}
    monkeypatch.setattr(PC, "routine_for_do", lambda app, goal: None)
    monkeypatch.setattr(PC, "do_intent", lambda app, goal: "do:apple music:adhd")
    monkeypatch.setattr(PC, "save_ui_routine", lambda intent, title, window, steps, sig: saved.update(intent=intent, steps=steps, window=window) or {"id": "r1", "status": "candidate"})
    app = web.Application()
    app.add_routes(RR.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/runs")).json()
            assert j["runs"][0]["id"] == "abc123" and j["runs"][0]["ms"] == 70500
            r = await (await c.post("/api/runs/abc123/save", json={"keep": [1, 3, 2]})).json()          # 2 is a refused answer: it pressed nothing, so it keeps nothing
            assert r == {"ok": True, "routine": "r1", "steps": 2, "status": "candidate"}
            assert [s["target"]["name"] for s in saved["steps"]] == ["Home", "ADHD"] and saved["window"] == "Apple Music"
            none = await (await c.post("/api/runs/abc123/save", json={"keep": [2]})).json()
            assert none["ok"] is False
            assert (await c.get("/api/runs/abc123/shot/001.jpg")).status == 404                      # no picture was stored for that one
            assert (await c.delete("/api/runs/abc123")).status == 200
            assert (await c.get("/api/runs/abc123")).status == 404
            assert "SAVE TICKED STEPS" in await (await c.get("/runs")).text()
    asyncio.run(go())


def test_the_agent_loop_takes_a_picture_and_the_press_time_per_step(store, monkeypatch):
    nodes = [{"control": "window", "name": "Apple Music", "window": "Apple Music", "x": 0, "y": 0, "path": "", "clickable": False},
             {"control": "Button", "name": "Home", "window": "Apple Music", "x": 5, "y": 5, "path": "", "clickable": True}]
    asked = []

    async def tree():
        return [dict(n) for n in nodes]

    async def click(x, y):
        nodes[1]["name"] = "Home!"                                              # the screen changes after the press

    async def shot(rid, step):
        asked.append((rid, step))
        return f"{step:03d}.jpg"
    answers = iter([json.dumps({"do": "click", "control": 1, "why": "go home"}), json.dumps({"do": "done", "say": "ok"})])

    async def decide(system, user):
        return next(answers)
    got = asyncio.run(DA.attempt("open home", "apple music", decide, tree=tree, click=click, type_=click, key=click, media=lambda: asyncio.sleep(0, []), settle=0, shot=shot, rid="abc123", shadow=False))
    assert asked == [("abc123", 0)]
    assert got["trace"][0]["shot"] == "000.jpg" and "press_ms" in got["trace"][0] and got["trace"][0]["press"] == 0
