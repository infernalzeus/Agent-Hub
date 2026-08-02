"""YouTube upload + download feature: state, streaming, and HTTP/WS routes."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import aiohttp
from aiohttp import web, WSMsgType

from ..config import (
    YOUTUBE_ACCOUNTS, MC_OUTPUT_DIR, YT_UPLOAD_SCRIPT,
    YT_DL_PYTHON, YT_DL_SCRIPT, YT_DL_AUDIO_DIR, YT_DL_VIDEO_DIR,
    YT_DL_COOKIES, YT_DL_COOKIES_BROWSER, logger,
)
from ..platform_win import _assign_to_job

routes = web.RouteTableDef()


def _scan_mc_edits() -> list[dict]:
    """Scan movie-clipper's output dir for finished edits, same pattern Agent
    CORE already uses: a folder counts if it has clip_final.mp4; metadata.json
    supplies title/description/tags; thumbnail.jpg is included only if present
    (narrated-mode outputs have one, classic-mode outputs don't)."""
    edits: list[dict] = []
    if not MC_OUTPUT_DIR.is_dir():
        return edits
    for folder in sorted(MC_OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        final = folder / "clip_final.mp4"
        if not final.is_file():
            continue
        meta: dict = {}
        meta_path = folder / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        thumb = folder / "thumbnail.jpg"
        mtime = datetime.fromtimestamp(final.stat().st_mtime)
        size_mb = final.stat().st_size / 1_048_576
        edits.append({
            "id": folder.name,
            "video_path": str(final),
            "title": meta.get("title", folder.name),
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "has_thumbnail": thumb.is_file(),
            "date": mtime.strftime("%Y-%m-%d %H:%M"),
            "size_mb": f"{size_mb:.1f}",
        })
    return edits


# ── YouTube upload state (single upload at a time — personal-use scope) ──────

class YTUploadState:
    def __init__(self) -> None:
        self.proc: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task | None = None
        self.lines: list[str] = []
        self.progress: int = 0
        self.done: bool = False
        self.ok: bool = False
        self.result: dict = {}
        self.subscribers: set[web.WebSocketResponse] = set()

    def reset(self) -> None:
        self.proc = None
        self.task = None
        self.lines = []
        self.progress = 0
        self.done = False
        self.ok = False
        self.result = {}

    @property
    def busy(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


yt_state = YTUploadState()

_PROGRESS_RE = re.compile(r"Progress:\s*(\d+)%")
_UPLOAD_URL_RE = re.compile(r"Upload complete!\s*(\S+)")


async def _yt_broadcast(payload: dict) -> None:
    dead = []
    for ws in yt_state.subscribers:
        try:
            await ws.send_str(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        yt_state.subscribers.discard(ws)


async def _yt_stream_upload(args: list[str]) -> None:
    cmd = [sys.executable, YT_UPLOAD_SCRIPT] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    yt_state.proc = proc
    _assign_to_job(proc.pid)

    assert proc.stdout
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        yt_state.lines.append(line)

        m = _PROGRESS_RE.search(line)
        if m:
            yt_state.progress = int(m.group(1))

        m2 = _UPLOAD_URL_RE.search(line)
        if m2:
            yt_state.result["url"] = m2.group(1)

        await _yt_broadcast({"type": "line", "text": line, "progress": yt_state.progress})

    rc = await proc.wait()
    yt_state.done = True
    yt_state.ok = (rc == 0)
    await _yt_broadcast({"type": "done", "ok": yt_state.ok, "result": yt_state.result})


# ── YouTube download state (single download at a time) ───────────────────────

class YTDownloadState:
    def __init__(self) -> None:
        self.proc: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task | None = None
        self.lines: list[str] = []
        self.progress: float = 0
        self.done: bool = False
        self.ok: bool = False
        self.result: dict = {}
        self.subscribers: set[web.WebSocketResponse] = set()

    def reset(self) -> None:
        self.proc = None
        self.task = None
        self.lines = []
        self.progress = 0
        self.done = False
        self.ok = False
        self.result = {}

    @property
    def busy(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


ytdl_state = YTDownloadState()

_DL_PROGRESS_RE = re.compile(r"Downloading:\s*([\d.]+)%")
_DL_SAVED_RE = re.compile(r"Saved to:\s*(.+)$")
_DL_ERROR_RE = re.compile(r"ERROR:\s*(.+)$")


async def _ytdl_broadcast(payload: dict) -> None:
    dead = []
    for ws in ytdl_state.subscribers:
        try:
            await ws.send_str(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ytdl_state.subscribers.discard(ws)


async def _ytdl_stream_download(args: list[str]) -> None:
    cmd = [YT_DL_PYTHON, YT_DL_SCRIPT] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    ytdl_state.proc = proc
    _assign_to_job(proc.pid)

    assert proc.stdout
    # ytdl.py's progress hook writes '\r...' with no newline for in-place
    # updates — asyncio's `async for line in stream` iteration calls readline()
    # under the hood, which only splits on '\n', so it would silently buffer
    # every '\r' update together and deliver them in one delayed burst. Reading
    # raw chunks via .read() and splitting on '\r' OR '\n' ourselves is what
    # actually gets real-time progress instead of stalled/bursty updates.
    buf = b""
    while True:
        chunk = await proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while b"\r" in buf or b"\n" in buf:
            idx = min((i for i in (buf.find(b"\r"), buf.find(b"\n")) if i != -1), default=-1)
            if idx == -1:
                break
            raw_line, buf = buf[:idx], buf[idx + 1:]
            line = raw_line.decode(errors="replace").strip()
            if not line:
                continue
            ytdl_state.lines.append(line)

            m = _DL_PROGRESS_RE.search(line)
            if m:
                ytdl_state.progress = float(m.group(1))

            m2 = _DL_SAVED_RE.search(line)
            if m2:
                ytdl_state.result["saved_to"] = m2.group(1).strip()

            # Keep the most recent ERROR line so the UI can show the real reason
            # (e.g. the cookies/bot-check hint) instead of a generic failure.
            m3 = _DL_ERROR_RE.search(line)
            if m3:
                ytdl_state.result["error"] = m3.group(1).strip()

            await _ytdl_broadcast({"type": "line", "text": line, "progress": ytdl_state.progress})

    rc = await proc.wait()
    ytdl_state.done = True
    ytdl_state.ok = (rc == 0)
    await _ytdl_broadcast({"type": "done", "ok": ytdl_state.ok, "result": ytdl_state.result})


@routes.get("/api/youtube/accounts")
async def yt_accounts(request: web.Request) -> web.Response:
    return web.json_response(list(YOUTUBE_ACCOUNTS.keys()))


@routes.get("/api/youtube/sources")
async def yt_sources(request: web.Request) -> web.Response:
    return web.json_response(_scan_mc_edits())


@routes.get("/api/youtube/thumbnail/{edit_id}")
async def yt_thumbnail(request: web.Request) -> web.Response:
    edit_id = request.match_info["edit_id"]
    # Guard against path traversal via a crafted edit_id — must be a direct child folder.
    path = (MC_OUTPUT_DIR / edit_id).resolve() / "thumbnail.jpg"
    if MC_OUTPUT_DIR.resolve() not in path.parents or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


@routes.get("/api/youtube/status")
async def yt_status(request: web.Request) -> web.Response:
    return web.json_response({
        "busy": yt_state.busy,
        "progress": yt_state.progress,
        "done": yt_state.done,
        "ok": yt_state.ok,
        "result": yt_state.result,
    })


@routes.post("/api/youtube/upload")
async def yt_upload(request: web.Request) -> web.Response:
    if yt_state.busy:
        raise web.HTTPConflict(text="An upload is already running")

    data = await request.json()
    account_tag = data.get("account", "")
    account = YOUTUBE_ACCOUNTS.get(account_tag)
    if not account:
        raise web.HTTPBadRequest(text=f"Unknown account: {account_tag}")

    video_path = (data.get("video_path") or "").strip()
    title = (data.get("title") or "").strip()
    if not video_path or not Path(video_path).is_file():
        raise web.HTTPBadRequest(text="Video file not found")
    if not title:
        raise web.HTTPBadRequest(text="Title is required")

    args = [
        "--video-path", video_path,
        "--title", title,
        "--privacy", data.get("privacy") or "unlisted",
        "--secrets-file", account["secrets_file"],
        "--token-file", account["token_file"],
    ]
    if data.get("description"):
        args += ["--description", data["description"]]
    tags = data.get("tags") or []
    if isinstance(tags, list):
        tags = ",".join(tags)
    if tags:
        args += ["--tags", tags]
    # Resolved server-side from the chosen output folder's name — never trust a
    # client-supplied filesystem path for this.
    source_id = data.get("source_id") or ""
    if source_id:
        thumb = (MC_OUTPUT_DIR / source_id).resolve() / "thumbnail.jpg"
        if MC_OUTPUT_DIR.resolve() in thumb.parents and thumb.is_file():
            args += ["--thumbnail", str(thumb)]

    yt_state.reset()
    yt_state.task = asyncio.create_task(_yt_stream_upload(args))
    return web.json_response({"ok": True})


@routes.get("/ws/youtube")
async def yt_ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    yt_state.subscribers.add(ws)

    for line in yt_state.lines:
        await ws.send_str(json.dumps({"type": "line", "text": line, "progress": yt_state.progress}))
    if yt_state.done:
        await ws.send_str(json.dumps({"type": "done", "ok": yt_state.ok, "result": yt_state.result}))

    async for msg in ws:
        if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
            break

    yt_state.subscribers.discard(ws)
    return ws


@routes.post("/api/youtube-dl/download")
async def ytdl_download(request: web.Request) -> web.Response:
    if ytdl_state.busy:
        raise web.HTTPConflict(text="A download is already running")

    data = await request.json()
    url = (data.get("url") or "").strip()
    fmt = data.get("format") or "video"
    if not url.startswith(("http://", "https://")):
        raise web.HTTPBadRequest(text="That doesn't look like a URL")
    if fmt not in ("audio", "video"):
        raise web.HTTPBadRequest(text="format must be 'audio' or 'video'")

    outdir = YT_DL_AUDIO_DIR if fmt == "audio" else YT_DL_VIDEO_DIR
    args = ["--url", url, "--format", fmt, "--outdir", outdir]

    # Authenticate the download. Prefer an exported cookies.txt; fall back to
    # reading cookies live from a browser if one is configured.
    if YT_DL_COOKIES and os.path.isfile(YT_DL_COOKIES):
        args += ["--cookies", YT_DL_COOKIES]
    elif YT_DL_COOKIES_BROWSER:
        args += ["--cookies-from-browser", YT_DL_COOKIES_BROWSER]

    ytdl_state.reset()
    ytdl_state.task = asyncio.create_task(_ytdl_stream_download(args))
    return web.json_response({"ok": True})


@routes.get("/ws/youtube-dl")
async def ytdl_ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ytdl_state.subscribers.add(ws)

    for line in ytdl_state.lines:
        await ws.send_str(json.dumps({"type": "line", "text": line, "progress": ytdl_state.progress}))
    if ytdl_state.done:
        await ws.send_str(json.dumps({"type": "done", "ok": ytdl_state.ok, "result": ytdl_state.result}))

    async for msg in ws:
        if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
            break

    ytdl_state.subscribers.discard(ws)
    return ws

