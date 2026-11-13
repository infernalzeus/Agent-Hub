"""R9a, R8b, R9b: settled sentences shown to the router's local model, a replay at other settings, and a suggested cut-off. The local model is replaced by a fake."""
import asyncio

import pytest

from hub.yard import knobs as K, router_tuning as RT


@pytest.fixture(autouse=True)
def knobs(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")


ROWS = [{"text": "play my adhd playlist on apple music", "label": "app_task", "source": "graded"}, {"text": "open apple music", "label": "launch_app", "source": "trusted routine"},
        {"text": "what is the weather in leeds", "label": "conversation", "source": "graded"}, {"text": "open notepad please", "label": "launch_app", "source": "graded"}]


def test_the_nearest_settled_sentences_come_with_their_right_bin_and_never_the_sentence_itself():
    got = RT.nearest("play the adhd playlist in apple music", 2, ROWS)
    assert got[0]["sentence"] == "play my adhd playlist on apple music" and got[0]["bin"] == "app_task"
    assert RT.nearest("open apple music", 3, ROWS) and all(e["sentence"] != "open apple music" for e in RT.nearest("open apple music", 3, ROWS))
    assert RT.nearest("xyzzy plugh", 3, ROWS) == []                                   # nothing alike: no examples


def test_zero_turns_the_examples_off_and_the_state_carries_them_when_there_are_some(monkeypatch):
    monkeypatch.setattr(RT, "pool", lambda: ROWS)
    assert "examples" in RT.state_for("play the adhd playlist in apple music")
    K.set_many({"router_examples": 0})
    assert RT.state_for("play the adhd playlist in apple music") == {"utterance": "play the adhd playlist in apple music"}


def test_a_replay_counts_right_bins_per_setting_and_never_shows_a_sentence_its_own_answer(monkeypatch):
    monkeypatch.setattr(RT, "pool", lambda: ROWS)
    seen = []

    async def post(body, key):
        import json
        st = json.loads(body["state"])
        seen.append((body.get("options"), st))
        guess = "app_task" if "play" in st["utterance"] else "launch_app" if "open" in st["utterance"] else "conversation"
        return {"answers": {"bin": {"answer": guess, "p": 0.9}}}
    from hub import decide as DEC
    monkeypatch.setattr(DEC, "_jev_read", lambda q, a: {"id": q["id"], "answer": (a or {}).get("answer"), "p": 0.9, "dist": None})
    rep = asyncio.run(RT.replay(post, temperatures=(0.0, 0.7), shots=(0, 2)))
    assert rep["calls"] == 4 * len(ROWS) and len(rep["rows"]) == 4 and all(r["right"] == len(ROWS) for r in rep["rows"])
    assert {o["temperature"] for o, _ in seen} == {0.0, 0.7}
    assert all(st["utterance"] not in [e["sentence"] for e in st.get("examples", [])] for _, st in seen)


def test_a_cutoff_is_suggested_only_with_enough_decisions_and_it_is_the_cheapest():
    assert RT.cutoffs([(0.9, True)] * 5)["ready"] is False
    pairs = [(0.95, True)] * 20 + [(0.85, True)] * 10 + [(0.6, False)] * 10 + [(0.55, False)] * 5
    got = RT.cutoffs(pairs)
    assert got["ready"] and 0.6 < got["suggested"] <= 0.85 and "suggestion only" in got["note"]
    assert min(r["cost"] for r in got["table"]) == next(r["cost"] for r in got["table"] if r["cutoff"] == got["suggested"])
