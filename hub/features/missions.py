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
import weakref
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path

from aiohttp import web

from .. import agent_knowledge, app_registry, config
from .. import decide as DEC
from ..config import logger
from ..platform_win import _assign_to_job
from ..runtime import python_for
from . import opencode as OCM   # reuse worktree / model / merge / materialize helpers
from . import claude_runtime as CRT   # second runtime: Claude Code CLI, alongside OpenCode

routes = web.RouteTableDef()

MISSIONS_DIR = OCM.WORKTREES / "_missions"
MISSION_TIMEOUT = 600          # a mission running longer than this is flagged/timed out
LOCAL_MISSION_TIMEOUT = 1200  # ollama/* runs re-read the whole prompt every step — slower, not stuck
STALL_SECS = 150               # one model call with no event for this long = stalled gateway/model: kill it, fail over
LOCAL_STALL_SECS = 420         # a big local model re-reading the prompt is slow, not stuck
QUIET_DONE_SECS = 20           # idle this long after the agent's final "stop" → done
EVENT_KEEP = 300               # events held in memory per mission for the SSE tail
FALLBACK_MODELS = ["ollama/qwen3.6:32k", "opencode/nemotron-3-ultra-free"]

# an error string that means "the provider blipped", not "the code is wrong" —
# worth a retry / model fallback rather than failing the mission
_TRANSIENT_RE = re.compile(
    r"50[234]\b|overload|upstream error|idle timeout|ECONNRESET|ETIMEDOUT|"
    r"rate.?limit|too many requests|temporarily|unavailable|stream (?:ended|closed)|"
    r"free tier can only be used from within|stalled",
    re.I)


def _mark_run(jsonl: Path, agent: str, model: str | None, phase: str, runtime: str) -> None:
    """One `hub_run` line per agent invocation — lets the RUN MAP split a mission's
    jsonl into per-agent segments (the phase label was in-memory only before)."""
    try:
        with open(jsonl, "a", encoding="utf-8") as jf:
            jf.write(json.dumps({"type": "hub_run", "t": time.time(), "agent": agent,
                                 "model": model, "phase": phase, "runtime": runtime}) + "\n")
    except Exception:
        pass


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
    status: str                     # see _ACTIVE + needs_input/plan_ready (orchestrator) + awaiting_review/applied/discarded/failed/timed_out
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
    verify: dict | None = None                        # hub-run checks after the agent: {ok, step, output, attempts}
    plan: list[dict] = field(default_factory=list)    # orchestrator pipeline: [{id, agent, brief, depends_on, status, summary, ...}]
    questions: list[dict] = field(default_factory=list)   # orchestrator ask-back: [{q, why, options, default}]
    answers: list[dict] = field(default_factory=list)     # your replies: [{q, a}]
    profile: str = "code"                             # work type: code | content | business | research (roster + hub gate)
    reference: bool = False                           # copy the LLM Wiki into the working copy as a reference library
    autonomy: str = "plan"                            # ask = always ask first | plan = plan, wait for RUN (default) | auto = run the plan, wait at REVIEW
    judge_extra: list = field(default_factory=list)   # answers from the local model on request (claims_supported ...)
    phase_started: float = 0.0                        # when the current agent call began — the watchdog times THIS, not the whole pipeline
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
            "session_id": self.session_id, "verify": self.verify,
            "plan": self.plan, "questions": self.questions, "answers": self.answers,
            "profile": self.profile, "reference": self.reference, "autonomy": self.autonomy,
            "work_secs": _tm(self)[0], "models_used": _tm(self)[1],
        }


# ── store ─────────────────────────────────────────────────────────────────
class Store:
    def __init__(self) -> None:
        self.m: dict[str, Mission] = {}
        self.events: dict[str, deque] = {}          # id -> recent parsed events
        self.procs: dict[str, asyncio.subprocess.Process] = {}
        self.timeouts: set[str] = set()             # pipeline missions whose current step was killed by the watchdog
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
                    m.status = "paused" if (m.kind == "orchestrator" and m.plan) else "failed"
                    m.error = ("the hub restarted while this ran — RESUME continues from the interrupted step"
                               if m.status == "paused" else (m.error or "hub restarted while running"))
                    for st in m.plan:
                        if st.get("status") == "running":
                            st["status"], st["note"] = "failed", "interrupted: the hub restarted"
                        elif st.get("status") == "queued":
                            st["status"] = "proposed"
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
    `<your new-projects folder>/<name>` so a mission can build it from
    scratch and APPLY into a real base branch."""
    from .. import locations as _LOC
    safe = re.sub(r"[^A-Za-z0-9 ._-]", "", (name or "").strip()).strip(" .")
    if not safe:
        raise web.HTTPBadRequest(text="a project name is required")
    dest = _LOC.new_project_parent() / safe
    if dest.exists():
        raise web.HTTPBadRequest(text=f"'{safe}' already exists — pick another name")
    dest.mkdir(parents=True, exist_ok=True)
    await OCM._git(dest, "init")
    await OCM._git(dest, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
                   "commit", "--allow-empty", "-m", f"init {safe}")
    await OCM._git(dest, "branch", "-M", "main")
    logger.info("missions: scaffolded new project %s", dest)
    return {"slug": OCM.slug_for(dest), "name": safe, "path": str(dest)}


def _recover_plan(d: Path) -> tuple[list[dict], str]:
    """A working copy with no record: rebuild its pipeline (and the ask, if it was logged) from mission.jsonl."""
    jsonl = d / ".ocdata" / "mission.jsonl"
    seen: set[str] = set()
    brief = ""
    try:
        for l in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(l)
            except Exception:
                continue
            if e.get("type") == "hub_run":
                mo = re.match(r"step (\S+) ", e.get("phase") or "")
                if mo:
                    seen.add(mo.group(1))
            elif e.get("type") == "prompt" and not brief:
                u = (e.get("user") or "")
                if "WORK TYPE:" in u or "AGENTS YOU MAY" in u or "PROJECT FILES" in u:
                    brief = u.split("\n\n---")[0].strip()[:400]
        plan = _normalise_plan(_plan_from_jsonl(jsonl), [a["name"] for a in agent_knowledge.list_agents()])
    except Exception:
        return [], ""
    for st in plan:
        st["status"] = "done" if st["id"] in seen else "proposed"
    return plan, brief


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
        plan, brief = _recover_plan(d)
        S.m[mid] = Mission(
            id=mid, project_slug=(OCM.slug_for(origin) if origin else mo.group("slug")),
            project_path=(origin or str(d)), project_name=name,
            brief=brief or "(recovered — the original brief isn't on disk)", agent="orchestrator" if plan else "?",
            kind="orchestrator" if plan else "single", status="orphaned", worktree=str(d),
            branch=f"agent/{d.name}", base_branch=base, plan=plan,
            error="Recovered from disk; its mission record was gone.")
        S.events.setdefault(mid, deque(maxlen=EVENT_KEEP))


def _parse_events_text(events: list[dict], text_max: int = 400) -> list[dict]:
    """Compact the raw NDJSON into UI rows. Handles both OpenCode's event shape
    (type: step_start/tool_use/text/reasoning/error/step_finish, a `part` dict)
    and Claude Code's stream-json shape (type: system/assistant/user/result,
    `message.content[]` blocks) — found missing entirely (claude-code missions
    showed a silently empty activity feed) while comparing the two runtimes."""
    rows = []
    for e in events:
        t = e.get("type")
        if t == "prompt":
            rows.append({"k": "prompt", "text": (e.get("user") or "")[:text_max * 6], "system": (e.get("system") or "")[:text_max * 6]})
            continue
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
                    rows.append({"k": "text", "text": tx[:text_max]})
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
                        rows.append({"k": "text", "text": tx[:text_max]})
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


def _jsonl_text(jsonl: Path) -> str:
    """All the assistant text in a mission's NDJSON — OpenCode (`part.text`) or
    Claude Code (`assistant.message.content[].text`). Claude missions' plans were
    previously never found because only the OpenCode shape was read."""
    try:
        lines = jsonl.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    out: list[str] = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        try:
            e = json.loads(l)
        except Exception:
            continue
        if e.get("type") == "assistant":
            out += [c.get("text") or "" for c in ((e.get("message") or {}).get("content") or [])
                    if c.get("type") == "text"]
        else:
            out.append((e.get("part") or {}).get("text", "") or "")
    return "\n".join(out)


def _run_stats(m: Mission) -> dict:
    """Per-agent segments of a mission, for the RUN MAP: who ran, on what model, for
    how long, how many steps/tools/tokens, which files it wrote, how it ended.
    Built from mission.jsonl (survives a hub restart)."""
    jsonl = Path(m.worktree) / ".ocdata" / "mission.jsonl"
    segs: list[dict] = []
    try:
        lines = jsonl.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {"segments": []}
    cur = None
    last_ts = 0.0
    for l in lines:
        l = l.strip()
        if not l:
            continue
        try:
            e = json.loads(l)
        except Exception:
            continue
        t = e.get("type")
        _tv, _tt = e.get("timestamp"), e.get("t")             # numbers only: Claude's stream-json carries ISO strings here
        ts = _tv / 1000.0 if isinstance(_tv, (int, float)) and _tv else (_tt if isinstance(_tt, (int, float)) else 0)
        if ts and cur is not None and t != "hub_run":
            cur["last"] = max(cur.get("last") or 0, ts)
        if cur is not None and not cur.get("session") and t != "hub_run":
            sid = e.get("sessionID") or (e.get("part") or {}).get("sessionID")
            if isinstance(sid, str) and sid.startswith("ses_"):
                cur["session"] = sid
        if t == "hub_run":
            cur = {"agent": e.get("agent"), "model": e.get("model"), "phase": e.get("phase") or "",
                   "runtime": e.get("runtime"), "start": e.get("t"), "steps": 0, "tools": {},
                   "tok_out": 0, "prompt": 0, "files": [], "end": None, "reason": "", "cost": None,
                   "errors": 0, "session": ""}
            segs.append(cur)
            continue
        if cur is None:
            continue
        p = e.get("part") or {}
        if t == "step_finish":                                   # OpenCode
            cur["steps"] += 1
            tk = p.get("tokens") or {}
            cur["tok_out"] += int(tk.get("output") or 0)
            cur["prompt"] = int(tk.get("input") or 0) + int(((tk.get("cache") or {}).get("read")) or 0)
            cur["reason"] = p.get("reason") or cur["reason"]
        elif t == "tool_use":                                    # OpenCode
            name = p.get("tool") or "tool"
            cur["tools"][name] = cur["tools"].get(name, 0) + 1
            inp = (p.get("state") or {}).get("input") or {}
            f = inp.get("filePath") or inp.get("file_path")
            if f and name in ("write", "edit") and Path(str(f)).name not in cur["files"]:
                cur["files"].append(Path(str(f)).name)
        elif t == "assistant":                                   # Claude Code
            cur["steps"] += 1
            for c in ((e.get("message") or {}).get("content") or []):
                if c.get("type") == "tool_use":
                    name = c.get("name") or "tool"
                    cur["tools"][name] = cur["tools"].get(name, 0) + 1
                    f = (c.get("input") or {}).get("file_path")
                    if f and name in ("Write", "Edit") and Path(str(f)).name not in cur["files"]:
                        cur["files"].append(Path(str(f)).name)
        elif t == "result":                                      # Claude Code
            u = e.get("usage") or {}
            cur["tok_out"] = int(u.get("output_tokens") or cur["tok_out"])
            cur["prompt"] = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) \
                + int(u.get("cache_creation_input_tokens") or 0)
            cur["cost"] = e.get("total_cost_usd")
            cur["reason"] = "error" if e.get("is_error") else (e.get("subtype") or "success")
        elif t == "error":
            cur["errors"] += 1
            cur["reason"] = "error"
    try:
        file_end = jsonl.stat().st_mtime           # older direct calls carried no timestamps: the file's last write is when they ended
    except Exception:
        file_end = 0
    for i, sg in enumerate(segs):
        st0 = sg["start"] or 0
        if i + 1 < len(segs):
            end = sg.get("last") or segs[i + 1]["start"]
        elif m.status == "running":
            end = time.time()
        else:
            end = sg.get("last") or file_end or st0            # a finished/waiting mission never keeps counting
        sg["secs"] = round(max(0.0, (end or 0) - st0), 1)
    return {"segments": segs}


def _json_objects(text: str) -> list[dict]:
    """Every JSON object in a model reply — fenced ```json blocks first, then bare `{...}` found by brace matching.
    (Seen live: the plan-retry reply was a bare object with no fence, so a fence-only regex found nothing.)"""
    out: list[dict] = []
    for mt in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S):
        try:
            o = json.loads(mt.group(1))
            if isinstance(o, dict):
                out.append(o)
        except Exception:
            pass
    if out:
        return out
    t, i = text or "", 0
    while True:
        i = t.find("{", i)
        if i < 0:
            return out
        depth, in_str, esc = 0, False, False
        for j in range(i, len(t)):
            c = t[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        o = json.loads(t[i:j + 1])
                        if isinstance(o, dict):
                            out.append(o)
                    except Exception:
                        pass
                    i = j + 1
                    break
        else:
            return out


_TM: dict[str, tuple] = {}


def _tm(m: "Mission") -> tuple[float, list[str]]:
    """(seconds the agents actually worked, models used) for a mission's card — cached per jsonl version unless it is running."""
    try:
        f = Path(m.worktree) / ".ocdata" / "mission.jsonl"
        stt = f.stat()
    except Exception:
        return 0.0, ([m.model] if m.model else [])
    key = (stt.st_mtime, stt.st_size)
    hit = _TM.get(m.id)
    if hit and hit[0] == key and m.status != "running":
        return hit[1]
    try:
        segs = _run_stats(m)["segments"]
    except Exception:
        segs = []
    models: list[str] = []
    for sg in segs:
        mo = sg.get("model")
        if mo and mo not in models:
            models.append(mo)
    res = (round(sum(sg.get("secs") or 0 for sg in segs), 1), models or ([m.model] if m.model else []))
    _TM[m.id] = (key, res)
    return res


def _plan_from_jsonl(jsonl: Path) -> list[dict]:
    """The orchestrator's {"missions":[...]} plan out of its text output."""
    for obj in _json_objects(_jsonl_text(jsonl)):
        if isinstance(obj.get("missions"), list):
            return obj["missions"]
    return []


def _questions_from_jsonl(jsonl: Path) -> list[dict]:
    """The orchestrator's ask-back: a fenced ```json {"questions":[...]} block."""
    for obj in _json_objects(_jsonl_text(jsonl)):
        qs = obj.get("questions")
        if not isinstance(qs, list):
            continue
        out = []
        for q in qs[:3]:
            if not isinstance(q, dict) or not str(q.get("q") or "").strip():
                continue
            opts = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()][:4]
            out.append({"q": str(q["q"]).strip()[:200], "why": str(q.get("why") or "").strip()[:200],
                        "options": opts, "default": str(q.get("default") or (opts[0] if opts else "")).strip()})
        if out:
            return out
    return []


def _allowed_agents(m: "Mission") -> list[str]:
    """Agents a plan may use: the ticked list, else the work-type roster."""
    pool = [x for x in (m.agents or agent_knowledge.profiles().get(m.profile, {}).get("roster") or []) if x != "orchestrator"]
    return pool or ["coder"]


def _normalise_plan(specs: list, allowed: list[str] | None = None) -> list[dict]:
    """Orchestrator JSON -> pipeline steps (≤6, known agents, valid deps). An unknown agent falls back to
    the first allowed agent that is not a read-only reviewer."""
    allowed = allowed or ["coder", "reviewer", "researcher", "tester", "doc-writer"]
    fallback = next((x for x in allowed if x not in agent_knowledge.READONLY_AGENTS), allowed[0])
    steps: list[dict] = []
    for i, sp in enumerate(specs[:6]):
        if not isinstance(sp, dict) or not str(sp.get("brief") or "").strip():
            continue
        sid = re.sub(r"[^A-Za-z0-9_-]", "", str(sp.get("id") or f"s{i + 1}")) or f"s{i + 1}"
        if any(x["id"] == sid for x in steps):
            sid = f"{sid}-{i + 1}"
        ag = str(sp.get("agent") or fallback).strip()
        st = {"id": sid, "agent": ag if ag in allowed else fallback,
              "brief": str(sp["brief"]).strip(), "depends_on": [str(d) for d in (sp.get("depends_on") or [])],
              "status": "proposed", "summary": "", "started": None, "ended": None}
        if str(sp.get("model") or "").strip():
            st["model"] = str(sp["model"]).strip()[:80]
        steps.append(st)
    ids = {x["id"] for x in steps}
    for st in steps:
        st["depends_on"] = [d for d in st["depends_on"] if d in ids and d != st["id"]]
    return steps


def _topo(steps: list[dict]) -> list[dict]:
    """Dependency order, stable by plan order; a cycle just falls back to plan order."""
    order: list[dict] = []
    left = list(steps)
    ids = {x["id"] for x in steps}
    while left:
        placed = {y["id"] for y in order}
        nxt = next((x for x in left if all(d in placed or d not in ids for d in x["depends_on"])), left[0])
        order.append(nxt)
        left.remove(nxt)
    return order


def _segment_text(jsonl: Path, tail: int = 500) -> str:
    """Assistant text produced since the last hub_run marker — i.e. the current step's own words."""
    try:
        lines = jsonl.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    out: list[str] = []
    for l in lines:
        try:
            e = json.loads(l)
        except Exception:
            continue
        if e.get("type") == "hub_run":
            out = []
        elif e.get("type") == "assistant":
            out += [c.get("text") or "" for c in ((e.get("message") or {}).get("content") or []) if c.get("type") == "text"]
        else:
            t = (e.get("part") or {}).get("text", "")
            if t:
                out.append(t)
    return "\n".join(out).strip()[-tail:]


# ── dispatch / run ────────────────────────────────────────────────────────
async def dispatch(project: dict, brief: str, agent: str, kind: str,
                   model: str | None = None, parent_id: str | None = None,
                   depends_on: list[str] | None = None,
                   agents: list[str] | None = None,
                   group_id: str | None = None,
                   runtime: str = "opencode", profile: str = "code",
                   reference: bool = False, autonomy: str = "plan") -> Mission:
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
                agents=list(agents or []), group_id=group_id,
                profile=profile if profile in agent_knowledge.profiles() else "code", reference=bool(reference),
                autonomy=autonomy if autonomy in ("ask", "plan", "auto") else "plan")
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
        icmd = [str(python_for("apps")) if a == "$PYTHON" else a for a in entry["install"]]
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


def _attach_reference(wt: Path) -> None:
    """Copy the LLM Wiki (minus raw/) into `.hub-ref/wiki/` — a read-only-by-convention reference library
    the agents can cite. Excluded from the diff like other hub scaffolding. Idempotent."""
    dest = wt / ".hub-ref" / "wiki"
    if (dest / "index.md").is_file():
        return
    src = agent_knowledge.WIKI_ROOT
    if not src.is_dir():
        return
    shutil.copytree(src, dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("raw", "*.canvas", ".obsidian", "*.png", "*.jpg", "*.webp"))


async def _prepare(m: Mission, wt: Path, data_dir: Path) -> None:
    """Persona files + autonomous opencode.json + AGENTS.md + resolved model,
    written once into the mission's private copy."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if m.reference:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _attach_reference, wt)
        except Exception as exc:
            logger.warning("missions %s: reference library not attached: %s", m.id, exc)
    roster = agent_knowledge.default_team().get("roster") or []
    names = list(dict.fromkeys(roster + list(agent_knowledge.UTILITY_AGENTS)))
    if m.runtime == "claude-code":
        try:
            CRT.materialize_agents(wt, names, agent_knowledge._load_persona)
        except Exception as exc:
            logger.warning("missions %s: claude persona materialize failed: %s", m.id, exc)
        return   # opencode.json / AGENTS.md / model-resolve below are OpenCode-specific
    try:
        skill_allow = [k["name"] for k in agent_knowledge.relevant_skills(m.project_name, wt)]
    except Exception:
        skill_allow = []
    try:
        adir = wt / ".opencode" / "agent"
        adir.mkdir(parents=True, exist_ok=True)
        for nm in names:
            txt = agent_knowledge.render_agent_file(
                nm, subdir=f"agents/{nm}", roster=roster,
                base_branch=m.base_branch, slug=m.branch, mission=True, headless=True,
                skill_allow=skill_allow)
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
    cfg["tools"] = {**(cfg.get("tools") or {}), "todowrite": False, "todoread": False}   # bookkeeping calls cost 10-50 s each
    cfg["permission"] = {"edit": "allow", "bash": "allow", "webfetch": "allow",
                         "skill": {"*": "deny", **{n: "allow" for n in skill_allow}}}
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
            agent_knowledge.render_agents_md(m.branch, wt, mission=True), encoding="utf-8")
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
    _mark_run(jsonl, agent, m.model, phase, "opencode")
    _log_prompt(jsonl, f"(persona '{agent}' + project AGENTS.md, applied by OpenCode)", brief)
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

    mdl = m.model or ""
    stall = LOCAL_STALL_SECS if (mdl.startswith("ollama/") and not mdl.endswith(":cloud")) else STALL_SECS

    async def _quiet_killer() -> None:
        while proc.returncode is None:
            await asyncio.sleep(8)
            if not st["stop"] and time.monotonic() - st["last"] > stall:
                m.error = f"stalled: no response for {stall}s from {mdl} — failing over to the next model"
                S.events[m.id].append({"type": "error", "error": m.error})
                logger.warning("missions %s: %s", m.id, m.error)
                try:
                    proc.kill()
                except Exception:
                    pass
                return
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
                    if "or newer is required" in m.error:
                        m.error = ("OpenCode is too old for the free tier (provider returned 426). Update it: "
                                   "setup banner -> Update OpenCode, or `npm install opencode-ai@latest` in the "
                                   "OpenCode folder. Raw: " + m.error[:200])
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
    _mark_run(jsonl, agent, model or "claude default", phase, "claude-code")
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
    m.phase_started = time.time()
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
            if m.id in S.timeouts:
                return rc, stop                       # the watchdog killed this step — don't retry another 30 min
            if (m.error or "").startswith("stalled"):
                break                                 # this model stopped answering — next model, don't re-wait on it
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


async def _repo_map(wt: Path, limit: int = 60) -> str:
    """The project's file list, handed to the agent up front. Free/local models
    burned whole missions `glob`/`ls`/`find`-ing for a file that wasn't there —
    an explicit list (or an explicit "empty project") ends that search."""
    rc, out = await OCM._git(wt, "ls-files")
    files = [f.strip().strip('"') for f in (out or "").splitlines()
             if rc == 0 and f.strip() and not OCM.ak_status._is_scaffolding(f.strip().strip('"'))]
    if not files:
        return "PROJECT FILES: (none — this project is empty; nothing exists yet.)"
    shown = files[:limit]
    more = f"\n… and {len(files) - limit} more" if len(files) > limit else ""
    return "PROJECT FILES (everything that exists):\n" + "\n".join(shown) + more


async def _with_repo_map(wt: Path, brief: str) -> str:
    return (f"{brief}\n\n---\n{await _repo_map(wt)}\n"
            "If a file the task refers to is NOT listed above it does not exist: create it "
            "if the task is to build it, otherwise end with `BLOCKED: <file> does not exist`. "
            "Do not search outside this folder.")


def _run_checks_sync(wt: Path, changed: list[dict]) -> dict | None:
    """Deterministic checks the HUB runs after an agent finishes (so reliability
    doesn't depend on a weak model remembering to test): byte-compile every changed
    .py, then run the project's tests if it has any. None = nothing to check."""
    py = [c["path"] for c in changed if str(c.get("path", "")).endswith(".py") and c.get("status") != "D"]
    if not py:
        return None
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def _run(args: list[str], timeout: int) -> tuple[int, str]:
        try:
            r = subprocess.run(args, cwd=str(wt), env=env, capture_output=True, text=True, timeout=timeout)
            return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
        except subprocess.TimeoutExpired as exc:
            part = ""
            for chunk in (exc.stdout, exc.stderr):
                if chunk:
                    part += chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
            return 1, (f"timed out after {timeout}s — the code or a test hangs (infinite loop / waits for input).\n"
                       + part.strip()[-900:])
        except Exception as exc:
            return 1, str(exc)

    rc, out = _run([str(python_for("apps")), "-m", "py_compile", *py], 30)
    if rc != 0:
        return {"ok": False, "step": "compile", "output": out[-1500:]}
    has_tests = any(p.name.startswith("test_") or p.name.endswith("_test.py")
                    for p in wt.rglob("*.py") if ".ocdata" not in p.parts and ".git" not in p.parts)
    if not has_tests:
        return {"ok": True, "step": "compile", "output": f"{len(py)} file(s) compile"}
    rc, out = _run([str(python_for("apps")), "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider",
                    "-o", "faulthandler_timeout=12"], 45)     # a hang dumps its stack after 12s so the fixer sees WHERE
    if rc == 5:                                   # pytest: no tests collected
        return {"ok": True, "step": "compile", "output": "compiles; no runnable tests found"}
    return {"ok": rc == 0, "step": "tests", "output": out[-1500:]}


_PLACEHOLDER_RE = re.compile(
    r"lorem ipsum|\[(?:your|company|brand|insert|name|tbd|todo|placeholder)[^\]\n]{0,40}\]|\{\{[^}\n]+\}\}|\bTODO\b|\bTBD\b|\bXXX\b", re.I)
_CHATTER_RE = re.compile(r"^\s*(sure|certainly|of course|absolutely|okay|here(?:'s| is| are))\b[,! ]", re.I)
_CHANNELS = [(re.compile(r"\b(?:x|twitter|tweet)\b", re.I), 280, "X/Twitter"),
             (re.compile(r"linkedin", re.I), 3000, "LinkedIn"),
             (re.compile(r"instagram|\big\b", re.I), 2200, "Instagram")]
_DOC_EXT = {".md", ".txt", ".html", ".svg"}


def _brand_avoid(wt: Path) -> list[str]:
    """Phrases under an 'Avoid' heading in the project's brand.md."""
    try:
        lines = (wt / "brand.md").read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out, on = [], False
    for l in lines:
        if l.lstrip().startswith("#"):
            on = "avoid" in l.lower()
        elif on and l.strip().startswith(("-", "*")):
            ph = l.strip().lstrip("-* ").strip().strip("\"'`").lower()
            if ph:
                out.append(ph)
    return out


def _run_docs_checks_sync(wt: Path, changed: list[dict]) -> dict | None:
    """Deterministic checks for non-code deliverables (the pytest of content work): empty files,
    placeholders, leftover assistant chatter, channel length limits, the brand 'Avoid' list, and
    designs that were never rendered to PNG. None when nothing reviewable changed."""
    files = [f["path"] for f in changed if Path(f["path"]).suffix.lower() in _DOC_EXT
             and not f["path"].replace("\\", "/").startswith("shared/") and f["path"] != "brand.md"]
    if not files:
        return None
    avoid = _brand_avoid(wt)
    issues: list[str] = []
    for rel in files:
        fp = wt / rel
        try:
            txt = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(txt.strip()) < 20:
            issues.append(f"{rel}: empty or near-empty")
            continue
        if fp.suffix.lower() == ".html" and "design" in Path(rel).parts and not fp.with_suffix(".png").is_file():
            issues.append(f"{rel}: designed but never rendered — run the render tool to produce {fp.with_suffix('.png').name}")
        first = next((l for l in txt.splitlines() if l.strip()), "")
        if _CHATTER_RE.match(first):
            issues.append(f"{rel}: starts with assistant chatter ({first[:40]!r})")
        for mt in list(_PLACEHOLDER_RE.finditer(txt))[:3]:
            issues.append(f"{rel}: placeholder text {mt.group(0)[:30]!r}")
        low = txt.lower()
        for ph in avoid:
            if ph in low:
                issues.append(f"{rel}: uses brand-avoid phrase {ph!r}")
        if fp.suffix.lower() == ".md":
            for sec in re.split(r"(?m)^(?=## )", txt):
                head = sec.splitlines()[0] if sec.strip() else ""
                if not head.startswith("## "):
                    continue
                body = "\n".join(l for l in sec.splitlines()[1:] if not re.match(r"\s*(CTA|chars?|characters?|count)\b", l, re.I)).strip()
                for rx, lim, nm in _CHANNELS:
                    if rx.search(head) and len(body) > lim:
                        issues.append(f"{rel}: '{head[3:50]}' is {len(body)} chars — {nm} limit is {lim}")
                        break
    if not issues:
        return {"ok": True, "step": "content", "output": f"{len(files)} file(s) checked: no placeholders, limits ok"}
    return {"ok": False, "step": "content", "output": "\n".join(issues[:14])}


async def _check_and_fix(m: Mission, wt: Path, data_dir: Path, *, tries: int = 2,
                         fix_agent: str | None = None) -> None:
    """Run the hub's checks; on failure feed the output back to a coder agent and
    re-check (max `tries` fix rounds). Result lands in `m.verify` and the feed."""
    if m.kind == "orchestrator" and not m.plan:
        return
    loop = asyncio.get_running_loop()
    attempts = 0
    res = None
    for round_ in range(tries + 1):
        try:
            changed = await OCM.ak_status.worktree_changed_files(wt)
        except Exception:
            changed = []
        gate = agent_knowledge.profiles().get(m.profile, {}).get("gate", "code")
        res = await loop.run_in_executor(None, (_run_docs_checks_sync if gate == "content" else _run_checks_sync), wt, changed)
        if res is None:
            m.verify = None
            return
        S.events[m.id].append({"type": "step_start", "part": {"phase": f"hub check: {res['step']} "
                               f"{'ok' if res['ok'] else 'FAILED'}"}})
        if res["ok"] or round_ == tries:
            break
        attempts += 1
        fixer = fix_agent or (m.agent if m.agent in ("coder", "tester") else "coder")
        fix_brief = (f"{m.brief}\n\n---\nAUTOMATED CHECK FAILED ({res['step']}). The hub ran the project's "
                     f"checks after your work:\n{res['output']}\n\nFix the problem in the EXISTING files "
                     f"(do not start over), then end with DONE:.")
        S.events[m.id].append({"type": "error", "error": f"hub check failed ({res['step']}) — asking "
                               f"{fixer} to fix it ({attempts}/{tries})"})
        m.error = ""
        await _call_step(m, {"id": "fix", "agent": fixer}, wt, data_dir, data_dir / "mission.jsonl", fix_brief,
                         f"fix {attempts}/{tries} · {fixer}")
    m.verify = {**(res or {}), "attempts": attempts + int((m.verify or {}).get("attempts") or 0)}   # cumulative across gate runs
    S.save(m)


def _decision_log() -> Path:
    return MISSIONS_DIR / "decisions.jsonl"


def _shadow(m: Mission) -> None:
    """Record what the deterministic judge says about a finished mission, so its agreement with the user's later choice can be measured."""
    try:
        verdict = next((x.get("verdict") for x in reversed(m.plan or []) if x.get("verdict")), None)
        state = {"verify": m.verify, "changed": len(m.changed_files or []), "verdict": verdict, "brief": (m.brief or "")[:400]}
        DEC.record(_decision_log(), m.id, "finish", DEC._decide_rules(state, DEC.REVIEW_QUESTIONS))
    except Exception:
        pass


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
            elif m.changed_files:
                # it produced work and THEN errored (doom-loop guard, denied tool, ...) — that
                # work is reviewable; "failed" would hide APPLY.
                m.status = "awaiting_review"
                m.model_note = m.model_note or "ended with an error after producing changes — review the diff before APPLY"
            else:
                m.status = "failed"
                if not m.error:
                    try:
                        m.error = (data_dir / "mission.log").read_text(encoding="utf-8")[-400:]
                    except Exception:
                        m.error = f"exit {rc}"
        if m.status == "awaiting_review":
            _shadow(m)
        S.save(m)


_IDLE_NUDGE = (
    "\n\n---\nYou ended your turn WITHOUT changing any files. Do not describe or plan the work — do it "
    "now: call the write/edit tool to create or modify the files the task requires, run a quick check if "
    "you can, then end with DONE:. If it truly cannot be done, end with BLOCKED: and the reason.")


async def _ensure_progress(m: Mission, wt: Path, data_dir: Path, agent: str,
                           rc: int, stop: bool, tries: int = 2, *, brief: str | None = None,
                           active: bool = False) -> tuple[int, bool]:
    """Free/small models sometimes 'finish' after announcing a plan and never touch a file
    (seen live: nemotron-lightning stopped after 50 output tokens). If the agent ended
    cleanly with zero changes and did not say BLOCKED, nudge it to actually do the work."""
    if (m.kind == "orchestrator" and not active) or not (rc == 0 or stop):
        return rc, stop
    jsonl = data_dir / "mission.jsonl"
    for i in range(tries):
        try:
            changed = await OCM.ak_status.worktree_changed_files(wt)
        except Exception:
            changed = []
        if changed or re.search(r"\bBLOCKED\s*:", _jsonl_text(jsonl)[-2500:]):
            break
        S.events[m.id].append({"type": "error", "error": f"{agent} ended without changing any files — "
                               f"nudging it to do the work ({i + 1}/{tries})"})
        rc, stop = await _stream_resilient(m, wt, data_dir, agent,
                                           await _with_repo_map(wt, (brief or m.brief) + _IDLE_NUDGE),
                                           phase=f"nudge {i + 1}/{tries} · {agent}")
        if not (rc == 0 or stop):
            break
    return rc, stop


_PLAN_NUDGE = (
    "\n\n---\nYour previous reply contained NO plan block. You are the orchestrator: you have NO write "
    "access outside shared/ (by design) and must not write or draft the implementation yourself. Reply "
    "now with ONLY one fenced ```json block of exactly this form — 2 to 6 self-contained sub-briefs, each "
    "`agent` one of the agent names listed in your request:\n"
    '```json\n{"missions":[{"id":"m1","agent":"coder","project":"same","brief":"...","depends_on":[]},'
    '{"id":"m2","agent":"tester","project":"same","brief":"...","depends_on":["m1"]}]}\n```\nNo other text.')


async def _run(m: Mission) -> None:
    async with S.lock(m.id):
        if m.status not in ("running", "queued"):
            return
        m.status = "running"
        wt = Path(m.worktree)
        data_dir = wt / ".ocdata"
        await _prepare(m, wt, data_dir)
        S.save(m)

    jsonl = data_dir / "mission.jsonl"
    if m.kind == "orchestrator":
        await _run_orchestrator(m, wt, data_dir, jsonl)
        return
    rc, stop = await _stream_resilient(m, wt, data_dir, m.agent, await _with_repo_map(wt, m.brief))
    rc, stop = await _ensure_progress(m, wt, data_dir, m.agent, rc, stop)
    if rc == 0 or stop:
        await _check_and_fix(m, wt, data_dir)
    await _finalize(m, wt, data_dir, rc, stop)


_REF_NOTE = ("REFERENCE LIBRARY: the LLM Wiki is copied at `.hub-ref/wiki/` (start with `index.md`; cite pages as "
             "[[name]]). Read it only if the task needs background.")


def _orch_brief(m: Mission) -> str:
    out = m.brief
    if m.answers:
        lines = "\n".join(f"- {a.get('q', '')}  →  {a.get('a', '')}" for a in m.answers)
        out += (f"\n\n---\nYOUR CLARIFYING QUESTIONS WERE ANSWERED BY THE USER:\n{lines}\n"
                "Do NOT ask further questions. Write the plan now.")
    if m.autonomy == "ask" and not m.answers:
        out += ("\n\n---\nAUTONOMY: ASK FIRST. The user wants to be asked before you plan: reply with 1-3 short clarifying "
                "questions (2-4 options each and a default). Do not write the plan yet.")
    prof = agent_knowledge.profiles().get(m.profile, {})
    out += (f"\n\n---\nWORK TYPE: {prof.get('label', m.profile)}. AGENTS YOU MAY PUT IN THE PLAN "
            f"(use these exact names):\n{agent_menu_for(m)}")
    if m.reference:
        out += "\n" + _REF_NOTE
    return out


def agent_menu_for(m: "Mission") -> str:
    return agent_knowledge.agent_menu(_allowed_agents(m))


DIRECT_PLANNER = True          # the orchestrator is ONE model call (no tool loop); tests switch this off
PLANNER_SYSTEM = """You are the ORCHESTRATOR of a team of AI agents. You do not do the work and you have no tools: you read the
request and reply with ONE JSON object and nothing else.

Case A — the request is too vague to plan well (e.g. "build a calculator": CLI, web or desktop? which operations?), and the user has
not answered yet: {"questions":[{"q":"Which interface?","why":"decides which files exist","options":["CLI","Web page","Desktop GUI"],"default":"CLI"}]}
  Max 3 questions, 2-4 short options each, a recommended `default`. Never ask when the request is clear or answers were already given.

Case B — otherwise, the plan: {"missions":[{"id":"m1","agent":"<exact name from the list>","project":"same","brief":"...","depends_on":[]},
  {"id":"m2","agent":"...","project":"same","brief":"...","depends_on":[]},
  {"id":"m3","agent":"<a reviewer>","project":"same","brief":"...","depends_on":["m1","m2"]}]}
  (m1 and m2 run in parallel; m3 reviews both.)
  - 2 to 6 steps in ONE shared working folder. Steps with the same `depends_on` run IN PARALLEL as one batch, and everything a batch
    produced is handed to the next stage together. USE THAT: independent work is a batch — e.g. the code and its tests written from the
    same spec, several documents, copy + visuals, research + outline — and a reviewer comes last, depending on ALL of them.
    Only chain steps (`depends_on`) when one truly needs the other's output. Parallel steps must not write the same file, and each
    of their briefs must state the exact file names / function names / interface they share.
  - Each brief is self-contained: the exact files to create/change, the constraints from the request, and what "done" looks like.
  - Pick the agent whose description fits the sub-task. End non-trivial work with a reviewing agent (reviewer / editor /
    compliance-reviewer). The hub runs compile/tests/content checks itself before the reviewer — never plan a "run the tests" step.
  - `project` is always "same".
Output only the JSON object."""


_OLLAMA_APP = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"
_ollama_starting: asyncio.Lock | None = None


async def _ensure_ollama(wait: float = 30.0) -> bool:
    """Start the Ollama desktop app if nothing answers on :11434, and wait for it. Every default model in the hub goes
    through Ollama (cloud Nemotron included), so a fresh boot with Ollama not yet running must not just fail."""
    import aiohttp
    global _ollama_starting
    if _ollama_starting is None:
        _ollama_starting = asyncio.Lock()

    async def up() -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as sess:
                async with sess.get("http://127.0.0.1:11434/api/version") as r:
                    return r.status == 200
        except Exception:
            return False

    async with _ollama_starting:
        if await up():
            return True
        if not _OLLAMA_APP.is_file():
            return False
        try:
            subprocess.Popen([str(_OLLAMA_APP)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x00000008 | 0x00000200)          # DETACHED_PROCESS | NEW_PROCESS_GROUP
            logger.info("missions: Ollama was not running — started it")
        except Exception as exc:
            logger.warning("missions: could not start Ollama: %s", exc)
            return False
        t0 = time.time()
        while time.time() - t0 < wait:
            await asyncio.sleep(1)
            if await up():
                return True
        return False


async def _direct_chat(model: str, system: str, user: str, *, temperature: float = 0.3,
                       timeout: float = 120.0, num_ctx: int = 32768) -> str:
    """One chat completion straight from Ollama (local or :cloud) — 3-6 s for cloud Nemotron, versus minutes through
    an agent tool-loop. Raises on any failure so the caller can fail over."""
    import aiohttp
    name = model.split("/", 1)[1]
    body = {"model": name, "stream": False, "options": {"temperature": temperature, "num_ctx": num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for attempt in (0, 1):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as sess:
                async with sess.post("http://127.0.0.1:11434/api/chat", json=body) as r:
                    if r.status != 200:
                        raise RuntimeError(f"ollama {r.status}: {(await r.text())[:160]}")
                    d = await r.json()
            break
        except aiohttp.ClientConnectorError:
            if attempt or not await _ensure_ollama():      # Ollama isn't running (fresh boot): start it once, then retry
                raise
    txt = ((d.get("message") or {}).get("content") or "").strip()
    if not txt:
        raise RuntimeError("empty reply")
    return txt


def _log_prompt(jsonl: Path, system: str, user: str) -> None:
    """The INPUT of an agent call, next to its output — a transcript you can review has to show what the agent was asked."""
    try:
        with open(jsonl, "a", encoding="utf-8") as jf:
            jf.write(json.dumps({"type": "prompt", "timestamp": int(time.time() * 1000),
                                 "system": (system or "")[:20000], "user": (user or "")[:60000]}) + "\n")
    except Exception:
        pass


def _log_direct(m: Mission, jsonl: Path, agent: str, phase: str, model: str, text: str,
                system: str = "", user: str = "") -> None:
    """Record a direct call exactly like an agent run, so transcripts / plan parsing / run map treat it uniformly."""
    _mark_run(jsonl, agent, model, phase, "direct")
    _log_prompt(jsonl, system, user)
    ev = {"type": "text", "timestamp": int(time.time() * 1000), "part": {"text": text}}
    try:
        with open(jsonl, "a", encoding="utf-8") as jf:
            jf.write(json.dumps(ev) + "\n")
    except Exception:
        pass
    S.events[m.id].append({"type": "step_start", "part": {"phase": f"{phase} · {model}"}})
    S.events[m.id].append(ev)


async def _orch_call(m: Mission, wt: Path, data_dir: Path, jsonl: Path, prompt: str, phase: str) -> tuple[int, bool]:
    """One orchestrator turn. Direct chat first (Ollama models in the failover chain, each with its own time limit);
    if none works, or the mission is pinned to a non-Ollama model, the old agent-loop path."""
    if DIRECT_PLANNER:
        chain = agent_knowledge.model_chain(m.model or None, None)
        if chain and chain[0].startswith("ollama/"):
            repo = await _repo_map(wt)
            user = f"{prompt}\n\n---\n{repo}"
            m.phase_started = time.time()
            for mdl in [x for x in chain if x.startswith("ollama/")]:
                local = not mdl.endswith(":cloud")
                try:
                    t0 = time.time()
                    text = await _direct_chat(mdl, PLANNER_SYSTEM, user, timeout=300 if local else 120)
                    _log_direct(m, jsonl, "orchestrator", phase, mdl, text, PLANNER_SYSTEM, user)
                    if mdl != m.model:
                        m.model_note = f"orchestrator ran on {mdl}" if m.model else m.model_note
                    S.events[m.id].append({"type": "text", "part": {"text": f"(planner answered in {time.time() - t0:.0f}s on {mdl})"}})
                    return 0, True
                except Exception as exc:
                    S.events[m.id].append({"type": "error", "error": f"planner on {mdl} failed ({str(exc)[:120]}) — next model"})
    return await _stream_resilient(m, wt, data_dir, m.agent, await _with_repo_map(wt, prompt), phase=phase)


async def _run_orchestrator(m: Mission, wt: Path, data_dir: Path, jsonl: Path) -> None:
    """Orchestrator turn: it either asks the user (-> needs_input) or plans (-> plan_ready).
    Nothing runs until the user presses DISPATCH; the plan then executes as ONE pipeline."""
    brief = _orch_brief(m)
    rc, stop = await _orch_call(m, wt, data_dir, jsonl, brief, "plan · orchestrator")
    if rc == 0 or stop:
        if not m.answers and not _plan_from_jsonl(jsonl):
            qs = _questions_from_jsonl(jsonl)
            if qs:
                m.questions, m.status, m.ended = qs, "needs_input", None
                S.save(m)
                return
        if not _plan_from_jsonl(jsonl):
            S.events[m.id].append({"type": "error", "error": "no plan block found — asking the orchestrator "
                                   "once more for ONLY the JSON plan"})
            rc, stop = await _orch_call(m, wt, data_dir, jsonl, brief + _PLAN_NUDGE, "plan retry · orchestrator")
        steps = _normalise_plan(_plan_from_jsonl(jsonl), _allowed_agents(m))
        if steps and (rc == 0 or stop):
            m.plan, m.status, m.ended, m.error = steps, "plan_ready", None, ""
            S.save(m)
            if m.autonomy == "auto":
                asyncio.create_task(run_plan(m.id))
            return
        m.error = m.error or "the orchestrator produced no usable plan"
        rc = rc or 1
    async with S.lock(m.id):
        if m.status == "running":
            m.status, m.ended = "failed", time.time()
            m.error = m.error or f"exit {rc}"
        S.save(m)


def _step_brief(m: Mission, st: dict, notes: list[str]) -> str:
    plan = " → ".join(f"{x['id']}:{x['agent']}" for x in m.plan)
    prev = "\n".join(notes) or "(none — you are the first step)"
    ref = ("\n" + _REF_NOTE + "\n") if m.reference else ""
    return (f"ORIGINAL REQUEST (for context): {m.brief}\n{ref}\nPLAN: {plan}\n"
            f"You are step {st['id']} ({st['agent']}). Work in THIS folder — earlier steps' files are already here; "
            f"build on them, do not redo them.\n\nYOUR TASK:\n{st['brief']}\n\nEARLIER STEPS' RESULTS:\n{prev}")


_NO_NUDGE = tuple(agent_knowledge.READONLY_AGENTS) + ("researcher",)
MAX_REVIEW_ROUNDS = 1


def _verdict(text: str) -> str | None:
    """`VERDICT: ship|changes-needed|blocked` from a reviewer's words (last one wins)."""
    hits = re.findall(r"VERDICT:\s*(ship|changes-needed|blocked)", text or "", re.I)
    if hits:
        return hits[-1].lower()
    if re.search(r"changes[- ]needed|request(?:ed)? changes", text or "", re.I):
        return "changes-needed"
    return None


DIRECT_STEPS = True            # writing roles produce their files in ONE model call (no tool loop); tests switch this off
# lenient: `<<<FILE path>>>` (asked for) or `<<<path>>>` (seen from gemma); the closing `<<<END>>>` is optional
# (a block also ends at the next block or at the DONE line)
_FILE_RE = re.compile(r"<<<(?!END>>>)(?:FILE\s+)?([^<>\n]{2,160}?)\s*>>>\r?\n(.*?)(?:\r?\n<<<END>>>|(?=\r?\n<<<[^<>\n]{2,160}>>>)|\r?\n\s*DONE:|\Z)", re.S)
_DENY_PATHS = (".git", ".ocdata", ".opencode", ".claude", ".hub-ref", "opencode.json", "AGENTS.md")
DIRECT_WRITER_RULES = """

---
HOW YOU DELIVER (you have no tools, and you do not need any): reply with the finished files and nothing else. For EVERY file:
<<<FILE relative/path/name.ext>>>
...the complete file content...
<<<END>>>
After the last file add ONE line: DONE: <what you produced>. No commentary, no code fences around the file blocks, no placeholders.
Ignore any instruction above about running commands, tests or checks: you cannot, and the hub compiles the code and runs the tests for you
right after your reply, then sends you the failure output if there is one.
Read-only roles (reviewers / editors) instead reply with their findings as plain text ending in `VERDICT: ship`, `VERDICT: changes-needed`
or `VERDICT: blocked`, then `DONE:`."""


def _is_direct(agent: str) -> bool:
    fm = (agent_knowledge._load_persona(agent) or {}).get("frontmatter", {})
    return str(fm.get("direct", "")).lower() == "true"


def _context_files(wt: Path, budget: int = 24000) -> str:
    """Text of the files earlier steps (and the project) left in the working copy — what a tool-using agent would `read`."""
    out, used = [], 0
    for f in sorted(wt.rglob("*")):
        rel = f.relative_to(wt).as_posix()
        if not f.is_file() or rel.startswith(_DENY_PATHS) or "/." in "/" + rel or f.suffix.lower() not in (
                ".md", ".txt", ".py", ".html", ".css", ".js", ".json", ".csv", ".svg", ".yml", ".yaml", ".toml"):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if used + len(txt) > budget:
            txt = txt[:max(0, budget - used)] + "\n… (truncated)"
        if txt.strip():
            out.append(f"===== {rel} =====\n{txt}")
            used += len(txt)
        if used >= budget:
            break
    return "\n\n".join(out)


def _wiki_context(wt: Path, brief: str, pages: int = 4, per_page: int = 5000) -> str:
    """Cheap retrieval over the copied LLM Wiki: its index + the few pages whose file names best match the request's words."""
    root = wt / ".hub-ref" / "wiki"
    if not (root / "index.md").is_file():
        return ""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", brief.lower())} - {"about", "write", "using", "cite", "pages", "wiki", "used", "what", "five", "bullets"}
    scored = []
    for sub in ("entities", "concepts", "sources", "analyses"):
        for f in (root / sub).glob("*.md") if (root / sub).is_dir() else []:
            stem_words = set(re.findall(r"[a-z0-9]{4,}", f.stem.lower()))
            sc = len(words & stem_words) * 3 + sum(1 for w in words if w in f.stem.lower())
            if sc:
                scored.append((sc, f))
    scored.sort(key=lambda x: -x[0])
    out = ["===== wiki index.md =====\n" + (root / "index.md").read_text(encoding="utf-8", errors="replace")[:6000]]
    for _, f in scored[:pages]:
        out.append(f"===== wiki page [[{f.stem}]] =====\n" + f.read_text(encoding="utf-8", errors="replace")[:per_page])
    return "\n\n".join(out)


def _small_project(wt: Path) -> bool:
    """Direct (one-call) code writing only when the whole project fits in a prompt: <= 40 text files and <= 100 KB."""
    n = size = 0
    for f in wt.rglob("*"):
        rel = f.relative_to(wt).as_posix()
        if not f.is_file() or rel.startswith(_DENY_PATHS) or "/." in "/" + rel or "node_modules" in rel or "__pycache__" in rel:
            continue
        n += 1
        try:
            size += f.stat().st_size
        except Exception:
            pass
        if n > 40 or size > 100_000:
            return False
    return True


_PATH_IN_BRIEF = re.compile(r"`([\w./\\-]+\.(?:md|txt|py|html|css|js|json|csv|svg|yml|yaml))`")


def _infer_target(wt: Path, brief: str, agent: str, step_id: str) -> str:
    """Where to file a reply that IS the deliverable (no file blocks): the first NEW file the task names, else a default."""
    task = brief.split("YOUR TASK:")[-1].split("EARLIER STEPS")[0]
    for mt in _PATH_IN_BRIEF.finditer(task):
        rel = mt.group(1).replace("\\", "/").lstrip("/")
        if "<" not in rel and not (wt / rel).exists() and not rel.startswith(_DENY_PATHS):
            return rel
    return f"deliverables/{agent}-{step_id}.md"


def _write_files(wt: Path, text: str) -> list[str]:
    wrote = []
    for mt in _FILE_RE.finditer(text or ""):
        rel = mt.group(1).strip().strip("`\"'").replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/") or rel.startswith(_DENY_PATHS) or ":" in rel.split("/")[0]:
            continue
        dest = wt / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(mt.group(2)[:200000], encoding="utf-8")
            wrote.append(rel)
        except Exception:
            continue
        if len(wrote) >= 14:
            break
    return wrote


def _render_designs(wt: Path, new: list[str]) -> list[str]:
    """The hub renders each new HTML design to a PNG itself (headless Edge) — the designer never runs a command."""
    made = []
    for rel in new:
        if not rel.lower().endswith(".html") or "design" not in Path(rel).parts:
            continue
        src = wt / rel
        try:
            head = src.read_text(encoding="utf-8", errors="replace")[:400]
        except Exception:
            continue
        mt = re.search(r"size:\s*(\d{3,4})\s*x\s*(\d{3,4})", head)
        w, h = (mt.group(1), mt.group(2)) if mt else ("1080", "1080")
        try:
            r = subprocess.run([str(python_for("apps")), str(agent_knowledge.RENDER_TOOL), str(src), str(src.with_suffix(".png")), w, h],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                made.append(src.with_suffix(".png").relative_to(wt).as_posix())
        except Exception:
            pass
    return made


def _step_model(st: dict, base: str | None) -> tuple[str | None, str]:
    """(model, why) for one plan step: the step's own pin (or the ★ suggestion) > the agent's saved SETTINGS model > the mission's model.
    The hub decides this itself — OpenCode is always handed the result with -m, so it can never silently prefer something else."""
    if st.get("model"):
        return st["model"], st.get("model_src") or "pinned"
    try:
        ov = (agent_knowledge.load_overrides().get(st.get("agent") or "") or {}).get("model")
    except Exception:
        ov = None
    if ov:
        return ov, "agent setting"
    return base, "mission"


# Independent steps are DECIDED together (the DAG), but the model CALLS are metered per kind of model: one local model on one GPU
# answers one call at a time; cloud models take a few at once. Resource management, not plan logic.
MODEL_SLOTS = {"local": 1, "cloud": 3, "zen": 2}
_SLOTS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()      # event loop -> {kind: Semaphore}


def _slot_kind(model: str | None) -> str:
    mo = model or ""
    if mo.startswith("ollama/"):
        return "cloud" if mo.endswith(":cloud") else "local"
    return "zen" if mo.startswith("opencode/") else "cloud"


def _slot(model: str | None) -> "tuple[asyncio.Semaphore, str]":
    kind = _slot_kind(model)
    per_loop = _SLOTS.setdefault(asyncio.get_running_loop(), {})
    if kind not in per_loop:
        per_loop[kind] = asyncio.Semaphore(MODEL_SLOTS[kind])
    return per_loop[kind], kind


async def _direct_step(m: Mission, st: dict, wt: Path, jsonl: Path, brief: str, phase: str | None = None) -> tuple[bool, str] | None:
    """One writing step as ONE model call. Returns (ok, summary), or None when no model in the chain could do it
    (the caller then falls back to the agent loop)."""
    persona = (agent_knowledge._load_persona(st["agent"]) or {}).get("body", "")
    system = persona.replace("{RENDER_TOOL}", "the hub") + DIRECT_WRITER_RULES
    ctx = await asyncio.get_running_loop().run_in_executor(None, _context_files, wt)
    if m.reference:
        wc = await asyncio.get_running_loop().run_in_executor(None, _wiki_context, wt, brief)
        if wc:
            ctx = (ctx + "\n\n" if ctx else "") + "REFERENCE LIBRARY (LLM Wiki excerpts — cite pages as [[page-name]]):\n" + wc
    user = (f"{brief}\n\n---\nFILES ALREADY IN THE WORKING FOLDER:\n{ctx or '(none)'}\n\n---\n"
            + ("REMINDER: reply as review text ending in `VERDICT: ship|changes-needed|blocked`, then `DONE:`."
               if st["agent"] in agent_knowledge.READONLY_AGENTS else
               "REMINDER: your whole reply is file blocks — `<<<FILE relative/path.ext>>>` newline, the full file, newline "
               "`<<<END>>>` — then one `DONE:` line. Nothing else."))
    eff, _src = _step_model(st, m.model)
    chain = [x for x in agent_knowledge.model_chain(eff or None, None) if x.startswith("ollama/")]
    readonly = st["agent"] in agent_knowledge.READONLY_AGENTS
    for mdl in chain:
        try:
            sem, kind = _slot(mdl)
            if sem.locked():
                S.events[m.id].append({"type": "text", "part": {"text": f"({st['agent']} is queued — {MODEL_SLOTS[kind]} {kind}-model call(s) at a time)"}})
            async with sem:
                t0 = time.time()
                text = await _direct_chat(mdl, system, user, temperature=float(
                    (agent_knowledge.effective_settings(st["agent"]).get("temperature") or {}).get("value") or 0.4),
                    timeout=180 if mdl.endswith(":cloud") else 420)
        except Exception as exc:
            S.events[m.id].append({"type": "error", "error": f"{st['agent']} on {mdl} failed ({str(exc)[:110]}) — next model"})
            continue
        _log_direct(m, jsonl, st["agent"], phase or f"step {st['id']} · {st['agent']}", mdl, text, system, user)
        wrote = [] if readonly else _write_files(wt, text)
        if not readonly and not wrote:
            body = re.sub(r"(?im)^\s*DONE:.*$", "", text).strip()
            if len(body) >= 20:
                # the model wrote the deliverable but skipped the file format — the hub files it (better than a retry)
                target = _infer_target(wt, brief, st["agent"], st["id"])
                try:
                    (wt / target).parent.mkdir(parents=True, exist_ok=True)
                    (wt / target).write_text(body, encoding="utf-8")
                    wrote = [target]
                    S.events[m.id].append({"type": "text", "part": {"text": f"(no file blocks in the reply — the hub saved it as {target})"}})
                except Exception:
                    wrote = []
            if not wrote:
                S.events[m.id].append({"type": "error", "error": f"{st['agent']} replied with nothing usable — trying the next model"})
                continue
        made = await asyncio.get_running_loop().run_in_executor(None, _render_designs, wt, wrote) if wrote else []
        done = re.findall(r"DONE:\s*(.+)", text)
        summary = (done[-1].strip() if done else "") + (f"\nFiles: {', '.join(wrote + made)}" if wrote else "") \
            + (f"\n{text.strip()[-600:]}" if readonly else "")
        S.events[m.id].append({"type": "text", "part": {"text": f"({st['agent']} answered in {time.time() - t0:.0f}s on {mdl}; "
                                                        f"wrote {len(wrote)} file(s){', rendered ' + str(len(made)) + ' PNG' if made else ''})"}})
        st["eff_model"] = mdl
        if mdl != eff:
            m.model_note = f"{st['agent']} ran on {mdl}"
        return True, summary.strip()
    return None


async def _direct_ok(m: Mission, agent: str, wt: Path) -> bool:
    """Can this agent's step be ONE direct model call (no tool loop)? Writing/reviewing roles yes; coder/tester only while the
    whole project fits in a prompt; analyst/researcher when a wiki reference is attached."""
    if not DIRECT_STEPS:
        return False
    if not (_is_direct(agent) or (m.reference and agent in ("analyst", "researcher"))):
        return False
    if agent in ("coder", "tester"):
        return await asyncio.get_running_loop().run_in_executor(None, _small_project, wt)
    return True


async def _call_step(m: Mission, st: dict, wt: Path, data_dir: Path, jsonl: Path, brief: str, phase: str) -> tuple[int, bool, str | None]:
    """Run one agent call for a plan step: ONE direct model call for writing/reviewing roles, the agent loop for the rest."""
    if await _direct_ok(m, st["agent"], wt):
        m.phase_started = time.time()
        d = await _direct_step(m, st, wt, jsonl, brief, phase)
        if d is not None:
            return 0, True, d[1]
    rc, stop = await _stream_resilient(m, wt, data_dir, st["agent"], await _with_repo_map(wt, brief), phase=phase)
    return rc, stop, None


async def _run_pipeline(m: Mission) -> None:
    """Execute the orchestrator's plan as a DAG in ONE shared working copy. Steps whose dependencies are done are READY; ready
    writing steps that are one-call direct steps run TOGETHER as a parallel batch (e.g. coder + tester + doc-writer from the same
    spec), their summaries are handed to the next stage. Steps that need the agent tool loop run one at a time. Before the first
    reviewing step the hub runs its checks (+ fix loop). A reviewer that says `changes-needed` sends its feedback back to the
    last writer ONCE (then checks + re-review). Finished steps (a resumed run) are skipped."""
    wt = Path(m.worktree)
    data_dir = wt / ".ocdata"
    jsonl = data_dir / "mission.jsonl"
    base_model = m.model
    notes: list[str] = []
    writers: list[dict] = []
    ids = {x["id"] for x in m.plan}
    ro_agents = agent_knowledge.READONLY_AGENTS
    state = {"gate": False, "rounds": 0, "rc": 0, "stop": False, "bad": False}

    for st in _topo(m.plan):                                   # resumed run: keep finished work, hand its summary on
        if st.get("status") == "done":
            if st["agent"] in ro_agents:
                state["gate"] = True
            else:
                writers.append(st)
            if st.get("summary"):
                notes.append(f"- {st['id']} ({st['agent']}): {st['summary'][-350:]}")

    async def run_writer(st: dict, parallel: bool) -> bool:
        st["status"], st["started"] = "running", time.time()
        st["eff_model"], st["eff_src"] = _step_model(st, base_model)
        if not parallel:
            m.agent = st["agent"]
            m.model = st["eff_model"] or base_model
        S.save(m)
        brief = _step_brief(m, st, notes)
        rc, stop, dsum = await _call_step(m, st, wt, data_dir, jsonl, brief, f"step {st['id']} · {st['agent']}")
        if m.status != "running":                              # paused / aborted while this call was in flight
            st["status"], st["note"], st["ended"] = "failed", "stopped by you — RESUME re-runs this step", time.time()
            S.save(m)
            return False
        if dsum is None and st["agent"] not in _NO_NUDGE:
            rc, stop = await _ensure_progress(m, wt, data_dir, st["agent"], rc, stop, brief=brief, active=True)
        st["ended"] = time.time()
        st["summary"] = dsum if dsum is not None else _segment_text(jsonl)
        ok = rc == 0 or stop
        if m.id in S.timeouts:
            S.timeouts.discard(m.id)
            try:
                wrote = await OCM.ak_status.worktree_changed_files(wt)
            except Exception:
                wrote = []
            if not ok and wrote:
                ok, rc = True, 0                               # slow gateway, not a failure: it had already written files
                st["note"] = "hit the per-step time limit after writing files — continued"
                m.model_note = "a step hit the time limit after producing changes — review it"
            else:
                st["note"] = "hit the per-step time limit"
        st["status"] = "done" if ok else "failed"
        state["rc"], state["stop"] = rc, stop
        S.save(m)
        return ok

    async def run_reviewer(st: dict) -> bool:
        if not state["gate"]:
            state["gate"] = True
            await _check_and_fix(m, wt, data_dir, fix_agent=(writers[-1]["agent"] if writers else None))
            if m.verify:
                notes.append(f"HUB CHECKS ({m.verify.get('step')}): {'passed' if m.verify.get('ok') else 'FAILED'}"
                             f"{' after ' + str(m.verify['attempts']) + ' fix round(s)' if m.verify.get('attempts') else ''}")
        if not await run_writer(st, False):
            return False
        if st["summary"]:
            notes.append(f"- {st['id']} ({st['agent']}): {st['summary'][-350:]}")
        st["verdict"] = _verdict(_segment_text(jsonl, 1800))
        if st["verdict"] == "changes-needed" and state["rounds"] < MAX_REVIEW_ROUNDS and writers:
            state["rounds"] += 1
            target = writers[-1]
            feedback = _segment_text(jsonl, 1800)
            S.events[m.id].append({"type": "error", "error": f"{st['agent']} asked for changes — sending them back to "
                                   f"{target['agent']} ({state['rounds']}/{MAX_REVIEW_ROUNDS})"})
            fix_brief = (_step_brief(m, target, notes) + f"\n\n---\nREVIEW FEEDBACK from {st['agent']} — address every "
                         f"point in the EXISTING files (do not start over), then end with DONE:\n{feedback}")
            m.agent, m.model = target["agent"], _step_model(target, base_model)[0] or base_model
            rc, stop, _ = await _call_step(m, target, wt, data_dir, jsonl, fix_brief, f"revise after review · {target['agent']}")
            state["rc"], state["stop"] = rc, stop
            if not (rc == 0 or stop):
                return False
            await _check_and_fix(m, wt, data_dir, fix_agent=target["agent"])
            m.agent, m.model = st["agent"], _step_model(st, base_model)[0] or base_model
            rc, stop, _ = await _call_step(
                m, st, wt, data_dir, jsonl,
                _step_brief(m, st, notes) + "\n\nThe author has revised the work after your feedback. Re-check it and give a final VERDICT.",
                f"re-review · {st['agent']}")
            state["rc"], state["stop"] = rc, stop
            st["summary"] = _segment_text(jsonl)
            st["verdict"] = _verdict(_segment_text(jsonl, 1800))
            st["rounds"] = state["rounds"]
            S.save(m)
            if not (rc == 0 or stop):
                return False
        return True

    while m.status == "running":
        done_ids = {x["id"] for x in m.plan if x.get("status") == "done"}
        remaining = [x for x in m.plan if x.get("status") != "done"]
        if not remaining:
            break
        ready = [x for x in _topo(remaining) if all(d in done_ids or d not in ids for d in (x.get("depends_on") or []))] or [remaining[0]]
        writers_ready = [x for x in ready if x["agent"] not in ro_agents]
        if writers_ready:
            batch = writers_ready
            parallel = len(batch) > 1
            if parallel:
                for x in batch:
                    if not await _direct_ok(m, x["agent"], wt):
                        parallel = False
                        break
            if not parallel:
                batch = batch[:1]
            results = await asyncio.gather(*[run_writer(x, parallel) for x in batch], return_exceptions=True)
            good = True
            for x, r in zip(batch, results):                    # hand results on in plan order
                if isinstance(r, BaseException) or r is not True:
                    good = False
                    if isinstance(r, BaseException):
                        x["status"], x["note"] = "failed", f"internal error: {str(r)[:120]}"
                    continue
                writers.append(x)
                if x["summary"]:
                    notes.append(f"- {x['id']} ({x['agent']}): {x['summary'][-350:]}")
            S.save(m)
            if not good:
                state["bad"] = True
                break
        else:
            if not await run_reviewer(ready[0]):
                state["bad"] = True
                break
    m.model = base_model or m.model
    rc, stop = state["rc"], state["stop"]
    if state["bad"] and (rc == 0 or stop):
        rc, stop = 1, False                                    # a step failed even though the last call returned cleanly
    if not state["bad"] and not state["gate"] and m.status == "running":
        await _check_and_fix(m, wt, data_dir, fix_agent=(writers[-1]["agent"] if writers else None))
    if m.status == "running":
        await _finalize(m, wt, data_dir, rc, stop)


async def answer(mid: str, answers: list[dict]) -> Mission:
    m = S.m.get(mid)
    if not m or m.status != "needs_input":
        raise web.HTTPBadRequest(text="this mission is not waiting for answers")
    clean = [{"q": str(a.get("q") or "")[:200], "a": str(a.get("a") or "").strip()[:500]} for a in answers]
    m.answers = [a for a in clean if a["a"]] or [{"q": q["q"], "a": q.get("default", "")} for q in m.questions]
    m.status, m.error = "running", ""
    S.save(m)
    asyncio.create_task(_run(m))
    return m


def _suggested_models() -> dict[str, str]:
    """agent -> recommended model id (model_recommendations.json), only those this machine can run."""
    try:
        recs = json.loads((Path(agent_knowledge.__file__).parent / "model_recommendations.json")
                          .read_text(encoding="utf-8")).get("roles", {})
    except Exception:
        return {}
    try:
        have = {x["id"] for x in OCM._known_models()}
    except Exception:
        have = set()
    return {a: r["pick"] for a, r in recs.items() if r.get("pick") and (not have or r["pick"] in have)}


async def resume(mid: str, from_step: str | None = None) -> Mission:
    """Continue a paused/failed/finished pipeline: finished steps are kept (their files stay in the working copy),
    the rest re-run. `from_step` re-runs that step and everything after it."""
    m = S.m.get(mid)
    if not m or m.kind != "orchestrator" or not m.plan or m.status not in ("paused", "failed", "timed_out", "awaiting_review"):
        raise web.HTTPBadRequest(text="nothing to resume here")
    order = _topo(m.plan)
    if from_step:
        ids = [x["id"] for x in order]
        if from_step not in ids:
            raise web.HTTPBadRequest(text="unknown step")
        redo = order[ids.index(from_step):]
    else:
        redo = [x for x in order if x.get("status") != "done"]
    if not redo:
        raise web.HTTPBadRequest(text="every step is already done")
    for st in redo:
        st.update(status="queued", summary="", started=None, ended=None)
        for k in ("verdict", "rounds", "note"):
            st.pop(k, None)
    m.status, m.error, m.ended, m.verify = "running", "", None, None
    S.save(m)
    asyncio.create_task(_run_pipeline(m))
    return m


async def run_plan(mid: str, use_suggested: bool = False) -> Mission:
    m = S.m.get(mid)
    if not m or m.status != "plan_ready" or not m.plan:
        raise web.HTTPBadRequest(text="no plan is waiting for DISPATCH")
    sug = _suggested_models() if use_suggested else {}
    m.status, m.ended, m.error = "running", None, ""
    for st in m.plan:
        st["status"] = "queued"
        if sug and not st.get("model") and sug.get(st["agent"]):
            st["model"], st["model_src"] = sug[st["agent"]], "suggested"
    S.save(m)
    asyncio.create_task(_run_pipeline(m))
    return m


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
        rc, stop = await _stream_resilient(m, wt, data_dir, ag, await _with_repo_map(wt, phase_brief),
                                           phase=f"{i + 1}/{len(team)} · {ag}")
        if rc != 0 and not stop:
            break

    if rc == 0 or stop:
        await _check_and_fix(m, wt, data_dir)
    await _finalize(m, wt, data_dir, rc, stop)


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
        if m.kind == "orchestrator" and m.plan:
            m.status, m.error = "paused", "paused by you — RESUME continues from the interrupted step"
        else:
            m.status, m.error = "failed", m.error or "aborted"
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
        DEC.record_outcome(_decision_log(), m.id, "applied")
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
    DEC.record_outcome(_decision_log(), m.id, "discarded")
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
                          runtime=m.runtime, profile=m.profile, reference=m.reference)


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


async def transcript(mid: str, host: str, session_id: str | None = None) -> dict:
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
    sid = session_id or m.session_id
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
def _kill_proc(mid: str) -> None:
    p = S.procs.get(mid)
    if p and p.returncode is None:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=6)
        except Exception:
            pass


async def _watchdog() -> None:
    while True:
        try:
            await asyncio.sleep(30)
            await _release_blocked()
            now = time.time()
            for m in list(S.m.values()):
                limit = LOCAL_MISSION_TIMEOUT if (m.model or "").startswith("ollama/") else MISSION_TIMEOUT
                clock = m.phase_started or m.created          # per agent call: a 5-step pipeline may legitimately take hours
                if m.status == "running" and m.kind == "orchestrator" and m.plan and now - clock > limit:
                    logger.warning("missions %s: step timed out (> %ds) — killing it, pipeline continues", m.id, limit)
                    S.timeouts.add(m.id)
                    _kill_proc(m.id)
                    m.phase_started = now
                    continue
                if m.status == "running" and now - clock > limit:
                    logger.warning("missions %s: timed out (> %ds)", m.id, limit)
                    await abort(m.id)
                    try:
                        m.changed_files = await OCM.ak_status.worktree_changed_files(Path(m.worktree))
                    except Exception:
                        pass
                    m.error = f"timed out after {limit}s"
                    if m.changed_files:
                        # slow gateway, not a failure: it had already written files (seen live —
                        # a free model spent its last 10 minutes re-testing finished work)
                        m.status = "awaiting_review"
                        m.model_note = "hit the time limit after producing changes — review the diff before APPLY"
                    else:
                        m.status = "timed_out"
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
        p = agent_knowledge._load_persona(a["name"]) or {}
        personas.append({**a, "utility": a["name"] in agent_knowledge.UTILITY_AGENTS, "frontmatter": p.get("frontmatter", {}),
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


@routes.get("/api/profiles")
async def api_profiles(request: web.Request) -> web.Response:
    return web.json_response({"profiles": agent_knowledge.profiles(),
                              "wiki": agent_knowledge.WIKI_ROOT.is_dir()})


def _judge_state(m: Mission) -> dict:
    verdict = next((x.get("verdict") for x in reversed(m.plan or []) if x.get("verdict")), None)
    return {"verify": m.verify, "changed": len(m.changed_files or []), "verdict": verdict, "brief": (m.brief or "")[:400]}


def _judge_view(m: Mission) -> dict:
    res = DEC._decide_rules(_judge_state(m), DEC.REVIEW_QUESTIONS)
    for x in m.judge_extra or []:
        res = [x if r["id"] == x["id"] else r for r in res]
    return {"results": res, "route": DEC.route([r for r in res if r["answer"] is not None]),
            "pending": [r["id"] for r in res if r["answer"] is None],
            "questions": {q["id"]: q["text"] for q in DEC.REVIEW_QUESTIONS}}


def _judge_output(m: Mission, limit: int = 12000) -> dict:
    out, used = {}, 0
    wt = Path(m.worktree)
    for f in (m.changed_files or []):
        path = f.get("path", "")
        if used >= limit or path.startswith("shared/") or Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".pyc"):
            continue
        try:
            t = (wt / path).read_text(encoding="utf-8", errors="replace")[: limit - used]
        except Exception:
            continue
        out[path] = t
        used += len(t)
    return out


@routes.post("/api/missions/{id}/judge")
async def api_judge(request: web.Request) -> web.Response:
    """Ask the LOCAL model the one question the rules cannot answer: is every claim in the output supported by the brief?
    Only when the user presses the button (one model call); the answer and its probability are kept on the mission and logged."""
    m = S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    chain = [x for x in agent_knowledge.model_chain(m.model or None, None) if x.startswith("ollama/")]
    if not chain:
        raise web.HTTPBadRequest(text="no Ollama model available for the check")
    state = {"brief": m.brief, "answers": m.answers, "output": _judge_output(m)}
    if not state["output"]:
        raise web.HTTPBadRequest(text="this mission has no text files to check yet")
    await _ensure_ollama()
    q = [x for x in DEC.REVIEW_QUESTIONS if x["id"] == "claims_supported"]
    res = await DEC.decide(state, q, backend="local", model=chain[0])
    r = res[0]
    r["model"] = chain[0]
    m.judge_extra = [x for x in (m.judge_extra or []) if x["id"] != r["id"]] + [r]
    DEC.record(_decision_log(), m.id, "local-check", res)
    S.save(m)
    return web.json_response(_judge_view(m))


@routes.get("/api/decisions")
async def api_decisions(request: web.Request) -> web.Response:
    """Shadow-mode calibration: how often the judge's verdict matched the user's APPLY / DISCARD."""
    return web.json_response({"agreement": DEC.agreement(_decision_log()), "log": str(_decision_log())})


@routes.get("/api/model-recommendations")
async def api_model_recs(request: web.Request) -> web.Response:
    """Per-role recommended models (hypotheses until the benchmark has measured them)."""
    try:
        d = json.loads((Path(agent_knowledge.__file__).parent / "model_recommendations.json")
                       .read_text(encoding="utf-8"))
    except Exception:
        d = {"roles": {}, "measured": {}}
    return web.json_response(d)


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
    # Smith answers in ONE model call (was an agent loop that took minutes); it is told the roster + work types so a new
    # agent does not duplicate an existing one and lands in the right work type.
    smith = (agent_knowledge._load_persona("agent-smith") or {}).get("body", "")
    if smith:
        names = [a["name"] for a in agent_knowledge.list_agents() if a["name"] not in agent_knowledge.UTILITY_AGENTS]
        ctx = ("\n\n---\nEXISTING AGENTS (do not duplicate one):\n" + agent_knowledge.agent_menu(names)
               + "\n\nWORK TYPES: " + "; ".join(f"{k} = {v.get('label')}" for k, v in agent_knowledge.profiles().items())
               + "\n\nSKILL NAMES you may reference in `skills`: "
               + ", ".join(sk["name"] for sk in agent_knowledge.list_skills())[:900])
        text = ""
        for mdl in [x for x in agent_knowledge.model_chain(None, None) if x.startswith("ollama/")]:
            try:
                text = await _direct_chat(mdl, smith, ask + ctx, temperature=0.5, timeout=150 if mdl.endswith(":cloud") else 400)
                break
            except Exception as exc:
                logger.info("agent-smith direct draft on %s failed: %s", mdl, exc)
        if text:
            mm = re.search(r"```(?:markdown)?\s*(---[\s\S]*?)```", text)
            md = mm.group(1).strip() if mm else (text.strip() if text.strip().startswith("---") else "")
            return web.json_response({"markdown": md, "raw": text[-2000:] if not md else ""})
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
    profile = b.get("profile") if b.get("profile") in agent_knowledge.profiles() else "code"
    reference = bool(b.get("reference"))
    autonomy = b.get("autonomy") if b.get("autonomy") in ("ask", "plan", "auto") else "plan"

    try:
        if kind == "orchestrator":
            if len(resolved) > 1:
                names = ", ".join(p["name"] for p in resolved)
                brief = (f"Projects you may assign sub-missions to: {names}. Each sub-mission's "
                         f"\"project\" field must be one of those names (or \"same\" for "
                         f"{primary['name']}).\n\n" + brief)
            known = {a["name"] for a in agent_knowledge.list_agents()}
            m = await dispatch(primary, brief, "orchestrator", "orchestrator", model=model, runtime=runtime,
                               agents=[a for a in agents if a in known], profile=profile, reference=reference, autonomy=autonomy)
            return web.json_response(m.summary())

        if kind == "team":
            roster = agents or [(b.get("agent") or "coder").strip()]
            m = await dispatch(primary, brief, roster[0], "team", model=model, agents=roster, runtime=runtime,
                               profile=profile, reference=reference)
            return web.json_response(m.summary())

        if kind == "parallel":
            roster = agents or [(b.get("agent") or "coder").strip()]
            gid = "g" + uuid.uuid4().hex[:8]
            out = [(await dispatch(primary, brief, ag, "single", model=model, group_id=gid, runtime=runtime,
                                   profile=profile, reference=reference)).summary()
                   for ag in roster]
            return web.json_response({"group": gid, "missions": out})

        agent = (b.get("agent") or "coder").strip()
        m = await dispatch(primary, brief, agent, "single", model=model, runtime=runtime,
                           profile=profile, reference=reference)
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
    d["runmap"] = _run_stats(m)
    d["children"] = [c.summary() for c in S.m.values() if c.parent_id == m.id]
    d["judge"] = _judge_view(m)
    try:
        from . import schedule as _SCH
        d["schedule"] = _SCH.for_mission(m.id)
    except Exception:
        d["schedule"] = None
    return web.json_response(d)


def _node_rows(jsonl: Path, node: str, text_max: int = 400) -> list[dict]:
    """Transcript rows for ONE pipeline node, read from mission.jsonl (persistent, unlike the in-memory tail).
    Segments are delimited by the hub_run markers: `orch` = the orchestrator's calls, `<step id>` = that step
    (+ its idle-nudges), `gate` = hub-check fixes and review revisions."""
    try:
        lines = jsonl.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    owner, cur_match, evs = "", False, []
    for l in lines:
        try:
            e = json.loads(l)
        except Exception:
            continue
        if e.get("type") == "hub_run":
            ph, ag = e.get("phase") or "", e.get("agent") or ""
            mo = re.match(r"step (\S+) ", ph)
            if mo:
                owner = mo.group(1)
                who = owner
            elif ph.startswith(("fix ", "revise", "re-review")):
                who = "gate"
            elif ph.startswith("nudge"):
                who = owner
            else:
                who = "orch" if ag == "orchestrator" else owner
            cur_match = (who == node) or node == "all"
            if cur_match:
                evs.append({"type": "step_start", "part": {"phase": f"{ag} · {ph or 'run'} · {(e.get('model') or '').replace('opencode/', '').replace('ollama/', '')}"}})
            continue
        if cur_match:
            evs.append(e)
    return _parse_events_text(evs, text_max)


@routes.get("/api/missions/{id}/rows")
async def api_rows(request: web.Request) -> web.Response:
    m = S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such mission")
    node = request.query.get("node", "orch")
    tmax = 8000 if request.query.get("full") else 400
    rows = await asyncio.get_running_loop().run_in_executor(
        None, _node_rows, Path(m.worktree) / ".ocdata" / "mission.jsonl", node, tmax)
    return web.json_response({"rows": rows, "live": m.status == "running"})


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


@routes.post("/api/missions/{id}/answer")
async def api_answer(request: web.Request) -> web.Response:
    """Answer the orchestrator's clarifying questions; it then plans (no further questions)."""
    b = await _body(request)
    ans = b.get("answers")
    if not isinstance(ans, list):
        raise web.HTTPBadRequest(text="answers: [{q, a}] required")
    m = await answer(request.match_info["id"], [a for a in ans if isinstance(a, dict)])
    return web.json_response(m.summary())


@routes.post("/api/missions/{id}/plan")
async def api_edit_plan(request: web.Request) -> web.Response:
    """Edit the plan before DISPATCH: steps [{id, agent, brief, depends_on, model?}] (agent/model/brief/deps/removal)."""
    m = S.m.get(request.match_info["id"])
    if not m or m.status != "plan_ready":
        raise web.HTTPBadRequest(text="the plan can only be edited while it is waiting for DISPATCH")
    b = await _body(request)
    steps = _normalise_plan(b.get("steps") or [], _allowed_agents(m))
    if not steps:
        raise web.HTTPBadRequest(text="a plan needs at least one step with a brief")
    m.plan = steps
    S.save(m)
    return web.json_response(m.summary())


@routes.post("/api/missions/{id}/resume")
async def api_resume(request: web.Request) -> web.Response:
    b = await _body(request)
    m = await resume(request.match_info["id"], (b.get("from_step") or None))
    return web.json_response(m.summary())


_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


@routes.get("/api/missions/{id}/file")
async def api_file(request: web.Request) -> web.StreamResponse:
    """The CONTENT of one result file (not a diff) so you can read what the agents produced."""
    m = S.m.get(request.match_info["id"])
    if not m or not m.worktree:
        raise web.HTTPNotFound(text="no such mission")
    rel = (request.query.get("path") or "").replace("\\", "/").lstrip("/")
    wt = Path(m.worktree).resolve()
    f = (wt / rel).resolve()
    if not rel or rel.startswith(_DENY_PATHS) or (wt != f and wt not in f.parents) or not f.is_file():
        raise web.HTTPNotFound(text="no such file")
    if request.query.get("raw"):
        return web.FileResponse(f)
    ext = f.suffix.lower()
    if ext in _IMG_EXT and ext != ".svg":
        return web.json_response({"kind": "image", "size": f.stat().st_size, "path": rel})
    try:
        data = f.read_bytes()
    except Exception as exc:
        raise web.HTTPNotFound(text=str(exc))
    if b"\x00" in data[:4000]:
        return web.json_response({"kind": "binary", "size": len(data), "path": rel})
    return web.json_response({"kind": "text", "path": rel, "size": len(data), "truncated": len(data) > 200000,
                              "text": data[:200000].decode("utf-8", "replace")})


@routes.post("/api/missions/{id}/run-plan")
async def api_run_plan(request: web.Request) -> web.Response:
    """DISPATCH: run the orchestrator's plan as one pipeline in the mission's working copy."""
    b = await _body(request)
    m = await run_plan(request.match_info["id"], use_suggested=bool(b.get("use_suggested")))
    return web.json_response(m.summary())


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
    b = await _body(request)
    return web.json_response(await transcript(request.match_info["id"], request.host, (b.get("session_id") or None)))


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
        asyncio.get_running_loop().run_in_executor(None, OCM._known_models)      # warm `opencode models` (1.2 s) off the request path

    async def _on_cleanup(_app: web.Application) -> None:
        t = _app.get("missions_watchdog")
        if t:
            t.cancel()

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
