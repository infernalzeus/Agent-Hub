"""OpenCode feature: multi-session manager for the AI coding agent.

One `opencode serve` per working folder ("chat"). OpenCode binds LOCALHOST only;
the hub (python.exe, which IS allowed through Windows Firewall) opens the public
port and relays raw TCP to it — so sessions are reachable over Tailscale from the
phone (opencode.exe is not firewall-allowed; python is). The relay is byte-
transparent, so HTTP + WebSocket + the SPA's root-absolute URLs just work.

NEW SESSION copies a source folder into Agent Code/<name>-<sid> and works there
(the original is only ever read). RESUME reopens an existing Agent Code/ folder
in place (no copy) so you can continue previous work.
"""
from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from ..config import logger
from ..platform_win import _assign_to_job

OPENCODE_ROOT = Path(r"N:\Code\git repositories\Open Source\opencode")
OPENCODE_EXE = str(OPENCODE_ROOT / "node_modules" / "opencode-ai" / "bin" / "opencode.exe")
OPENCODE_CONFIG = str(OPENCODE_ROOT / "opencode.json")
WORKROOT = OPENCODE_ROOT / "Agent Code"
PUBLIC_PORTS = range(8100, 8150)          # python-owned, firewall-reachable
INTERNAL_OFFSET = 100                     # opencode listens on public_port + 100 (localhost)
COPY_IGNORE = shutil.ignore_patterns(
    ".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache",
)

# Guides weak/agentic models to stay inside the project instead of scanning the
# whole drive (the "listing immense directories" problem). Only written if the
# folder doesn't already have one, so a repo's own AGENTS.md is never clobbered.
AGENTS_MD = """# Project context — READ FIRST

This directory IS the project root and the ONLY place you may work. It is a
disposable working copy. An identical copy of these files exists ELSEWHERE on
this machine (the user's original repo) — you must NEVER find, open, read, or
edit that original. All of your reads and edits must use paths INSIDE this
folder (relative paths, or absolute paths that start with this folder).

Rules:
- Start by listing the current directory (`ls`); everything you need is here.
- NEVER search the whole filesystem/drive: no `find N:\\ ...`, no `dir -Recurse`
  from the drive root, no listing `/`, `/var`, `/home`, `/Users`, `/workspace`.
- NEVER edit a file outside this directory. If a tool would write to a path that
  is not inside this folder, do not do it — the edit belongs in the copy here.
- If you can't find a file, `ls` subfolders HERE. It is not elsewhere.
"""

AUTH_ENABLED = os.getenv("AGENT_HUB_OPENCODE_AUTH", "0") == "1"
SERVER_USERNAME = os.getenv("OPENCODE_SERVER_USERNAME", "opencode")
SERVER_PASSWORD = os.getenv("OPENCODE_SERVER_PASSWORD") or secrets.token_urlsafe(9)

# The OPEN link points at http://<host>:<opencode-port>. It must be a host the
# PHONE can reach — NOT request.host, because behind Tailscale serve that is the
# loopback backend (127.0.0.1:8081), which on the phone means the phone itself.
# The opencode relay binds 0.0.0.0, so the machine's tailnet name reaches it from
# any tailnet device. Detected once from `tailscale status`; override via env.
OPENCODE_PUBLIC_HOST = os.getenv("OPENCODE_PUBLIC_HOST", "")
_tailnet_host_cache: str | None = None


def _tailnet_host() -> str:
    """The machine's Tailscale MagicDNS name (cached), or '' if unavailable."""
    global _tailnet_host_cache
    if _tailnet_host_cache is not None:
        return _tailnet_host_cache
    _tailnet_host_cache = ""
    try:
        import json as _json
        import subprocess
        from ..config import TAILSCALE_EXE
        out = subprocess.run([TAILSCALE_EXE, "status", "--json"],
                             capture_output=True, text=True, timeout=5)
        name = (_json.loads(out.stdout).get("Self") or {}).get("DNSName", "")
        _tailnet_host_cache = name.rstrip(".")
    except Exception:
        _tailnet_host_cache = ""
    return _tailnet_host_cache


def _public_host(request_host: str) -> str:
    """Pick the host the phone should use to reach an opencode session: an explicit
    override, else the tailnet name, else the request host (only right when it's a
    real hostname, e.g. on the local LAN)."""
    if OPENCODE_PUBLIC_HOST:
        return OPENCODE_PUBLIC_HOST
    bare = request_host.split(":")[0]
    if bare in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return _tailnet_host() or bare
    return bare or _tailnet_host()

routes = web.RouteTableDef()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


class Session:
    def __init__(self, sid: str, name: str, source: Path, cwd: Path, port: int) -> None:
        self.id = sid
        self.name = name
        self.source = str(source)
        self.cwd = cwd
        self.port = port
        self.internal_port = port + INTERNAL_OFFSET
        self.proc: asyncio.subprocess.Process | None = None
        self.relay: asyncio.AbstractServer | None = None
        self.created_at = time.time()
        self.status = "starting"

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def as_dict(self, host: str) -> dict:
        return {
            "id": self.id, "name": self.name, "source": self.source, "cwd": str(self.cwd),
            "folder": Path(self.cwd).name,   # Agent Code/<folder> — lets the UI restart a stopped session
            "port": self.port, "running": self.running,
            "status": self.status if self.running else "stopped",
            # Reachable from the phone over the tailnet (see _public_host). No
            # ?directory needed: OPENCODE_CONFIG lives in this folder, so opencode
            # opens rooted here by default.
            "open_url": f"http://{_public_host(host)}:{self.port}",
            "created": self.created_at,
        }


class Manager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.lock = asyncio.Lock()

    def _free_port(self) -> int:
        used = {s.port for s in self.sessions.values() if s.running}
        for p in PUBLIC_PORTS:
            if p not in used:
                return p
        raise RuntimeError(f"No free OpenCode ports ({PUBLIC_PORTS.start}-{PUBLIC_PORTS.stop - 1} all in use)")

    def list_folders(self) -> list[dict]:
        """Existing Agent Code/ folders, newest first — for the Resume dropdown."""
        if not WORKROOT.exists():
            return []
        active = {str(Path(s.cwd).resolve()): s.id for s in self.sessions.values() if s.running}
        out = []
        for p in sorted(WORKROOT.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_dir():
                out.append({
                    "folder": p.name, "path": str(p),
                    "active_session": active.get(str(p.resolve())),
                    "mtime": p.stat().st_mtime,
                })
        return out

    async def _reserve(self, name: str, source: Path, dest: Path) -> Session:
        async with self.lock:
            sid = uuid.uuid4().hex[:8]
            port = self._free_port()
            sess = Session(sid, name, source, dest, port)
            self.sessions[sid] = sess
            return sess

    async def _launch(self, sess: Session) -> Session:
        """git-init + AGENTS.md + spawn opencode (localhost) + public relay."""
        dest = sess.cwd
        # opencode roots a project at its git worktree; without one it falls back
        # to "/". A throwaway `git init` makes this folder the project root.
        if not (dest / ".git").exists():
            try:
                gi = await asyncio.create_subprocess_exec(
                    "git", "init", cwd=str(dest),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(gi.wait(), timeout=10)
            except Exception:
                pass
        agents = dest / "AGENTS.md"
        if not agents.exists():
            try:
                agents.write_text(AGENTS_MD, encoding="utf-8")
            except Exception:
                pass

        # THE directory lock: opencode derives its DEFAULT project directory from
        # the FOLDER that OPENCODE_CONFIG lives in (not cwd, and the web UI ignores
        # ?directory on load). Copying the shared config INTO this folder makes this
        # folder the default worktree — so the agent is rooted here, period. This is
        # why edits/searches stay in the copy instead of wandering to N:\.
        session_cfg = dest / "opencode.json"
        try:
            shutil.copy(OPENCODE_CONFIG, session_cfg)
        except Exception:
            pass
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["OPENCODE_CONFIG"] = str(session_cfg)
        if AUTH_ENABLED:
            env["OPENCODE_SERVER_USERNAME"] = SERVER_USERNAME
            env["OPENCODE_SERVER_PASSWORD"] = SERVER_PASSWORD

        logger.info("OpenCode: starting session %s (%s) internal=%d public=%d",
                    sess.id, sess.name, sess.internal_port, sess.port)
        sess.proc = await asyncio.create_subprocess_exec(
            OPENCODE_EXE, "serve", "--hostname", "127.0.0.1", "--port", str(sess.internal_port),
            cwd=str(dest), env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        _assign_to_job(sess.proc.pid)
        await self._wait_ready(sess)

        async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                up_r, up_w = await asyncio.open_connection("127.0.0.1", sess.internal_port)
            except Exception:
                try:
                    writer.close()
                except Exception:
                    pass
                return
            await asyncio.gather(_pipe(reader, up_w), _pipe(up_r, writer), return_exceptions=True)

        sess.relay = await asyncio.start_server(_handle, "0.0.0.0", sess.port)
        logger.info("OpenCode: session %s public relay up on 0.0.0.0:%d", sess.id, sess.port)
        return sess

    async def create(self, source: str, name: str | None) -> Session:
        raw = source.strip().strip('"').strip()
        if "%" in raw:                      # decode percent-encoded pasted paths
            try:
                raw = unquote(raw)
            except Exception:
                pass
        src = Path(raw)
        if not src.is_dir():
            raise FileNotFoundError(f"Not a folder: {raw}")

        base = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or src.name)).strip("-") or "session"
        dest = WORKROOT / f"{base}-{uuid.uuid4().hex[:8]}"
        sess = await self._reserve(name or base, src, dest)
        WORKROOT.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: shutil.copytree(src, dest, ignore=COPY_IGNORE))
        except Exception:
            self.sessions.pop(sess.id, None)
            raise
        return await self._launch(sess)

    async def resume(self, folder: str, name: str | None) -> Session:
        """Reopen an existing Agent Code/ folder in place — no copy."""
        dest = (WORKROOT / folder).resolve()
        if not str(dest).startswith(str(WORKROOT.resolve())) or not dest.is_dir():
            raise FileNotFoundError(f"No such Agent Code folder: {folder}")
        # if a session is already live on this folder, just return it
        for s in self.sessions.values():
            if s.running and Path(s.cwd).resolve() == dest:
                return s
        sess = await self._reserve(name or folder, dest, dest)
        return await self._launch(sess)

    async def _wait_ready(self, sess: Session, timeout: float = 30.0) -> None:
        url = f"http://127.0.0.1:{sess.internal_port}/"
        deadline = time.monotonic() + timeout
        async with aiohttp.ClientSession() as s:
            while time.monotonic() < deadline:
                if not sess.running:
                    sess.status = "exited"
                    raise RuntimeError("opencode serve exited during startup")
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=2)) as r:
                        if r.status < 500:
                            sess.status = "running"
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.4)
        sess.status = "timeout"

    async def stop(self, sid: str) -> None:
        s = self.sessions.get(sid)
        if not s:
            return
        if s.relay is not None:
            try:
                s.relay.close()
                await asyncio.wait_for(s.relay.wait_closed(), timeout=2)
            except Exception:
                pass
            s.relay = None
        if s.running:
            logger.info("OpenCode: stopping session %s (pid %s)", sid, s.proc.pid)
            # opencode.exe spawns children; terminate() orphans them. taskkill /T
            # kills the whole tree so the server actually stops.
            try:
                tk = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(s.proc.pid),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(tk.wait(), timeout=5)
            except Exception:
                try:
                    s.proc.kill()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(s.proc.wait(), timeout=3)
            except Exception:
                pass
        s.status = "stopped"

    async def remove(self, sid: str, purge: bool = False) -> None:
        await self.stop(sid)
        s = self.sessions.pop(sid, None)
        if s and purge:
            cwd = Path(s.cwd).resolve()
            if str(cwd).startswith(str(WORKROOT.resolve())) and cwd != WORKROOT.resolve():
                logger.info("OpenCode: deleting copied folder %s", cwd)
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: shutil.rmtree(cwd, ignore_errors=True))

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(sid) for sid in list(self.sessions)), return_exceptions=True)


OC = Manager()


@routes.get("/api/opencode/sessions")
async def oc_list(request: web.Request) -> web.Response:
    host = request.host.split(":")[0]
    return web.json_response({
        "auth": ({"username": SERVER_USERNAME, "password": SERVER_PASSWORD} if AUTH_ENABLED else None),
        "sessions": [s.as_dict(host) for s in OC.sessions.values()],
    })


@routes.get("/api/opencode/folders")
async def oc_folders(request: web.Request) -> web.Response:
    return web.json_response(OC.list_folders())


async def _body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@routes.post("/api/opencode/sessions")
async def oc_create(request: web.Request) -> web.Response:
    body = await _body(request)
    source = (body.get("source") or "").strip()
    if not source:
        raise web.HTTPBadRequest(text="A source folder path is required")
    try:
        sess = await OC.create(source, (body.get("name") or "").strip() or None)
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(sess.as_dict(request.host.split(":")[0]))


@routes.post("/api/opencode/sessions/resume")
async def oc_resume(request: web.Request) -> web.Response:
    body = await _body(request)
    folder = (body.get("folder") or "").strip()
    if not folder:
        raise web.HTTPBadRequest(text="A folder is required")
    try:
        sess = await OC.resume(folder, (body.get("name") or "").strip() or None)
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(sess.as_dict(request.host.split(":")[0]))


@routes.post("/api/opencode/sessions/{sid}/stop")
async def oc_stop(request: web.Request) -> web.Response:
    await OC.stop(request.match_info["sid"])
    return web.json_response({"ok": True})


@routes.delete("/api/opencode/sessions/{sid}")
async def oc_remove(request: web.Request) -> web.Response:
    await OC.remove(request.match_info["sid"], purge=request.query.get("purge") == "1")
    return web.json_response({"ok": True})


def setup(app: web.Application) -> None:
    async def _cleanup(_app: web.Application) -> None:
        await OC.stop_all()
    app.on_cleanup.append(_cleanup)
