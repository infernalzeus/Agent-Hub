"""Every Claude Code and Codex session on this PC, read from the logs those tools already write.

Nothing is asked of the agents and nothing is installed: Claude Code keeps one JSON-lines file per session under
`~/.claude/projects/<project>/`, Codex one per session under `~/.codex/sessions/YYYY/MM/DD/`. The last few records say
what a session is doing:

* **working**   - the file changed in the last minute and the last record is not a finished answer;
* **needs you** - the last answer ended in a question, or a tool call has been waiting for a result for more than
                  45 seconds (a permission prompt or a very long command: the log cannot tell which, so it says both);
* **idle**      - the last answer was a finished statement.

This is a reading of logs, not a promise: a session that died looks idle, and a long command looks like waiting.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

CLAUDE_DIR = Path(os.path.expanduser("~/.claude/projects"))
CODEX_DIR = Path(os.path.expanduser("~/.codex/sessions"))
WORKING_S = 60
PENDING_TOOL_S = 45
WINDOW_S = 24 * 3600
TAIL_BYTES = 262_144


def _tail_records(path: Path) -> "list[dict]":
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - TAIL_BYTES))
            raw = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    if size > TAIL_BYTES and raw:
        raw = raw[1:]                       # the first line is cut in the middle
    out = []
    for line in raw:
        try:
            d = json.loads(line)
            if isinstance(d, dict):
                out.append(d)
        except ValueError:
            continue
    return out


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(x.get("text") or "") for x in content if isinstance(x, dict) and x.get("type") == "text")
    return ""


def _short(s: str, n: int = 140) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _project_name(dirname: str) -> str:
    # "N--Code-git-repositories--LLM-Wiki---Obsidian-Second-Brain" -> the last meaningful part
    parts = [p for p in re.split(r"-{2,}", dirname) if p]
    return (parts[-1] if parts else dirname).replace("-", " ")[:48]


def _claude_state(recs: "list[dict]", age: float) -> "tuple[str, str]":
    chat = [r for r in recs if r.get("type") in ("user", "assistant")]
    if not chat:
        return "idle", ""
    last = chat[-1]
    msg = last.get("message") or {}
    if last["type"] == "assistant":
        text = _text_of(msg.get("content"))
        if msg.get("stop_reason") == "tool_use":
            if age < PENDING_TOOL_S:
                return "working", ""
            return "needs_you", f"A tool call has waited {int(age // 60) or 1} min for a result: a permission prompt or a long command"
        if text.strip().endswith("?"):
            return "needs_you", _short(text.strip().splitlines()[-1] if text.strip() else "")
        return "idle", ""
    return ("working", "") if age < WORKING_S else ("idle", "")


def _codex_state(recs: "list[dict]", age: float) -> "tuple[str, str]":
    for r in reversed(recs):
        p = r.get("payload") or {}
        t = p.get("type") if isinstance(p, dict) else None
        if r.get("type") == "event_msg" and t == "task_complete":
            msg = str(p.get("last_agent_message") or "")
            return ("needs_you", _short(msg.strip().splitlines()[-1])) if msg.strip().endswith("?") else ("idle", "")
        if r.get("type") == "event_msg" and t in ("task_started", "user_message", "agent_message", "exec_command_begin"):
            return ("working", "") if age < WORKING_S else ("idle", "")
    return ("working", "") if age < WORKING_S else ("idle", "")


def _title(recs: "list[dict]") -> str:
    """The most recent thing a person typed to it, with system wrappers removed."""
    for r in reversed(recs):
        if r.get("type") == "user":
            t = _text_of((r.get("message") or {}).get("content"))
            t = re.sub(r"<([a-z-]+)[^>]*>.*?</\1>", "", t, flags=re.S).strip()
            if t:
                return _short(t, 70)
    return ""


def scan(now: "float | None" = None, limit: int = 10) -> "list[dict]":
    now = now or time.time()
    rows: "list[dict]" = []
    files: "list[tuple[float, str, Path]]" = []
    try:
        for p in CLAUDE_DIR.glob("*/*.jsonl"):
            m = p.stat().st_mtime
            if now - m < WINDOW_S:
                files.append((m, "claude", p))
    except OSError:
        pass
    try:
        for p in CODEX_DIR.glob("**/*.jsonl"):
            m = p.stat().st_mtime
            if now - m < WINDOW_S:
                files.append((m, "codex", p))
    except OSError:
        pass
    files.sort(reverse=True)
    for m, agent, p in files[:limit]:
        recs = _tail_records(p)
        age = now - m
        state, ask = (_claude_state if agent == "claude" else _codex_state)(recs, age)
        rows.append({
            "agent": agent, "project": _project_name(p.parent.name) if agent == "claude" else "Codex",
            "title": _title(recs), "state": state, "ask": ask, "age_s": int(age), "id": p.stem[:12],
        })
    return rows
