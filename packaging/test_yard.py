"""The practice yard: the pretend apps are exact, the real agent runs against them, the learner learns, and it never reaches outside itself."""
import asyncio
import json

import pytest

np = pytest.importorskip("numpy")

from hub.features import desktop_agent as DA
from hub.yard import api, learner as L, practice as P
from hub.yard.world import APP, FAMILIES, World


def _nodes(w):
    return asyncio.run(w.tree())


def test_the_goal_names_a_control_the_agent_lists_even_deep_in_a_long_list():
    # before the fix the list cap ran before the ranking, so entry 20 of 30 was never shown to the model
    w = World("long", 1)
    assert w.items.index(w.target) >= 18
    assert any(c["node"]["name"] == w.target for c in DA.controls(_nodes(w), APP, w.goal))


def test_a_control_with_no_name_is_never_listed_and_the_diagnosis_says_so():
    w = World("unnamed", 1)
    asyncio.run(w.click(*sorted(w.needed())[0]))                       # open the playlist page
    assert not any(c["node"]["name"] == "" for c in DA.controls(_nodes(w), APP, w.goal))
    assert P.cause(w) == "a control with no name is never listed"


@pytest.mark.parametrize("family", [f for f in FAMILIES if f != "unnamed"])
def test_every_visible_family_can_be_won_by_following_the_needed_controls(family):
    w = World(family, 3)
    for _ in range(8):
        need = w.needed()
        if not need:
            break
        x, y = sorted(need)[0]
        node = next(n for n in _nodes(w) if (n.get("x"), n.get("y")) == (x, y))
        asyncio.run(w.type_(w.target, [x, y]) if node["control"] == "edit" else w.click(x, y))
    assert w.success()


def test_pressing_the_players_own_play_does_nothing_and_a_wrong_playlist_is_not_a_win():
    w = World("direct", 2)
    bar_play = next(n for n in _nodes(w) if n["name"] == "Play")
    asyncio.run(w.click(bar_play["x"], bar_play["y"]))
    assert w.playing is None and not w.success()


def test_the_pretend_app_state_not_the_agents_word_decides_success():
    w = World("direct", 4)
    res = P.run_episode(w, L.random_policy(1))
    assert res["success"] == w.success()


def test_a_learner_trained_for_a_short_time_beats_the_rule_of_thumb_on_apps_it_never_saw():
    lr, curve = P.train(1500, hidden=0, seed=0)
    fams = [f for f in FAMILIES if f != "unnamed"]
    learned = P.evaluate(lambda: lr.policy(False), 10, fams)
    rule = P.evaluate(lambda: L.greedy_policy, 10, fams)
    mean = lambda t: np.mean([t[f]["train"]["success"] for f in fams])
    assert mean(learned) > mean(rule) + 0.2
    assert curve[-1][1] > curve[0][1]


def test_a_policy_only_ever_chooses_what_the_agents_own_parser_accepts():
    pol = L.Learner(seed=1).policy(True)
    bad = sum(P.run_episode(World(f, k), pol)["invalid"] for k, f in enumerate(FAMILIES * 4))
    assert bad == 0 and all(r["a"] < len(r["p"]) for r in pol.records)


def test_practice_without_write_leaves_no_file_and_does_not_touch_the_learning_log(tmp_path, monkeypatch):
    from hub.features import learning
    monkeypatch.setattr(learning, "CHOICES", tmp_path / "choices.jsonl")
    monkeypatch.setattr(P, "REPORT", tmp_path / "yard" / "report.json")
    P.practice(episodes=100, n_eval=2, write=False)
    assert not (tmp_path / "yard").exists() and not (tmp_path / "choices.jsonl").exists()


def test_status_works_before_any_run_and_reads_a_report(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REPORT", tmp_path / "report.json")
    assert api.status()["ran"] is False
    (tmp_path / "report.json").write_text(json.dumps({"means": {"x": 1}}))
    assert api.status()["report"] == {"means": {"x": 1}}


from test_ui_lifecycle import hub  # noqa: E402,F401  (an isolated Hub on its own state folder)


def test_a_running_hub_serves_the_yard_status(hub):
    import urllib.request
    d = json.load(urllib.request.urlopen(hub + "/api/yard/status"))
    assert d["ready"] is True and d["max_episodes"] == api.MAX_EPISODES
