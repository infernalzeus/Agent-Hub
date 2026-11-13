"""R8c + R8d, live: every finished mission step is scored without grading, a tally per role learns which preset suits it, shadow only records, apply uses the pick (never over your own setting)."""
import random
import types

import pytest

from hub import agent_knowledge as AK
from hub.yard import knobs as K, presets as P


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")
    monkeypatch.setattr(P, "_dir", lambda: tmp_path)
    return tmp_path


def _m(answer="Added the toggle and saved the theme.", ok=True, agent="coder"):
    return types.SimpleNamespace(id="m1", kind="single", agent=agent, answer=answer, verify={"ok": ok}, plan=[])


def test_a_call_counts_for_the_preset_it_is_close_to_and_otherwise_for_none():
    assert P.nearest({"temperature": "0.2"}) == "terse" and P.nearest({"temperature": 0.0, "top_p": 0.8}) == "precise" and P.nearest({"temperature": 1.5}) == "own" and P.nearest({}) == "own"


def test_the_default_is_shadow_and_a_finished_mission_is_scored_and_a_pick_is_written_but_nothing_changes(monkeypatch):
    assert P.mode() == "shadow"
    rows = P.note_mission(_m())
    assert len(rows) == 1 and rows[0]["role"] == "coder" and rows[0]["reward"] > 0 and rows[0]["parts"]["checks"] > 0
    assert P.summary()["calls"] == 1 and P.summary()["roles"][0]["pick"]["applied"] is False
    assert P.applied("coder") is None                                                       # shadow: the agent's settings are not touched
    assert AK.effective_settings("coder")["temperature"]["source"] != "preset"


def test_off_records_nothing():
    K.set_many({"preset_mode": "off"})
    assert P.note_mission(_m()) == [] and P.calls() == []


def test_every_preset_gets_its_turn_before_the_draw_and_the_better_one_wins_after():
    seen = {P.suggest("coder", random.Random(i))["pick"] for i in range(60)}
    assert seen == set(P.PRESETS)                                                           # with no tries, any can be picked
    rows = [{"role": "coder", "preset": n, "reward": r, "at": i} for i, (n, r) in enumerate([(n, 1.0 if n == "precise" else 0.1) for n in P.PRESETS for _ in range(6)])]
    import json
    (P._dir() / "preset_calls.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    picks = [P.suggest("coder", random.Random(i))["pick"] for i in range(40)]
    assert picks.count("precise") >= 30                                                      # after enough tries the one that scored well is drawn most


def test_apply_uses_the_pick_but_never_over_a_setting_you_made_yourself(monkeypatch):
    K.set_many({"preset_mode": "apply"})
    P.note_mission(_m())
    pick = P.summary()["roles"][0]["pick"]["name"]
    eff = AK.effective_settings("coder")
    assert eff["temperature"]["source"] == "preset" and eff["temperature"]["value"] == P.PRESETS[pick]["temperature"]
    monkeypatch.setattr(AK, "load_overrides", lambda: {"coder": {"temperature": 0.77}})
    assert AK.effective_settings("coder")["temperature"] == {"value": 0.77, "source": "override"}      # yours wins


def test_a_preset_chosen_for_an_agent_is_used_unless_you_set_the_value_yourself(monkeypatch):
    assert P.applied("neo") is None
    P.set_choice("neo", "precise")
    use = P.applied("neo")
    assert use["name"] == "precise" and use["by"] == "you" and use["options"]["top_k"] == 20 and use["options"]["num_predict"] == 1024
    eff = AK.effective_settings("neo")
    assert eff["temperature"] == {"value": 0.0, "source": "preset", "note": "the precise preset, chosen by you for this role"} and eff["options"]["value"]["top_k"] == 20
    monkeypatch.setattr(AK, "load_overrides", lambda: {"neo": {"temperature": 0.9, "options": {"top_k": 5}}})
    eff = AK.effective_settings("neo")
    assert eff["temperature"]["value"] == 0.9 and eff["temperature"]["source"] == "override" and eff["options"]["value"]["top_k"] == 5 and eff["options"]["value"]["min_p"] == 0.05
    P.set_choice("neo", "")
    assert P.applied("neo") is None


def test_the_doctors_talk_answers_use_the_doctors_preset_through_the_researcher_persona():
    P.set_choice("doctor", "terse")
    assert P.applied("researcher") is None
    with P.speaking_as("researcher", "doctor"):
        assert P.applied("researcher")["name"] == "terse"
    assert P.applied("researcher") is None


def test_the_routes_list_the_presets_and_save_a_choice_for_the_four_core_agents_only():
    import asyncio
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def go():
        app = web.Application()
        app.add_routes(P.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/agents/presets")).json()
            assert set(j["presets"]) == set(P.PRESETS) and j["core"] == ["smith", "orchestrator", "neo", "doctor"] and j["choices"] == {}
            assert (await c.post("/api/agents/smith/preset", json={"preset": "varied"})).status == 200
            assert (await (await c.get("/api/agents/presets")).json())["choices"] == {"smith": "varied"}
            assert (await c.post("/api/agents/coder/preset", json={"preset": "varied"})).status == 404
    asyncio.run(go())
