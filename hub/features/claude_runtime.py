"""Claude Code CLI as a second Missions runtime, alongside OpenCode.

Plays the same role here that `opencode.py` plays for the OpenCode branch:
build the subprocess argv, and hand missions.py events in the shape
`_stream_one` already expects — so the worktree/diff/apply/discard lifecycle,
the SSE tail, and mission bookkeeping need no changes at all. Only
`_stream_resilient` (in missions.py) branches on `Mission.runtime` to come
here instead of the OpenCode path. See the architecture write-up
(`LLM Wiki/entities/agent-hub.md`, Round 7) for the design rationale.

Verified live on this machine (2026-09-14, `claude --version` → 2.1.170,
already installed, no extra dependency to bootstrap here): headless/streaming
shape is

    claude -p "<brief>" --output-format stream-json --verbose \
        --permission-mode acceptEdits [--model <id>] --agent <name>

**Persona passing: file-based, not `--agents <json>`.** The first version of
this module passed every roster persona inline as one `--agents` JSON blob —
that FAILED live with "The command line is too long" (Windows' ~8k argv
limit; the roster+utility set serializes to ~10.5 KB). Fixed by writing each
persona to `.claude/agents/<name>.md` in the worktree instead — Claude Code's
own project-level subagent convention, discovered from `cwd` exactly the way
OpenCode discovers `.opencode/agent/<name>.md`. Same source persona `.md`
files, a second directory-based renderer — not a second persona system, and
not a second failure mode. `.claude` was added to `HUB_SCAFFOLDING`
(opencode.py) so these files never appear in a mission's diff or an APPLY
merge, same as `.opencode` already didn't.

Auth is via `claude auth login` (this machine's OAuth token was expired when
this was written — that's a one-time interactive step, never done by this
code) and shares the user's Pro-plan usage pool with every other Claude Code
session on the machine, per their explicit choice over the ANTHROPIC_API_KEY
alternative (isolated quota, metered cost — see the write-up).

Verified end-to-end against the real CLI (2026-09-14): a `--agent coder` run
against the materialized `.claude/agents/` correctly resolved the persona, the
subprocess produced `system/init` (with `session_id`), `system/api_retry`,
and a terminal `type:"result"` event — the run itself failed only on this
machine's expired OAuth token (`api_error_status: 401`), which `auth login`
fixes; the plumbing (argv, cwd, event stream, session_id extraction,
`is_stop_event`/`error_text` both firing correctly on the 401) is confirmed,
not assumed.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

CLAUDE_EXE = shutil.which("claude") or "claude"


def render_agent_md(name: str, load_persona) -> str | None:
    """One persona .md → Claude Code's `.claude/agents/<name>.md` shape. Claude
    only reads `description` from the frontmatter; OpenCode-specific keys
    (mode/bash/skills/permission/temperature/steps) don't carry over — those
    are applied through --model / mission settings instead, same as they
    already are for the OpenCode branch."""
    p = load_persona(name)
    if not p:
        return None
    fm = p.get("frontmatter") or {}
    body = (p.get("body") or "").strip()
    return f'---\ndescription: {json.dumps(fm.get("description", name))}\n---\n\n{body}\n'


def materialize_agents(wt: Path, names: list[str], load_persona) -> None:
    adir = wt / ".claude" / "agents"
    adir.mkdir(parents=True, exist_ok=True)
    for name in names:
        txt = render_agent_md(name, load_persona)
        if txt:
            (adir / f"{name}.md").write_text(txt, encoding="utf-8")


def build_cmd(*, brief: str, agent: str, model: str | None) -> list[str]:
    cmd = [CLAUDE_EXE, "-p", brief, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--agent", agent]
    if model:
        cmd += ["--model", model]
    return cmd


def extract_session_id(ev: dict) -> str | None:
    sid = ev.get("session_id") or ev.get("sessionId")
    if not sid:
        sid = (ev.get("message") or {}).get("session_id")
    return sid if isinstance(sid, str) and sid else None


def error_text(ev: dict) -> str | None:
    """None if `ev` isn't an error; otherwise a short description."""
    if ev.get("is_error"):
        return json.dumps(ev)[:400]
    if ev.get("type") == "system" and ev.get("subtype") in ("error", "api_retry"):
        return ev.get("error") or json.dumps(ev)[:400]
    if ev.get("type") == "result" and ev.get("subtype") not in (None, "success"):
        return f"result: {ev.get('subtype')}"
    return None


def is_stop_event(ev: dict) -> bool:
    return ev.get("type") == "result"
