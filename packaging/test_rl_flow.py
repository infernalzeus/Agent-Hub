"""Round 5 of the learning layer, CPU only, small made-up cases and short pretend-app sessions; no GPU, no model, no Ollama, nothing from this PC's real data.

  knobs        every adjustable number has a range, is clamped, is saved, can be reset, and really changes what reads it; the defaults change nothing
  events/flow  a session reports each step to the canvas; every arrow it names exists on the canvas file that Obsidian opens
  session      a short real yard session emits the stream, saves a version that names its method, and honours replay and hindsight
  memory       the replay buffer favours the unsure; hindsight keeps the action and changes the goal; approved live tasks (never attested ones) can be imitated
  methods      Bayesian optimisation, sampling presets with a label-free reward, the router classifier, the re-rank and the support check
  small items  forbidden controls can be hidden, the mission reward puts your approval first, trusting a routine is logged, live shadow lines join their task
"""
import asyncio
import json
import random
import sqlite3

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import desktop_agent as DA
from hub.features import learning as LRN
from hub.features import pc_control as PC
from hub.yard import bo, conservative as CON, demos as DM, events as EV, evidence as EVI, fitness as FIT, flow, knobs as K, learner as L, memory as MEM
from hub.yard import practice as P, presets, route_classifier as RC, search as S, settings as YS
from hub.yard.world import APP, FAMILIES, World


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def state(tmp_path, monkeypatch):
    d = tmp_path / "yard"
    monkeypatch.setattr(YS, "FILE", d / "settings.json")
    monkeypatch.setattr(YS, "_CACHE", {"at": 0.0, "data": {}, "file": None})
    monkeypatch.setattr(EVI, "DIR", d)
    monkeypatch.setattr(EVI, "FILE", d / "evidence.jsonl")
    monkeypatch.setattr(EVI, "SHOTS", d / "evidence")
    monkeypatch.setattr(EVI, "LABELS", d / "evidence_labels.json")
    monkeypatch.setattr(MEM, "MEMORY_STEPS", d / "memory_steps.jsonl")
    monkeypatch.setattr(FIT, "DIR", d / "frozen")
    monkeypatch.setattr(FIT, "STATE", tmp_path)
    monkeypatch.setattr(LRN, "CHOICES", tmp_path / "choices.jsonl")
    monkeypatch.setattr(P, "REPORT", d / "report.json")
    monkeypatch.setattr(P, "POLICY", d / "policy.json")
    LRN._close()
    EV.clear()
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)
    monkeypatch.delenv("HUB_LEARNING_LOG", raising=False)
    yield d
    LRN._close()


# ---------------------------------------------------------------- knobs
def test_every_knob_has_a_range_is_clamped_saved_reset_and_the_defaults_change_nothing():
    assert K.FAMILIES == FAMILIES and len(K.SPEC) >= 60
    assert (K.get("step_cost"), K.get("invalid_cost"), K.get("false_done_cost"), K.get("win")) == (0.02, 0.1, 0.5, 1.0)       # what practice.py hard-coded
    assert (K.get("lr_actor"), K.get("gamma"), K.get("entropy_beta"), K.get("min_frozen"), K.get("shadow_n"), K.get("conf_cap")) == (0.05, 0.95, 0.02, 50, 30, 0.75)
    assert all(s["default"] is not None for s in K.SPEC.values())
    out = K.set_many({"episodes": 100000, "gamma": 0.1, "hindsight": True, "vocab": "train"})
    assert out["episodes"] == 3000 and out["gamma"] == 0.5 and out["hindsight"] is True and out["vocab"] == "train"          # clamped to the range
    assert json.loads(K.FILE.read_text())["episodes"] == 3000
    for bad in ({"episodes": "many"}, {"hindsight": 1}, {"vocab": "huge"}, {"nonsense": 1}):
        with pytest.raises((ValueError, KeyError)):
            K.set_many(bad)
    assert K.reset("episodes")["episodes"] == 1500 and K.get("hindsight") is True and K.reset()["hindsight"] is False
    K.set_many({f"family_{f}": False for f in FAMILIES})
    assert K.families() == list(FAMILIES)                                                    # never an empty set


def test_a_changed_knob_really_changes_what_reads_it():
    ep = {"trace": [{"do": "click"}, {"do": "invalid"}, {"do": "done"}], "agent_said_ok": True, "success": True}
    base = P.rewards(ep)
    K.set_many({"step_cost": 0.1, "win": 3.0})
    assert P.rewards(ep)[0] == pytest.approx(-0.1) and P.rewards(ep)[-1] == pytest.approx(base[-1] - 0.08 + 2.0)
    assert EVI.confidence({"windows_confirms": True})["p"] == 0.85
    K.set_many({"w_windows": 0.5, "conf_cap": 0.6})
    assert EVI.confidence({"windows_confirms": True})["p"] == 0.5 and EVI.confidence({"agent_done": True, "routine_clean": True, "screen_changed": True})["p"] == 0.6
    from hub.yard import gate, ope
    assert gate.evaluate({"k": 30, "n": 30}, {"p": 0.5})["steps"][0]["state"] == "failed"
    K.set_many({"min_frozen": 10})
    assert gate.evaluate({"k": 30, "n": 30}, {"p": 0.5})["steps"][0]["state"] == "passed"
    rows = [{"chosen": "a", "p": 0.01, "ok": True}] + [{"chosen": "a", "p": 1.0, "ok": False}] * 9
    wide = ope.snips(rows, lambda r: 1.0)["ess"]
    K.set_many({"ope_cap": 2.0})
    assert ope.snips(rows, lambda r: 1.0)["ess"] > wide                                       # a lower cap lets the heavy row matter less
    assert L.Learner(hidden=0).lr == 0.05
    K.set_many({"lr_actor": 0.2, "gamma": 0.8})
    lr = L.Learner(hidden=0)
    assert lr.lr == 0.2 and lr.gamma == 0.8 and L.Learner(hidden=4).lr == pytest.approx(0.6)


def test_the_knob_api_lists_sets_resets_and_names_what_cannot_be_changed():
    async def go():
        app = web.Application()
        app.add_routes(K.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/yard/knobs")).json()
            assert {k["group"] for k in j["knobs"]} >= {"Yard session", "Rewards", "Gate", "Task confidence", "Safety (tighten only)"}
            assert {f["name"] for f in j["fixed"]} >= {"Never-press list", "Taint gate", "Confirm before acting"} and all(not k["changed"] for k in j["knobs"])
            j = await (await c.post("/api/yard/knobs", json={"win": 2.5})).json()
            assert next(k for k in j["knobs"] if k["name"] == "win") ["changed"] is True
            assert (await c.post("/api/yard/knobs", json={"win": "big"})).status == 400 and (await c.post("/api/yard/knobs", json={"zzz": 1})).status == 400
            j = await (await c.post("/api/yard/knobs/reset", json={"name": "win"})).json()
            assert next(k for k in j["knobs"] if k["name"] == "win")["value"] == 1.0
    _run(go())


# ---------------------------------------------------------------- events and the canvas
def test_events_are_numbered_and_only_the_newest_come_back():
    EV.clear()
    a = EV.emit("env", "episode", "x", 3, edge="soft>env")
    b = EV.emit("rew", "reward", "y", -0.5, edge="env>rew", total=1)
    assert b == a + 1 and [e["node"] for e in EV.since(a)] == ["rew"] and EV.since(b) == [] and EV.since(0)[0]["edge"] == "soft>env" and EV.since(0)[-1]["total"] == 1
    for i in range(900):
        EV.emit("env", "episode", str(i))
    assert len(EV.since(0, limit=10000)) == 800


def test_the_canvas_is_valid_json_canvas_and_every_arrow_a_session_names_exists_on_it(tmp_path):
    c = flow.canvas()
    text = [n for n in c["nodes"] if n["type"] == "text"]
    ids = {n["id"] for n in text}
    assert len(ids) == 22 and all({"x", "y", "width", "height", "text", "color"} <= set(n) for n in text)
    groups = [n for n in c["nodes"] if n["type"] == "group"]
    assert len(groups) == len(flow.GROUPS) and all(n["label"] for n in groups)                              # Obsidian draws the frames too
    assert {m for _, _, ms in flow.GROUPS for m in ms} == ids and sum(len(ms) for _, _, ms in flow.GROUPS) == 22      # every block is in exactly one frame
    assert all(e["fromNode"] in ids and e["toNode"] in ids and e["fromSide"] in ("left", "right", "top", "bottom") for e in c["edges"])
    edge_ids = {e["id"] for e in c["edges"]}
    src = open(P.__file__, encoding="utf-8").read()
    import re
    named = set(re.findall(r'edge="([a-z]+>[a-z]+)"', src)) | {"live>mem", "mem>upd", "demos>gate", "gate>ver", "fit>gate", "ver>safety", "safety>gate"}
    assert named <= edge_ids, named - edge_ids                                              # a session never lights an arrow that is not on the canvas
    assert {e["node"] for e in []} <= ids
    from pathlib import Path
    shipped = json.loads((Path(P.__file__).parent / "learning.canvas").read_text(encoding="utf-8"))
    assert shipped == c, "hub/yard/learning.canvas is out of date: run  python -m hub.yard.flow hub/yard/learning.canvas"
    flow.write(str(tmp_path / "learning.canvas"))
    again = json.loads((tmp_path / "learning.canvas").read_text(encoding="utf-8"))
    assert again == c and all(n["text"].startswith("## ") for n in again["nodes"] if n["type"] == "text")

    async def go():
        app = web.Application()
        app.add_routes(flow.routes)
        async with TestClient(TestServer(app)) as cl:
            j = await (await cl.get("/api/yard/canvas")).json()
            actor = next(n for n in j["nodes"] if n["id"] == "actor")
            assert actor["title"].startswith("Actor") and "weights" in actor["info"] and actor["state"] in ("tested", "built", "user", "todo", "now")
    _run(go())


# ---------------------------------------------------------------- a short real session
def _small():
    K.set_many({"episodes": 100, "eval_per_cell": 4, "family_direct": True, "family_modal": True, **{f"family_{f}": False for f in FAMILIES if f not in ("direct", "modal")}})


def test_a_short_session_reports_each_step_saves_a_version_that_names_its_method_and_uses_only_the_chosen_layouts(state):
    _small()
    K.set_many({"replay_every": 20, "replay_batch": 3, "hindsight": True, "hidden_units": 8})
    rep = P.practice(write=True)
    assert rep["layouts"] == ["direct", "modal"] and set(rep["table"]["learned, linear"]) == {"direct", "modal"} and rep["hidden_units"] == 8 and rep["episodes"] == 100
    assert rep["methods"]["hidden16"].endswith("8 tanh units") and rep["knobs"]["hindsight"] is True
    kinds = {(e["node"], e["kind"]) for e in EV.since(0, limit=5000)}
    assert {("enc", "ready"), ("env", "episode"), ("rew", "reward"), ("crit", "advantage"), ("upd", "update"), ("actor", "weights"), ("fit", "evaluated"),
            ("repl", "replay"), ("ver", "saved"), ("gate", "decided"), ("safety", "replayed")} <= kinds, kinds
    assert rep["safety"]["screens"] == 60 and rep["safety"]["breaches"] >= 0
    upd = [e for e in EV.since(0, limit=5000) if e["kind"] == "update"]
    assert upd and all(e["value"] >= 0 for e in upd) and any(e["value"] > 0 for e in upd) and all(e["total"] > 0 for e in upd)       # weights moved, and by how much
    v = json.loads((state / "versions" / "v1.json").read_text(encoding="utf-8"))
    assert v["meta"]["methods"]["linear"].startswith("advantage actor-critic") and (state / "policy.json").exists()
    second = P.practice(write=True)                                                          # a warm start continues from the saved learner
    assert second["warm_from"] == 1


def test_a_session_does_not_save_when_nothing_is_asked_to_be_written_and_stop_says_so(state):
    _small()
    P.CONTROL["stop"] = False
    rep = P.practice(write=False)
    assert "saved" not in rep and not (state / "versions").exists()


# ---------------------------------------------------------------- memory: replay, hindsight, approved live tasks
def test_replay_favours_the_episodes_the_learner_was_unsure_about():
    buf = MEM.ReplayBuffer(50, "uncertainty")
    for i in range(20):
        buf.add([{"p": [0.9, 0.1]}], [0.0], MEM.surprise([{"p": [0.97, 0.03]}]))
    sure = len(buf)
    for i in range(5):
        buf.add([{"p": [0.5, 0.5]}], [1.0], MEM.surprise([{"p": [0.5, 0.5]}]))
    rng = np.random.default_rng(0)
    picked = [rw[0] for _ in range(60) for _, rw in buf.sample(2, rng)]
    assert sum(1 for x in picked if x == 1.0) / len(picked) > 5 / (sure + 5) * 2            # the unsure ones are drawn far more than their share
    assert MEM.surprise([{"p": [0.5, 0.5]}]) == pytest.approx(1.0) and MEM.surprise([{"p": [1.0, 0.0]}]) < 0.01
    uni = MEM.ReplayBuffer(50, "uniform")
    uni.add([{"p": [0.5, 0.5]}], [0.0], 1.0)
    assert len(uni.sample(5, rng)) == 1


def _prompt(seed=1, family="direct"):
    w = World(family, seed)
    nodes = _run(w.tree())
    shown = DA.controls(nodes, APP, w.goal)
    return w, shown, DA.brief(w.goal, APP, shown, [], [], 0)


def test_hindsight_keeps_the_action_and_changes_only_the_goal_words():
    w, shown, prompt = _prompt()
    lr = L.Learner(hidden=0)
    pol = lr.policy(True)
    _run(pol(DA._SYSTEM, prompt))
    rec = pol.records[0]
    other = next(n for n in w.items if n != w.target)
    new = MEM.relabel(lr, pol.records, f"play the {other} playlist")
    assert len(new) == 1 and new[0]["a"] == rec["a"] and new[0]["X"].shape == rec["X"].shape
    assert not np.allclose(new[0]["X"], rec["X"])                                            # the goal words are in the features, so they changed
    assert MEM.relabel(lr, [{"a": 0, "p": [1.0]}], "x") == []                                # no prompt kept: nothing to rebuild


def test_approved_live_tasks_can_be_imitated_and_attested_or_wrong_ones_never_are(state):
    YS.update({"shadow": True})
    w, shown, prompt = _prompt(3)
    press = next(c for c in shown if c["node"]["name"] == w.target) if any(c["node"]["name"] == w.target for c in shown) else shown[0]
    now = 1_000_000.0
    steps = [{"at": now - 5, "goal": w.goal, "app": "pretend", "step": 0, "prompt": prompt, "live": {"do": "click", "id": press["id"]}}]
    MEM.MEMORY_STEPS.parent.mkdir(parents=True, exist_ok=True)
    MEM.MEMORY_STEPS.write_text("".join(json.dumps(s) + "\n" for s in steps), encoding="utf-8")

    def rec(goal, markers, routine=None, ok=True, at=now):
        rid = EVI.record("agent" if not routine else "saved routine", goal, "app", ok, markers, 3.0, routine=routine)
        rows = EVI._rows()
        for r in rows:
            if r["id"] == rid:
                r["at"] = at
        EVI.FILE.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return rid
    good = rec(w.goal, {"windows_confirms": True, "agent_done": True, "screen_changed": True})
    assert [d["task"] for d in MEM.live_dataset()] == [good] and MEM.live_dataset()[0]["name"].startswith(press["node"]["name"])
    EVI.LABELS.write_text(json.dumps({good: {"grade": "wrong", "at": 1.0}}), encoding="utf-8")
    assert MEM.live_dataset() == []                                                         # you said it was wrong
    EVI.LABELS.write_text(json.dumps({good: {"grade": "right", "at": 1.0}}), encoding="utf-8")
    data = MEM.live_dataset()
    assert len(data) == 1
    lr = L.Learner(hidden=0)
    first = lr.imitate(data)
    for _ in range(6):
        last = lr.imitate(data)
    assert last > first and last > 1 / max(2, len(shown) + 4)                                # it comes to give the approved press more of the probability
    # an attested routine's task is never used
    YS.golden_path = None
    gfile = YS._golden_file()
    gfile.write_text(json.dumps({"at": 1, "routines": [{"id": "r-x", "title": "X"}]}), encoding="utf-8")
    att = rec(w.goal, {"windows_confirms": True}, routine="r-x")
    assert EVI._rows()[-1]["attested"] is True and all(d["task"] != att for d in MEM.live_dataset())


def test_a_session_can_imitate_approved_live_steps_first(state):
    _small()
    YS.update({"shadow": True})
    w, shown, prompt = _prompt(4)
    now = __import__("time").time()
    MEM.MEMORY_STEPS.parent.mkdir(parents=True, exist_ok=True)
    MEM.MEMORY_STEPS.write_text(json.dumps({"at": now - 2, "goal": w.goal, "app": "p", "step": 0, "prompt": prompt, "live": {"do": "click", "id": shown[0]["id"]}}) + "\n", encoding="utf-8")
    rid = EVI.record("agent", w.goal, "app", True, {"windows_confirms": True, "agent_done": True}, 3.0)
    EVI.LABELS.write_text(json.dumps({rid: {"grade": "right", "at": 1.0}}), encoding="utf-8")
    K.set_many({"memory_epochs": 2})
    P.practice(write=False)
    ev = EV.since(0, limit=5000)
    assert any(e["node"] == "mem" and e["kind"] == "imitated" and "1 approved live steps" in e["text"] for e in ev)


# ---------------------------------------------------------------- the other methods
def test_bayesian_optimisation_beats_random_search_on_a_small_noisy_problem():
    space = {"a": (0, 1), "b": (0, 1)}
    peak = (0.7, 0.2)
    exact = lambda c: -((c["a"] - peak[0]) ** 2 + (c["b"] - peak[1]) ** 2)               # noqa: E731
    got_bo, got_rnd = [], []
    for seed in range(8):
        rng = random.Random(seed + 100)
        got_bo.append(exact(bo.bayes_opt(lambda c: exact(c) + rng.gauss(0, 0.01), space, tries=25, seed=seed)["candidate"]))
        rng = random.Random(seed + 100)
        got_rnd.append(exact(S.random_search(lambda c: exact(c) + rng.gauss(0, 0.01), space, tries=25, seed=seed)["candidate"]))
    assert np.mean(got_bo) > np.mean(got_rnd) and np.mean(got_bo) > -0.01
    first = bo.bayes_opt(exact, space, tries=12, seed=3)
    assert first["tries"] == 12 and first == bo.bayes_opt(exact, space, tries=12, seed=3)


def test_sampling_presets_and_the_reward_that_needs_no_label():
    assert set(presets.PRESETS) == {"precise", "balanced", "varied", "terse", "long"} and presets.PRESETS["precise"]["temperature"] == 0.0
    assert presets.repeat_ratio("the cat sat on the mat the cat sat on the mat") > 0.2 and presets.repeat_ratio("a b c d e f g h") == 0.0
    good = presets.label_free_reward('{"a": 1}', "stop", 100, 2048, True, expect_json=True)
    bad = presets.label_free_reward("loop loop loop loop loop loop loop loop loop loop", "length", 2048, 2048, False, expect_json=True)
    assert good["reward"] > bad["reward"] and good["parts"]["valid"] > 0 and bad["parts"]["valid"] == 0 and bad["parts"]["not_cut_off"] == 0
    K.set_many({"rw_checks": 0.0})
    assert presets.label_free_reward("x y z w", "stop", 10, 2048, True)["parts"]["checks"] == 0.0
    calls = [{"role": "coder", "preset": "precise", "reward": 0.9, "at": i} for i in range(6)] + [{"role": "coder", "preset": "varied", "reward": 0.2, "at": 10 + i} for i in range(6)]
    from hub.yard import learners as LN
    rows = presets.rows_for_tally(calls, "coder")
    assert LN.Tally().fit(rows).choose({}, ["precise", "varied"])[0] == "precise" and presets.rows_for_tally(calls, "tester") == []


def test_the_router_classifier_learns_from_all_graded_requests_by_gradient_descent():
    bins = {"launch_app": ["open", "start", "launch", "run"], "conversation": ["tell", "joke", "weather", "story"], "hub_command": ["show", "missions", "graph", "status"]}
    rng = random.Random(1)
    ex = []
    for lab, words in bins.items():
        for _ in range(14):
            ex.append({"text": f"please {rng.choice(words)} the {rng.choice(words)} thing", "label": lab, "rules_right": rng.random() < 0.5})
    res = RC.kfold_accuracy(ex)
    assert res["ready"] and res["classifier"] >= 0.9 and res["classifier"] > res["current"]
    m = RC.Softmax().fit([e["text"] for e in ex], [e["label"] for e in ex])
    assert m.predict("launch the run thing")[0] == "launch_app" and m.predict("tell the story thing")[0] == "conversation"
    assert RC.kfold_accuracy(ex[:6]) == {"n": 6, "ready": False, "needs": 10}
    K.set_many({"clf_epochs": 20})
    assert RC.Softmax().epochs == 20


def test_the_rerank_keeps_the_model_unless_the_learned_head_has_seen_the_situation():
    model = {"a": 0.6, "b": 0.5, "c": 0.1}
    afford = {"a": 0.2, "b": 0.9, "c": 0.9}
    pick, scores = CON.rerank(model, afford)
    assert pick == "b" and scores["b"] == pytest.approx(0.45)                               # learned feasibility moved b above a
    pick2, _ = CON.rerank(model, afford, covered={"a": False, "b": False, "c": False})
    assert pick2 == "a"                                                                     # nothing like it seen: the model's own order stands


# ---------------------------------------------------------------- attested routines as a check
def test_the_agreement_with_attested_routines_is_a_check_on_pretend_screens_and_never_trains():
    rts = [{"id": "r1", "title": "play the focus playlist", "steps": [{"role": "list item", "name": "ADHD Focus"}, {"role": "button", "name": "Play"}]},
           {"id": "r2", "title": "empty", "steps": []}]
    lr = L.Learner(hidden=0)
    before = lr.vec().copy()
    got = DM.agreement(lr, rts)
    assert got["routines"] == 1 and got["steps"] == 2 and 0 <= got["agree"] <= 2 and got["rate"] == got["agree"] / 2 and got["rows"][0]["id"] == "r1"
    assert np.array_equal(lr.vec(), before)                                                 # measuring changes nothing in the learner
    assert DM.agreement(lr, [])["rate"] is None


# ---------------------------------------------------------------- the small items
def test_forbidden_controls_can_be_hidden_from_the_agent_and_that_only_tightens():
    nodes = [{"window": APP, "control": "window", "name": APP, "parent": None, "flags": ""},
             {"window": APP, "control": "button", "name": "Play", "parent": 0, "flags": "", "x": 10, "y": 10, "clickable": True},
             {"window": APP, "control": "button", "name": "Delete playlist", "parent": 0, "flags": "", "x": 10, "y": 40, "clickable": True}]
    names = lambda: {c["node"]["name"] for c in DA.controls(nodes, APP, "play it")}           # noqa: E731
    assert names() == {"Play", "Delete playlist"}                                             # today: listed, refused when pressed
    K.set_many({"hide_forbidden": True})
    assert names() == {"Play"} and PC.never_press("Delete playlist")


def test_a_mission_is_rewarded_by_your_approval_first_and_by_the_checks_second(state, monkeypatch):
    from types import SimpleNamespace
    from hub.agent_knowledge import model_stats as MS
    from hub.features import missions as M
    ms = {k: SimpleNamespace(id=k, brief="b", project_name="p", status=s, created=float(i), model="gemma", agent="a", verify={"ok": ok})
          for i, (k, s, ok) in enumerate([("a", "applied", False), ("b", "discarded", True), ("c", "awaiting_review", True), ("d", "awaiting_review", False)], 1)}
    monkeypatch.setattr(M, "S", SimpleNamespace(m=ms))
    monkeypatch.setattr(LRN, "MISSION_LABELS", state.parent / "labels.json")
    monkeypatch.setattr(MS, "OUTCOMES", state.parent / "outcomes.json")
    for k, ok in (("a", False), ("b", True), ("c", True), ("d", False)):
        MS.record(["gemma"], ok, 5, 100, k)
    got = {e["mission"]: (e["reward"], e["reward_by"]) for e in LRN._model_events()}
    assert got == {"a": (1.0, "you"), "b": (0.0, "you"), "c": (0.7, "checks"), "d": (0.2, "checks")}


def test_trusting_a_candidate_routine_is_written_to_the_choice_log(state, monkeypatch):
    YS.update({"learning": True})
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE pc_routines (id TEXT, title TEXT, status TEXT, updated REAL)")
    db.execute("INSERT INTO pc_routines VALUES ('r9', 'Open Notepad', 'candidate', 0)")
    monkeypatch.setattr(PC, "_db", lambda: db)

    async def go():
        app = web.Application()
        app.add_routes(PC.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/pc/routines/r9/approve")).status == 200
            assert (await c.post("/api/pc/routines/nope/approve")).status == 404
    _run(go())
    rows = [json.loads(l) for l in LRN.CHOICES.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["kind"] == "trust" and rows[-1]["routine"] == "r9" and rows[-1]["by"] == "you" and rows[-1]["ok"] is True
    assert "trust" in LRN.KINDS and "trust" in LRN.status()["per_kind"]


def test_live_shadow_lines_are_joined_to_the_task_they_belong_to_and_the_doctor_can_see_the_layer(state, tmp_path):
    YS.update({"shadow": True})
    rid = EVI.record("agent", "play the focus playlist", "app", True, {"windows_confirms": True, "agent_done": True}, 12.0)
    at = EVI._rows()[-1]["at"]
    (tmp_path / "data" / "yard").mkdir(parents=True, exist_ok=True)
    lines = [{"kind": "step", "at": at - 8, "goal": "play the focus playlist", "agree": True}, {"kind": "step", "at": at - 4, "goal": "play the focus playlist", "agree": False},
             {"kind": "step", "at": at - 3, "goal": "something else", "agree": True}, {"kind": "step", "at": at - 5000, "goal": "play the focus playlist", "agree": True}]
    (tmp_path / "data" / "yard" / "shadow.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    got = FIT.live_shadow()
    assert got["tasks"] == 1 and got["in_good_tasks"]["n"] == 2 and got["in_good_tasks"]["k"] == 1 and got["in_other_tasks"]["n"] == 0
    from hub.features import diagnose
    assert diagnose._learning()["installed"] is True and diagnose._learning()["tasks_kept"] == 1 and diagnose._learning()["shadow"] is True
    assert rid


# ---------------------------------------------------------------- the yard's view of candidate routines, and the safety replay
def _routine_db(monkeypatch, rows, steps):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE pc_routines (id TEXT, title TEXT, status TEXT, successes INT, failures INT, updated REAL)")
    db.execute("CREATE TABLE pc_steps (routine_id TEXT, ordinal INT, tool TEXT, args_json TEXT, target_json TEXT)")
    db.executemany("INSERT INTO pc_routines VALUES (?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO pc_steps VALUES (?,?,?,?,?)", steps)
    monkeypatch.setattr(PC, "_db", lambda: db)


def test_the_yard_says_which_candidate_routines_look_ready_and_why_the_others_do_not(state, monkeypatch):
    from hub.yard import candidates as CD
    step = lambda rid, i, name, role="button": (rid, i, "Click", "{}", json.dumps({"name": name, "control": role}))     # noqa: E731
    _routine_db(monkeypatch, [("good", "play the focus list", "candidate", 3, 0, 5.0), ("risky", "tidy up", "candidate", 3, 0, 4.0), ("new", "open mail", "candidate", 1, 0, 3.0),
                              ("flaky", "do a thing", "candidate", 4, 2, 2.0), ("done", "trusted one", "trusted", 5, 0, 1.0), ("bare", "launch", "candidate", 3, 0, 0.5)],
               [step("good", 0, "ADHD Focus", "list item"), step("good", 1, "Play"), step("risky", 0, "Delete playlist"), step("new", 0, "Inbox"), step("flaky", 0, "Play")])
    monkeypatch.setattr(CD, "_learner", lambda: None)
    got = {c["id"]: c for c in CD.candidates()}
    assert set(got) == {"good", "risky", "new", "flaky", "bare"}                            # trusted ones are not candidates
    assert got["good"]["ready"] and got["good"]["agree"] is None and got["good"]["reasons"] == []
    assert not got["risky"]["ready"] and got["risky"]["forbidden"] == ["Delete playlist"] and "forbidden control" in got["risky"]["reasons"][0]
    assert any("needs 2 clean" in r for r in got["new"]["reasons"]) and any("failed 2" in r for r in got["flaky"]["reasons"]) and any("no named controls" in r for r in got["bare"]["reasons"])
    lr = L.Learner(hidden=0)
    monkeypatch.setattr(CD, "_learner", lambda: lr)
    K.set_many({"candidate_agree": 1.0})
    with_lr = {c["id"]: c for c in CD.candidates()}
    assert with_lr["good"]["agree"] is not None and (with_lr["good"]["ready"] == (with_lr["good"]["agree"] >= 1.0))      # the learner's agreement now counts

    async def go():
        app = web.Application()
        app.add_routes(CD.routes)
        async with TestClient(TestServer(app)) as c:
            assert {x["id"] for x in (await (await c.get("/api/yard/candidates")).json())["candidates"]} == set(got)
    _run(go())


def test_the_safety_replay_counts_how_often_a_learner_picks_a_forbidden_control_and_the_api_says_when_there_is_no_learner(monkeypatch):
    from hub.yard import candidates as CD
    lr = L.Learner(hidden=0)
    res = CD.breaches(lr, 30)
    assert res["screens"] == 30 and 0 <= res["breaches"] <= 30 and res["forbidden_listed"] and all(PC.never_press(n) for n in res["forbidden_listed"])
    # a learner that loves anything on the never-press list is caught
    lr.actor.w = np.zeros_like(lr.actor.w)
    base = L.BASE
    for flag in range(L.NFLAG):
        lr.actor.w[flag * base + len(L.KINDS) + len(L.ROLES) + 1 + 6] = 5.0          # the "on the never-press list" feature, under every step flag
    assert CD.breaches(lr, 30)["breaches"] > 0
    monkeypatch.setattr(CD, "_learner", lambda: None)

    async def go(ready):
        app = web.Application()
        app.add_routes(CD.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/yard/safety")).json()
            assert j["ready"] is ready
            return j
    assert "needs" in _run(go(False))
    monkeypatch.setattr(CD, "_learner", lambda: L.Learner(hidden=0))
    assert _run(go(True))["screens"] == 200


def test_pressing_a_forbidden_control_in_practice_can_be_charged_and_is_free_by_default():
    ep = {"trace": [{"do": "click", "control": 'button "Delete playlist"'}, {"do": "click", "control": 'button "Play"'}], "agent_said_ok": False, "success": False}
    assert P.rewards(ep) == [-0.02, -0.02]
    K.set_many({"forbidden_cost": 1.0})
    assert P.rewards(ep) == [pytest.approx(-1.02), pytest.approx(-0.02)]


# ---------------------------------------------------------------- every setting belongs to a block, and each block can say what is inside it
def test_every_setting_belongs_to_exactly_one_block_and_each_block_has_an_inside_taken_from_the_code():
    used = sum(flow.NODE_KNOBS.values(), [])
    assert sorted(used) == sorted(set(used)) and set(used) == set(K.SPEC)                      # nothing is left over for a "more settings" bucket
    assert set(flow.NODE_KNOBS) == set(flow.NODES) and flow.OUTSIDE <= set(flow.NODES)
    a = flow.arch("actor")
    assert [l["size"] for l in a["layers"]][:1] == ["357"] and any(r["label"] == "learned numbers, hidden" and r["value"] == str(357 * 16 + 32) for r in a["rows"])
    K.set_many({"hidden_units": 8, "gamma": 0.9, "win": 2.0})
    assert any(r["value"] == str(357 * 8 + 16) for r in flow.arch("actor")["rows"]) and "0.9" in flow.arch("upd")["formula"][0] and "+ 2.0 when the target" in flow.arch("rew")["formula"][-1]
    assert flow.arch("enc")["layers"][-1]["size"] == "357" and flow.arch("crit")["layers"][0]["size"] == "11" and flow.arch("router")["layers"][1]["size"] == "512"
    for nid in flow.NODES:
        a = flow.arch(nid)
        assert a["layers"] or a["rows"] or a["formula"], nid                                     # no block is a black box

    async def go():
        app = web.Application()
        app.add_routes(flow.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/yard/canvas?compact=1")).json()
            assert len(j["nodes"]) == 22 and all("arch" in n and "knobs" in n and n["kind"] for n in j["nodes"]) and {n["id"] for n in j["nodes"] if n["outside"]} == flow.OUTSIDE
            assert all(n["width"] == 210 and n["height"] == 70 for n in j["nodes"]) and len(j["groups"]) == 5 and all(e["label"] and e["info"].startswith("What travels") for e in j["edges"])
    _run(go())


# ---------------------------------------------------------------- roll back, manual routine runs, the tev dataset
def test_a_saved_version_can_be_made_the_one_in_use_again_without_deleting_anything(state, monkeypatch):
    _small()
    P.practice(write=True)
    P.practice(write=True)
    from hub.yard import api, store
    monkeypatch.setattr(api, "REPORT", P.REPORT)
    assert store.current_version(P.POLICY) in (1, 2) and len(list((state / "versions").glob("v*.json"))) == 2
    assert store.restore(state, P.POLICY, 1) and store.current_version(P.POLICY) == 1 and not store.restore(state, P.POLICY, 99)
    assert len(list((state / "versions").glob("v*.json"))) == 2

    async def go():
        app = web.Application()
        app.add_routes(api.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/yard/rollback", json={"version": 2})).status == 200 and store.current_version(P.POLICY) == 2
            assert (await c.post("/api/yard/rollback", json={"version": 99})).status == 404 and (await c.post("/api/yard/rollback", json={})).status == 400
    _run(go())
    assert any(e["kind"] == "restored" for e in EV.since(0, limit=5000))


def test_a_routine_run_from_the_routines_tab_is_recorded_as_evidence_while_shadow_is_on(state, monkeypatch):
    YS.update({"shadow": True})
    _routine_db(monkeypatch, [("r1", "Open Notepad", "trusted", 3, 0, 1.0)], [])
    monkeypatch.setattr(EVI, "_grab_jpeg", lambda: b"jpeg")

    async def fake_run(rid, request="manual run"):
        return {"ok": True, "say": "ran"}
    monkeypatch.setattr(PC, "run_routine", fake_run)

    async def go():
        app = web.Application()
        app.add_routes(PC.routes)
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/pc/routines/r1/run")
            assert r.status == 200 and (await r.json())["ok"] is True
    _run(go())
    rows = EVI._rows()
    assert len(rows) == 1 and rows[0]["way"] == "manual routine" and rows[0]["goal"] == "Open Notepad" and rows[0]["routine"] == "r1" and rows[0]["pics"] == ["before", "after"]
    YS.update({"shadow": False})
    _run(go())
    assert len(EVI._rows()) == 1                                                             # shadow off: nothing new is kept


def test_the_tev_plan_says_how_many_graded_requests_exist_and_whether_this_pc_can_train(state, tmp_path, monkeypatch):
    from hub.features import binning as BIN
    from hub.yard import tev_dataset as TD
    monkeypatch.setattr(TD, "DIR", tmp_path / "tev")
    rows = []
    for i in range(30):
        rows += [{"at": 1000.0 + i, "text": f"open the number {i} app", "bin": "launch_app"}, {"kind": "verdict", "at": 2000.0 + i, "of": 1000.0 + i, "ok": i % 3 != 0, "correct": "app_task", "by": "teach"}]
    log = tmp_path / "utterance_decisions.jsonl"      # never the real log: this test once wrote 60 made-up rows into the user's own
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(BIN, "LOG", log)
    p = TD.plan()
    assert p["rows"] == 30 and p["train"] + p["held_out"] == 30 and p["held_out"] > 0 and p["enough"] is False and p["needed"] == 100
    assert "hardware" in p and "note" in p["hardware"] and "-(1/n) sum log p" in p["objective"]
    out = TD.export()
    assert out["train"] == p["train"] and (tmp_path / "tev" / "train.jsonl").exists() and (tmp_path / "tev" / "held_out.jsonl").exists()
    held = {json.loads(l)["text"] for l in (tmp_path / "tev" / "held_out.jsonl").read_text().splitlines()}
    train = {json.loads(l)["text"] for l in (tmp_path / "tev" / "train.jsonl").read_text().splitlines()}
    assert not (held & train)                                                                  # the held-out part is never trained on

    async def go():
        app = web.Application()
        app.add_routes(TD.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await (await c.get("/api/yard/tev")).json())["rows"] == 30
    _run(go())
