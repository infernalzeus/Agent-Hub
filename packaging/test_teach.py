"""TEACH: one tap is one exact label, written as the verdict line the router already understands; only unlabelled decisions are offered."""
import asyncio
import json

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import binning as BIN, learning as LRN
from hub.yard import teach as T


def _log(tmp_path, monkeypatch):
    log = tmp_path / "decisions.jsonl"
    rows = [{"at": 100.0, "text": "open apple music", "bin": "launch_app", "said": "Opening Apple Music."},
            {"at": 200.0, "text": "what is the weather", "bin": "app_task", "said": "x"},
            {"kind": "outcome", "at": 101.0, "action": "pc_app", "ok": True}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(BIN, "LOG", log)
    return log


def _run(coro):
    return asyncio.run(coro)


def test_offers_only_unlabelled_decisions_newest_first_and_a_tap_labels_exactly(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)

    async def go():
        app = web.Application(); app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/learning/teach")).json()
            assert [i["of"] for i in j["items"]] == [200.0, 100.0] and j["left"] == 2
            assert (await c.post("/api/learning/teach", json={"of": 200.0, "ok": False, "correct": "conversation", "note": "  I was asking a question, not giving a command  "})).status == 200
            j = await (await c.get("/api/learning/teach")).json()
            assert [i["of"] for i in j["items"]] == [100.0]
    _run(go())
    verdict = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"verdict"' in l][0]
    assert verdict["of"] == 200.0 and verdict["ok"] is False and verdict["by"] == "teach" and verdict["correct"] == "conversation"
    assert verdict["note"] == "I was asking a question, not giving a command"                  # why, in the person's own words
    ev = {e["at"]: e for e in LRN._route_events()}
    assert ev[200.0]["ok"] is False                                   # the learning log reads the tap as an exact label


def test_bad_taps_are_refused_and_an_unknown_bin_is_not_stored(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)

    async def go():
        app = web.Application(); app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/learning/teach", json={"of": 999.0, "ok": True})).status == 404
            assert (await c.post("/api/learning/teach", json={"of": 100.0, "ok": "yes"})).status == 400
            assert (await c.post("/api/learning/teach", data="x")).status == 400
            assert (await c.post("/api/learning/teach", json={"of": 100.0, "ok": False, "correct": "rm -rf"})).status == 200
    _run(go())
    v = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"verdict"' in l]
    assert len(v) == 1 and "correct" not in v[0]


def test_the_page_is_served():
    async def go():
        app = web.Application(); app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/teach")
            assert r.status == 200 and "RIGHT" in await r.text()
    _run(go())


def test_skip_partly_and_not_the_routers_fault_never_come_back_and_a_correction_changes_the_route(tmp_path, monkeypatch):
    """5 Nov: SKIP only hid a card until the page reloaded, and PARTLY or a speech-to-text miss (no exact label) were offered again and again."""
    log = _log(tmp_path, monkeypatch)
    monkeypatch.setattr(BIN, "_MEMORY", {"key": None, "map": {}})

    async def go():
        app = web.Application(); app.add_routes(T.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/learning/teach", json={"of": 100.0, "grade": "skip"})).status == 200
            assert (await c.post("/api/learning/teach", json={"of": 200.0, "grade": "wrong", "cause": "heard", "note": "garbled"})).status == 200
            j = await (await c.get("/api/learning/teach")).json()
            assert j["items"] == [] and j["left"] == 0
    _run(go())
    # a WRONG that names the right bin is the one tap that changes behaviour: the same sentence is routed that way next time
    log.write_text(log.read_text(encoding="utf-8") + json.dumps({"kind": "verdict", "at": 300.0, "of": 200.0, "grade": "wrong", "by": "teach", "ok": False, "correct": "conversation"}) + "\n", encoding="utf-8")
    d = BIN.decide("What is the weather?")
    assert d["bin"] == "conversation" and d["by"] == "you"
