"""Learners are versioned, never overwritten by a worse one, and the experience is appended."""
import json

from hub.yard import store


def rep(held, known=0.9, at=1.0):
    return {"at": at, "episodes": 100, "seed": 0,
            "means": {"learned, linear": {"train": known, "held": held}, "learned, one hidden layer": {"train": known, "held": held - .1}},
            "table": {"learned, linear": {"direct": {}, "modal": {}}}}


def test_a_better_learner_replaces_the_one_in_use_a_clearly_worse_one_does_not_and_all_are_kept(tmp_path):
    pol = tmp_path / "policy.json"
    a = store.save(tmp_path, pol, rep(0.60), {"linear": {"w": 1}})
    assert a == {"version": 1, "adopted": True, "held": 0.60, "best_before": None}
    assert json.loads(pol.read_text())["version"] == 1
    b = store.save(tmp_path, pol, rep(0.40), {"linear": {"w": 2}})             # a bad session
    assert b["adopted"] is False and json.loads(pol.read_text())["linear"] == {"w": 1}
    c = store.save(tmp_path, pol, rep(0.59), {"linear": {"w": 3}})             # within 0.02 of the best: as good, adopted
    assert c["adopted"] is True and json.loads(pol.read_text())["version"] == 3
    assert [v["n"] for v in store.versions(tmp_path)] == [1, 2, 3]
    assert store.current_version(pol) == 3
    lines = [json.loads(l) for l in (tmp_path / "sessions.jsonl").read_text().splitlines()]
    assert [l["adopted"] for l in lines] == [True, False, True]               # the experience is appended, one line per session


def test_only_the_newest_twelve_versions_are_kept(tmp_path):
    pol = tmp_path / "policy.json"
    for i in range(15):
        store.save(tmp_path, pol, rep(0.5 + i * .01, at=float(i)), {"linear": {}})
    assert [v["n"] for v in store.versions(tmp_path)] == list(range(4, 16))


def test_the_next_session_continues_from_the_saved_learner_and_the_history_stays_small(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("numpy")
    from hub.yard import practice as P
    monkeypatch.setattr(P, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(P, "POLICY", tmp_path / "policy.json")
    first = P.practice(episodes=120, n_eval=2)
    assert first["warm_from"] is None
    saved = json.loads((tmp_path / "policy.json").read_text())
    assert saved["linear_state"]["critic"] and saved["hidden_state"]["actor"]["hidden"] == 16      # the critic is saved with the actor, so it can be continued
    second = P.practice(episodes=120, n_eval=2)
    assert second["warm_from"] == saved["version"]                                                   # it started from the saved learner
    metas = store.versions(tmp_path)
    assert metas[-1]["total_episodes"] == 240 and metas[-1]["warm_from"] == 1
    cold = P.practice(episodes=120, n_eval=2, warm=False)
    assert cold["warm_from"] is None
    for i in range(210):                                                                              # the history is capped
        store.save(tmp_path, tmp_path / "x.json", rep(0.5, at=float(i)), {"linear": {}})
    assert len((tmp_path / "sessions.jsonl").read_text().splitlines()) == 200
