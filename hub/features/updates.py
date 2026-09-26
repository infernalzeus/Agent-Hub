"""Does a newer Agent Hub exist, and can this one become it?

Two endpoints:

  GET  /api/update            what this build is, what the latest release is, and
                              whether they differ. Cached in STATE so the Hub asks
                              GitHub at most once every few hours, not once per page.
  POST /api/update/install    fetch that release's installer and run it.

**The installer is the update mechanism, not a file copy.** Pulling loose files out
of the repository would skip every check the build performs, and a half-swapped
`_internal` is an application that no longer starts. Running the published installer
upgrades in place by `AppId`, and `STATE` is a different folder, so configured tools,
ingested apps and the user's own skills all survive - see
`user-state-in-the-program-folder` in the wiki for why that last one is only true
as of this version.

Nothing here runs unless asked. The status read is a HEAD-weight GET against the
public releases API with no credentials; no telemetry is sent.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from .. import runtime as RT
from ..config import logger

routes = web.RouteTableDef()

REPO = "infernalzeus/Agent-Hub"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "Agent-Hub-Setup.exe"          # fixed name; releases/latest/download resolves by it
CACHE = RT.STATE / "update.json"
MAX_AGE = 6 * 3600                     # a check per browser refresh would be rude
_busy = asyncio.Lock()


def _parts(version: str) -> tuple:
    """(1, 2, 10) from '0.1.10' or 'v0.1.10'. Unparseable -> empty, which never wins."""
    try:
        return tuple(int(p) for p in version.strip().lstrip("vV").split(".") if p != "")
    except ValueError:
        return ()


def is_newer(latest: str, current: str) -> bool:
    """Numeric compare, so 0.1.10 beats 0.1.9 — which a string compare gets wrong."""
    a, b = _parts(latest), _parts(current)
    return bool(a) and bool(b) and a > b


def _cached() -> dict:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _clean(notes: str | None) -> str:
    """Release notes come from a PowerShell build step, and a BOM has a habit of
    surviving all the way into the GitHub release body. Strip it rather than show it."""
    return (notes or "").lstrip("\ufeff").replace("\r\n", "\n").strip()[:4000]


async def _fetch() -> dict:
    """The newest published release. Drafts are not returned by this endpoint."""
    timeout = aiohttp.ClientTimeout(total=12)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AgentHub"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(API) as response:
            if response.status == 404:
                return {"error": "No published release yet."}
            if response.status != 200:
                return {"error": f"GitHub answered {response.status}."}
            body = await response.json()
    return {
        "latest": (body.get("tag_name") or "").lstrip("vV"),
        # The notes are written by a PowerShell build step, and a BOM has a habit of
        # surviving all the way into the release body. Strip it rather than show it.
        "notes": _clean(body.get("body")),
        "published": body.get("published_at"),
        "page": body.get("html_url"),
        "checked_at": time.time(),
    }


async def status(refresh: bool = False) -> dict:
    current = RT.version()
    out = {"current": current, "supported": RT.PACKAGED, "repo": REPO}
    cache = _cached()
    fresh = cache.get("checked_at", 0) > time.time() - MAX_AGE
    if refresh or not fresh:
        async with _busy:
            try:
                cache = await _fetch()
                if "error" not in cache:
                    RT.write_json(CACHE, cache)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                cache = {**cache, "error": f"Could not reach GitHub: {str(exc)[:120]}"}
    out.update({k: cache.get(k) for k in ("latest", "notes", "published", "page", "checked_at", "error")})
    # Also clean on the way out: a cache written by an older build still holds
    # whatever GitHub gave us then, and it must not reach the page.
    out["notes"] = _clean(out.get("notes"))
    out["newer"] = bool(current and cache.get("latest") and is_newer(cache["latest"], current))
    return out


@routes.get("/api/update")
async def api_update(request: web.Request) -> web.Response:
    return web.json_response(await status(refresh=request.query.get("refresh") == "1"))


@routes.post("/api/update/install")
async def api_update_install(request: web.Request) -> web.Response:
    """Download the published installer and hand over to it.

    The Hub cannot replace its own running files on Windows, so it starts the
    installer detached and stops. `CloseApplications=yes` in the installer handles
    anything still holding a file.
    """
    state = await status()
    if not RT.PACKAGED:
        raise web.HTTPBadRequest(text="This Hub runs from source. Update it with git, not the installer.")
    if os.name != "nt":
        raise web.HTTPBadRequest(text="In-app update is Windows only. Download the package for your OS.")
    if not state.get("newer"):
        raise web.HTTPBadRequest(text=f"Already on the newest release ({state.get('current')}).")

    target = RT.STATE / "updates"
    target.mkdir(parents=True, exist_ok=True)
    installer = target / ASSET
    url = f"https://github.com/{REPO}/releases/latest/download/{ASSET}"
    timeout = aiohttp.ClientTimeout(total=1800, sock_read=120)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "AgentHub"}) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise web.HTTPBadGateway(text=f"Download failed: GitHub answered {response.status}.")
                expected = int(response.headers.get("Content-Length") or 0)
                partial = installer.with_suffix(".part")
                written = 0
                with partial.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(1 << 16):
                        handle.write(chunk)
                        written += len(chunk)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise web.HTTPBadGateway(text=f"Download failed: {str(exc)[:160]}")
    # A truncated installer is worse than no installer: it would run and fail halfway.
    if expected and written != expected:
        partial.unlink(missing_ok=True)
        raise web.HTTPBadGateway(text=f"Download was incomplete ({written} of {expected} bytes). Nothing was run.")
    if written < 1_000_000:
        partial.unlink(missing_ok=True)
        raise web.HTTPBadGateway(text="The downloaded file is too small to be the installer. Nothing was run.")
    partial.replace(installer)
    logger.info("update: downloaded %s (%d bytes) for %s", ASSET, written, state.get("latest"))

    try:
        subprocess.Popen([str(installer)], close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    except OSError as exc:
        raise web.HTTPInternalServerError(text=f"Could not start the installer: {exc}")

    async def _bow_out():
        await asyncio.sleep(1.5)     # let this response reach the browser first
        logger.info("update: installer started; stopping so it can replace files")
        os._exit(0)

    asyncio.create_task(_bow_out())
    return web.json_response({"ok": True, "version": state.get("latest"), "installer": str(installer),
                              "message": "The installer is starting. Agent Hub will close, "
                                         "and your settings, apps and skills are kept."})
