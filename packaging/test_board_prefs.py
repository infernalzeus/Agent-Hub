"""The shared dashboard preferences: one JSON object, replaced whole, capped, and never interpreted."""
import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import board_prefs as BP


def test_roundtrip_replace_and_refusals(tmp_path, monkeypatch):
    monkeypatch.setattr(BP, "FILE", tmp_path / "prefs.json")

    async def go():
        app = web.Application(); app.add_routes(BP.routes)
        async with TestClient(TestServer(app)) as c:
            assert await (await c.get("/api/board/prefs")).json() == {}
            assert (await c.put("/api/board/prefs", json={"layers": ["tools", "system"], "hideMap": True})).status == 200
            assert await (await c.get("/api/board/prefs")).json() == {"layers": ["tools", "system"], "hideMap": True}
            assert (await c.put("/api/board/prefs", json={"hideMap": False})).status == 200
            assert await (await c.get("/api/board/prefs")).json() == {"hideMap": False}            # replaced whole
            assert (await c.put("/api/board/prefs", data="[1,2]")).status == 400
            assert (await c.put("/api/board/prefs", data="not json")).status == 400
            assert (await c.put("/api/board/prefs", data="{\"x\":\"" + "a" * 70000 + "\"}")).status == 413
            assert await (await c.get("/api/board/prefs")).json() == {"hideMap": False}            # refusals changed nothing
    asyncio.run(go())
