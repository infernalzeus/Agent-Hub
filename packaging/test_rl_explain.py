"""Why the learner would press what it would press, and which weights a step would move. A small learner is taught one rule (goal words in a control's name are good),
saved the way a session saves it, and read back through the endpoints."""
import json
import random

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.yard import demos as DM, explain as EX, learner as L, memory as MEM, shadow as SH


@pytest.fixture
def policy(tmp_path, monkeypatch):
    lr = L.Learner()
    lr.actor.w = np.zeros(L.DIM)
    names = EX.base_names()
    for i, f in enumerate(EX.FLAGS):
        lr.actor.w[i * L.BASE + names.index("goal words in its name")] = 3.0      # for every step situation: a name that shares the goal's words is good
        lr.actor.w[i * L.BASE + names.index("on the never-press list")] = -5.0
    f = tmp_path / "policy.json"
    f.write_text(json.dumps({"linear": lr.actor.dump()}), encoding="utf-8")
    monkeypatch.setattr(SH, "POLICY", f)
    return lr


def _run(c):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(c)


def _screen(goal="play the Coding Flow playlist"):
    from hub.features import pc_control as PC
    cl = [{"id": 1, "role": "button", "name": "Share", "path": "", "row": ""}, {"id": 2, "role": "list item", "name": "Coding Flow", "path": "Your playlists", "row": ""},
          {"id": 3, "role": "menu item", "name": "Delete playlist", "path": "", "row": ""}]
    return {"goal": goal, "goal_words": PC.target_words(goal), "step": 0, "controls": cl, "pressed": set(), "unchanged": set(), "n_pressed": 0, "typed": False,
            "item_pressed": False, "last_changed": False, "last_nothing": False, "playing": False}


def test_a_screen_is_explained_by_the_features_that_made_each_score(policy):
    e = EX.screen(_screen(), policy.actor, chosen=2, advantage=1.0)
    top = e["candidates"][0]
    assert top["action"].startswith("press list item") and top["pressed"] and top["best"]
    assert any(x["feature"].startswith("goal words in its name") and x["part"] > 0 for x in top["because"])
    assert abs(sum(c["p"] for c in EX.screen(_screen(), policy.actor, show=20)["candidates"]) - 1) < 0.01          # the probabilities add up
    assert e["moves"] and e["moves"][0]["weight"] and e["advantage"] == 1.0
    json.dumps(e)                                                                                                    # numpy values must not leak into the answer
    never = next(c for c in EX.screen(_screen(), policy.actor, show=20)["candidates"] if "Delete playlist" in c["action"])
    assert never["p"] < 0.01 and any(x["feature"].startswith("on the never-press list") for x in never["because"])


def test_the_weights_a_good_press_would_move_are_the_features_only_the_pressed_control_had(policy):
    e = EX.screen(_screen(), policy.actor, chosen=2, advantage=1.0)
    ups = [m for m in e["moves"] if m["direction"] == "up"]
    assert any(m["weight"].startswith("goal words in its name") for m in ups)
    bad = EX.screen(_screen(), policy.actor, chosen=2, advantage=-1.0)
    assert all(m["direction"] == "down" for m in bad["moves"] if m["weight"].startswith("goal words in its name"))      # a bad press pushes the same weight the other way


def test_a_hidden_layer_actor_is_explained_too(policy):
    a = L.Actor(4, seed=3)
    e = EX.screen(_screen(), a, chosen=2, advantage=1.0)
    assert e["linear"] is False and e["candidates"] and json.dumps(e)


def test_a_routine_is_walked_step_by_step_through_the_endpoint(policy, monkeypatch):
    rt = {"id": "r1", "title": "Play the Coding Flow playlist", "steps": [{"role": "list item", "name": "Coding Flow"}, {"role": "button", "name": "Play"}]}
    monkeypatch.setattr(DM, "routines", lambda: [rt])

    async def go():
        app = web.Application()
        app.add_routes(EX.routes)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/yard/why/routine/r1")
            assert r.status == 200
            return await r.json()
    j = _run(go())
    assert j["of"] == 2 and len(j["steps"]) == 2 and j["steps"][0]["routine_presses"].startswith("list item")
    assert j["steps"][0]["agrees"] is True                                                                          # the taught rule picks the playlist
    assert "Weights moved" in j["note"] or "move" in j["note"]


def test_a_live_task_shows_the_screens_the_agent_really_had(policy, tmp_path, monkeypatch):
    prompt = ('GOAL: play the Coding Flow playlist\nAPP: Pretend Music\nSTEP 1 of 9\nNOW PLAYING: nothing\n\nSO FAR:\n(nothing yet)\n\nCONTROLS:\n1. button "Share" in "Player bar"\n'
              '2. list item "Coding Flow" in "Your playlists"\n3. button "Next" in "Player bar"')
    f = tmp_path / "memory_steps.jsonl"
    f.write_text(json.dumps({"at": 1000.0, "goal": "play the Coding Flow playlist", "step": 0, "prompt": prompt, "live": {"do": "click", "id": 2}}) + "\n", encoding="utf-8")
    monkeypatch.setattr(MEM, "MEMORY_STEPS", f)
    tasks = EX.live_tasks()
    assert tasks and tasks[0]["steps"] == 1
    j = EX.live_task(tasks[0]["goal"], tasks[0]["at"])
    assert j["of"] == 1 and j["agree"] == 1 and j["steps"][0]["live_did"].startswith("press list item")


def test_without_a_saved_learner_it_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "POLICY", tmp_path / "none.json")
    assert "start a session" in EX.routine("x")["error"]
