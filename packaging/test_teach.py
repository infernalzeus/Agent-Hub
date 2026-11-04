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
            assert (await c.post("/api/learning/teach", json={"of": 200.0, "ok": False, "correct": "conversation"})).status == 200
            j = await (await c.get("/api/learning/teach")).json()
            assert [i["of"] for i in j["items"]] == [100.0]
    _run(go())
    verdict = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if '"verdict"' in l][0]
    assert verdict["of"] == 200.0 and verdict["ok"] is False and verdict["by"] == "teach" and verdict["correct"] == "conversation"
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
