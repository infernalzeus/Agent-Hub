"""A window as real video for a phone: the ffmpeg command, the playlist and pieces it serves, and that it stops. The capture source is a test pattern; no real window is filmed."""
import asyncio
import shutil
import subprocess

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import window_mirror as WM, window_video as V

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def test_the_command_makes_even_sizes_short_pieces_and_no_sound(tmp_path):
    c = V.command(["-f", "gdigrab", "-i", "title=X"], tmp_path, "amf", 30, 1280)
    j = " ".join(c)
    assert "h264_amf" in j and "-an" in c and "-hls_time 1" in j and "trunc(min(1280" in j and "yuv420p" in j
    assert "libx264" in " ".join(V.command(["-i", "x"], tmp_path, "x264", 30, 960))


def test_the_window_capture_is_by_title_and_the_region_capture_is_by_the_windows_rectangle(monkeypatch):
    assert V.source_args({"id": 5, "title": "Claude"}, "window", 30)[-1] == "title=Claude"
    monkeypatch.setattr(WM, "window_rect", lambda h: (100, 50, 801, 601))
    src = " ".join(V.source_args({"id": 5, "title": "Claude"}, "region", 30))
    assert "ddagrab" in src and "offset_x=100" in src and "video_size=800x600" in src


def test_it_starts_serves_a_playlist_and_pieces_and_stops_leaving_nothing_behind(monkeypatch):
    monkeypatch.setattr(V, "source_args", lambda win, mode, fps: ["-re", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate={fps}"])
    monkeypatch.setattr(WM, "list_windows", lambda: [{"id": 5, "title": "Test", "exe": "t.exe", "w": 640, "h": 360, "minimised": False}])

    async def go():
        app = web.Application()
        app.add_routes(V.routes)
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/windows/5/video/start?fps=30&w=640", headers={"Origin": str(c.make_url(""))})
            j = await r.json()
            assert j["ok"] and j["playlist"] == "/api/windows/5/video/index.m3u8" and j["fps"] == 30, j
            pl = await c.get(j["playlist"])
            text = await pl.text()
            assert pl.status == 200 and "#EXTM3U" in text and pl.headers["Content-Type"].startswith("application/vnd.apple.mpegurl")
            piece = next(l for l in text.splitlines() if l.endswith(".ts"))
            seg = await c.get("/api/windows/5/video/" + piece)
            body = await seg.read()
            assert seg.status == 200 and len(body) > 1000
            assert (await c.get("/api/windows/5/video/../../secret")).status == 404 and (await c.get("/api/windows/6/video/index.m3u8")).status == 404
            folder = V._RUN["cur"]["dir"]
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,avg_frame_rate", "-of", "csv=p=0", str(folder / piece)], capture_output=True, text=True).stdout.strip()
            assert probe.startswith("h264") and "30" in probe, probe
            assert (await (await c.get("/api/windows/video")).json())["running"] is True
            assert (await (await c.post("/api/windows/5/video/stop")).json())["was_running"] is True
            assert not folder.exists() and (await (await c.get("/api/windows/video")).json())["running"] is False
    _run(go())


def test_a_stream_nobody_watches_stops(monkeypatch):
    monkeypatch.setattr(V, "source_args", lambda win, mode, fps: ["-re", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate={fps}"])
    monkeypatch.setattr(V, "IDLE_SECONDS", 1)

    async def go():
        j = await V.start({"id": 7, "title": "T"}, "window", 15, 320)
        assert j["ok"]
        await asyncio.sleep(5)
        assert V.status()["running"] is False
    _run(go())


def test_the_phones_heartbeat_becomes_a_crash_report_in_words(monkeypatch):
    import time
    V.BEATS.clear()
    assert V.report()["seen"] is False

    async def post(c, **kw):
        return await c.post("/api/windows/video/beat", json=kw)

    async def go():
        app = web.Application()
        app.add_routes(V.routes)
        async with TestClient(TestServer(app)) as c:
            await post(c, id=5, kind="start", t=0, ready=4, view="3d")
            await post(c, id=5, kind="beat", t=4, ready=4, dropped=0, total=120, view="3d")
            await post(c, id=5, kind="stalled", t=5, ready=2, view="3d")
            await post(c, id=5, kind="beat", t=9, ready=4, dropped=3, total=240, view="3d")
            j = await (await c.get("/api/windows/video/report")).json()
            assert j["seen"] and j["problems"] == {"stalled": 1} and j["view"] == "3d" and "still reporting" in j["verdict"], j
            V.BEATS[-1]["at"] -= 30                                                        # the phone goes quiet, no goodbye
            monkeypatch.setitem(V._RUN, "cur", {"id": 5, "last": time.time(), "proc": None, "dir": None})
            j = await (await c.get("/api/windows/video/report")).json()
            assert "most likely crashed" in j["verdict"], j
            await post(c, id=5, kind="pagehide", view="3d")
            assert "left normally" in (await (await c.get("/api/windows/video/report")).json())["verdict"]
    _run(go())
    V._RUN.pop("cur", None)
