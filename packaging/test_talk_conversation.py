"""Talk's conversation: the phrasing people really use is understood, and an open-ended ask gets one short question instead of a guess."""
import asyncio

import pytest

from hub.features import binning as B
from hub.features import desktop_agent as DA
from hub.features import pc_control as PC


@pytest.mark.parametrize("text", ["Can you pull up the latest mission on the Hub dashboard for me?", "pull up the graph", "display the agents", "check the missions",
                                  "look at the graph please", "bring up the missions"])
def test_pull_up_and_its_kin_are_hub_commands(text):
    assert B.decide(text)["bin"] == "hub_command"


@pytest.mark.parametrize("text,open_ended", [("play some music", True), ("Play something", True), ("put something on", True), ("play some music from apple music", True),
                                              ("play the ADHD playlist", False), ("shuffle all songs in my library", False), ("play my favourites", False)])
def test_what_counts_as_an_open_ended_play(text, open_ended):
    assert PC._open_ended_play(text, "apple music") is open_ended


def test_an_open_ended_play_asks_before_it_acts_and_a_named_one_does_not(monkeypatch):
    calls = []

    async def fake_run(goal, app, **kw):
        calls.append(goal)
        return {"ok": True, "say": "Done.", "tries": [], "routine": None}
    monkeypatch.setattr(DA, "run", fake_run)
    monkeypatch.setattr(PC, "_routine", lambda *a, **k: None)
    asked = asyncio.run(PC.after("apple music", "play some music", "play some music"))
    assert asked["confirm"] and asked["action"]["id"] == "desktop_task" and "shuffle" in asked["action"]["args"]["goal"] and calls == []
    assert "Shall I shuffle your library?" in asked["say"]
    named = asyncio.run(PC.after("apple music", "play the ADHD playlist", "play the ADHD playlist"))
    assert named["ok"] and calls == ["play the ADHD playlist"]
