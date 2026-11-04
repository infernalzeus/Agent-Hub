"""R LEARNING: practice can be stopped and reports progress; the most recent missions appear in TEACH; your decision on a mission is an exact label."""
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.agent_knowledge import model_stats as MS
from hub.features import learning as LRN, missions as M
from hub.yard import api, practice as P, teach as T


def _mission(mid, status, created, ok=None, model="gemma"):
    return SimpleNamespace(id=mid, brief=f"brief of {mid}\nmore", project_name="proj", status=status, created=created, model=model, agent="a", verify={"ok": ok} if ok is not None else {})


def test_a_practice_run_reports_progress_and_stops_at_once_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(P, "POLICY", tmp_path / "policy.json")
    out = {}
    t = threading.Thread(target=lambda: out.update(P.practice(episodes=400, n_eval=2)))
    t.start()
    for _ in range(100):
        if P.CONTROL["running"] and P.CONTROL["done"] > 3:
            break
        time.sleep(0.02)
    assert P.CONTROL["running"] and P.CONTROL["total"] > 400 and P.CONTROL["phase"]
    P.CONTROL["stop"] = True
    t.join(20)
    assert not t.is_alive()
    assert out.get("stopped") is True and out["done"] < out["total"]
    assert not (tmp_path / "report.json").exists() and not (tmp_path / "policy.json").exists()      # a stopped run saves nothing
    assert P.CONTROL["running"] is False and P.CONTROL["stop"] is False


def test_the_stop_endpoint_only_acts_on_a_run_that_is_going():
    async def go():
        app = web.Application(); app.add_routes(api.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await (await c.post("/api/yard/practice/stop")).json()) == {"was_running": False}
            st = await (await c.get("/api/yard/status")).json()
            assert st["progress"]["running"] is False
    asyncio.run(go())


def test_missions_are_listed_newest_first_and_your_decision_is_the_label(tmp_path, monkeypatch):
    monkeypatch.setattr(LRN, "MISSION_LABELS", tmp_path / "labels.json")
    ms = {"a": _mission("a", "applied", 1), "b": _mission("b", "discarded", 2, ok=True), "c": _mission("c", "awaiting_review", 3, ok=True)}
    monkeypatch.setattr(M, "S", SimpleNamespace(m=ms))
    monkeypatch.setattr(MS, "OUTCOMES", tmp_path / "outcomes.json")
    for mid, ok in (("a", False), ("b", True), ("c", True)):          # the project's own checks said: a failed, b and c passed
        MS.record(["gemma"], ok, 5, 100, mid)
    v = LRN.mission_verdicts()
    assert v == {"a": True, "b": False}                                # applied = yes, discarded = no, awaiting review = nothing yet
    ev = {e["mission"]: e["ok"] for e in LRN._model_events()}
    assert ev == {"a": True, "b": False, "c": True}                    # your decision beats the checks (a failed its tests but you applied it); c keeps the checks' answer
    assert [m["id"] for m in T._missions()] == ["c", "b", "a"]

    async def go():
        app = web.Application(); app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/learning/teach/mission", json={"id": "c", "ok": False})).status == 200
            assert (await c.post("/api/learning/teach/mission", json={"id": "zzz", "ok": True})).status == 404
            assert (await c.post("/api/learning/teach/mission", json={"id": "c", "ok": "yes"})).status == 400
            got = (await (await c.get("/api/learning/teach/missions")).json())["missions"]
            assert got[0]["id"] == "c" and got[0]["verdict"] is False and got[0]["decided_by"] == "you tapped"
    asyncio.run(go())
    assert {e["mission"]: e["ok"] for e in LRN._model_events()}["c"] is False           # the tap is now the label
