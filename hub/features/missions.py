"""Missions — distributed autonomous agent runs.

A **mission** is one `opencode run` against its own git worktree on a throwaway
branch: a precise brief handed to one agent, run headless to completion, its
result reviewed as a diff and applied or discarded. An **orchestrator** mission
plans a goal into a set of sub-briefs which the hub dispatches as their own
missions (possibly other projects).

    opencode run --dir <worktree> --agent <name> [-m <model>] --format json "<brief>"

emits NDJSON events (step_start / tool_use / step_finish / text / reasoning /
error) and exits 0 (done) or 1 (any error).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path

from aiohttp import web

from .. import agent_knowledge, app_registry, config
from ..config import logger
from ..platform_win import _assign_to_job
from . import opencode as OCM   # reuse worktree / model / merge / materialize helpers
from . import claude_runtime as CRT   # second runtime: Claude Code CLI, alongside OpenCode

routes = web.RouteTableDef()

MISSIONS_DIR = OCM.WORKTREES / "_missions"
MISSION_TIMEOUT = 900          # a mission running longer than this is flagged/timed out
QUIET_DONE_SECS = 20           # idle this long after the agent's final "stop" → done
EVENT_KEEP = 300               # events held in memory per mission for the SSE tail
FALLBACK_MODELS = ["ollama/qwen3.6:latest", "opencode/nemotron-3-ultra-free"]

# an error string that means "the provider blipped", not "the code is wrong" —
# worth a retry / model fallback rather than failing the mission
_TRANSIENT_RE = re.compile(
    r"50[234]\b|overload|upstream error|idle timeout|ECONNRESET|ETIMEDOUT|"
    r"rate.?limit|too many requests|temporarily|unavailable|stream (?:ended|closed)",
    re.I)


def _looks_transient(text: str) -> bool:
    return bool(text and _TRANSIENT_RE.search(text))

_ACTIVE = {"running", "queued", "blocked", "proposed"}
_TERMINAL = {"applied", "discarded", "failed", "timed_out"}

# a mission's private working copy on disk is "<project-slug[:32]>--m<hex8>"
_MID_RE = re.compile(r"^(?P<slug>.+)--(?P<mid>m[0-9a-f]{8})$")


# ── model ─────────────────────────────────────────────────────────────────
@dataclass
class Mission:
    id: str
    project_slug: str
    project_path: str
    project_name: str
    brief: str
    agent: str
    kind: str                       # "single" | "team" | "parallel" | "orchestrator"
    status: str                     # see _ACTIVE + awaiting_review/applied/discarded/failed/timed_out
    runtime: str = "opencode"       # "opencode" | "claude-code" — which agent backend runs it
    worktree: str = ""
    branch: str = ""
    base_branch: str = ""
    parent_id: str | None = None
    model: str | None = None
    model_note: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    error: str = ""
    depends_on: list[str] = field(default_factory=list)
    changed_files: list[dict] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)   # team: ordered relay; parallel: unused
    group_id: str | None = None                       # parallel drafts share one
    session_id: str = ""                              # opencode session, for OPEN TRANSCRIPT
    created: float = field(default_factory=time.time)
    ended: float | None = None

    def summary(self) -> dict:
        return {
            "id": self.id, "project_slug": self.project_slug, "project_name": self.project_name,
            "brief": self.brief, "agent": self.agent, "kind": self.kind, "status": self.status,
            "runtime": self.runtime,
            "parent_id": self.parent_id, "model": self.model, "model_note": self.model_note,
            "changed": len(self.changed_files), "error": self.error[:200],
            "exit_code": self.exit_code, "pid": self.pid,
            "created": self.created, "ended": self.ended, "depends_on": list(self.depends_on),
            "worktree": self.worktree, "agents": list(self.agents), "group_id": self.group_id,
            "session_id": self.session_id,
        }


# ── store ─────────────────────────────────────────────────────────────────
class Store:
    def __init__(self) -> None:
        self.m: dict[str, Mission] = {}
        self.events: dict[str, deque] = {}          # id -> recent parsed events
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, mid: str) -> asyncio.Lock:
        return self._locks.setdefault(mid, asyncio.Lock())

    def load(self) -> None:
        MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
        for f in MISSIONS_DIR.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                m = Mission(**d)
                # a mission that was 'running' when the hub died is orphaned
                if m.status in ("running", "queued"):
                    m.status = "failed"
                    m.error = m.error or "hub restarted while running"
                self.m[m.id] = m
            except Exception as exc:
                logger.warning("missions: could not load %s: %s", f.name, exc)

    def save(self, m: Mission) -> None:
        try:
            (MISSIONS_DIR / f"{m.id}.json").write_text(
                json.dumps(asdict(m), indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("missions: could not save %s: %s", m.id, exc)

    def forget(self, mid: str) -> None:
        self.m.pop(mid, None)
        self.events.pop(mid, None)
        try:
            (MISSIONS_DIR / f"{mid}.json").unlink()
        except Exception:
            pass


S = Store()


# ── helpers ───────────────────────────────────────────────────────────────
def _new_id() -> str:
    return "m" + uuid.uuid4().hex[:8]


def _projects() -> list[dict]:
    from ..agent_knowledge.projects import discover_projects
    return [p for p in discover_projects() if not p.get("readonly")]


def _resolve_project(ref: str, same_path: str | None = None) -> dict | None:
    """A project reference from the NEW-MISSION form or an orchestrator plan:
    'same' | a discovery slug | a folder name | an absolute path."""
    ref = (ref or "").strip()
    if not ref or ref.lower() == "same":
        if same_path:
            p = Path(same_path)
            return {"slug": OCM.slug_for(p), "name": p.name, "path": str(p)}
        return None
    projs = _projects()
    for p in projs:                                   # exact slug
        if p["slug"] == ref:
            return p
    low = ref.lower()
    for p in projs:                                   # name / basename match
        if p["name"].lower() == low or Path(p["path"]).name.lower() == low:
            return p
    pth = Path(ref)
    if pth.is_dir():
        return {"slug": OCM.slug_for(pth), "name": pth.name, "path": str(pth)}
    return None


async def _scaffold_new_project(name: str) -> dict:
    """`project: "new:<name>"` — create a fresh git repo under
    `git repositories/_unsorted projects/<name>` so a mission can build it from
    scratch and APPLY into a real base branch."""
    from ..agent_knowledge.projects import REPOS_ROOT
    safe = re.sub(r"[^A-Za-z0-9 ._-]", "", (name or "").strip()).strip(" .")
    if not safe:
        raise web.HTTPBadRequest(text="a project name is required")
    dest = REPOS_ROOT / "_unsorted projects" / safe
    if dest.exists():
        raise web.HTTPBadRequest(text=f"'{safe}' already exists — pick another name")
    dest.mkdir(parents=True)
    await OCM._git(dest, "init")
    await OCM._git(dest, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "--allow-empty", "-m", f"init {safe}")
    await OCM._git(dest, "branch", "-M", "main")
    logger.info("missions: scaffolded new project %s", dest)
    return {"slug": OCM.slug_for(dest), "name": safe, "path": str(dest)}


def _reconcile_orphans() -> None:
    """Surface mission working copies present on disk that `S.m` doesn't know
    about (JSON cleared, hub reinstalled, crash mid-run) so the board matches
    what the graph shows. Disk-derived rows are `status='orphaned'`; a real
    action (apply / discard) persists them."""
    root = OCM.WORKTREES
    if not root.is_dir():
        return
    # disk-derived rows track the disk exactly: if the working copy is gone, so
    # is the row (a real mission is persisted and never dropped here).
    for mid, m in list(S.m.items()):
        if m.status == "orphaned" and not Path(m.worktree or "").is_dir():
            S.m.pop(mid, None)
            S.events.pop(mid, None)
    known_wt = {m.worktree for m in S.m.values() if m.worktree}
    try:
        entries = sorted(root.iterdir())
    except Exception:
        return
    for d in entries:
        if not d.is_dir() or d.name in ("_missions", "_scratch"):
            continue
        mo = _MID_RE.match(d.name)
        if not mo:
            continue
        mid = mo.group("mid")
        if mid in S.m or str(d) in known_wt:
            continue
        origin = OCM.read_origin(d)
        try:
            base = (d / ".agent-hub-base").read_text(encoding="utf-8").strip() or "main"
        except Exception:
            base = "main"
        name = (Path(origin).name if origin else mo.group("slug").replace("-", " ")) or d.name
        S.m[mid] = Mission(
            id=mid, project_slug=(OCM.slug_for(origin) if origin else mo.group("slug")),
            project_path=(origin or str(d)), project_name=name,
            brief="(recovered — the original brief isn't on disk)", agent="?",
            kind="single", status="orphaned", worktree=str(d),
            branch=f"agent/{d.name}", base_branch=base,
            error="Recovered from disk; its mission record was gone.")
        S.events.setdefault(mid, deque(maxlen=EVENT_KEEP))


def _parse_events_text(events: list[dict]) -> list[dict]:
    """Compact the raw NDJSON into UI rows. Handles both OpenCode's event shape
    (type: step_start/tool_use/text/reasoning/error/step_finish, a `part` dict)
    and Claude Code's stream-json shape (type: system/assistant/user/result,
    `message.content[]` blocks) — found missing entirely (claude-code missions
    showed a silently empty activity feed) while comparing the two runtimes."""
    rows = []
    for e in events:
        t = e.get("type")
        if t in ("step_start", "tool_use", "text", "reasoning", "error", "step_finish"):
            p = e.get("part") or {}
            if t == "step_start":
                rows.append({"k": "step", "text": (p.get("phase") or "step")})
            elif t == "tool_use":
                st = (p.get("state") or {})
                inp = st.get("input") or {}
                hint = inp.get("filePath") or inp.get("command") or inp.get("pattern") or inp.get("path") or ""
                rows.append({"k": "tool", "text": f"{p.get('tool','tool')} {str(hint)[:80]}".strip(),
                             "status": st.get("status", "")})
            elif t == "text":
                tx = (p.get("text") or "").strip()
                if tx:
                    rows.append({"k": "text", "text": tx[:400]})
            elif t == "reasoning":
                rows.append({"k": "reasoning", "text": "thinking…"})
            elif t == "error":
                rows.append({"k": "error", "text": json.dumps(e.get("error") or e)[:300]})
            elif t == "step_finish":
                r = p.get("reason") or ""
                if r and r != "tool-calls":
                    rows.append({"k": "step", "text": f"finished ({r})"})
            continue
        if t == "assistant":
            for c in ((e.get("message") or {}).get("content") or []):
                ct = c.get("type")
                if ct == "text":
                    tx = (c.get("text") or "").strip()
                    if tx:
                        rows.append({"k": "text", "text": tx[:400]})
                elif ct == "thinking":
                    rows.append({"k": "reasoning", "text": "thinking…"})
                elif ct == "tool_use":
                    inp = c.get("input") or {}
                    hint = inp.get("file_path") or inp.get("command") or inp.get("pattern") or inp.get("path") or ""
                    rows.append({"k": "tool", "text": f"{c.get('name','tool')} {str(hint)[:80]}".strip(),
                                 "status": "completed"})
        elif t == "result":
            if e.get("is_error"):
                rows.append({"k": "error", "text": (e.get("result") or json.dumps(e))[:300]})
            else:
                rows.append({"k": "step", "text":
                    f"finished ({e.get('subtype', 'done')}, {e.get('num_turns', '?')} turns)"})
        elif t == "system" and e.get("subtype") == "api_retry":
            rows.append({"k": "error", "text": f"retrying: {e.get('error', 'transient error')}"})
        elif t == "system" and e.get("subtype") == "error":
            rows.append({"k": "error", "text": e.get("error") or "error"})
        # "system/init" and "user" (tool_result feedback) are protocol noise, not
        # agent activity — deliberately not rendered.
    return rows[-EVENT_KEEP:]


def _plan_from_jsonl(jsonl: Path) -> list[dict]:
    """Pull the orchestrator's fenced ```json {"missions":[...]} block out of its
    text output."""
    try:
        text = "\n".join(
            (json.loads(l).get("part") or {}).get("text", "")
            for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()
        )
    except Exception:
        return []
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj.get("missions"), list):
                return obj["missions"]
        except Exception:
            continue
    return []


# ── dispatch / run ────────────────────────────────────────────────────────
async def dispatch(project: dict, brief: str, agent: str, kind: str,
                   model: str | None = None, parent_id: str | None = None,
                   depends_on: list[str] | None = None,
                   agents: list[str] | None = None,
                   group_id: str | None = None,
                   runtime: str = "opencode") -> Mission:
    mid = _new_id()
    src = Path(project["path"])
    if not src.is_dir():
        raise FileNotFoundError(f"project folder gone: {src}")
    mslug = f"{project['slug'][:32]}--{mid}"
    wt = await OCM._ensure_worktree(src, mslug)      # own private copy + branch agent/<mslug>

    m = Mission(id=mid, project_slug=project["slug"], project_path=str(src),
                project_name=project["name"], brief=brief, agent=agent, kind=kind,
                status="blocked" if depends_on else "running",
                runtime=runtime if runtime in ("opencode", "claude-code") else "opencode",
                worktree=str(wt["worktree"]), branch=wt["branch"], base_branch=wt["base"],
                parent_id=parent_id, model=model, depends_on=list(depends_on or []),
                agents=list(agents or []), group_id=group_id)
    S.m[mid] = m
    S.events[mid] = deque(maxlen=EVENT_KEEP)
    S.save(m)
    if m.status == "running":
        asyncio.create_task(_run_team(m) if kind == "team" else _run(m))
    return m


# ── auto-ingest: git URL → a hub-fronted app ──────────────────────────────
_INGEST_SCHEMA = '''{
  "id": "<kebab-case>", "name": "<Display Name>", "emoji": "<one emoji>",
  "cmd": ["$PYTHON", "app.py"], "port": 8110, "serve": "direct",
  "health_path": "/", "idle_minutes": 20,
  "install": ["$PYTHON", "-m", "pip", "install", "-r", "requirements.txt"],
  "env": {"HOST": "0.0.0.0", "PORT": "8110"}
}'''


async def _clone_for_ingest(url: str, slug: str, branch: str | None) -> dict:
    OCM.WORKTREES.mkdir(parents=True, exist_ok=True)
    wt = OCM.WORKTREES / slug
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    args = ["clone", "--depth", "1"]
    if branch:
        args += ["--branch", branch]
    args += [url, str(wt)]
    rc, out = await OCM._git(OCM.WORKTREES, *args, timeout=240)
    if rc != 0 or not (wt / ".git").exists():
        raise RuntimeError(f"git clone failed: {(out or '')[-300:]}")
    _, b = await OCM._git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    base = (b or "main").strip() or "main"
    wbranch = f"agent/{slug}"
    await OCM._git(wt, "checkout", "-b", wbranch)
    return {"worktree": wt, "branch": wbranch, "base": base}


def _ingest_brief(url: str, id_hint: str, name: str | None, emoji: str | None) -> str:
    hint = []
    if name:
        hint.append(f'Use the name "{name}".')
    else:
        hint.append(f'Suggested id: "{id_hint}".')
    if emoji:
        hint.append(f'Use the emoji "{emoji}".')
    return (
        f"This folder is a fresh clone of {url}. Onboard it as a hub app.\n\n"
        "Work out: framework · the one-shot install command · the argv command to "
        "run its web server (`$PYTHON` token for Python) · the PORT it listens on "
        "(if configurable, pick a free port in 8110-8199 and pin it) · a health "
        "path that returns 200. Make it bind 0.0.0.0 (via env/args) so the hub can "
        "reach it over the tailnet.\n\n"
        "Do NOT start its web server to verify — a compile/import check plus "
        "reading the entrypoint is enough (a running server blocks forever).\n\n"
        "Write `app-hub.json` at the repo root (schema below; `serve` is always "
        '"direct") and `HUB_INGEST.md` (what it is, how it runs, the port, anything '
        "unusual — a DB, an API key, a build step). " + " ".join(hint) + "\n\n"
        f"SCHEMA:\n{_INGEST_SCHEMA}\n\n"
        "End `DONE:` with a one-line manifest summary, or `BLOCKED:` with exactly "
        "what's missing."
    )


async def dispatch_ingest(url: str, name: str | None = None, emoji: str | None = None,
                          branch: str | None = None) -> Mission:
    url = (url or "").strip()
    if not re.match(r"^(https?://|git@)", url):
        raise ValueError("give an http(s):// or git@ URL")
    mid = _new_id()
    raw = (name or url.rstrip("/").split("/")[-1]).replace(".git", "")
    id_hint = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "app"
    slug = f"ingest-{id_hint[:24]}--{mid}"
    wt = await _clone_for_ingest(url, slug, (branch or "").strip() or None)
    m = Mission(id=mid, project_slug=id_hint, project_path=url,
                project_name=(name or id_hint).strip() or id_hint,
                brief=_ingest_brief(url, id_hint, name, emoji),
                agent="app-ingestor", kind="ingest-app", status="running",
                worktree=str(wt["worktree"]), branch=wt["branch"], base_branch=wt["base"])
    S.m[mid] = m
    S.events[mid] = deque(maxlen=EVENT_KEEP)
    S.save(m)
    asyncio.create_task(_run(m))
    return m


async def _apply_ingest(m: Mission) -> dict:
    """WIRE IN: read the agent's app-hub.json, copy the clone into
    hub/ingested_apps/<id>/, run its install once, register it."""
    wt = Path(m.worktree)
    mf = wt / "app-hub.json"
    if not mf.is_file():
        return {"ok": False, "reason": "the agent didn't write app-hub.json — open the transcript"}
    try:
        man = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": f"app-hub.json isn't valid JSON: {exc}"}
    aid = re.sub(r"[^a-z0-9-]+", "-", str(man.get("id") or m.project_slug).lower()).strip("-") or "app"
    if not man.get("cmd") or not man.get("port"):
        return {"ok": False, "reason": "the manifest is missing `cmd` or `port`"}
    if aid in config.APPS:
        return {"ok": False, "reason": f"an app '{aid}' is already wired in — remove it first"}

    dest = app_registry.INGESTED / aid
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(
        ".git", ".ocdata", ".opencode", "AGENTS.md", "opencode.json", "app-hub.json",
        "HUB_INGEST.md", ".agent-hub-base", ".agent-hub-origin",
        ".agent-hub-ready-to-push", "__pycache__", "*.pyc")
    await asyncio.get_running_loop().run_in_executor(
        None, lambda: shutil.copytree(wt, dest, ignore=ignore))

    entry = {
        "id": aid, "name": man.get("name") or m.project_name or aid,
        "emoji": man.get("emoji") or "\U0001F4E6",
        "cwd": f"$HUB/ingested_apps/{aid}",
        "cmd": [str(a) for a in man["cmd"]], "port": int(man["port"]),
        "serve": man.get("serve") or "direct",
        "base_path": man.get("base_path") or f"/app/{aid}",
        "health_path": man.get("health_path") or "/",
        "idle_minutes": int(man.get("idle_minutes") or 20),
        "install": [str(a) for a in man["install"]] if man.get("install") else None,
        "env": {str(k): str(v) for k, v in (man.get("env") or {}).items()},
        "builtin": False, "source": m.project_path, "hidden": False,
    }
    if entry["install"]:
        icmd = [sys.executable if a == "$PYTHON" else a for a in entry["install"]]
        try:
            p = await asyncio.create_subprocess_exec(
                *icmd, cwd=str(dest), stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(p.communicate(), timeout=900)
            if p.returncode != 0:
                shutil.rmtree(dest, ignore_errors=True)
                return {"ok": False, "reason": "install failed:\n"
                        + (err or b"").decode("utf-8", "replace")[-600:]}
            (dest / ".hub-installed").write_text("ok", encoding="utf-8")
        except Exception as exc:
            shutil.rmtree(dest, ignore_errors=True)
            return {"ok": False, "reason": f"install error: {exc}"}

    app_registry.add(entry)
    config.reload_apps()
    try:
        from ..supervisor import rebuild_app_procs
        rebuild_app_procs()
    except Exception as exc:
        logger.warning("ingest %s: rebuild_app_procs failed: %s", m.id, exc)
    m.status = "applied"
    S.save(m)
    return {"ok": True, "app_id": aid, "serve": entry["serve"],
            "note": f"'{entry['name']}' wired in — open the hub menu and START it"}


async def _prepare(m: Mission, wt: Path, data_dir: Path) -> None:
    """Persona files + autonomous opencode.json + AGENTS.md + resolved model,
    written once into the mission's private copy."""
    data_dir.mkdir(parents=True, exist_ok=True)
    roster = agent_knowledge.default_team().get("roster") or []
    names = list(dict.fromkeys(roster + list(agent_knowledge.UTILITY_AGENTS)))
    if m.runtime == "claude-code":
        try:
            CRT.materialize_agents(wt, names, agent_knowledge._load_persona)
        except Exception as exc:
            logger.warning("missions %s: claude persona materialize failed: %s", m.id, exc)
        return   # opencode.json / AGENTS.md / model-resolve below are OpenCode-specific
    try:
        adir = wt / ".opencode" / "agent"
        adir.mkdir(parents=True, exist_ok=True)
        for nm in names:
            txt = agent_knowledge.render_agent_file(
                nm, subdir=f"agents/{nm}", roster=roster,
                base_branch=m.base_branch, slug=m.branch, mission=True, headless=True)
            if txt:
                (adir / f"{nm}.md").write_text(txt, encoding="utf-8")
    except Exception as exc:
        logger.warning("missions %s: persona materialize failed: %s", m.id, exc)

    try:
        base_cfg = json.loads(Path(OCM.OPENCODE_CONFIG).read_text(encoding="utf-8"))
    except Exception:
        base_cfg = {}
    try:
        cfg = agent_knowledge.apply_session_config(base_cfg, m.branch, wt)
    except Exception:
        cfg = base_cfg
    cfg["permission"] = {"edit": "allow", "bash": "allow", "webfetch": "allow",
                         "skill": {"*": "allow"}}
    want_model = m.model or agent_knowledge.resolved_default_model(cfg.get("model"))
    try:
        known = await asyncio.get_running_loop().run_in_executor(None, OCM._known_models)
        got, note = OCM._resolve_model(want_model, known) if want_model else (want_model, None)
        if got and got != want_model:
            m.model_note = note
        m.model = got or want_model
        if m.model:
            cfg["model"] = m.model
    except Exception:
        m.model = want_model
    try:
        (wt / "opencode.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        (wt / "AGENTS.md").write_text(
            agent_knowledge.render_agents_md(m.branch, wt), encoding="utf-8")
    except Exception:
        pass


async def _stream_one(m: Mission, wt: Path, data_dir: Path, agent: str, brief: str,
                      *, phase: str = "") -> tuple[int, bool]:
    """One `opencode run` for `agent` in `wt`; stream its NDJSON into the mission;
    return (exit_code, saw_final_stop). Appends to mission.jsonl / mission.log."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["XDG_DATA_HOME"] = str(data_dir)
    env["OPENCODE_CONFIG"] = str(wt / "opencode.json")

    cmd = [OCM.OPENCODE_EXE, "run", "--dir", str(wt), "--agent", agent, "--format", "json"]
    if m.model:
        cmd += ["-m", m.model]
    cmd.append(brief)
    logger.info("missions %s: %s%s  (%s)", m.id, agent,
                f" [{phase}]" if phase else "", brief[:70])
    jsonl = data_dir / "mission.jsonl"
    errlog = data_dir / "mission.log"
    try:
        errf = open(errlog, "a", encoding="utf-8")
    except Exception:
        errf = asyncio.subprocess.DEVNULL
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(wt), env=env, stdout=asyncio.subprocess.PIPE, stderr=errf)
    _assign_to_job(proc.pid)
    m.pid = proc.pid
    S.procs[m.id] = proc

    st = {"last": time.monotonic(), "stop": False}

    async def _quiet_killer() -> None:
        while proc.returncode is None:
            await asyncio.sleep(8)
            if st["stop"] and time.monotonic() - st["last"] > QUIET_DONE_SECS:
                logger.info("missions %s: idle after stop — finishing", m.id)
                try:
                    proc.kill()
                except Exception:
                    pass
                return

    killer = asyncio.create_task(_quiet_killer())
    if phase:
        S.events[m.id].append({"type": "step_start", "part": {"phase": phase}})
    try:
        with open(jsonl, "a", encoding="utf-8") as jf:
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                jf.write(line)
                jf.flush()
                st["last"] = time.monotonic()
                s = line.strip()
                if not s:
                    continue
                try:
                    ev = json.loads(s)
                except Exception:
                    continue
                S.events[m.id].append(ev)
                if not m.session_id:
                    p = ev.get("part") or {}
                    info = ev.get("info") or {}
                    sid = (ev.get("sessionID") or p.get("sessionID") or p.get("sessionId")
                           or info.get("sessionID") or info.get("id")
                           or (ev.get("properties") or {}).get("sessionID"))
                    if isinstance(sid, str) and sid:
                        m.session_id = sid
                if ev.get("type") == "error":
                    m.error = json.dumps(ev.get("error") or ev)[:400]
                if ev.get("type") == "step_finish" and (ev.get("part") or {}).get("reason") == "stop":
                    st["stop"] = True
    except Exception as exc:
        logger.info("missions %s: stream ended: %s", m.id, exc)

    rc = await proc.wait()
    killer.cancel()
    S.procs.pop(m.id, None)
    return rc, st["stop"]


async def _stream_one_claude(m: Mission, wt: Path, data_dir: Path, agent: str, brief: str,
                             *, phase: str = "") -> tuple[int, bool]:
    """The claude-code counterpart to `_stream_one` — same signature, same
    return contract, same S.events/mission.jsonl sink, so _finalize/diff/apply/
    discard/the SSE tail need no changes at all. See claude_runtime.py."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    model = m.model if m.model and "/" not in m.model else None   # skip opencode-shaped ids
    cmd = CRT.build_cmd(brief=brief, agent=agent, model=model)
    logger.info("missions %s: claude %s%s  (%s)", m.id, agent,
                f" [{phase}]" if phase else "", brief[:70])
    jsonl = data_dir / "mission.jsonl"
    errlog = data_dir / "mission.log"
    try:
        errf = open(errlog, "a", encoding="utf-8")
    except Exception:
        errf = asyncio.subprocess.DEVNULL
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(wt), env=env, stdout=asyncio.subprocess.PIPE, stderr=errf)
    _assign_to_job(proc.pid)
    m.pid = proc.pid
    S.procs[m.id] = proc

    stop = False
    if phase:
        S.events[m.id].append({"type": "step_start", "part": {"phase": phase}})
    try:
        with open(jsonl, "a", encoding="utf-8") as jf:
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                jf.write(line)
                jf.flush()
                s = line.strip()
                if not s:
                    continue
                try:
                    ev = json.loads(s)
                except Exception:
                    continue
                S.events[m.id].append(ev)
                if not m.session_id:
                    sid = CRT.extract_session_id(ev)
                    if sid:
                        m.session_id = sid
                err = CRT.error_text(ev)
                if err:
                    m.error = err
                if CRT.is_stop_event(ev):
                    stop = True
    except Exception as exc:
        logger.info("missions %s: claude stream ended: %s", m.id, exc)

    rc = await proc.wait()
    S.procs.pop(m.id, None)
    return rc, stop


async def _stream_resilient_claude(m: Mission, wt: Path, data_dir: Path, agent: str, brief: str,
                                   *, phase: str = "") -> tuple[int, bool]:
    """`-p` mode is documented to exit on its own (unlike `opencode run`), and
    the Claude API doesn't have OpenCode Zen's free-tier flakiness — so this
    only retries the SAME call on a transient network blip, no cross-provider
    model-chain walk (that chain is OpenCode-model-shaped and meaningless
    here; the CLI's own --fallback-model would be the equivalent, not yet wired)."""
    rc, stop = 1, False
    for attempt in range(3):
        m.error = ""
        rc, stop = await _stream_one_claude(m, wt, data_dir, agent, brief, phase=phase)
        if rc == 0 or stop:
            return rc, stop
        if not _looks_transient(m.error):
            return rc, stop
        if attempt < 2:
            wait = 3 * (attempt + 1) ** 2
            S.events[m.id].append({"type": "error", "error":
                f"claude: transient error — retrying in {wait}s ({attempt + 1}/2)"})
            await asyncio.sleep(wait)
    return rc, stop


async def _stream_resilient(m: Mission, wt: Path, data_dir: Path, agent: str, brief: str,
                            *, phase: str = "") -> tuple[int, bool]:
    """`_stream_one` wrapped in retry + model fallback. On a transient provider
    error (502 / overloaded / idle-timeout) it retries the same model twice with
    backoff, then walks the model chain. A real (code) failure returns straight
    away — no point retrying that."""
    if m.runtime == "claude-code":
        return await _stream_resilient_claude(m, wt, data_dir, agent, brief, phase=phase)
    try:
        ws_model = json.loads(Path(OCM.OPENCODE_CONFIG).read_text(encoding="utf-8")).get("model")
    except Exception:
        ws_model = None
    chain = agent_knowledge.model_chain(m.model or None, ws_model)
    rc, stop = 1, False
    for ci, model in enumerate(chain):
        m.model = model
        if ci > 0:
            S.events[m.id].append({"type": "error",
                                   "error": f"→ falling back to {model}"})
            m.model_note = f"fell back to {model} after a provider error"
        for attempt in range(3):
            m.error = ""
            rc, stop = await _stream_one(m, wt, data_dir, agent, brief, phase=phase)
            if rc == 0 or stop:
                return rc, stop
            tail = ""
            try:
                tail = (data_dir / "mission.log").read_text(encoding="utf-8")[-800:]
            except Exception:
                pass
            if not _looks_transient(f"{m.error} {tail}"):
                return rc, stop                       # genuine failure — stop here
            if attempt < 2:
                wait = 3 * (attempt + 1) ** 2         # 3s, 12s
                S.events[m.id].append({"type": "error", "error":
                    f"{model}: transient error — retrying in {wait}s ({attempt + 1}/2)"})
                await asyncio.sleep(wait)
    return rc, stop


async def _finalize(m: Mission, wt: Path, data_dir: Path, rc: int, stop: bool) -> None:
    async with S.lock(m.id):
        m.exit_code = rc
        m.ended = time.time()
        try:
            m.changed_files = await OCM.ak_status.worktree_changed_files(wt)
        except Exception:
            pass
        if m.status == "running":
            if rc == 0 or stop:
                m.status = "awaiting_review"
            else:
                m.status = "failed"
                if not m.error:
                    try:
                        m.error = (data_dir / "mission.log").read_text(encoding="utf-8")[-400:]
                    except Exception:
                        m.error = f"exit {rc}"
        S.save(m)


async def _run(m: Mission) -> None:
    async with S.lock(m.id):
        if m.status not in ("running", "queued"):
            return
        m.status = "running"
        wt = Path(m.worktree)
        data_dir = wt / ".ocdata"
        await _prepare(m, wt, data_dir)
        S.save(m)

    rc, stop = await _stream_resilient(m, wt, data_dir, m.agent, m.brief)
    await _finalize(m, wt, data_dir, rc, stop)

    if m.kind == "orchestrator" and (rc == 0 or stop):
        _spawn_plan_children(m, data_dir / "mission.jsonl")


async def _run_team(m: Mission) -> None:
    """A relay: each agent in m.agents runs in turn in the SAME private copy,
    building on the previous one's work. One combined diff to review."""
    async with S.lock(m.id):
        if m.status not in ("running", "queued"):
            return
        m.status = "running"
        wt = Path(m.worktree)
        data_dir = wt / ".ocdata"
        await _prepare(m, wt, data_dir)
        S.save(m)

    team = m.agents or [m.agent]
    rc, stop = 0, False
    for i, ag in enumerate(team):
        m.agent = ag                      # surface the current phase on the board
        S.save(m)
        if i == 0:
            phase_brief = m.brief
        else:
            phase_brief = (
                f"{m.brief}\n\n---\nYou are step {i + 1} of {len(team)} in a relay "
                f"({' -> '.join(team)}). Earlier steps already worked in this folder — "
                f"continue from its CURRENT state in your role as {ag} (review, fix, "
                f"extend, document, or test). Do not start over.")
        rc, stop = await _stream_resilient(m, wt, data_dir, ag, phase_brief,
                                           phase=f"{i + 1}/{len(team)} · {ag}")
        if rc != 0 and not stop:
            break

    await _finalize(m, wt, data_dir, rc, stop)


def _spawn_plan_children(m: Mission, jsonl: Path) -> None:
    """Orchestrator finished → its fenced JSON plan becomes `proposed` children."""
    for spec in _plan_from_jsonl(jsonl):
        try:
            proj = _resolve_project(spec.get("project", "same"), m.project_path) \
                or {"slug": m.project_slug, "name": m.project_name, "path": m.project_path}
            cid = _new_id()
            child = Mission(
                id=cid, project_slug=proj["slug"], project_path=proj["path"],
                project_name=proj["name"], brief=spec.get("brief", "").strip(),
                agent=(spec.get("agent") or "coder").strip(), kind="single",
                status="proposed", parent_id=m.id,
                depends_on=[f"{m.id}:{d}" for d in (spec.get("depends_on") or [])])
            child.__dict__["_plan_id"] = spec.get("id")
            S.m[cid] = child
            S.events[cid] = deque(maxlen=EVENT_KEEP)
            S.save(child)
        except Exception as exc:
            logger.warning("missions %s: bad plan entry: %s", m.id, exc)


async def _release_blocked() -> None:
    """A child whose deps have all reached awaiting_review/applied starts running."""
    done_states = {"awaiting_review", "applied"}
    for m in list(S.m.values()):
        if m.status != "blocked":
            continue
        deps = []
        for d in m.depends_on:
            # d is "<parentid>:<planlocalid>" — map to a sibling mission
            _, _, plid = d.partition(":")
            sib = next((x for x in S.m.values()
                        if x.parent_id == m.parent_id and x.__dict__.get("_plan_id") == plid), None)
            deps.append(sib.status in done_states if sib else False)
        if deps and all(deps):
            m.status = "running"
            S.save(m)
            asyncio.create_task(_run(m))


# ── actions ───────────────────────────────────────────────────────────────
async def abort(mid: str) -> None:
    m = S.m.get(mid)
    if not m:
        return
    p = S.procs.get(mid)
    if p and p.returncode is None:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, timeout=6)
        except Exception:
            pass
    if m.status in ("running", "queued", "blocked"):
        m.status = "failed"
        m.error = m.error or "aborted"
        m.ended = time.time()
        try:
            m.changed_files = await OCM.ak_status.worktree_changed_files(Path(m.worktree))
        except Exception:
            pass
        S.save(m)


async def apply(mid: str) -> dict:
    m = S.m.get(mid)
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    if m.kind == "ingest-app":
        return await _apply_ingest(m)
    wt = Path(m.worktree)
    await OCM._git(wt, "add", "-A", "--", *OCM._SCAFFOLD_EXCLUDE)
    await OCM._git(wt, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "-m", f"mission {m.id}: {m.brief[:60]}", "--allow-empty")
    src = Path(m.project_path)
    if not (src / ".git").exists():
        return {"ok": False, "reason": "project is not a git repo",
                "run_this": f'(copy files from {wt} by hand)'}
    res = await OCM.merge_branch(src, m.branch, m.base_branch)
    if res.get("ok"):
        m.status = "applied"
        S.save(m)
    return res


async def discard(mid: str) -> None:
    m = S.m.get(mid)
    if not m:
        return
    await abort(mid)
    src = Path(m.project_path)
    wt = Path(m.worktree)
    if (src / ".git").exists():
        await OCM._git(src, "worktree", "remove", "--force", str(wt))
        await OCM._git(src, "worktree", "prune")
    for _ in range(6):
        if not wt.exists():
            break
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: shutil.rmtree(wt, ignore_errors=True))
        if not wt.exists():
            break
        await asyncio.sleep(0.5)
    m.status = "discarded"
    m.ended = m.ended or time.time()
    S.save(m)


async def forget(mid: str) -> None:
    """Drop a finished mission's row (and any leftover working copy) from the
    board. Refuses while the mission is still active."""
    m = S.m.get(mid)
    if not m:
        return
    if m.status in _ACTIVE:
        raise web.HTTPBadRequest(text="mission is still active — abort it first")
    try:
        await discard(mid)          # aborts (no-op), removes the working copy
    except Exception as exc:
        logger.info("missions %s: forget cleanup blip: %s", mid, exc)
    S.forget(mid)


async def retry(mid: str, model: str | None = None) -> Mission:
    m = S.m.get(mid)
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    proj = {"slug": m.project_slug, "name": m.project_name, "path": m.project_path}
    kind = "single" if m.kind == "parallel" else m.kind
    return await dispatch(proj, m.brief, m.agent, kind, model=model or m.model,
                          parent_id=m.parent_id, agents=m.agents, group_id=m.group_id,
                          runtime=m.runtime)


async def continue_(mid: str, msg: str) -> None:
    m = S.m.get(mid)
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    wt = Path(m.worktree)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(wt / ".ocdata")
    env["OPENCODE_CONFIG"] = str(wt / "opencode.json")
    cmd = [OCM.OPENCODE_EXE, "run", "--dir", str(wt), "--continue", "--format", "json", msg]
    m.status = "running"
    m.ended = None
    S.save(m)
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(wt), env=env, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    _assign_to_job(proc.pid)
    S.procs[m.id] = proc
    m.pid = proc.pid

    async def _pump() -> None:
        jsonl = wt / ".ocdata" / "mission.jsonl"
        try:
            with open(jsonl, "a", encoding="utf-8") as jf:
                async for raw in proc.stdout:
                    line = raw.decode("utf-8", "replace")
                    jf.write(line); jf.flush()
                    try:
                        ev = json.loads(line.strip())
                        S.events[m.id].append(ev)
                    except Exception:
                        pass
        except Exception:
            pass
        rc = await proc.wait()
        S.procs.pop(m.id, None)
        m.exit_code = rc
        m.ended = time.time()
        m.changed_files = await OCM.ak_status.worktree_changed_files(wt)
        m.status = "awaiting_review" if rc == 0 else "failed"
        S.save(m)

    asyncio.create_task(_pump())


async def transcript(mid: str, host: str) -> dict:
    """Spin the real OpenCode serve on this mission's private copy and open it
    **on the mission's own conversation** — not the SPA's blank 'Build anything'
    screen. The serve shares `XDG_DATA_HOME=<wt>/.ocdata` with the run, so the
    session is in that DB."""
    m = S.m.get(mid)
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    rt = await OCM.OC.open_worktree(m.branch.split("/", 1)[-1], "interactive")
    ui = await rt.ui_dir()
    h = (host or "127.0.0.1").split(":")[0]
    base = f"http://{h}:{rt.port}/{ui}"
    sid = m.session_id
    if not sid:                                   # capture never landed — ask the serve
        try:
            _, sessions = await rt._api("GET", "session", timeout=10)
            if isinstance(sessions, list) and sessions:
                sessions.sort(
                    key=lambda s: (s.get("time") or {}).get("created")
                    or s.get("created") or 0, reverse=True)
                sid = sessions[0].get("id")
        except Exception:
            pass
    return {"root_url": f"{base}/session/{sid}" if sid else base,
            "open_url": rt.open_url(host)}


async def open_folder(mid: str) -> dict:
    """Open the mission's private working copy in the OS file browser."""
    m = S.m.get(mid)
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    p = Path(m.worktree)
    if not p.is_dir():
        raise web.HTTPBadRequest(text="the working copy is gone (discarded?)")
    try:
        os.startfile(str(p))                      # Windows Explorer
    except Exception as exc:
        raise web.HTTPBadRequest(text=f"could not open folder: {exc}")
    return {"ok": True, "path": str(p)}


# ── watchdog ──────────────────────────────────────────────────────────────
async def _watchdog() -> None:
    while True:
        try:
            await asyncio.sleep(30)
            await _release_blocked()
            now = time.time()
            for m in list(S.m.values()):
                if m.status == "running" and now - m.created > MISSION_TIMEOUT:
                    logger.warning("missions %s: timed out (> %ds)", m.id, MISSION_TIMEOUT)
                    await abort(m.id)
                    m.status = "timed_out"
                    m.error = f"timed out after {MISSION_TIMEOUT}s"
                    S.save(m)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("missions watchdog blip: %s", exc)


# ── routes ────────────────────────────────────────────────────────────────
async def _body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@routes.get("/api/projects")
async def api_projects(request: web.Request) -> web.Response:
    return web.json_response({"projects": _projects()})


# ── agents management (project-less) ──────────────────────────────────────
@routes.get("/api/agents")
async def api_agents(request: web.Request) -> web.Response:
    personas = []
    for a in agent_knowledge.list_agents():
        if a["name"] in agent_knowledge.UTILITY_AGENTS:
            continue
        p = agent_knowledge._load_persona(a["name"]) or {}
        personas.append({**a, "frontmatter": p.get("frontmatter", {}),
                         "body": p.get("body", ""),
                         "settings": agent_knowledge.effective_settings(a["name"])})
    models = await asyncio.get_running_loop().run_in_executor(None, OCM._known_models)
    try:
        ws_default = json.loads(Path(OCM.OPENCODE_CONFIG).read_text(encoding="utf-8")).get("model")
    except Exception:
        ws_default = None
    models = [{**m, "workspace_default": m.get("id") == ws_default} for m in models]
    return web.json_response({"personas": personas, "models": models,
                              "team": agent_knowledge.default_team(),
                              "workspace_model": ws_default})


@routes.post("/api/agents/draft")
async def api_agent_draft(request: web.Request) -> web.Response:
    """Run `agent-smith` one-shot to draft a persona .md from a description."""
    b = await _body(request)
    desc = (b.get("description") or "").strip()
    base = (b.get("base") or "").strip()
    if not desc:
        raise web.HTTPBadRequest(text="description required")
    ask = (f"Revise this existing agent per the request, keeping its overall shape "
           f"and frontmatter keys.\n\nREQUEST: {desc}\n\nCURRENT FILE:\n{base}"
           if base else f"I want an agent that: {desc}")
    wt = OCM.SCRATCH_DIR
    wt.mkdir(parents=True, exist_ok=True)
    if not (wt / ".git").exists():
        await OCM._git(wt, "init")
        await OCM._git(wt, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                       "commit", "--allow-empty", "-m", "scratch")
    OCM.materialize_agents(wt, base_branch="base", slug="scratch", headless=True)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(wt / ".ocdata")
    env["OPENCODE_CONFIG"] = str(OCM.OPENCODE_CONFIG)
    proc = await asyncio.create_subprocess_exec(
        OCM.OPENCODE_EXE, "run", "--dir", str(wt), "--agent", "agent-smith",
        "--format", "json", ask,
        cwd=str(wt), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    _assign_to_job(proc.pid)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError:
        proc.kill()
        raise web.HTTPGatewayTimeout(text="agent-smith timed out")
    text = "\n".join(
        (json.loads(l).get("part") or {}).get("text", "")
        for l in out.decode("utf-8", "replace").splitlines() if l.strip())
    mm = re.search(r"```(?:markdown)?\s*(---[\s\S]*?)```", text)
    md = mm.group(1).strip() if mm else ""
    return web.json_response({"markdown": md, "raw": text[-2000:] if not md else ""})


@routes.get("/api/missions")
async def api_board(request: web.Request) -> web.Response:
    _reconcile_orphans()
    ms = sorted(S.m.values(), key=lambda x: x.created, reverse=True)
    return web.json_response({"missions": [m.summary() for m in ms]})


async def _resolve_ref(ref: str) -> dict | None:
    ref = (ref or "").strip()
    if ref.startswith("new:"):
        return await _scaffold_new_project(ref[4:])
    return _resolve_project(ref)


@routes.post("/api/missions")
async def api_dispatch(request: web.Request) -> web.Response:
    b = await _body(request)
    brief = (b.get("brief") or "").strip()
    if not brief:
        raise web.HTTPBadRequest(text="a brief is required")
    kind = b.get("kind") if b.get("kind") in ("single", "team", "parallel", "orchestrator") else "single"
    model = b.get("model") or None
    runtime = b.get("runtime") if b.get("runtime") in ("opencode", "claude-code") else "opencode"

    # project refs — a list for orchestrator, one for the rest
    refs = b.get("projects") or ([b["project"]] if b.get("project") else [])
    resolved: list[dict] = []
    seen: set[str] = set()
    try:
        for r in refs:
            p = await _resolve_ref(r)
            if p and p["path"] not in seen:
                seen.add(p["path"])
                resolved.append(p)
    except web.HTTPException:
        raise
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))
    if not resolved:
        raise web.HTTPBadRequest(text="pick at least one project (a real folder — not Scratch)")
    primary = resolved[0]
    agents = [a.strip() for a in (b.get("agents") or []) if a and a.strip()]

    try:
        if kind == "orchestrator":
            if len(resolved) > 1:
                names = ", ".join(p["name"] for p in resolved)
                brief = (f"Projects you may assign sub-missions to: {names}. Each sub-mission's "
                         f"\"project\" field must be one of those names (or \"same\" for "
                         f"{primary['name']}).\n\n" + brief)
            m = await dispatch(primary, brief, "orchestrator", "orchestrator", model=model, runtime=runtime)
            return web.json_response(m.summary())

        if kind == "team":
            roster = agents or [(b.get("agent") or "coder").strip()]
            m = await dispatch(primary, brief, roster[0], "team", model=model, agents=roster, runtime=runtime)
            return web.json_response(m.summary())

        if kind == "parallel":
            roster = agents or [(b.get("agent") or "coder").strip()]
            gid = "g" + uuid.uuid4().hex[:8]
            out = [(await dispatch(primary, brief, ag, "single", model=model, group_id=gid, runtime=runtime)).summary()
                   for ag in roster]
            return web.json_response({"group": gid, "missions": out})

        agent = (b.get("agent") or "coder").strip()
        m = await dispatch(primary, brief, agent, "single", model=model, runtime=runtime)
        return web.json_response(m.summary())
    except web.HTTPException:
        raise
    except Exception as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.get("/api/missions/{id}")
async def api_detail(request: web.Request) -> web.Response:
    m = S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    # live changed-files for an in-flight or disk-recovered mission so RESULT isn't stale
    if m.status in ("running", "orphaned") and Path(m.worktree).is_dir():
        try:
            m.changed_files = await OCM.ak_status.worktree_changed_files(Path(m.worktree))
        except Exception:
            pass
    d = m.summary()
    d["changed_files"] = m.changed_files
    d["events"] = _parse_events_text(list(S.events.get(m.id, [])))
    d["children"] = [c.summary() for c in S.m.values() if c.parent_id == m.id]
    return web.json_response(d)


@routes.get("/api/missions/{id}/events")
async def api_events(request: web.Request) -> web.StreamResponse:
    m = S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    resp = web.StreamResponse(headers={"Content-Type": "text/event-stream",
                                       "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    await resp.prepare(request)
    sent = 0
    try:
        while True:
            evs = list(S.events.get(m.id, []))
            rows = _parse_events_text(evs)
            for r in rows[sent:]:
                await resp.write(f"data: {json.dumps(r)}\n\n".encode())
            sent = len(rows)
            if m.status not in _ACTIVE:
                await resp.write(f"data: {json.dumps({'k':'done','text':m.status})}\n\n".encode())
                break
            await asyncio.sleep(1.5)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    return resp


@routes.get("/api/missions/{id}/diff")
async def api_diff(request: web.Request) -> web.Response:
    m = S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    wt = Path(m.worktree)
    rel = request.query.get("path")
    if rel:
        return web.Response(text=await OCM.ak_status.worktree_file_diff(wt, rel),
                            content_type="text/plain")
    await OCM._git(wt, "add", "-N", "--", *OCM._SCAFFOLD_EXCLUDE, ".")
    _, out = await OCM._git(wt, "--no-pager", "diff", m.base_branch, "--", *OCM._SCAFFOLD_EXCLUDE)
    return web.Response(text=out, content_type="text/plain")


@routes.post("/api/missions/{id}/abort")
async def api_abort(request: web.Request) -> web.Response:
    await abort(request.match_info["id"])
    return web.json_response({"ok": True})


@routes.post("/api/missions/{id}/apply")
async def api_apply(request: web.Request) -> web.Response:
    return web.json_response(await apply(request.match_info["id"]))


@routes.post("/api/missions/{id}/discard")
async def api_discard(request: web.Request) -> web.Response:
    """Stop the mission and delete its working copy — the row stays on the board
    as `discarded` (history). Use /forget to remove the row entirely."""
    await discard(request.match_info["id"])
    return web.json_response({"ok": True})


@routes.post("/api/missions/{id}/forget")
async def api_forget(request: web.Request) -> web.Response:
    await forget(request.match_info["id"])
    return web.json_response({"ok": True})


@routes.post("/api/missions/{id}/retry")
async def api_retry(request: web.Request) -> web.Response:
    b = await _body(request)
    m = await retry(request.match_info["id"], model=(b.get("model") or None))
    return web.json_response(m.summary())


@routes.post("/api/missions/{id}/continue")
async def api_continue(request: web.Request) -> web.Response:
    b = await _body(request)
    msg = (b.get("message") or "").strip()
    if not msg:
        raise web.HTTPBadRequest(text="message required")
    await continue_(request.match_info["id"], msg)
    return web.json_response({"ok": True})


@routes.post("/api/missions/{id}/dispatch")
async def api_dispatch_one(request: web.Request) -> web.Response:
    """Promote one 'proposed' orchestrator child to a running mission."""
    m = S.m.get(request.match_info["id"])
    if not m or m.status != "proposed":
        raise web.HTTPBadRequest(text="not a proposed mission")
    proj = {"slug": m.project_slug, "name": m.project_name, "path": m.project_path}
    child = await dispatch(proj, m.brief, m.agent, "single", parent_id=m.parent_id,
                           depends_on=m.depends_on)
    child.__dict__["_plan_id"] = m.__dict__.get("_plan_id")
    S.forget(m.id)
    return web.json_response(child.summary())


@routes.post("/api/missions/plan/{id}/dispatch-all")
async def api_dispatch_all(request: web.Request) -> web.Response:
    parent = request.match_info["id"]
    out = []
    for m in [x for x in S.m.values() if x.parent_id == parent and x.status == "proposed"]:
        proj = {"slug": m.project_slug, "name": m.project_name, "path": m.project_path}
        child = await dispatch(proj, m.brief, m.agent, "single", parent_id=parent,
                               depends_on=m.depends_on)
        child.__dict__["_plan_id"] = m.__dict__.get("_plan_id")
        S.forget(m.id)
        out.append(child.summary())
    return web.json_response({"dispatched": out})


@routes.post("/api/missions/{id}/transcript")
async def api_transcript(request: web.Request) -> web.Response:
    return web.json_response(await transcript(request.match_info["id"], request.host))


@routes.post("/api/missions/{id}/folder")
async def api_open_folder(request: web.Request) -> web.Response:
    return web.json_response(await open_folder(request.match_info["id"]))


@routes.get("/api/model-policy")
async def api_get_model_policy(request: web.Request) -> web.Response:
    pol = agent_knowledge.model_policy()
    return web.json_response({
        "policy": pol,
        "resolved": agent_knowledge.resolved_default_model(),
        "fast_free": agent_knowledge.FAST_FREE_MODEL,
        "local": agent_knowledge.LOCAL_MODEL,
        "has_paid_key": agent_knowledge._paid_provider_model() is not None,
    })


@routes.post("/api/model-policy")
async def api_set_model_policy(request: web.Request) -> web.Response:
    b = await _body(request)
    agent_knowledge.set_model_policy((b.get("policy") or "auto").strip())
    return web.json_response({"ok": True, "policy": agent_knowledge.model_policy()})


def setup(app: web.Application) -> None:
    async def _on_startup(_app: web.Application) -> None:
        S.load()
        _reconcile_orphans()
        _app["missions_watchdog"] = asyncio.create_task(_watchdog())

    async def _on_cleanup(_app: web.Application) -> None:
        t = _app.get("missions_watchdog")
        if t:
            t.cancel()

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
