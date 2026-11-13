"""A window of this PC as real video, for a phone: 30 frames a second, not pictures.

A phone cannot hold five pictures a second without running out of memory, but it plays video natively and in hardware. So for the one window you ask to watch, ffmpeg captures it, encodes
H.264 (the processor's x264 at its fastest setting; the AMD card's encoder is tried first only if HUB_VIDEO_ENCODER=amf, because on this PC it wrote nothing until it was stopped) and cuts it into one-second HLS pieces that Safari plays in a <video> element. No sound.

    POST /api/windows/{id}/video/start?mode=window|region&fps=30&w=1280   starts it (one at a time: starting another stops the first); returns the playlist address
    GET  /api/windows/{id}/video/{file}                                   the playlist and the pieces
    POST /api/windows/{id}/video/stop                                     stops it
    GET  /api/windows/video                                               what is running

Nothing keeps running unasked: it stops when the page stops fetching (20 seconds), when you stop it, and when the Hub shuts down. The pieces live in a temporary folder that is removed with it.
mode window  captures the window by its title (works for most apps; some draw through the graphics card and come out black)
mode region  captures that rectangle of the screen (shows video content too, but the window must be in front and stay where it is)
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from . import window_mirror as WM

routes = web.RouteTableDef()
IDLE_SECONDS = 20
_RUN: dict = {}                                   # at most one: {"id", "proc", "dir", "last", "mode", "encoder", "started"}
_REAPER: "asyncio.Task | None" = None


def ffmpeg_path() -> "str | None":
    return shutil.which("ffmpeg")


def command(src: "list[str]", out_dir: Path, encoder: str, fps: int, width: int, flt: str = "") -> "list[str]":
    """The ffmpeg command line. Even sizes (H.264 needs them), no more than `width` wide, one-second pieces, a short list so old ones are deleted."""
    vf = (flt + "," if flt else "") + f"scale=trunc(min({width}\\,iw)/2)*2:-2,format=yuv420p"
    enc = (["-c:v", "h264_amf", "-usage", "lowlatency", "-quality", "speed", "-b:v", "3M"] if encoder == "amf"
           else ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-b:v", "3M"])
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *src, "-vf", vf, *enc, "-g", str(fps), "-an", "-f", "hls", "-hls_time", "1", "-hls_list_size", "4",
            "-hls_flags", "delete_segments+independent_segments", "-hls_segment_filename", str(out_dir / "seg%05d.ts"), str(out_dir / "index.m3u8")]


def source_args(win: dict, mode: str, fps: int) -> "list[str]":
    if mode == "region":
        r = WM.window_rect(int(win["id"])) if hasattr(WM, "window_rect") else None
        if r:
            x, y, w, h = r
            return ["-f", "lavfi", "-i", f"ddagrab=0:framerate={fps}:offset_x={x}:offset_y={y}:video_size={w // 2 * 2}x{h // 2 * 2}:draw_mouse=0,hwdownload,format=bgra"]
    return ["-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0", "-i", "title=" + str(win.get("title") or "")]


async def _spawn(args: "list[str]") -> "subprocess.Popen":
    flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0                      # no console window
    return await asyncio.to_thread(lambda: subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags))


async def stop() -> bool:
    """Stop what is running and remove its pieces. True when something was running."""
    cur = _RUN.pop("cur", None)
    if not cur:
        return False
    p = cur["proc"]
    try:
        if p.poll() is None:
            p.terminate()
            try:
                await asyncio.to_thread(p.wait, 3)
            except subprocess.TimeoutExpired:
                p.kill()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(cur["dir"], ignore_errors=True)
    return True


async def start(win: dict, mode: str = "window", fps: int = 30, width: int = 1280) -> dict:
    """Start capturing a window with the processor's H.264 encoder (the graphics card's first when HUB_VIDEO_ENCODER=amf)."""
    global _REAPER
    if not ffmpeg_path():
        return {"ok": False, "error": "ffmpeg is not installed on this PC"}
    await stop()
    fps, width = max(5, min(30, int(fps))), max(320, min(1920, int(width)))
    out = Path(tempfile.mkdtemp(prefix="hub-video-"))
    last_err = ""
    import os
    for encoder in (("amf", "x264") if os.environ.get("HUB_VIDEO_ENCODER", "").lower() == "amf" else ("x264",)):
        p = await _spawn(command(source_args(win, mode, fps), out, encoder, fps, width))
        for _ in range(40):                                                         # wait for the first piece, or for the encoder to give up
            await asyncio.sleep(0.15)
            if (out / "index.m3u8").exists() and any(out.glob("seg*.ts")):
                _RUN["cur"] = {"id": int(win["id"]), "proc": p, "dir": out, "last": time.time(), "mode": mode, "encoder": encoder, "started": time.time(), "fps": fps}
                if _REAPER is None or _REAPER.done() or _REAPER.get_loop() is not asyncio.get_running_loop():
                    _REAPER = asyncio.ensure_future(_reap())
                logger.info("window video: %s of window %s started with %s", mode, win["id"], encoder)
                return {"ok": True, "encoder": encoder, "mode": mode, "fps": fps, "playlist": f"/api/windows/{int(win['id'])}/video/index.m3u8"}
            if p.poll() is not None:
                break
        try:
            last_err = (p.stderr.read() or b"").decode("utf-8", "replace")[-200:] if p.poll() is not None else "no picture within 6 s"
        except Exception:  # noqa: BLE001
            last_err = "failed"
        if p.poll() is None:
            p.terminate()
    shutil.rmtree(out, ignore_errors=True)
    return {"ok": False, "error": "could not capture that window: " + last_err.strip()}


async def _reap() -> None:
    while _RUN.get("cur"):
        await asyncio.sleep(3)
        cur = _RUN.get("cur")
        if cur and (cur["proc"].poll() is not None or time.time() - cur["last"] > IDLE_SECONDS):
            logger.info("window video: stopped (%s)", "ended" if cur["proc"].poll() is not None else "nobody was watching")
            await stop()


def status() -> dict:
    cur = _RUN.get("cur")
    return {"running": bool(cur), "window": cur and cur["id"], "encoder": cur and cur["encoder"], "mode": cur and cur["mode"], "ffmpeg": bool(ffmpeg_path())}


# ---- what the phone says while it watches: the only crash report Safari gives us is silence
BEATS: list = []                                   # the last 300 things the page said: {"at", "id", "kind", "t", "ready", "dropped", "total", "view", "ua", ...}


@routes.post("/api/windows/video/beat")
async def api_beat(request: web.Request) -> web.Response:
    """The page watching a video says, every 4 seconds, that it is alive, and at once when it waits, stalls, errors or leaves. A page that stops saying anything while the stream is still being
    fetched, and never said it was leaving, has crashed (or the phone slept)."""
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="json please")
    row = {"at": time.time(), "id": b.get("id"), "kind": str(b.get("kind") or "beat")[:20], "t": b.get("t"), "ready": b.get("ready"), "dropped": b.get("dropped"), "total": b.get("total"),
           "view": str(b.get("view") or "")[:12], "moving": bool(b.get("moving")), "ua": request.headers.get("User-Agent", "")[:60]}
    BEATS.append(row)
    del BEATS[:-300]
    if row["kind"] != "beat":
        logger.info("window video: the page reports %s (window %s, board view %s, %s dropped of %s frames)", row["kind"], row["id"], row["view"] or "?", row["dropped"], row["total"])
    return web.json_response({"ok": True})


def report() -> dict:
    """What happened in the last video session, in words: how long it ran, what the page reported, and whether it went quiet without saying goodbye."""
    if not BEATS:
        return {"seen": False, "say": "No phone has reported watching a video yet."}
    last = BEATS[-1]
    start = next((r for r in reversed(BEATS) if r["kind"] == "start"), BEATS[0])
    mine = [r for r in BEATS if r["at"] >= start["at"]]
    bad = [r["kind"] for r in mine if r["kind"] in ("waiting", "stalled", "error")]
    left = any(r["kind"] == "pagehide" for r in mine)
    quiet = time.time() - last["at"]
    cur = _RUN.get("cur")
    verdict = ("left normally" if left else f"went quiet {int(quiet)} s ago without saying goodbye while the stream " + ("is still being fetched: the page most likely crashed" if cur and time.time() - cur["last"] < 8 else "had already stopped") if quiet > 12 else "is still reporting")
    return {"seen": True, "ran_seconds": int(last["at"] - start["at"]), "view": last["view"], "problems": {k: bad.count(k) for k in set(bad)}, "dropped": last.get("dropped"), "total": last.get("total"),
            "verdict": verdict, "say": f"Video on the {last['view'] or '?'} board ran {int(last['at'] - start['at'])} s; " + (", ".join(f"{bad.count(k)} {k}" for k in set(bad)) or "no stalls") + f"; the page {verdict}."}


@routes.get("/api/windows/video/report")
async def api_report(request: web.Request) -> web.Response:
    return web.json_response(report())


@routes.get("/api/windows/video")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(status())


@routes.post("/api/windows/{id}/video/start")
async def api_start(request: web.Request) -> web.Response:
    hwnd = int(request.match_info["id"])
    win = next((w for w in await asyncio.to_thread(WM.list_windows) if int(w["id"]) == hwnd), None)
    if not win or win.get("minimised"):
        raise web.HTTPNotFound(text="that window is gone or minimised")
    q = request.query
    mode = q.get("mode") if q.get("mode") in ("window", "region") else "window"
    return web.json_response(await start(win, mode, int(q.get("fps", "30")), int(q.get("w", "1280"))))


@routes.post("/api/windows/{id}/video/stop")
async def api_stop(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "was_running": await stop()})


@routes.get("/api/windows/{id}/video/{file}")
async def api_file(request: web.Request) -> web.StreamResponse:
    cur = _RUN.get("cur")
    name = request.match_info["file"]
    if not cur or cur["id"] != int(request.match_info["id"]) or not re.fullmatch(r"(index\.m3u8|seg\d{5}\.ts)", name):
        raise web.HTTPNotFound()
    cur["last"] = time.time()
    f = cur["dir"] / name
    if not f.is_file():
        raise web.HTTPNotFound()
    ctype = "application/vnd.apple.mpegurl" if name.endswith(".m3u8") else "video/mp2t"
    return web.FileResponse(f, headers={"Content-Type": ctype, "Cache-Control": "no-store"})
