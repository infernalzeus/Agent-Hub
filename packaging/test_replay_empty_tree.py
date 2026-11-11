"""A routine replay must not give up because the app's window had not drawn yet (5 Nov: the signature of an empty tree, three fall-throughs)."""
import asyncio
import json

from hub.features import pc_control as PC


def test_an_empty_tree_is_read_again_before_the_screen_is_called_different(monkeypatch):
    calls = []

    async def fake_snapshot(window=""):
        calls.append(1)
        return [] if len(calls) < 3 else [{"name": "Playlists", "control": "list item", "window": "Apple Music", "x": 1, "y": 1}]

    async def no_sleep(_):
        return None

    monkeypatch.setattr(PC, "_snapshot", fake_snapshot)
    monkeypatch.setattr(PC.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(PC, "_steps", lambda rid: [{"ordinal": 0, "tool": "Click", "args_json": "{}", "target_json": "{}"}])
    monkeypatch.setattr(PC, "_record_run", lambda *a, **k: None)
    routine = {"id": "x", "title": "T", "status": "candidate", "successes": 0, "signature_json": json.dumps({"window": "Apple Music", "stable": "nothing-like-this"})}
    out = asyncio.run(PC.replay_ui_routine(routine, "play"))
    assert len(calls) == 3, "it looked again until the window had drawn"
    assert out["route"] == "fall-through" and "not on the screen" in out["say"]        # and only then judged the screen: its first control is missing, so nothing is pressed
