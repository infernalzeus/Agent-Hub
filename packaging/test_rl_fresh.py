"""EXPERIMENTAL learning layer, round 2: a FRESH START so checked routines are never training samples, skip and delete in TEACH that stay gone,
the held-out frozen set, the fitness report, the gate, the extra fields on a choice row, and the R button's click behaviour."""
import asyncio
import json
import sqlite3

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import binning as BIN
from hub.features import learning as LRN
from hub.yard import evidence as EV
from hub.yard import fitness as FIT
from hub.yard import gate as G
from hub.yard import settings as YS
from hub.yard import teach as T


@pytest.fixture()
def state(tmp_path, monkeypatch):
    d = tmp_path / "yard"
    monkeypatch.setattr(YS, "FILE", d / "settings.json")
    monkeypatch.setattr(YS, "_CACHE", {"at": 0.0, "data": {}, "file": None})
    monkeypatch.setattr(EV, "DIR", d)
    monkeypatch.setattr(EV, "FILE", d / "evidence.jsonl")
    monkeypatch.setattr(EV, "SHOTS", d / "evidence")
    monkeypatch.setattr(EV, "LABELS", d / "evidence_labels.json")
    monkeypatch.setattr(FIT, "DIR", d / "frozen")
    monkeypatch.setattr(FIT, "STATE", tmp_path)                                    # never this PC's real report
    from hub.yard import shadow as SH
    monkeypatch.setattr(SH, "POLICY", d / "policy.json")                           # nor its real learner
    SH._CACHE.update(mtime=None, learner=None)
    monkeypatch.setattr(LRN, "CHOICES", tmp_path / "choices.jsonl")
    monkeypatch.setattr(LRN, "MISSION_LABELS", tmp_path / "mission_labels.json")
    monkeypatch.setattr(BIN, "LOG", tmp_path / "decisions.jsonl")
    LRN._close()
    from types import SimpleNamespace
    from hub.agent_knowledge import model_stats as MS
    from hub.features import missions as M
    monkeypatch.setattr(MS, "OUTCOMES", tmp_path / "outcomes.json")           # never this PC's real mission history
    monkeypatch.setattr(M, "S", SimpleNamespace(m={}))
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)
    monkeypatch.delenv("HUB_LEARNING_LOG", raising=False)
    # a routine store with two trusted routines and one candidate, instead of this PC's real one
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE pc_routines (id TEXT, title TEXT, status TEXT)")
    db.executemany("INSERT INTO pc_routines VALUES (?,?,?)", [("r-outlook", "Open Outlook", "trusted"), ("r-notepad", "Open Notepad", "trusted"), ("r-new", "A new one", "candidate")])
    from hub.features import pc_control as PC
    monkeypatch.setattr(PC, "_db", lambda: db)
    yield d
    LRN._close()


def _decisions(tmp_path_log, rows):
    tmp_path_log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _run(coro):
    return asyncio.run(coro)


# ---- the gate
def test_the_interval_is_wide_for_a_few_rows_and_narrow_for_many():
    lo, hi = G.wilson(8, 10)
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.95            # 8 of 10 could really be anything from about a half up to nearly always
    lo2, _ = G.wilson(80, 100)
    assert lo2 > 0.71 and G.wilson(0, 0) == (0.0, 1.0)


def test_the_gate_waits_fails_and_passes_in_order():
    waiting = G.evaluate({"k": 10, "n": 12}, {"p": 0.6})
    assert not waiting["promote"] and "frozen set" in waiting["failed"] and "beats the baseline" in waiting["waiting"]
    clean = G.evaluate({"k": 90, "n": 100}, {"p": 0.6}, breaches=0, shadow={"n": 40, "agree": 36}, user_yes=True)
    assert clean["promote"] and not clean["failed"] and not clean["waiting"]
    not_better = G.evaluate({"k": 62, "n": 100}, {"p": 0.6}, breaches=0, shadow={"n": 40, "agree": 40}, user_yes=True)
    assert not not_better["promote"] and not_better["failed"] == ["beats the baseline"]        # 62 % is not clearly above 60 %
    unsafe = G.evaluate({"k": 95, "n": 100}, {"p": 0.5}, breaches=1, shadow={"n": 40, "agree": 40}, user_yes=True)
    assert not unsafe["promote"] and unsafe["failed"] == ["safety set clean"]
    no = G.evaluate({"k": 95, "n": 100}, {"p": 0.5}, breaches=0, shadow={"n": 40, "agree": 40}, user_yes=False)
    assert not no["promote"] and no["failed"] == ["you say yes"]
    shy = G.evaluate({"k": 95, "n": 100}, {"p": 0.5}, breaches=0, shadow={"n": 10, "agree": 10}, user_yes=True)
    assert not shy["promote"] and shy["waiting"] == ["shadow"]


# ---- a choice row carries what a learner needs
def test_a_choice_row_keeps_its_chance_context_and_sampling_settings(state):
    YS.update({"learning": True})
    LRN.note("model", "desktop_task", "gemma", ["gemma", "qwen"], True, 900, p=1.0, ctx={"goal_words": 5, "music": True, "x": "y" * 90}, sampling={"temperature": 0, "num_predict": 140, "junk": {"a": 1}})
    row = json.loads(LRN.CHOICES.read_text(encoding="utf-8").splitlines()[-1])
    assert row["p"] == 1.0 and row["ctx"]["goal_words"] == 5 and row["ctx"]["music"] is True and len(row["ctx"]["x"]) == 40
    assert row["sampling"] == {"temperature": 0, "num_predict": 140}                      # only plain numbers, text and flags are kept


# ---- fresh start
def test_the_first_switch_on_is_a_fresh_start_that_sets_trusted_routines_apart(state):
    assert YS.fresh_since() == 0.0 and YS.golden() == {}
    YS.update({"shadow": True, "learning": True})
    assert YS.fresh_since() > 0
    assert {r["id"] for r in YS.golden()["routines"]} == {"r-outlook", "r-notepad"}          # the candidate is not attested
    first = YS.fresh_since()
    YS.update({"shadow": False})
    YS.update({"shadow": True})
    assert YS.fresh_since() == first                                                      # switching on again is not a new start
    assert YS.update({"fresh": True})["fresh_since"] >= first                               # but you can ask for one


def test_rows_from_before_the_fresh_start_are_kept_but_never_counted(state, tmp_path):
    now = 2_000_000_000.0
    _decisions(BIN.LOG, [{"at": 100.0, "text": "old one", "bin": "launch_app"}, {"kind": "verdict", "at": 101.0, "of": 100.0, "ok": True, "by": "teach"},
                         {"at": now + 5, "text": "new one", "bin": "launch_app"}, {"kind": "verdict", "at": now + 6, "of": now + 5, "ok": False, "by": "teach"}])
    assert len(LRN.events()) == 2 and LRN.status()["per_kind"]["route"]["labelled"] == 2          # no fresh start yet: everything counts
    YS.FILE.parent.mkdir(parents=True, exist_ok=True)
    YS.FILE.write_text(json.dumps({"experimental": True, "shadow": True, "since": now}), encoding="utf-8")
    YS._CACHE["at"] = 0.0
    st = LRN.status()
    assert [e["at"] for e in LRN.events()] == [now + 5] and st["per_kind"]["route"]["labelled"] == 1 and st["before_fresh_start"] == 1
    assert len(LRN.events(every=True)) == 2                                                # still there for audit


# ---- TEACH: skip stays gone, delete removes, nothing returns
def test_a_skipped_request_does_not_come_back_and_a_deleted_one_is_used_for_nothing(state):
    _decisions(BIN.LOG, [{"at": float(i), "text": f"sentence {i}", "bin": "conversation", "said": "x"} for i in range(1, 6)])

    async def go():
        app = web.Application()
        app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            assert [i["of"] for i in (await (await c.get("/api/learning/teach")).json())["items"]] == [5.0, 4.0, 3.0, 2.0, 1.0]
            assert (await c.post("/api/learning/teach", json={"of": 5.0, "grade": "skip"})).status == 200
            assert (await c.post("/api/learning/teach", json={"of": 4.0, "grade": "delete"})).status == 200
            for _ in range(2):                                                              # asking again, as a reload does
                j = await (await c.get("/api/learning/teach")).json()
                assert [i["of"] for i in j["items"]] == [3.0, 2.0, 1.0] and j["left"] == 3
    _run(go())
    rows = LRN.events()
    assert all(e["at"] != 4.0 for e in rows)                                                # deleted: not an event at all
    skipped = [e for e in rows if e["at"] == 5.0][0]
    assert skipped["ok"] is None and skipped["hidden"] == "skip"                            # skipped: never a label
    assert LRN.status()["per_kind"]["route"]["skipped"] == 1


def test_a_hidden_or_deleted_mission_leaves_the_list_and_its_model_events(state, monkeypatch):
    from types import SimpleNamespace
    from hub.agent_knowledge import model_stats as MS
    from hub.features import missions as M
    ms = {k: SimpleNamespace(id=k, brief=f"b {k}", project_name="p", status="awaiting_review", created=float(i), model="gemma", agent="a", verify={"ok": True}) for i, k in enumerate("abc", 1)}
    monkeypatch.setattr(M, "S", SimpleNamespace(m=ms))
    monkeypatch.setattr(MS, "OUTCOMES", state.parent / "outcomes.json")
    for k in "abc":
        MS.record(["gemma"], True, 5, 100, k)

    async def go():
        app = web.Application()
        app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            assert [m["id"] for m in (await (await c.get("/api/learning/teach/missions")).json())["missions"]] == ["c", "b", "a"]
            assert (await c.post("/api/learning/teach/mission", json={"id": "c", "grade": "skip"})).status == 200
            assert (await c.post("/api/learning/teach/mission", json={"id": "b", "grade": "delete"})).status == 200
            assert [m["id"] for m in (await (await c.get("/api/learning/teach/missions")).json())["missions"]] == ["a"]
    _run(go())
    assert sorted(e["mission"] for e in LRN._model_events()) == ["a", "c"]                    # b was deleted; c was only hidden


# ---- attested routines are checks, never training samples
def test_a_task_from_an_attested_routine_is_flagged_and_left_out_of_the_confidence_fit(state):
    YS.update({"shadow": True})
    old = EV.record("saved routine", "open outlook", "outlook", True, {"routine_clean": True}, 6.0, routine="r-outlook")
    new = EV.record("saved routine", "open a new thing", "app", True, {"routine_clean": True}, 6.0, routine="r-new")
    rows = {r["id"]: r for r in EV._rows()}
    assert rows[old]["attested"] is True and rows[new]["attested"] is False

    async def go():
        app = web.Application()
        app.add_routes(EV.routes)
        async with TestClient(TestServer(app)) as c:
            for rid in (old, new):
                assert (await c.post(f"/api/yard/evidence/{rid}/label", json={"grade": "right"})).status == 200
            cal = (await (await c.get("/api/yard/evidence")).json())["calibration"]
            assert sum(b["graded"] for b in cal) == 1                                      # only the new one teaches the confidence
            g = await (await c.get("/api/yard/golden")).json()
            assert {r["title"] for r in g["routines"]} == {"Open Outlook", "Open Notepad"}
            assert (await c.post(f"/api/yard/evidence/{new}/label", json={"grade": "skip"})).status == 200
            assert [i["id"] for i in (await (await c.get("/api/yard/evidence")).json())["items"]] == [old]      # hidden: gone from the list
            assert (await c.delete(f"/api/yard/evidence/{old}")).status == 200
            assert (await (await c.get("/api/yard/evidence")).json())["items"] == []
            assert (await c.delete(f"/api/yard/evidence/{old}")).status == 404
    _run(go())


# ---- the held-out set and the fitness report
def test_a_third_of_the_sentences_are_held_out_the_same_way_every_time_and_kept_apart(state):
    texts = [f"open the {w} please" for w in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi")]
    held = [FIT.held_out(t) for t in texts]
    assert held == [FIT.held_out(t.upper() + "  ") for t in texts] and 2 <= sum(held) <= 9        # case and spacing do not change the side
    rows = []
    for i, t in enumerate(texts, 1):
        rows += [{"at": 1000.0 + i, "text": t, "bin": "launch_app"}, {"kind": "verdict", "at": 2000.0 + i, "of": 1000.0 + i, "ok": i % 4 != 0, "by": "teach"}]
    _decisions(BIN.LOG, rows)
    frozen = FIT.sync()
    assert len(frozen) == sum(held) and {r["text"] for r in frozen} == {t for t, h in zip(texts, held) if h}
    BIN.LOG.write_text("", encoding="utf-8")                                              # the log rotates and forgets...
    assert len(FIT.sync()) == len(frozen)                                                 # ...the held-out rows are still there
    assert len(FIT.sync()) == len(frozen)                                                 # and syncing twice adds nothing


def test_the_fitness_report_counts_only_fresh_rows_and_scores_the_confidence_with_a_brier_number(state):
    YS.update({"shadow": True})
    ids = [EV.record("agent", f"g{i}", "app", True, m, 3.0) for i, m in enumerate([{"windows_confirms": True}, {"windows_confirms": True}, {"agent_done": True}])]
    labels = {ids[0]: "right", ids[1]: "wrong", ids[2]: "wrong"}
    EV.LABELS.write_text(json.dumps({k: {"grade": v, "at": 1.0} for k, v in labels.items()}), encoding="utf-8")
    rep = FIT.report()
    conf = next(h for h in rep["heads"] if h["head"] == "Task confidence")
    assert conf["graded"] == 3 and conf["brier"] == pytest.approx(((0.85 - 1) ** 2 + (0.85 - 0) ** 2 + (0.25 - 0) ** 2) / 3, abs=0.001)
    assert {h["head"] for h in rep["heads"]} >= {"Route", "Model", "Rung", "Task confidence", "Control (yard)"} and rep["gate"]["min_frozen"] == 50

    async def go():
        app = web.Application()
        app.add_routes(FIT.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.get("/api/yard/fitness")).status == 200
            got = await (await c.post("/api/yard/gate", json={"candidate": {"k": 90, "n": 100}, "baseline": {"p": 0.6}, "breaches": 0, "shadow": {"n": 40, "agree": 36}, "user_yes": True})).json()
            assert got["promote"] is True
            assert (await c.post("/api/yard/gate", data="not json")).status == 400
    _run(go())


def test_the_confidence_fit_is_only_a_proposal_and_needs_enough_graded_tasks(state):
    YS.update({"shadow": True})
    EV.record("agent", "g", "app", True, {"agent_done": True}, 1.0)

    async def go(expect_ready):
        app = web.Application()
        app.add_routes(EV.routes)
        async with TestClient(TestServer(app)) as c:
            got = await (await c.get("/api/yard/confidence/fit")).json()
            assert got["ready"] is expect_ready
            return got
    assert _run(go(False))["needs"] == 30
    labels = {}
    for i in range(40):
        win = i % 2 == 0
        rid = EV.record("agent", f"g{i}", "app", True, {"windows_confirms": win, "agent_done": True}, 1.0)
        labels[rid] = {"grade": "right" if win else "wrong", "at": 1.0}
    EV.LABELS.write_text(json.dumps(labels), encoding="utf-8")
    got = _run(go(True))
    assert got["weights"]["windows_confirms"] > 0 and got["rows"] == 40
    assert EV.POS["windows_confirms"] == 0.85                                              # proposing changed nothing
