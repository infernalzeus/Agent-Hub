"""The swappable learning methods, on made-up numbers only: CPU, a few seconds, no model, no GPU, no Ollama, nothing from this PC's real logs.

What each test checks, in plain words:
  CMA-ES        finds a better set of numbers than random tries with the same budget, also when the score is noisy
  OPE           the off-policy estimate counts only rows the candidate would have chosen, weights by the logged chance, and says when it is not worth much
  learners      tally, Thompson and LinUCB follow one interface; Thompson tries each option before preferring one; LinUCB learns that the best option depends on context
  weights       averaging, smoothing, differences and adding differences back behave like arithmetic on saved versions; the greedy soup refuses a version that hurts
  calibration   an over-confident rule is pulled down; the fitted marker weights are offered only with enough graded rows and only called better when they are
  router kNN    every graded request, right or wrong, is an example; held-out accuracy is measured by leaving each one out
  support       a screen unlike anything trained on is reported as not covered
  TEACH order   unsure decisions come first
"""
import asyncio
import json
import random

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import binning as BIN
from hub.yard import calibrate as CAL
from hub.yard import conservative as CON
from hub.yard import fitness as FIT
from hub.yard import learners as LN
from hub.yard import ope
from hub.yard import router_challenger as RC
from hub.yard import search as S
from hub.yard import settings as YS
from hub.yard import teach as T
from hub.yard import weights as W


# ---- CMA-ES
def test_cma_es_beats_random_search_with_the_same_number_of_tries_even_when_the_score_is_noisy():
    space = {k: (0.0, 1.0) for k in "abcd"}
    peak = {"a": 0.7, "b": 0.2, "c": 0.5, "d": 0.9}
    exact = lambda c: -sum((c[k] - peak[k]) ** 2 for k in peak)                         # noqa: E731
    wins = 0
    for seed in range(5):
        cma = S.cma_es(exact, space, tries=300, seed=seed)
        rnd = S.random_search(exact, space, tries=300, seed=seed)
        wins += cma["score"] > rnd["score"]
        assert cma["tries"] == 300 and set(cma["candidate"]) == set(space)
    assert wins == 5 and S.cma_es(exact, space, tries=300, seed=0)["score"] > -0.03
    rng = random.Random(3)
    noisy = lambda c: exact(c) + rng.gauss(0, 0.02)                                       # noqa: E731
    got = S.cma_es(noisy, space, tries=400, seed=1, repeat=2)["candidate"]
    assert all(abs(got[k] - peak[k]) < 0.2 for k in peak)                                 # still lands near the peak
    assert S.cma_es(exact, space, tries=60, seed=2) == S.cma_es(exact, space, tries=60, seed=2)      # repeatable


# ---- off-policy evaluation
def test_the_off_policy_estimate_counts_only_agreeing_rows_and_weights_by_the_logged_chance():
    rows = [{"chosen": "a", "p": 1.0, "ok": True}] * 6 + [{"chosen": "a", "p": 1.0, "ok": False}] * 2 + [{"chosen": "b", "p": 1.0, "ok": True}] * 4
    only_a = ope.snips(rows, lambda r: 1.0 if r["chosen"] == "a" else 0.0)
    assert only_a["estimate"] == pytest.approx(0.75) and only_a["used"] == 8 and only_a["n"] == 12 and only_a["ci"] is not None
    nothing = ope.snips(rows, lambda r: 0.0)
    assert nothing["estimate"] is None and nothing["ess"] == 0.0
    lucky = [{"chosen": "a", "p": 0.1, "ok": True}, {"chosen": "a", "p": 0.9, "ok": False}]      # chosen rarely and won; chosen often and lost
    got = ope.snips(lucky, lambda r: 1.0)
    assert got["estimate"] > 0.85                                                          # the rare win counts for more
    spread = ope.snips([{"chosen": "a", "p": 0.001, "ok": True}] + [{"chosen": "a", "p": 1.0, "ok": False}] * 9, lambda r: 1.0)
    assert spread["ess"] < 4.0                                                             # one very heavy row (capped at 10): worth about 3 of the 10 rows, not 10


# ---- learners
def _rows(kind, spec):
    out = []
    for i, (ctx, chosen, ok) in enumerate(spec):
        out.append({"kind": kind, "context": "c", "chosen": chosen, "ok": ok, "ctx": ctx, "at": float(i + 1), "p": 1.0})
    return out


def test_the_learners_share_one_interface_and_a_new_one_can_be_registered():
    assert {"tally", "thompson", "linucb"} <= set(LN.REGISTRY)
    rows = _rows("rung", [({}, "replay", True)] * 4 + [({}, "agent", False)] * 3)
    for name in ("tally", "thompson", "linucb"):
        lr = LN.make(name).fit(rows)
        pick, p = lr.choose({}, ["replay", "agent"])
        assert pick == "replay" and 0 < p <= 1 and "name" in lr.dump()
    with pytest.raises(KeyError):
        LN.make("nonesuch")

    @LN.register
    class Always(LN.Learner):
        name = "always-first"
        description = "a test learner"
    try:
        assert LN.make("always-first").choose({}, ["x", "y"])[0] == "y"                  # the interface is enough: it appears in the registry
        assert "always-first" in {r["learner"] for r in LN.compare(rows, "rung")}
    finally:
        LN.REGISTRY.pop("always-first")


def test_thompson_tries_every_option_before_preferring_one():
    lr = LN.Thompson(min_n=3).fit(_rows("model", [({}, "big", True)] * 5))
    assert lr.choose({}, ["big", "small"])[0] == "small"                                    # small has never been tried: it goes first
    lr = LN.Thompson(min_n=3).fit(_rows("model", [({}, "big", True)] * 8 + [({}, "small", False)] * 4 + [({}, "small", True)]))
    assert lr.choose({}, ["big", "small"])[0] == "big"                                      # now the record decides


def test_linucb_learns_that_the_best_option_depends_on_the_situation():
    spec = []
    for i in range(12):
        spec += [({"app": "outlook"}, "replay", True), ({"app": "outlook"}, "agent", False), ({"app": "music"}, "replay", False), ({"app": "music"}, "agent", True)]
    lr = LN.LinUCB(alpha=0.1).fit(_rows("rung", spec))
    assert lr.choose({"app": "outlook"}, ["replay", "agent"])[0] == "replay"
    assert lr.choose({"app": "music"}, ["replay", "agent"])[0] == "agent"
    tally = LN.Tally().fit(_rows("rung", spec))
    assert tally.choose({"app": "outlook"}, ["replay", "agent"])[0] == tally.choose({"app": "music"}, ["replay", "agent"])[0]      # a tally cannot tell them apart


def test_a_learner_is_scored_on_logged_choices_without_repeating_any_test(tmp_path, monkeypatch):
    spec = [({}, "replay", True)] * 6 + [({}, "agent", False)] * 4 + [({}, "replay", True)] * 4
    res = LN.evaluate("tally", _rows("rung", spec), "rung")
    assert res["decided"] >= 5 and res["used"] <= res["n"] and res["estimate"] is not None
    assert {r["learner"] for r in LN.compare(_rows("rung", spec), "rung")} == set(LN.REGISTRY)
    monkeypatch.setattr(LN, "CONFIG", tmp_path / "learners.json")
    assert LN.selected() == {"model": "tally", "rung": "tally"}
    assert LN.select("model", "thompson") == {"model": "thompson", "rung": "tally"} and LN.selected()["model"] == "thompson"
    with pytest.raises(KeyError):
        LN.select("model", "nonesuch")


# ---- weight space
def _dump(seed, hidden=2):
    r = np.random.default_rng(seed)
    return {"hidden": hidden, "W1": r.normal(size=(4, hidden)).tolist(), "b1": r.normal(size=hidden).tolist(), "w2": r.normal(size=hidden).tolist()}


def test_saved_versions_can_be_averaged_smoothed_differenced_and_added_back():
    a, b, c = _dump(1), _dump(2), _dump(3)
    soup = W.average([a, b, c])
    assert np.allclose(soup["w2"], (np.array(a["w2"]) + np.array(b["w2"]) + np.array(c["w2"])) / 3)
    assert W.average([a, b], [3, 1])["b1"][0] == pytest.approx(0.75 * a["b1"][0] + 0.25 * b["b1"][0])
    assert W.ema(a, b, 0.0) == a and np.allclose(W.ema(a, b, 1.0)["W1"], b["W1"])
    d = W.delta(a, b)
    assert np.allclose(W.apply(a, d)["W1"], b["W1"]) and np.allclose(W.apply(b, d, -1.0)["W1"], a["W1"])       # add it back, take it away
    assert W.distance(a, a) == 0 and W.distance(a, b) == pytest.approx(W.norm(d))
    small = W.clip_delta(d, 0.5)
    assert W.norm(small) == pytest.approx(0.5) and W.clip_delta(d, 1e6) is d
    with pytest.raises(ValueError):
        W.average([a, _dump(4, hidden=3)])                                                  # different shapes cannot be mixed
    lin = {"hidden": 0, "w": [1.0, 2.0]}
    assert W.average([lin, {"hidden": 0, "w": [3.0, 4.0]}])["w"] == [2.0, 3.0]


def test_the_greedy_soup_keeps_a_version_only_if_the_held_out_score_does_not_drop():
    good1, good2 = {"hidden": 0, "w": [1.2, 0.8]}, {"hidden": 0, "w": [0.8, 1.2]}          # each is off in a different direction; their mean is exact
    bad = {"hidden": 0, "w": [-5.0, 9.0]}
    score = lambda d: -float(np.linalg.norm(np.array(d["w"]) - np.array([1.0, 1.0])))      # noqa: E731  (higher is better; the truth is [1, 1])
    out = W.greedy_soup([bad, good1, good2], score)
    assert out["used"] == 2 and out["of"] == 3 and out["score"] >= score(good1) - 1e-9


# ---- calibration
def test_an_overconfident_score_is_pulled_down_and_fitted_weights_need_enough_graded_rows():
    rng = random.Random(0)
    pairs = [(0.9, 1.0 if rng.random() < 0.6 else 0.0) for _ in range(200)]                 # says 90 %, is right 60 %
    a, b = CAL.platt_fit(pairs)
    assert CAL.platt_apply(a, b, 0.9) < 0.75 and CAL.ece(pairs) > 0.25
    calibrated = [(CAL.platt_apply(a, b, p), y) for p, y in pairs]
    assert CAL.ece(calibrated) < 0.1 and CAL.brier(calibrated) < CAL.brier(pairs)
    keys = ["windows_confirms", "agent_done", "screen_changed"]
    cur = lambda m: 0.5                                                                      # noqa: E731
    assert CAL.fit_marker_weights([({"agent_done": True}, 1.0)] * 5, keys, cur) == {"ready": False, "needs": 30, "have": 5}
    graded = []
    for i in range(60):
        win = i % 2 == 0
        graded.append(({"windows_confirms": win, "agent_done": True}, 1.0 if win else 0.0))   # Windows confirming is what predicts "right"
    got = CAL.fit_marker_weights(graded, keys, cur)
    assert got["ready"] and got["weights"]["windows_confirms"] > got["weights"]["agent_done"] and got["better"] and got["brier_fitted"] < got["brier_current"]


# ---- router kNN and support
def _graded_log(tmp_path, monkeypatch, pairs):
    log = tmp_path / "decisions.jsonl"
    rows = []
    for i, (text, chosen, ok, correct) in enumerate(pairs, 1):
        rows.append({"at": 1000.0 + i, "text": text, "bin": chosen})
        v = {"kind": "verdict", "at": 2000.0 + i, "of": 1000.0 + i, "ok": ok, "by": "teach"}
        if correct:
            v["correct"] = correct
        rows.append(v)
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(BIN, "LOG", log)
    monkeypatch.setattr(YS, "FILE", tmp_path / "settings.json")
    monkeypatch.setattr(YS, "_CACHE", {"at": 0.0, "data": {}, "file": None})


def test_every_graded_request_right_or_wrong_is_an_example_and_held_out_accuracy_is_measured(tmp_path, monkeypatch):
    pairs = []
    for w in ("outlook", "notepad", "apple music", "calculator", "edge", "word"):
        pairs.append((f"open {w}", "launch_app", True, None))
        pairs.append((f"please open {w} now", "conversation", False, "launch_app"))          # a WRONG with the right bin named
    for w in ("the weather", "a joke", "what you are", "my name", "the time", "your age"):
        pairs.append((f"tell me {w}", "conversation", True, None))
    _graded_log(tmp_path, monkeypatch, pairs)
    ex = RC.examples()
    assert len(ex) == 18 and {e["label"] for e in ex} == {"launch_app", "conversation"}
    res = RC.loo_accuracy(ex)
    assert res["ready"] and res["knn"] >= 0.9 and res["current"] == round(12 / 18, 3) and res["better"]
    assert RC.loo_accuracy(ex[:3]) == {"n": 3, "ready": False, "needs": 5}
    knn = RC.KNN(3).fit([(e["text"], e["label"]) for e in ex])
    assert knn.predict("open firefox please")[0] == "launch_app" and knn.predict("tell me a story")[0] == "conversation"


def test_a_screen_unlike_anything_trained_on_is_not_covered():
    rng = np.random.default_rng(0)
    base = rng.normal(size=8)
    train = np.stack([base + rng.normal(scale=0.1, size=8) for _ in range(20)])
    sup = CON.Support(0.8).fit(train)
    assert sup.covered(base) and not sup.covered(-base) and sup.coverage(train) == 1.0 and CON.Support().nearest(base) == 0.0


# ---- TEACH: the unsure ones first
def test_teach_offers_unsure_decisions_before_obvious_ones(tmp_path, monkeypatch):
    log = tmp_path / "decisions.jsonl"
    rows = [{"at": 1.0, "text": "obvious", "bin": "launch_app", "confidence": 0.99, "by": "rules"},
            {"at": 2.0, "text": "near the cut-off", "bin": "app_task", "confidence": 0.76, "by": "rules"},
            {"at": 3.0, "text": "tev was asked", "bin": "conversation", "confidence": 0.5, "by": "model", "asked": [{"answer": "x"}]},
            {"at": 4.0, "text": "my own earlier fix", "bin": "launch_app", "confidence": 0.9, "by": "you"}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(BIN, "LOG", log)
    monkeypatch.setattr(YS, "FILE", tmp_path / "settings.json")
    monkeypatch.setattr(YS, "_CACHE", {"at": 0.0, "data": {}, "file": None})

    async def go():
        app = web.Application()
        app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/learning/teach")).json()
            assert [i["text"] for i in j["items"]] == ["near the cut-off", "tev was asked", "obvious", "my own earlier fix"] and "most useful first" in j["order"]
    asyncio.run(go())


# ---- the API that lists the learners
def test_the_learners_api_lists_them_and_remembers_the_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(LN, "CONFIG", tmp_path / "learners.json")
    from hub.features import learning as LRN
    monkeypatch.setattr(LRN, "events", lambda *a, **k: _rows("model", [({}, "gemma", True)] * 4 + [({}, "qwen", False)] * 4))

    async def go():
        app = web.Application()
        app.add_routes(FIT.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/yard/learners")).json()
            assert j["selected"]["model"] == "tally" and {r["learner"] for r in j["heads"]["model"]} == set(LN.REGISTRY)
            assert (await c.post("/api/yard/learners", json={"head": "rung", "learner": "linucb"})).status == 200
            assert (await (await c.get("/api/yard/learners")).json())["selected"]["rung"] == "linucb"
            assert (await c.post("/api/yard/learners", json={"head": "rung", "learner": "nonesuch"})).status == 400
    asyncio.run(go())
