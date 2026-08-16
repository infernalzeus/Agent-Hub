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
import json
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

from .. import agent_knowledge
from ..config import logger
from ..platform_win import _assign_to_job

OPENCODE_ROOT = Path(r"N:\Code\opencode")
# Deliberately OUTSIDE `git repositories\`: WORKROOT (below) lives inside this
# tree, so keeping OPENCODE_ROOT itself under `git repositories\` would let a
# session's working copy get swept up as a "source" by anything that scans
# that folder for projects (the self-replication trap).
OPENCODE_EXE = str(OPENCODE_ROOT / "node_modules" / "opencode-ai" / "bin" / "opencode.exe")
OPENCODE_CONFIG = str(OPENCODE_ROOT / "opencode.json")
WORKROOT = OPENCODE_ROOT / "Agent Code"
# WORKROOT splits into two: PROJECTS_ROOT holds every copy made FROM a real
# git-repositories source (what the status/diff engine compares); CHATS_ROOT
# holds standalone folders with no such source (today: pre-existing/manually
# made folders like "new test" - see agent_knowledge.projects.discover_orphan_chats).
# Both are just "another folder for opencode to work out of" - no functional
# difference to opencode itself, purely an organizational split.
PROJECTS_ROOT = WORKROOT / "projects"
CHATS_ROOT = WORKROOT / "chats"


def _junction_cmd(link: Path, target: Path) -> list[str]:
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
            f'New-Item -ItemType Junction -Path "{link}" -Target "{target}" | Out-Null']


def _make_junction_sync(link: Path, target: Path) -> None:
    """Blocking version — for the startup migration, which runs at module
    import time before any event loop exists. See `_make_junction` for what
    this actually does and why it's safe."""
    import subprocess
    result = subprocess.run(_junction_cmd(link, target), capture_output=True)
    if result.returncode != 0 or not link.is_dir():
        raise OSError(f"junction creation failed ({link} -> {target}): {result.stderr.decode(errors='replace')}")


async def _make_junction(link: Path, target: Path) -> None:
    """An NTFS directory junction: `link` becomes an alternate path to the
    SAME physical content as `target` (no admin/dev-mode needed, unlike a
    real symlink). Used so every chat gets its own path for OpenCode's
    path-keyed session history while all chats for one project share the
    exact same files on disk — never a fresh duplicate copy per chat.
    Verified safe to tear down later: `os.rmdir()` on a junction removes
    only the link; `shutil.rmtree()` refuses outright rather than
    following it into the real target (tested empirically, not assumed)."""
    proc = await asyncio.create_subprocess_exec(
        *_junction_cmd(link, target),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not link.is_dir():
        raise OSError(f"junction creation failed ({link} -> {target}): {stderr.decode(errors='replace')}")


def _remove_workroot_entry(path: Path) -> None:
    """Safely remove one Agent Code entry.

    A chats/ junction into projects/: unlink the LINK only (`os.rmdir` —
    verified empirically this never touches the real target's content;
    `shutil.rmtree` was tested too and refuses outright on a reparse point
    rather than risking following it, but rmdir is the correct intentional
    op here, not a fallback).

    A real directory: normal recursive delete — UNLESS it's the shared
    projects/ folder itself and another chat still junctions into it, in
    which case deleting it would yank the files out from under every other
    open/resumable chat for that project, so this refuses instead.
    """
    target = path.resolve()
    into_projects = target != path and str(target).startswith(str(PROJECTS_ROOT.resolve()))
    if into_projects:
        try:
            os.rmdir(path)
        except OSError as exc:
            logger.warning("OpenCode: failed to unlink chat junction %s: %s", path, exc)
        return
    if str(target).startswith(str(PROJECTS_ROOT.resolve())) and CHATS_ROOT.is_dir():
        still_linked = any(c.is_dir() and c.resolve() == target for c in CHATS_ROOT.iterdir())
        if still_linked:
            logger.warning("OpenCode: refusing to delete %s — other chats still link to it", path)
            return
    shutil.rmtree(path, ignore_errors=True)


def resolve_workroot_child(name: str) -> Path | None:
    """A bare Agent Code child name -> its own Path (the junction/folder
    itself — deliberately NOT `.resolve()`d through a chats/ junction, since
    callers need the chat's own distinct path for OpenCode's session
    identity, not the shared project folder it links to). Checks chats/ then
    projects/ (then the flat WORKROOT itself, a defensive fallback for
    anything the startup migration didn't catch). `name` must be a bare leaf
    name, never a nested/traversal path."""
    if not name or "/" in name or "\\" in name or name in ("..", "."):
        return None
    for root in (CHATS_ROOT, PROJECTS_ROOT, WORKROOT):
        p = root / name
        if p.is_dir() and p.resolve() not in (PROJECTS_ROOT.resolve(), CHATS_ROOT.resolve()):
            return p
    return None


def _migrate_legacy_layout() -> None:
    """One-time reconciliation, safe to call on every startup:

    1. Anything sitting directly under WORKROOT (the old flat layout, or an
       earlier round's wrong chats/-only orphan placement) gets real content
       moved into PROJECTS_ROOT — ALWAYS projects/, regardless of whether it
       has a real, discovered external source. A folder started from scratch
       inside Agent Code (no matching git-repositories source — "a project
       that hasn't been added to my work yet") is still a real project, it
       just has no external source to diff against; that only affects its
       graph state/wiki-linking, never which physical folder it lives in.
    2. Every PROJECTS_ROOT entry gets a matching CHATS_ROOT junction if it
       doesn't already have one — chats/ is ONLY ever junctions (or, for
       anything this pass hasn't reconciled yet, real folders it will fix
       on the next run), never a second copy of real content.
    """
    if not WORKROOT.is_dir():
        return
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    CHATS_ROOT.mkdir(parents=True, exist_ok=True)

    for child in list(WORKROOT.iterdir()):
        if not child.is_dir() or child.resolve() in (PROJECTS_ROOT.resolve(), CHATS_ROOT.resolve()):
            continue
        target = PROJECTS_ROOT / child.name
        try:
            if not target.exists():
                child.rename(target)
                logger.info("OpenCode: migrated legacy folder %s -> projects/", child.name)
            else:
                logger.warning("OpenCode: migration skipped %s — projects/%s already exists", child, child.name)
        except Exception as exc:
            logger.warning("OpenCode: could not migrate %s: %s", child, exc)

    # A folder that landed in chats/ directly (an earlier round's mistake,
    # or a manually-made folder) with REAL content (not a junction) needs
    # its content promoted to projects/ too, then relinked.
    for child in list(CHATS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.resolve() != child:      # already a junction — fine as-is
            continue
        target = PROJECTS_ROOT / child.name
        if target.exists():
            continue
        try:
            child.rename(target)
            logger.info("OpenCode: promoted chats/%s (real content, no junction) -> projects/", child.name)
        except Exception as exc:
            logger.warning("OpenCode: could not promote chats/%s: %s", child, exc)

    for project_dir in list(PROJECTS_ROOT.iterdir()):
        if not project_dir.is_dir():
            continue
        chat_dir = CHATS_ROOT / project_dir.name
        if chat_dir.exists():
            continue
        try:
            _make_junction_sync(chat_dir, project_dir)
            logger.info("OpenCode: linked chats/%s -> projects/%s", project_dir.name, project_dir.name)
        except Exception as exc:
            logger.warning("OpenCode: could not link chats/%s: %s", project_dir.name, exc)
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
        """Existing chats/ entries, newest first — for the Resume dropdown.
        Each is either a junction into a shared projects/ copy, or (for a
        standalone/orphan chat) a real folder — both list uniformly here.
        projects/ folders themselves aren't independently resumable
        identities; they're the shared storage chats link into."""
        if not CHATS_ROOT.is_dir():
            return []
        active = {str(Path(s.cwd)): s.id for s in self.sessions.values() if s.running}
        children = [p for p in CHATS_ROOT.iterdir() if p.is_dir()]
        out = []
        for p in sorted(children, key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({
                "folder": p.name, "path": str(p),
                "active_session": active.get(str(p)),
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
        # Marker linking this copy back to its source — the in-memory Session
        # doesn't survive a hub restart, but the graph's status engine (see
        # hub/agent_knowledge/status.py) needs this pairing even for copies
        # from a previous run. Written once, at first launch, never touched
        # again (it's the copy's *origin*, not its current state).
        marker = dest / ".agent-hub-source.json"
        if not marker.exists():
            try:
                marker.write_text(json.dumps({"source": str(sess.source)}), encoding="utf-8")
            except Exception:
                pass

        agents = dest / "AGENTS.md"
        if not agents.exists():
            # Project-aware: safety rules + a wiki-sourced project summary +
            # a skill index (see hub/agent_knowledge). Falls back to the
            # generic AGENTS_MD if generation fails for any reason — a
            # session must never be left without the safety-rules section.
            try:
                agents.write_text(agent_knowledge.render_agents_md(sess.name, dest), encoding="utf-8")
            except Exception:
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
            # Merge in the knowledge layer's lsp/mcp/model-options config
            # (additive — never touches the base config's model/provider/
            # permission keys unless model_options.json explicitly overrides
            # a specific provider.model.options value).
            base_cfg = json.loads(session_cfg.read_text(encoding="utf-8"))
            merged_cfg = agent_knowledge.apply_session_config(base_cfg, sess.name, dest)
            session_cfg.write_text(json.dumps(merged_cfg, indent=2), encoding="utf-8")
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
        """Open `source` in Agent Code. ONE real copy per project
        (projects/<base>) and ONE chat identity per project (a junction at
        chats/<base> into that copy) — both made once, reused every time
        after. This is deliberately NOT "one folder per conversation":
        OpenCode already supports many sessions within a single directory
        natively (its own web UI has its own "new session" picker, tracked
        in its own opencode.db) — Hub only needs to get you INTO that one
        directory, not fabricate a folder per conversation. If this project
        is already open, this just reconnects to it (same as `resume`)."""
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
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        CHATS_ROOT.mkdir(parents=True, exist_ok=True)

        project_dir = PROJECTS_ROOT / base
        if not project_dir.exists():
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: shutil.copytree(src, project_dir, ignore=COPY_IGNORE))
            except Exception:
                if project_dir.exists():
                    shutil.rmtree(project_dir, ignore_errors=True)
                raise

        chat_dir = CHATS_ROOT / base
        if not chat_dir.exists():
            await _make_junction(chat_dir, project_dir)

        for s in self.sessions.values():
            if s.running and Path(s.cwd) == chat_dir:
                return s
        sess = await self._reserve(name or base, src, chat_dir)
        return await self._launch(sess)

    async def resume(self, folder: str, name: str | None) -> Session:
        """Reopen an existing projects/ or chats/ folder in place — no copy."""
        dest = resolve_workroot_child(folder)
        if dest is None:
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
            cwd = Path(s.cwd)  # NOT resolved — must act on the chat's own path,
                                # never silently follow a junction to its target
            resolved = cwd.resolve()
            roots = (PROJECTS_ROOT.resolve(), CHATS_ROOT.resolve())
            if str(resolved).startswith(str(WORKROOT.resolve())) and resolved not in roots:
                logger.info("OpenCode: removing %s", cwd)
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: _remove_workroot_entry(cwd))

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(sid) for sid in list(self.sessions)), return_exceptions=True)


_migrate_legacy_layout()
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
