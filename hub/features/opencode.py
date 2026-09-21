"""OpenCode feature — a per-project agent RUNTIME.

One `opencode serve` per project. The project's port is a **pure function of its
source path** (hashed into 8100–8139, +1000 for the private serve port) — no
allocation, no in-memory table as source of truth, no race. Opening a project is
idempotent: same project → same port → the same runtime is reused. That is what
makes "open project X and land in project X" reliable, and what a browser tab at
`http://<host>:<port>` can trust across reopens.

The agent works in a **git worktree** of the real repo on branch `agent/<slug>`
(a real, disposable, history-sharing checkout) — never the real working tree.
Review = `git diff`; apply = merge the branch; drop = `git worktree remove`.
Non-git sources get a one-time snapshot repo in the worktree instead.

Two consumers of the same runtime:
  * interactive — a browser window over Tailscale (a small byte-transparent
    forwarder exposes the localhost serve on 0.0.0.0);
  * autonomous — the `/tasks` API drives OpenCode's own session/message API
    headlessly so a utility on top can run agents across many projects.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import time
import zlib
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from .. import agent_knowledge
from .. import locations as LOC
from ..agent_knowledge import status as ak_status
from ..config import PORT as HUB_PORT, logger
from ..platform_win import _assign_to_job

# ── constants ──────────────────────────────────────────────────────────────
OPENCODE_ROOT = Path(LOC.get("opencode_home"))
OPENCODE_EXE = str(OPENCODE_ROOT / "node_modules" / "opencode-ai" / "bin" / "opencode.exe")
OPENCODE_CONFIG = str(OPENCODE_ROOT / "opencode.json")

# git worktrees live here — outside `git repositories\` so a worktree is never
# mistaken for a source project by the graph's folder scan.
WORKTREES = Path(LOC.get("work_dir"))

PUBLIC_BASE = 8100
PORT_SPAN = 40                     # public 8100–8139
INTERNAL_OFFSET = 1000             # private serve on public+1000 (9100–9139)
PUBLIC_RANGE = range(PUBLIC_BASE, PUBLIC_BASE + PORT_SPAN)
INTERNAL_RANGE = range(PUBLIC_BASE + INTERNAL_OFFSET, PUBLIC_BASE + PORT_SPAN + INTERNAL_OFFSET)

# The Scratch workspace — one always-present repo-less workspace (quick chats,
# web searches, MCP calls, repo-less agents), just above the project port band.
SCRATCH_SLUG = "scratch"
SCRATCH_PORT = PUBLIC_BASE + PORT_SPAN          # 8140 (internal 9140)
SCRATCH_DIR = WORKTREES / "_scratch"

# transient stream failure (OpenCode Zen free tier stalls) — auto-resume budget
STREAM_RETRY_BUDGET = 3
_TRANSIENT = re.compile(r"\b504\b|idle timeout|upstream|econnreset|fetch failed|"
                        r"socket hang up|network|timed out", re.I)
# a chat stuck 'busy' longer than this is auto-aborted by the watchdog
WATCHDOG_SECONDS = 720
# model fallback chain for the "continue on a steadier model" action
FALLBACK_MODELS = ["opencode/nemotron-3-ultra-free", "ollama/qwen3.6:32k"]

COPY_IGNORE = shutil.ignore_patterns(
    ".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache", ".ocdata",
)

AGENTS_MD = """# Project context — READ FIRST

This directory is a **git worktree** on branch `agent/<name>` — a disposable,
isolated checkout of the user's repo. Work here freely; the user reviews your
branch with `git diff` and merges or discards it. Do NOT `git checkout` another
branch, and do NOT touch anything outside this folder.
"""

AUTH_ENABLED = os.getenv("AGENT_HUB_OPENCODE_AUTH", "0") == "1"
SERVER_USERNAME = os.getenv("OPENCODE_SERVER_USERNAME", "opencode")
SERVER_PASSWORD = os.getenv("OPENCODE_SERVER_PASSWORD") or secrets.token_urlsafe(9)
OPENCODE_PUBLIC_HOST = os.getenv("OPENCODE_PUBLIC_HOST", "")

routes = web.RouteTableDef()


# ── host / port helpers ────────────────────────────────────────────────────
_tailnet_host_cache: str | None = None


def _tailnet_host() -> str:
    global _tailnet_host_cache
    if _tailnet_host_cache is not None:
        return _tailnet_host_cache
    _tailnet_host_cache = ""
    try:
        from ..config import TAILSCALE_EXE
        out = subprocess.run([TAILSCALE_EXE, "status", "--json"],
                             capture_output=True, text=True, timeout=5)
        name = (json.loads(out.stdout).get("Self") or {}).get("DNSName", "")
        _tailnet_host_cache = name.rstrip(".")
    except Exception:
        _tailnet_host_cache = ""
    return _tailnet_host_cache


def _public_host(request_host: str) -> str:
    if OPENCODE_PUBLIC_HOST:
        return OPENCODE_PUBLIC_HOST
    bare = (request_host or "").split(":")[0]
    if bare in ("", "127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return _tailnet_host() or bare or "localhost"
    return bare


def _port_bindable(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _listening(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.25)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def _pids_listening_on(port_range: range) -> set[int]:
    pids: set[int] = set()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                             capture_output=True, text=True, timeout=6).stdout
    except Exception:
        return pids
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        try:
            if int(parts[1].rsplit(":", 1)[1]) in port_range:
                pids.add(int(parts[4]))
        except (ValueError, IndexError):
            continue
    return pids


def _kill_pids(pids: set[int], why: str) -> None:
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=6)
            logger.warning("OpenCode: killed pid=%s (%s)", pid, why)
        except Exception:
            pass


# ── model list + resilient fallback ────────────────────────────────────────
# OpenCode Zen rotates its free tier (an id that worked last month 404s today),
# which silently no-ops every agent request. We enumerate what OpenCode can
# actually reach and, when the configured id isn't in that set, fall back:
# free → another free → local (ollama/vllm). Only self-hosted / BYO-key ids
# never rotate — see SETUP.md.
_model_cache: dict = {"at": 0.0, "models": []}
_MODEL_TTL = 600.0


def _classify_model(mid: str) -> dict:
    prov = mid.split("/", 1)[0] if "/" in mid else ""
    low = mid.lower()
    return {
        "provider": prov, "id": mid, "label": mid,
        "free": low.endswith("-free") or "free" in low,
        "local": prov in ("ollama", "vllm", "lmstudio", "llamacpp"),
    }


def _probe_models_cli(timeout: float = 10.0) -> list[dict]:
    """`opencode models` → [{provider,id,label,free,local}]. [] on any failure
    (the caller then leaves the configured id untouched — no worse than today)."""
    try:
        env = os.environ.copy()
        env["OPENCODE_CONFIG"] = OPENCODE_CONFIG
        out = subprocess.run([OPENCODE_EXE, "models"], capture_output=True, text=True,
                             timeout=timeout, env=env).stdout
    except Exception as exc:
        logger.warning("OpenCode: `opencode models` probe failed: %s", exc)
        return []
    seen: dict[str, dict] = {}
    for line in out.splitlines():
        tok = line.strip().split()
        if not tok:
            continue
        mid = tok[0]
        if "/" not in mid or mid.startswith("-"):
            continue
        seen.setdefault(mid, _classify_model(mid))
    return list(seen.values())


def _known_models(force: bool = False) -> list[dict]:
    now = time.time()
    if not force and _model_cache["models"] and now - _model_cache["at"] < _MODEL_TTL:
        return _model_cache["models"]
    models = _probe_models_cli()
    if models:
        _model_cache.update(at=now, models=models)
    return _model_cache["models"]


def _resolve_model(want: str, known: list[dict]) -> tuple[str, str | None]:
    """(id_to_use, note). note is set only when we had to substitute."""
    if not want or not known:
        return want, None
    ids = {m["id"] for m in known}
    if want in ids:
        return want, None
    for m in known:                                   # another free cloud id
        if m["free"] and not m["local"]:
            return m["id"], f"'{want}' is unavailable — using free '{m['id']}'"
    for m in known:                                   # any local model
        if m["local"]:
            return m["id"], f"'{want}' is unavailable — using local '{m['id']}'"
    return known[0]["id"], f"'{want}' is unavailable — using '{known[0]['id']}'"


# ── project identity ───────────────────────────────────────────────────────
def _canonical(source: str | Path) -> Path:
    raw = str(source).strip().strip('"').strip()
    if "%" in raw:
        try:
            raw = unquote(raw)
        except Exception:
            pass
    return Path(raw).resolve()


def _slug(source: Path) -> str:
    """Stable, filesystem-safe id for a project from its canonical path.
    Same path → same slug → same port → same runtime, always."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip("-").lower() or "project"
    tag = format(zlib.crc32(str(source).lower().encode()) & 0xFFFFFF, "06x")
    return f"{base}-{tag}"


def _hash_port(slug: str) -> int:
    return PUBLIC_BASE + (zlib.crc32(slug.encode()) % PORT_SPAN)


# public helpers for status.py / graph.py
def slug_for(source: str | Path) -> str:
    return _slug(_canonical(source))


def worktree_for(source: str | Path) -> Path:
    """The worktree path for a project (whether or not it exists yet)."""
    return WORKTREES / slug_for(source)


# ── git worktree ───────────────────────────────────────────────────────────
async def _git(cwd: Path, *args: str, timeout: float = 30) -> tuple[int, str]:
    try:
        p = await asyncio.create_subprocess_exec(
            "git", "-c", "core.autocrlf=false", *args, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
        return p.returncode or 0, out.decode("utf-8", "replace").strip()
    except Exception as exc:
        return 1, str(exc)


async def _default_branch(repo: Path) -> str:
    rc, out = await _git(repo, "symbolic-ref", "--short", "HEAD")
    if rc == 0 and out:
        return out
    for cand in ("main", "master"):
        rc, _ = await _git(repo, "rev-parse", "--verify", cand)
        if rc == 0:
            return cand
    return "HEAD"


# Files the hub drops into a worktree — never "the agent changed the project".
# A linked worktree SHARES .git/info/exclude with the main repo, so we must NOT
# write there (it would pollute the user's real repo). status.py filters these
# out of the diff/state instead; a local .git/info/exclude for the snapshot case
# is safe because that repo is ours alone.
HUB_SCAFFOLDING = frozenset({
    "AGENTS.md", "opencode.json", ".agent-hub-base", ".agent-hub-ready-to-push",
    ".agent-hub-origin", ".opencode", ".claude", ".hub-ref",
})
# git pathspecs that keep hub scaffolding + the per-project data dir out of every
# `git add` / `git diff` the hub runs — so it never lands in the user's branch.
_SCAFFOLD_EXCLUDE = (
    tuple(f":(exclude){n}" for n in sorted(HUB_SCAFFOLDING))
    + (":(exclude).ocdata", ":(exclude)**/__pycache__/**", ":(exclude)**/*.pyc",
       ":(exclude)node_modules/**", ":(exclude).venv/**")
)


def _exclude_scaffolding_snapshot(wt: Path) -> None:
    """Only for a hub-owned snapshot repo (non-git source) — safe to write its
    own .git/info/exclude."""
    try:
        info = wt / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text(
            "\n".join(sorted(HUB_SCAFFOLDING) + [".ocdata/"]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _write_origin(wt: Path, source: Path) -> None:
    """Record the source folder inside the worktree so an orphan (source folder
    later deleted) can still show where it came from. Best-effort, scaffolding."""
    try:
        marker = wt / ".agent-hub-origin"
        if not marker.exists():
            marker.write_text(json.dumps(
                {"source": str(source), "created": time.time()}), encoding="utf-8")
    except Exception:
        pass


def read_origin(wt: Path) -> str:
    """Best-effort original source path for a worktree, for the graph's orphan
    nodes. Tries the marker, then the git-linked `.git` pointer file."""
    try:
        data = json.loads((wt / ".agent-hub-origin").read_text(encoding="utf-8"))
        src = (data or {}).get("source")
        if src:
            return src
    except Exception:
        pass
    try:                                     # linked git worktree: .git is a file
        gitfile = wt / ".git"
        if gitfile.is_file():
            line = gitfile.read_text(encoding="utf-8").strip()
            if line.startswith("gitdir:"):
                gd = Path(line.split(":", 1)[1].strip())
                # <source>/.git/worktrees/<slug>  →  <source>
                parts = gd.parts
                if "worktrees" in parts:
                    i = parts.index("worktrees")
                    if i >= 2 and parts[i - 1] == ".git":
                        return str(Path(*parts[: i - 1]))
    except Exception:
        pass
    return ""


def materialize_agents(dest: Path, *, base_branch: str, slug: str,
                       headless: bool) -> list[str]:
    """Write the baseline persona team into <dest>/.opencode/agent/ and create
    each worker's writable subdir + the shared area. Returns the roster (not the
    always-materialised utility agents). Shared by Runtime and the mission runner."""
    team = agent_knowledge.default_team()
    roster = team.get("roster") or []
    write_names = list(dict.fromkeys(roster + list(agent_knowledge.UTILITY_AGENTS)))
    if not write_names:
        return []
    agent_dir = dest / ".opencode" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (dest / "shared").mkdir(exist_ok=True)
    for nm in write_names:
        (dest / "agents" / nm).mkdir(parents=True, exist_ok=True)
        txt = agent_knowledge.render_agent_file(
            nm, subdir=f"agents/{nm}", roster=roster,
            base_branch=base_branch, slug=slug, headless=headless)
        if txt:
            (agent_dir / f"{nm}.md").write_text(txt, encoding="utf-8")
    return list(roster)


async def merge_branch(source: Path, branch: str, base: str) -> dict:
    """Merge `branch` into `base` in the `source` repo — only when it's safely on
    `base` with a clean tree; else hand back the exact command. Used by /merge and
    a mission's APPLY."""
    hint = f'git -C "{source}" merge --no-ff {branch}'
    cur = (await _git(source, "symbolic-ref", "--short", "HEAD"))[1]
    _, dirty = await _git(source, "status", "--porcelain")
    if cur != base or dirty.strip():
        return {"ok": False, "branch": branch, "base": base,
                "reason": f"source repo is on '{cur}'"
                          + (" with uncommitted changes" if dirty.strip() else ""),
                "run_this": hint}
    rc, out = await _git(source, "merge", "--no-ff", "-m", f"merge {branch}", branch)
    return {"ok": rc == 0, "output": out, "branch": branch}


async def _ensure_worktree(source: Path, slug: str) -> dict:
    """Return {worktree, branch, base, vcs}. Idempotent — reuses an existing
    worktree/branch so a project's agent work persists across reopens."""
    wt = WORKTREES / slug
    branch = f"agent/{slug}"
    WORKTREES.mkdir(parents=True, exist_ok=True)

    is_git = (source / ".git").exists()
    if is_git:
        await _git(source, "worktree", "prune")
        base = await _default_branch(source)
        if not wt.exists():
            rc, _ = await _git(source, "rev-parse", "--verify", branch)
            if rc == 0:                      # resume prior agent work
                rc, out = await _git(source, "worktree", "add", str(wt), branch)
            else:                            # fresh branch off base
                rc, out = await _git(source, "worktree", "add", str(wt), "-b", branch, base)
            if rc != 0 and not wt.exists():
                rc, out = await _git(source, "worktree", "add", "--force", str(wt), "-B", branch, base)
                if rc != 0:
                    raise RuntimeError(f"git worktree add failed: {out}")
        try:
            (wt / ".agent-hub-base").write_text(base, encoding="utf-8")
        except Exception:
            pass
        _write_origin(wt, source)
        return {"worktree": wt, "branch": branch, "base": base, "vcs": "git"}

    # non-git source: one-time snapshot repo in the worktree
    if not wt.exists():
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: shutil.copytree(source, wt, ignore=COPY_IGNORE))
        await _git(wt, "init")
        await _git(wt, "add", "-A")
        await _git(wt, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "-m", "snapshot", "--allow-empty")
        await _git(wt, "branch", "-M", "base")
        await _git(wt, "checkout", "-B", branch)
    try:
        (wt / ".agent-hub-base").write_text("base", encoding="utf-8")
    except Exception:
        pass
    _write_origin(wt, source)
    _exclude_scaffolding_snapshot(wt)
    return {"worktree": wt, "branch": branch, "base": "base", "vcs": "snapshot"}


async def _ensure_scratch() -> dict:
    """The pinned 'quick chat' repo — a standalone git repo so /diff and chat
    history behave, but not tied to any source project."""
    wt = SCRATCH_DIR
    wt.mkdir(parents=True, exist_ok=True)
    if not (wt / ".git").exists():
        await _git(wt, "init")
        await _git(wt, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "--allow-empty", "-m", "scratch")
        await _git(wt, "branch", "-M", "base")
    try:
        (wt / ".agent-hub-base").write_text("base", encoding="utf-8")
    except Exception:
        pass
    _exclude_scaffolding_snapshot(wt)
    return {"worktree": wt, "branch": "base", "base": "base", "vcs": "snapshot"}


# ── the runtime ────────────────────────────────────────────────────────────
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


class Runtime:
    """One `opencode serve` for one project worktree + the public forwarder."""

    def __init__(self, slug: str, source: Path, wt: dict, mode: str) -> None:
        self.slug = slug
        self.source = str(source)
        self.worktree = wt["worktree"]
        self.branch = wt["branch"]
        self.base = wt["base"]
        self.vcs = wt["vcs"]
        self.mode = mode
        self.port = _hash_port(slug)          # may be re-set by the manager on collision
        self.proc: asyncio.subprocess.Process | None = None
        self.forwarder: asyncio.AbstractServer | None = None
        self.created_at = time.time()
        self.status = "starting"
        self.model: str | None = None        # what the serve is actually using
        self.model_note: str | None = None   # set when we had to fall back
        self.agents: list[str] = []          # persona names materialized into the worktree
        self._ui_dir: str | None = None      # base64 {dir} for the SPA session deep-link
        self.stream_retries: dict[str, int] = {}   # sessionID -> auto-resume attempts
        self.last_error: dict[str, str] = {}       # sessionID -> last stream error text
        self._busy_since: dict[str, float] = {}    # sessionID -> monotonic when it went busy
        self._bg: list[asyncio.Task] = []          # event watcher + watchdog

    @property
    def internal_port(self) -> int:
        return self.port + INTERNAL_OFFSET

    async def ui_dir(self) -> str:
        """The `{dir}` segment for OpenCode's SPA session deep-link
        `/{dir}/session/{id}` — `base64url(utf8(directory))`. Uses the directory
        string OpenCode itself reports so the encoding always matches."""
        if self._ui_dir:
            return self._ui_dir
        directory = str(self.worktree)
        try:
            st, data = await self._api("GET", "project", timeout=4)
            if st and st < 400:
                if isinstance(data, list) and data:
                    directory = data[0].get("worktree") or directory
                elif isinstance(data, dict):
                    directory = data.get("worktree") or directory
        except Exception:
            pass
        self._ui_dir = base64.urlsafe_b64encode(directory.encode()).decode().rstrip("=")
        return self._ui_dir

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def open_url(self, host: str) -> str:
        return f"http://{_public_host(host)}:{self.port}"

    def as_dict(self, host: str) -> dict:
        return {
            "slug": self.slug, "folder": self.slug, "name": Path(self.source).name,
            "source": self.source, "worktree": str(self.worktree),
            "branch": self.branch, "base": self.base, "vcs": self.vcs, "mode": self.mode,
            "port": self.port, "internal_port": self.internal_port,
            "running": self.alive, "status": self.status if self.alive else "stopped",
            "open_url": self.open_url(host), "created": self.created_at,
            "scratch": self.slug == SCRATCH_SLUG,
            "model": self.model, "model_note": self.model_note, "agents": list(self.agents),
        }

    async def _api(self, method: str, path: str, **kw) -> tuple[int, object]:
        """Call the private opencode serve API. The real routes live at the
        ROOT (`/project`, `/session`, ...); `/api/<path>` is the SPA catch-all
        and returns index.html with 200 — so we accept a response ONLY when it
        is actually JSON, and try the bare path first."""
        base = f"http://127.0.0.1:{self.internal_port}"
        timeout = aiohttp.ClientTimeout(total=kw.pop("timeout", 15))
        p = path.lstrip("/")
        async with aiohttp.ClientSession() as s:
            for url in (f"{base}/{p}", f"{base}/api/{p}"):
                try:
                    async with s.request(method, url, timeout=timeout, **kw) as r:
                        if r.status == 404:
                            continue
                        ct = r.headers.get("Content-Type", "")
                        if "json" in ct.lower():
                            return r.status, await r.json()
                        body = await r.text()
                        if body[:1] in ("{", "["):
                            try:
                                return r.status, json.loads(body)
                            except Exception:
                                pass
                        # HTML / non-JSON — this spelling is the SPA, keep looking
                        continue
                except Exception:
                    continue
        return 0, None

    async def _served_worktree(self) -> str | None:
        st, data = await self._api("GET", "project", timeout=3)
        if st and st < 500:
            if isinstance(data, list) and data:
                return data[0].get("worktree") or ""
            if isinstance(data, dict):
                return data.get("worktree") or ""
        return None

    async def serves_this_project(self) -> bool:
        wt = await self._served_worktree()
        if wt is None:
            return False
        if wt in ("", "/", "\\"):
            return True   # up, worktree not recorded yet — the isolated DB guarantees it's ours
        try:
            return Path(wt).resolve() == self.worktree.resolve()
        except Exception:
            return False

    async def start(self) -> None:
        dest = self.worktree
        data_dir = dest / ".ocdata"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # AGENTS.md (project-aware, else the generic guard rails)
        agents = dest / "AGENTS.md"
        if not agents.exists():
            try:
                agents.write_text(agent_knowledge.render_agents_md(self.slug, dest), encoding="utf-8")
            except Exception:
                try:
                    agents.write_text(AGENTS_MD, encoding="utf-8")
                except Exception:
                    pass

        # session config: shared base + knowledge layer + per-mode permission
        session_cfg = dest / "opencode.json"
        try:
            base_cfg = json.loads(Path(OPENCODE_CONFIG).read_text(encoding="utf-8"))
        except Exception:
            base_cfg = {}
        try:
            cfg = agent_knowledge.apply_session_config(base_cfg, self.slug, dest)
        except Exception:
            cfg = base_cfg
        if self.mode == "autonomous":
            cfg["permission"] = {"edit": "allow", "bash": "allow", "webfetch": "allow",
                                 "skill": {"*": "allow"}}
        else:
            cfg.setdefault("permission", {"edit": "ask", "bash": "ask", "webfetch": "ask"})
            if isinstance(cfg["permission"], dict):
                cfg["permission"].setdefault("skill", {"*": "allow"})

        # resolve model ids against what OpenCode can actually reach right now
        try:
            known = await asyncio.get_running_loop().run_in_executor(None, _known_models)
            for key in ("model", "small_model"):
                want = cfg.get(key)
                if not isinstance(want, str) or not want:
                    continue
                got, note = _resolve_model(want, known)
                if got != want:
                    cfg[key] = got
                    if key == "model":
                        self.model_note = note
                    logger.warning("OpenCode %s: %s", self.slug, note)
            self.model = cfg.get("model")
        except Exception as exc:
            logger.warning("OpenCode %s: model resolve skipped: %s", self.slug, exc)

        try:
            session_cfg.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

        # materialize the agent team into <worktree>/.opencode/agent/ — every
        # workspace (Scratch included) can start chats with any agent
        try:
            self._materialize_agents(dest)
        except Exception as exc:
            logger.warning("OpenCode %s: agent team materialize skipped: %s", self.slug, exc)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["OPENCODE_CONFIG"] = str(session_cfg)
        env["XDG_DATA_HOME"] = str(data_dir)      # per-project opencode.db — no shared "current project" row
        if AUTH_ENABLED:
            env["OPENCODE_SERVER_USERNAME"] = SERVER_USERNAME
            env["OPENCODE_SERVER_PASSWORD"] = SERVER_PASSWORD

        logger.info("OpenCode: starting runtime %s mode=%s internal=%d public=%d wt=%s",
                    self.slug, self.mode, self.internal_port, self.port, self.worktree)
        log_path = data_dir / "serve.log"
        try:
            log_f = open(log_path, "w", encoding="utf-8")
        except Exception:
            log_f = asyncio.subprocess.DEVNULL
        self._log_f = log_f
        self.proc = await asyncio.create_subprocess_exec(
            OPENCODE_EXE, "serve", "--hostname", "127.0.0.1", "--port", str(self.internal_port),
            "--print-logs",
            cwd=str(dest), env=env,
            stdout=log_f, stderr=asyncio.subprocess.STDOUT)
        _assign_to_job(self.proc.pid)

        await self._wait_ready()

        async def _handle(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            try:
                ur, uw = await asyncio.open_connection("127.0.0.1", self.internal_port)
            except Exception:
                try:
                    w.close()
                except Exception:
                    pass
                return
            await asyncio.gather(_pipe(r, uw), _pipe(ur, w), return_exceptions=True)

        self.forwarder = await asyncio.start_server(_handle, "0.0.0.0", self.port)
        self.status = "running"
        logger.info("OpenCode: runtime %s forwarder up on 0.0.0.0:%d", self.slug, self.port)
        self._bg = [asyncio.create_task(self._watch_events()),
                    asyncio.create_task(self._watchdog())]

    def _materialize_agents(self, dest: Path) -> None:
        self.agents = materialize_agents(dest, base_branch=self.base, slug=self.slug,
                                         headless=(self.mode == "autonomous"))
        logger.info("OpenCode %s: materialized agents %s", self.slug, self.agents)

    async def _wait_ready(self, timeout: float = 40.0) -> None:
        deadline = time.monotonic() + timeout
        first_ok = None
        while time.monotonic() < deadline:
            if not self.alive:
                self.status = "exited"
                raise RuntimeError(f"opencode serve for {self.slug} exited during startup")
            wt = await self._served_worktree()
            if wt is not None:                       # server answered
                first_ok = first_ok or time.monotonic()
                if wt in ("", "/", "\\"):
                    if time.monotonic() - first_ok > 2:   # up, isolated DB → it's ours
                        return
                elif Path(wt).resolve() == self.worktree.resolve():
                    return
                else:
                    raise RuntimeError(
                        f"internal port {self.internal_port} serves {wt!r}, not {self.worktree} "
                        "— stale process on that port")
            await asyncio.sleep(0.4)
        self.status = "timeout"
        raise RuntimeError(f"opencode serve for {self.slug} not ready in {timeout:.0f}s")

    async def _resume(self, sid: str, text: str = "continue") -> None:
        await self._api("POST", f"session/{sid}/prompt_async",
                        json={"parts": [{"type": "text", "text": text}]}, timeout=15)

    async def _watch_events(self) -> None:
        """Follow the serve's /event SSE. On a transient stream failure
        (Zen free-tier stall), auto-resume the affected chat up to the budget."""
        url = f"http://127.0.0.1:{self.internal_port}/event"
        while self.alive:
            try:
                to = aiohttp.ClientTimeout(total=None, sock_read=None)
                async with aiohttp.ClientSession(timeout=to) as s:
                    async with s.get(url) as up:
                        async for raw in up.content:
                            line = raw.decode("utf-8", "replace").strip()
                            if not line.startswith("data:"):
                                continue
                            try:
                                ev = json.loads(line[5:].strip())
                            except Exception:
                                continue
                            await self._on_event(ev)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(3)      # serve blipped — reconnect

    async def _on_event(self, ev: dict) -> None:
        t = ev.get("type", "")
        p = ev.get("properties", {}) or {}
        sid = p.get("sessionID") or (p.get("info") or {}).get("id")
        if t in ("session.status",):
            st = (p.get("status") or {}).get("type")
            if sid and st == "busy":
                self._busy_since.setdefault(sid, time.monotonic())
            elif sid:
                self._busy_since.pop(sid, None)
        elif t in ("session.idle",):
            if sid:
                self._busy_since.pop(sid, None)
        elif t in ("session.error", "message.error"):
            err = json.dumps(p.get("error") or p)[:300]
            if not sid:
                return
            self.last_error[sid] = err
            n = self.stream_retries.get(sid, 0)
            if _TRANSIENT.search(err) and n < STREAM_RETRY_BUDGET:
                self.stream_retries[sid] = n + 1
                logger.warning("OpenCode %s: transient stream error on %s — auto-resume %d/%d",
                               self.slug, sid, n + 1, STREAM_RETRY_BUDGET)
                await asyncio.sleep(2 + 2 * n)
                await self._resume(sid)

    async def _watchdog(self) -> None:
        while self.alive:
            try:
                await asyncio.sleep(30)
                cutoff = time.monotonic() - WATCHDOG_SECONDS
                for sid, since in list(self._busy_since.items()):
                    if since < cutoff:
                        logger.warning("OpenCode %s: watchdog aborting %s (busy > %ds)",
                                       self.slug, sid, WATCHDOG_SECONDS)
                        self.stream_retries.pop(sid, None)
                        self._busy_since.pop(sid, None)
                        self.last_error[sid] = "timed_out"
                        await self._api("POST", f"session/{sid}/abort", timeout=10)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.info("OpenCode %s: watchdog blip: %s", self.slug, exc)

    async def stop(self) -> None:
        for t in self._bg:
            t.cancel()
        self._bg = []
        if self.forwarder is not None:
            try:
                self.forwarder.close()
                await asyncio.wait_for(self.forwarder.wait_closed(), timeout=2)
            except Exception:
                pass
            self.forwarder = None
        if self.proc is not None:
            try:
                tk = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(self.proc.pid),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(tk.wait(), timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except Exception:
                pass
        self.status = "stopped"


# ── the manager ────────────────────────────────────────────────────────────
class Manager:
    def __init__(self) -> None:
        self.runtimes: dict[str, Runtime] = {}     # cache; the OS port state is the truth
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, slug: str) -> asyncio.Lock:
        lk = self._locks.get(slug)
        if lk is None:
            lk = self._locks[slug] = asyncio.Lock()
        return lk

    def _pick_port(self, slug: str) -> int:
        """Deterministic hash, then a deterministic linear probe for the first
        pair that is either free or already ours for this slug."""
        want = _hash_port(slug)
        mine = {r.port for s, r in self.runtimes.items() if s != slug and r.alive}
        for i in range(PORT_SPAN):
            p = PUBLIC_BASE + ((want - PUBLIC_BASE) + i) % PORT_SPAN
            if p in mine:
                continue
            cur = self.runtimes.get(slug)
            if cur and cur.alive and cur.port == p:
                return p
            if _port_bindable(p) and _port_bindable(p + INTERNAL_OFFSET):
                return p
        raise RuntimeError(f"no free OpenCode port in {PUBLIC_BASE}-{PUBLIC_BASE + PORT_SPAN - 1}")

    async def open_scratch(self) -> Runtime:
        """The pinned 'quick chat' runtime — no project, fixed port."""
        async with self._lock(SCRATCH_SLUG):
            rt = self.runtimes.get(SCRATCH_SLUG)
            if rt and rt.alive and await rt.serves_this_project():
                return rt
            if rt:
                await rt.stop()
                self.runtimes.pop(SCRATCH_SLUG, None)
            wt = await _ensure_scratch()
            rt = Runtime(SCRATCH_SLUG, SCRATCH_DIR, wt, "interactive")
            rt.port = SCRATCH_PORT
            try:
                await rt.start()
            except Exception:
                await rt.stop()
                raise
            self.runtimes[SCRATCH_SLUG] = rt
            return rt

    async def open_project(self, source: str, mode: str = "interactive") -> Runtime:
        if (source or "").strip().lower() in ("", "scratch", "_scratch"):
            return await self.open_scratch()
        src = _canonical(source)
        if not src.is_dir():
            raise FileNotFoundError(f"Not a folder: {source}")
        slug = _slug(src)
        async with self._lock(slug):
            rt = self.runtimes.get(slug)
            if rt and rt.alive and rt.mode == mode and await rt.serves_this_project():
                return rt
            if rt:                              # dead, wrong mode, or aliased → restart clean
                await rt.stop()
                self.runtimes.pop(slug, None)

            wt = await _ensure_worktree(src, slug)
            rt = Runtime(slug, src, wt, mode)
            rt.port = self._pick_port(slug)
            try:
                await rt.start()
            except Exception:
                await rt.stop()
                raise
            self.runtimes[slug] = rt
            return rt

    async def open_worktree(self, slug: str, mode: str = "autonomous") -> Runtime:
        """Start a runtime directly on an existing worktree — for an orphan
        (source folder gone) or a stopped worktree we resume by slug. Skips
        `_ensure_worktree`; the `wt` dict is reconstructed from disk."""
        if slug == SCRATCH_SLUG:
            return await self.open_scratch()
        wt = WORKTREES / slug
        if not wt.is_dir():
            raise FileNotFoundError(f"no worktree {slug}")
        async with self._lock(slug):
            rt = self.runtimes.get(slug)
            if rt and rt.alive and rt.mode == mode and await rt.serves_this_project():
                return rt
            if rt:
                await rt.stop()
                self.runtimes.pop(slug, None)
            is_git_file = (wt / ".git").is_file()
            base = "base"
            try:
                b = (wt / ".agent-hub-base").read_text(encoding="utf-8").strip()
                base = b or ("HEAD" if is_git_file else "base")
            except Exception:
                base = "HEAD" if is_git_file else "base"
            wtd = {"worktree": wt, "branch": f"agent/{slug}", "base": base,
                   "vcs": "git" if is_git_file else "snapshot"}
            src = read_origin(wt) or _source_for_slug(slug) or str(wt)
            rt = Runtime(slug, Path(src), wtd, mode)
            rt.port = self._pick_port(slug)
            try:
                await rt.start()
            except Exception:
                await rt.stop()
                raise
            self.runtimes[slug] = rt
            return rt

    async def get(self, slug: str) -> Runtime | None:
        rt = self.runtimes.get(slug)
        if rt and not rt.alive:
            await rt.stop()
            self.runtimes.pop(slug, None)
            return None
        return rt

    async def stop_project(self, slug: str, remove_worktree: bool = False) -> None:
        rt = self.runtimes.pop(slug, None)
        if rt:
            await rt.stop()
        if remove_worktree and slug != SCRATCH_SLUG:
            wt = WORKTREES / slug
            if wt.exists():
                # find the owning repo even when we have no live runtime: a linked
                # worktree's real .git lives in the source repo — remove it there so
                # no stale registration is left; otherwise just delete the dir.
                owner = Path(rt.source) if rt and (Path(rt.source) / ".git").exists() else None
                if owner is None:
                    rc, common = await _git(wt, "rev-parse", "--git-common-dir")
                    if rc == 0 and common and "worktrees" not in Path(common).parts[-2:]:
                        cand = Path(common).parent if Path(common).name == ".git" else Path(common)
                        if (cand / ".git").exists() or cand.name == ".git":
                            owner = cand if cand.name != ".git" else cand.parent
                if owner is not None:
                    await _git(owner, "worktree", "remove", "--force", str(wt))
                    await _git(owner, "worktree", "prune")
                # Windows holds the just-stopped serve's .ocdata db handle for a
                # beat — retry the delete so the dir actually goes.
                for _ in range(6):
                    if not wt.exists():
                        break
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda: shutil.rmtree(wt, ignore_errors=True))
                    if not wt.exists():
                        break
                    await asyncio.sleep(0.5)

    async def reap(self) -> None:
        for slug, rt in list(self.runtimes.items()):
            if not rt.alive:
                await rt.stop()
                self.runtimes.pop(slug, None)
                logger.info("OpenCode: reaped dead runtime %s", slug)

    async def _reaper_loop(self, every: float = 15.0) -> None:
        while True:
            try:
                await asyncio.sleep(every)
                await self.reap()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("OpenCode: reaper iteration failed: %s", exc)

    async def stop_all(self) -> None:
        await asyncio.gather(*(rt.stop() for rt in list(self.runtimes.values())),
                             return_exceptions=True)

    def list(self, host: str) -> list[dict]:
        return [rt.as_dict(host) for rt in self.runtimes.values() if rt.alive]


OC = Manager()


# ── startup housekeeping (runs AFTER the hub is listening — see setup) ──────
def _startup_housekeeping() -> None:
    WORKTREES.mkdir(parents=True, exist_ok=True)
    # kill orphaned serves in our private range from a previous crash — but not
    # if another hub already owns this machine's HUB_PORT.
    if _port_bindable(HUB_PORT):
        sweep = range(INTERNAL_RANGE.start, SCRATCH_PORT + INTERNAL_OFFSET + 1)
        _kill_pids(_pids_listening_on(sweep), "orphaned opencode serve (startup sweep)")
    try:
        from ..agent_knowledge.skills_sync import sync_all
        sync_all()
    except Exception as exc:
        logger.warning("OpenCode: skill library sync skipped: %s", exc)


# ── routes: projects + tasks (the new API) ─────────────────────────────────
async def _body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@routes.get("/api/opencode/projects")
async def oc_projects(request: web.Request) -> web.Response:
    await OC.reap()
    return web.json_response({
        "auth": ({"username": SERVER_USERNAME, "password": SERVER_PASSWORD} if AUTH_ENABLED else None),
        "projects": OC.list(request.host),
        "stopped": _stopped_rows(),
    })


@routes.post("/api/opencode/projects")
async def oc_open(request: web.Request) -> web.Response:
    body = await _body(request)
    source = (body.get("source") or "").strip()          # blank / "scratch" → quick chat
    mode = "autonomous" if body.get("mode") == "autonomous" else "interactive"
    try:
        rt = await OC.open_project(source or "scratch", mode)
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(rt.as_dict(request.host))


@routes.get("/api/opencode/models")
async def oc_models(request: web.Request) -> web.Response:
    force = request.query.get("refresh") == "1"
    models = await asyncio.get_running_loop().run_in_executor(None, lambda: _known_models(force))
    return web.json_response({"models": models, "count": len(models)})


@routes.post("/api/opencode/scratch/clear")
async def oc_scratch_clear(request: web.Request) -> web.Response:
    """Wipe the quick-chat working dir (keep .git and the running serve's db),
    then commit the empty state so /diff is clean again."""
    keep = {".git", ".ocdata"} | HUB_SCAFFOLDING
    if SCRATCH_DIR.is_dir():
        for child in list(SCRATCH_DIR.iterdir()):
            if child.name in keep:
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
            except Exception:
                pass
        await _git(SCRATCH_DIR, "add", "-A")
        await _git(SCRATCH_DIR, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "--allow-empty", "-m", "clear scratch")
    return web.json_response({"ok": True})


@routes.delete("/api/opencode/projects/{slug}")
async def oc_close(request: web.Request) -> web.Response:
    await OC.stop_project(request.match_info["slug"],
                          remove_worktree=request.query.get("remove_worktree") == "1")
    return web.json_response({"ok": True})


async def _start_task(rt: Runtime, prompt: str, agent: str | None) -> str:
    """Create an OpenCode session (optionally bound to a named agent) and post
    the opening prompt WITHOUT blocking on the full turn. Returns the task id."""
    sess_body = {"agent": agent} if agent else {}
    st, sess = await rt._api("POST", "session", json=sess_body)
    if not (st and st < 400) or not isinstance(sess, dict):
        raise web.HTTPBadGateway(text=f"opencode session create failed ({st}): {sess}")
    tid = sess.get("id") or sess.get("sessionID")
    msg: dict = {"parts": [{"type": "text", "text": prompt}]}
    if agent:
        msg["agent"] = agent
    # prefer the fire-and-forget route; fall back to a detached sync post so the
    # HTTP call here still returns immediately while the agent runs server-side.
    st2, _ = await rt._api("POST", f"session/{tid}/prompt_async", json=msg, timeout=15)
    if not st2 or st2 >= 400:
        asyncio.create_task(rt._api("POST", f"session/{tid}/message", json=msg, timeout=1800))
    return tid


@routes.post("/api/opencode/projects/{slug}/tasks")
async def oc_task_start(request: web.Request) -> web.Response:
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    body = await _body(request)
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise web.HTTPBadRequest(text="prompt is required")
    agent = (body.get("agent") or "").strip() or None
    if agent is None and rt.mode == "autonomous":
        agent = "orchestrator" if "orchestrator" in rt.agents else None
    tid = await _start_task(rt, prompt, agent)
    return web.json_response({"task_id": tid, "slug": rt.slug, "agent": agent})


@routes.get("/api/opencode/projects/{slug}/tasks/{tid}")
async def oc_task_status(request: web.Request) -> web.Response:
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    tid = request.match_info["tid"]
    st, hist = await rt._api("GET", f"session/{tid}/message", timeout=10)
    _, kids = await rt._api("GET", f"session/{tid}/children", timeout=10)
    changed = await _worktree_changes(rt)
    return web.json_response({"task_id": tid, "http": st, "messages": hist,
                              "children": kids if isinstance(kids, list) else [],
                              "changed_files": changed})


@routes.get("/api/opencode/projects/{slug}/agents")
async def oc_agents(request: web.Request) -> web.Response:
    """The baseline persona team + which agents the live serve has discovered."""
    rt = await OC.get(request.match_info["slug"])
    team = agent_knowledge.default_team()
    defined = agent_knowledge.list_agents()
    live: object = []
    if rt is not None:
        _, live = await rt._api("GET", "agent", timeout=5)
    detailed = []
    for a in defined:
        p = agent_knowledge._load_persona(a["name"]) or {}
        detailed.append({**a, "frontmatter": p.get("frontmatter", {}),
                         "body": p.get("body", ""),
                         "origin": "user" if agent_knowledge.is_user_agent(a["name"]) else "baseline"})
    return web.json_response({
        "team": team, "defined": detailed,
        "overrides": agent_knowledge.load_overrides(),
        "materialized": list(rt.agents) if rt else [],
        "live": live if isinstance(live, list) else [],
    })


# ── workspace chats: the unified chat view's data (§4) ────────────────────
@routes.get("/api/opencode/projects/{slug}/chats")
async def oc_chats(request: web.Request) -> web.Response:
    """Sessions in this workspace's serve + the base64 {dir} for the SPA
    deep-link + a live busy/idle status map. The chat view nests children by
    parentID and points each iframe at `<root_url>/session/<id>`."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such workspace")
    # the iframe loads from the SAME host the hub page was served on (loopback
    # for local, the tailnet name for a tailnet client) — not the public-host
    # rewrite, which is only for OPEN-in-a-new-window.
    host = (request.host or "127.0.0.1").split(":")[0]
    ui = await rt.ui_dir()
    _, sessions = await rt._api("GET", "session", timeout=10)
    _, statuses = await rt._api("GET", "session/status", timeout=6)
    smap = statuses if isinstance(statuses, dict) else {}
    chats = []
    for s in (sessions if isinstance(sessions, list) else []):
        sid = s.get("id") or s.get("sessionID")
        if not sid:
            continue
        chats.append({
            "id": sid, "agent": s.get("agent"), "title": s.get("title") or "",
            "parentID": s.get("parentID"),
            "created": (s.get("time") or {}).get("created") or 0,
            "status": (smap.get(sid) or {}).get("type", "idle"),
            "retries": rt.stream_retries.get(sid, 0),
            "error": rt.last_error.get(sid, ""),
            "url": f"http://{host}:{rt.port}/{ui}/session/{sid}",
        })
    chats.sort(key=lambda c: c["created"])
    return web.json_response({
        "open_url": rt.open_url(request.host), "ui_dir": ui,
        "root_url": f"http://{host}:{rt.port}/{ui}",
        "mode": rt.mode, "scratch": rt.slug == SCRATCH_SLUG,
        "agents": list(rt.agents), "chats": chats,
    })


@routes.post("/api/opencode/projects/{slug}/chats")
async def oc_chat_new(request: web.Request) -> web.Response:
    """Start a new chat bound to an agent (default: none → OpenCode's `build`)."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such workspace")
    body = await _body(request)
    agent = (body.get("agent") or "").strip() or None
    message = (body.get("message") or "").strip()
    st, sess = await rt._api("POST", "session", json={"agent": agent} if agent else {})
    if not (st and st < 400) or not isinstance(sess, dict):
        raise web.HTTPBadGateway(text=f"session create failed ({st}): {sess}")
    sid = sess.get("id") or sess.get("sessionID")
    if message:
        msg: dict = {"parts": [{"type": "text", "text": message}]}
        if agent:
            msg["agent"] = agent
        st2, _ = await rt._api("POST", f"session/{sid}/prompt_async", json=msg, timeout=15)
        if not st2 or st2 >= 400:
            asyncio.create_task(rt._api("POST", f"session/{sid}/message", json=msg, timeout=1800))
    host = (request.host or "127.0.0.1").split(":")[0]
    ui = await rt.ui_dir()
    return web.json_response({"id": sid, "agent": agent,
                             "url": f"http://{host}:{rt.port}/{ui}/session/{sid}"})


@routes.post("/api/opencode/projects/{slug}/chats/{sid}/abort")
async def oc_chat_abort(request: web.Request) -> web.Response:
    """Abort a chat's current turn — cascades to any `task`-spawned subagents."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such workspace")
    sid = request.match_info["sid"]
    rt.stream_retries.pop(sid, None)             # cancel any pending auto-resume
    st, _ = await rt._api("POST", f"session/{sid}/abort", timeout=10)
    return web.json_response({"ok": bool(st and st < 400), "http": st})


@routes.post("/api/opencode/projects/{slug}/chats/{sid}/model")
async def oc_chat_model(request: web.Request) -> web.Response:
    """Switch a chat's model mid-run (the 504 fallback), optionally resume it."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such workspace")
    sid = request.match_info["sid"]
    body = await _body(request)
    model = (body.get("model") or "").strip()
    if not model:
        raise web.HTTPBadRequest(text="model is required")
    prov, _, mid = model.partition("/")
    st, _ = await rt._api("POST", f"session/{sid}/model",
                          json={"providerID": prov, "modelID": mid or prov}, timeout=10)
    if not st or st >= 400:
        st, _ = await rt._api("POST", f"session/{sid}/model", json={"model": model}, timeout=10)
    if body.get("resume"):
        rt.stream_retries.pop(sid, None)
        await rt._api("POST", f"session/{sid}/prompt_async",
                      json={"parts": [{"type": "text", "text": "continue"}]}, timeout=15)
    return web.json_response({"ok": bool(st and st < 400), "http": st, "model": model})


# ── slug-keyed worktree routes (orphans / resume-by-slug — no source needed) ─
@routes.post("/api/opencode/folders/{slug}/open")
async def oc_folder_open(request: web.Request) -> web.Response:
    body = await _body(request)
    mode = "autonomous" if body.get("mode") == "autonomous" else "interactive"
    try:
        rt = await OC.open_worktree(request.match_info["slug"], mode)
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(rt.as_dict(request.host))


@routes.get("/api/opencode/folders/{slug}/changes")
async def oc_folder_changes(request: web.Request) -> web.Response:
    wt = WORKTREES / request.match_info["slug"]
    if not wt.is_dir():
        raise web.HTTPNotFound(text="no such worktree")
    return web.json_response({"changed_files": await ak_status.worktree_changed_files(wt),
                              "origin": read_origin(wt)})


@routes.get("/api/opencode/folders/{slug}/diff")
async def oc_folder_diff(request: web.Request) -> web.Response:
    wt = WORKTREES / request.match_info["slug"]
    if not wt.is_dir():
        raise web.HTTPNotFound(text="no such worktree")
    rel = request.query.get("path")
    if rel:
        return web.Response(text=await ak_status.worktree_file_diff(wt, rel),
                            content_type="text/plain")
    await _git(wt, "add", "-N", "--", *_SCAFFOLD_EXCLUDE, ".")
    _, out = await _git(wt, "--no-pager", "diff", ak_status._wt_base(wt), "--", *_SCAFFOLD_EXCLUDE)
    return web.Response(text=out, content_type="text/plain")


# ── agent library: save / settings / delete (§5) ─────────────────────────
@routes.post("/api/opencode/agents")
async def oc_agent_save(request: web.Request) -> web.Response:
    """Save a persona .md into agents_user/ (gitignored, personal)."""
    body = await _body(request)
    name = (body.get("name") or "").strip()
    text = body.get("text") or ""
    if not name or not text.strip():
        raise web.HTTPBadRequest(text="name and text are required")
    p = agent_knowledge.save_user_agent(name, text)
    return web.json_response({"ok": True, "name": p.stem, "path": str(p)})


@routes.delete("/api/opencode/agents/{name}")
async def oc_agent_delete(request: web.Request) -> web.Response:
    ok = agent_knowledge.delete_user_agent(request.match_info["name"])
    return web.json_response({"ok": ok})


@routes.post("/api/opencode/agents/{name}/settings")
async def oc_agent_settings(request: web.Request) -> web.Response:
    """Per-agent LLM knobs → agent_overrides.json (applied on next workspace start)."""
    body = await _body(request)
    patch = {k: body.get(k) for k in ("model", "temperature", "top_p", "variant", "steps")}
    if isinstance(body.get("options"), dict):
        patch["options"] = body["options"]
    agent_knowledge.save_override(request.match_info["name"], patch)
    return web.json_response({"ok": True, "overrides": agent_knowledge.load_overrides()})


@routes.post("/api/opencode/projects/{slug}/orchestrate")
async def oc_orchestrate(request: web.Request) -> web.Response:
    """Kick off a goal under the orchestrator agent — it decomposes and delegates
    to the worker team via OpenCode's `task` tool."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    body = await _body(request)
    goal = (body.get("goal") or "").strip()
    if not goal:
        raise web.HTTPBadRequest(text="goal is required")
    if "orchestrator" not in rt.agents:
        raise web.HTTPBadRequest(text="this workspace has no orchestrator persona")
    prompt = (
        f"GOAL: {goal}\n\n"
        "Decompose this into sub-tasks and delegate each to the right worker "
        "agent (coder / reviewer / researcher / tester / doc-writer) via the "
        "`task` tool. Write your plan to shared/PLAN.md first, keep it updated, "
        "and finish with shared/SUMMARY.md."
    )
    tid = await _start_task(rt, prompt, "orchestrator")
    return web.json_response({"task_id": tid, "slug": rt.slug, "agent": "orchestrator"})


@routes.get("/api/opencode/projects/{slug}/activity")
async def oc_activity(request: web.Request) -> web.StreamResponse:
    """Server-Sent Events proxy of the project serve's own /event stream."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream", "Cache-Control": "no-cache",
        "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })
    await resp.prepare(request)
    url = f"http://127.0.0.1:{rt.internal_port}/event"
    try:
        timeout = aiohttp.ClientTimeout(total=None, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as up:
                async for chunk in up.content.iter_any():
                    await resp.write(chunk)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    except Exception as exc:
        logger.info("OpenCode %s: activity stream ended: %s", rt.slug, exc)
    return resp


@routes.get("/api/opencode/projects/{slug}/changes")
async def oc_changes(request: web.Request) -> web.Response:
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    return web.json_response({"changed_files": await _worktree_changes(rt)})


@routes.get("/api/opencode/projects/{slug}/diff")
async def oc_diff(request: web.Request) -> web.Response:
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    # intent-to-add new files so they appear in the diff, but never the
    # hub's own scaffolding / the per-project .ocdata dir
    await _git(rt.worktree, "add", "-N", "--", *_SCAFFOLD_EXCLUDE, ".")
    rc, out = await _git(rt.worktree, "--no-pager", "diff", rt.base, "--", *_SCAFFOLD_EXCLUDE)
    return web.Response(text=out, content_type="text/plain")


@routes.post("/api/opencode/projects/{slug}/merge")
async def oc_merge(request: web.Request) -> web.Response:
    """Commit the agent's pending work onto `agent/<slug>`, then merge that
    branch into the source repo's base branch — but ONLY when the source repo
    is safely on `base` with a clean tree. Otherwise hand back the exact
    command so the user merges it themselves. Never auto-merges into whatever
    branch the source happens to be sitting on."""
    rt = await OC.get(request.match_info["slug"])
    if rt is None:
        raise web.HTTPNotFound(text="no such open project")
    if rt.vcs != "git":
        raise web.HTTPBadRequest(text="merge only applies to a git-backed project")
    src = Path(rt.source)
    await _git(rt.worktree, "add", "-A", "--", *_SCAFFOLD_EXCLUDE)
    await _git(rt.worktree, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
               "commit", "-m", "agent work", "--allow-empty")
    res = await merge_branch(src, rt.branch, rt.base)
    return web.json_response(res, status=200 if res.get("ok") else 409)


def _source_for_slug(slug: str) -> str:
    """Best-effort slug → source folder path ("" if it can't be resolved)."""
    if slug == SCRATCH_SLUG:
        return "scratch"
    rt = OC.runtimes.get(slug)
    if rt:
        return rt.source
    try:
        from ..agent_knowledge.projects import discover_projects, discover_local_projects
        for p in list(discover_projects()) + list(discover_local_projects()):
            if slug_for(p["path"]) == slug:
                return p["path"]
    except Exception:
        pass
    return ""


def _stopped_rows() -> list[dict]:
    """Worktree dirs on disk with no live runtime — RESUME-able rows for the UI."""
    rows: list[dict] = []
    if not WORKTREES.is_dir():
        return rows
    for d in sorted(WORKTREES.iterdir(),
                    key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if not d.is_dir() or d.name == "_scratch":
            continue
        rt = OC.runtimes.get(d.name)
        if rt and rt.alive:
            continue
        src = _source_for_slug(d.name)
        rows.append({
            "slug": d.name, "folder": d.name,
            "name": Path(src).name if src else d.name,
            "source": src, "worktree": str(d), "running": False, "status": "stopped",
            "scratch": False, "open_url": "", "model": None, "model_note": None, "agents": [],
        })
    return rows


def _is_scaffolding_path(p: str) -> bool:
    p = p.strip().strip('"')
    return (p in HUB_SCAFFOLDING or p == "serve.log"
            or p.startswith(".ocdata") or p.startswith(".opencode"))


async def _worktree_changes(rt: Runtime) -> list[dict]:
    """Committed diff vs base + uncommitted working changes, hub scaffolding
    filtered out."""
    seen: dict[str, str] = {}
    rc, out = await _git(rt.worktree, "--no-pager", "diff", "--name-status", f"{rt.base}...HEAD")
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and not _is_scaffolding_path(parts[-1]):
                seen[parts[-1]] = parts[0][:1]
    rc2, dirty = await _git(rt.worktree, "status", "--porcelain")
    if rc2 == 0:
        for line in dirty.splitlines():
            if not line.strip():
                continue
            code = line[:2].strip()
            rest = line[2:].strip().strip('"')
            path = rest.split(" -> ")[-1].strip().strip('"')
            if path and not _is_scaffolding_path(path):
                seen[path] = (code[:1] or "M").replace("?", "A")
    return [{"status": s, "path": p} for p, s in sorted(seen.items())]


# ── routes: back-compat adapters for the /graph panel ─────────────────────
@routes.get("/api/opencode/sessions")
async def oc_sessions(request: web.Request) -> web.Response:
    await OC.reap()
    return web.json_response({
        "auth": ({"username": SERVER_USERNAME, "password": SERVER_PASSWORD} if AUTH_ENABLED else None),
        "sessions": OC.list(request.host),
        "stopped": _stopped_rows(),
    })


@routes.post("/api/opencode/sessions")
async def oc_sessions_create(request: web.Request) -> web.Response:
    return await oc_open(request)


@routes.post("/api/opencode/sessions/resume")
async def oc_sessions_resume(request: web.Request) -> web.Response:
    body = await _body(request)
    folder = (body.get("folder") or "").strip()          # an opencode project slug
    source = (body.get("source") or "").strip()
    if not source and folder:
        source = _source_for_slug(folder)
    if not source:
        raise web.HTTPBadRequest(text="cannot resolve a source folder for that project")
    return await oc_open_with(request, source)


async def oc_open_with(request: web.Request, source: str) -> web.Response:
    try:
        rt = await OC.open_project(source, "interactive")
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(rt.as_dict(request.host))


@routes.post("/api/opencode/sessions/{slug}/stop")
async def oc_sessions_stop(request: web.Request) -> web.Response:
    await OC.stop_project(request.match_info["slug"])
    return web.json_response({"ok": True})


@routes.delete("/api/opencode/sessions/{slug}")
async def oc_sessions_delete(request: web.Request) -> web.Response:
    await OC.stop_project(request.match_info["slug"],
                          remove_worktree=request.query.get("purge") == "1")
    return web.json_response({"ok": True})


@routes.get("/api/opencode/folders")
async def oc_folders(request: web.Request) -> web.Response:
    # existing worktrees, for a "resume" list
    out = []
    if WORKTREES.is_dir():
        for d in sorted(WORKTREES.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0,
                        reverse=True):
            if d.is_dir() and d.name != "_scratch":
                active = d.name in OC.runtimes
                out.append({"folder": d.name, "path": str(d), "active": active,
                            "active_session": active, "mtime": d.stat().st_mtime})
    return web.json_response(out)


def setup(app: web.Application) -> None:
    async def _housekeeping_soon() -> None:
        # a beat after the server is answering — keeps cold start fast
        await asyncio.sleep(0.5)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _startup_housekeeping)
        except Exception as exc:
            logger.warning("OpenCode: startup housekeeping failed: %s", exc)

    async def _on_startup(_app: web.Application) -> None:
        _app["oc_reaper"] = asyncio.create_task(OC._reaper_loop())
        _app["oc_housekeeping"] = asyncio.create_task(_housekeeping_soon())

    async def _on_cleanup(_app: web.Application) -> None:
        t = _app.get("oc_reaper")
        if t:
            t.cancel()
        await OC.stop_all()

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
