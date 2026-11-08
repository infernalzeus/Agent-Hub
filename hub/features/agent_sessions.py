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
    """The most recent thing a person typed to it, with system wrappers removed. Claude Code writes it as a `user` record; Codex as a
    `response_item` message with role user, mixed in with its own context blocks, which start with a tag and are skipped."""
    for r in reversed(recs):
        t = ""
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if r.get("type") == "user":
            t = _text_of((r.get("message") or {}).get("content"))
        elif r.get("type") == "response_item" and pl.get("type") == "message" and pl.get("role") == "user":
            t = " ".join(str(x.get("text") or "") for x in (pl.get("content") or []) if isinstance(x, dict) and x.get("type") == "input_text")
        elif r.get("type") == "event_msg" and pl.get("type") == "user_message":
            t = str(pl.get("message") or "")
        else:
            continue
        t = re.sub(r"<([A-Za-z_-]+)[^>]*>.*?</\1>", "", t, flags=re.S).strip()
        if t and not t.startswith(("<", "# AGENTS.md", "AGENTS.md")):
            return _short("Doctor session" if t.startswith("You are the doctor for Agent Hub") else t, 70)
    return ""


def _own_title(recs: "list[dict]", path: Path) -> str:
    """The name the session itself carries (Claude Code writes a `custom-title` when you rename it and an `ai-title` it makes up), not the last thing typed to it. Looked for in the
    recent records first, then through the file, newest record winning; empty when it has none."""
    def of(r: dict) -> str:
        return str(r.get("customTitle") or r.get("aiTitle") or "") if r.get("type") in ("custom-title", "ai-title") else ""
    for r in reversed(recs):
        if of(r):
            return _short(of(r), 70)
    best = ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '-title"' in line:
                    try:
                        best = of(json.loads(line)) or best
                    except ValueError:
                        pass
    except OSError:
        pass
    return _short(best, 70) if best else ""


def _cwd(recs: "list[dict]", path: Path) -> str:
    """The folder the session works in. Claude Code writes it on every record; Codex writes it once, in the first line (session_meta)."""
    for r in reversed(recs):
        c = r.get("cwd") or ((r.get("payload") or {}).get("cwd") if isinstance(r.get("payload"), dict) else None)
        if isinstance(c, str) and c:
            return c
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            first = json.loads(f.readline() or "{}")
        c = first.get("cwd") or (first.get("payload") or {}).get("cwd")
        return c if isinstance(c, str) else ""
    except (OSError, ValueError, AttributeError):
        return ""


_HEAD: dict = {}


def _first_asked(path: Path) -> str:
    """When the tail of a long session holds no message from the person (a long run of tool output), the first thing they asked, from the start of the file."""
    try:
        key = (str(path), path.stat().st_mtime)
        if key in _HEAD:
            return _HEAD[key]
        recs = []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(400):
                line = f.readline()
                if not line:
                    break
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    pass
        out = _title(list(reversed(recs)))                       # _title looks from the end; the first request is the oldest, so hand it the list reversed and take its last
        for r in recs:
            t = _title([r])
            if t:
                out = t
                break
        _HEAD.clear()
        _HEAD[key] = out
        return out
    except (OSError, ValueError):
        return ""


def _helper_session(title: str, last: str) -> bool:
    """Codex runs small review sessions of its own (it asks itself whether an action is allowed). They are not conversations with the person."""
    return title.startswith("The following is the Codex agent history") or last.startswith('{"risk_level"')


def _last_said(recs: "list[dict]") -> str:
    """The last thing the agent itself wrote, short. Empty when the tail holds none."""
    for r in reversed(recs):
        if r.get("type") == "assistant":
            t = _text_of((r.get("message") or {}).get("content")).strip()
            if t:
                return _short(t, 220)
        rp = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if r.get("type") == "response_item" and rp.get("type") == "message" and rp.get("role") == "assistant":
            t = " ".join(str(x.get("text") or "") for x in (rp.get("content") or []) if isinstance(x, dict) and x.get("type") == "output_text").strip()
            if t:
                return _short(t, 220)
        p = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        if r.get("type") == "event_msg" and p.get("type") in ("agent_message", "task_complete"):
            t = str(p.get("message") or p.get("last_agent_message") or "").strip()
            if t:
                return _short(t, 220)
    return ""


def folder_of(session_id: str) -> "str | None":
    """The folder of a session the scan currently lists, by id; never a path taken from a request."""
    for row in scan(limit=40):
        if row["id"] == session_id and row.get("cwd") and Path(row["cwd"]).is_dir():
            return row["cwd"]
    return None


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
        cwd = _cwd(recs, p)
        asked = _title(recs) or (_first_asked(p) if agent == "codex" else "")
        title = (_own_title(recs, p) if agent == "claude" else "") or asked
        last = _last_said(recs)
        if agent == "codex" and _helper_session(title, last):
            continue
        rows.append({
            "agent": agent, "project": _project_name(p.parent.name) if agent == "claude" else (Path(cwd).name or "Codex"),
            "title": title, "asked": asked, "state": state, "ask": ask, "age_s": int(age), "id": p.stem[:12],
            "cwd": cwd, "last": last,
        })
    return rows


# --- usage: how much Claude Code has written lately, counted from the same logs --------------------------------------------
_USAGE: dict = {"at": 0.0, "value": None, "busy": False}
USAGE_TTL_S = 300
_TS = re.compile(r'"timestamp":"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)')
_OUT = re.compile(r'"output_tokens":(\d+)')
_IN = re.compile(r'"input_tokens":(\d+)')


def _compute_usage(now: float) -> dict:
    """Output and fresh input tokens Claude Code logged, by hour for the last 24 h and in total for 5 h and 7 days.

    The plan's own limit is not in the logs, so this is a count, not a percentage."""
    import calendar
    hours = [0] * 24
    t5h = t7d = msgs5h = 0
    for p in CLAUDE_DIR.glob("*/*.jsonl"):
        try:
            if now - p.stat().st_mtime > 7 * 86400:
                continue
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"output_tokens"' not in line:
                        continue
                    m = _TS.search(line)
                    o = _OUT.search(line)
                    if not (m and o):
                        continue
                    when = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
                    age = now - when
                    if age < 0 or age > 7 * 86400:
                        continue
                    n = int(o.group(1)) + int((_IN.search(line) or [0, 0])[1] if _IN.search(line) else 0)
                    t7d += n
                    if age <= 5 * 3600:
                        t5h += n
                        msgs5h += 1
                    if age <= 24 * 3600:
                        hours[23 - int(age // 3600)] += n
        except OSError:
            continue
    return {"claude": {"tokens_5h": t5h, "tokens_7d": t7d, "replies_5h": msgs5h, "by_hour": hours}, "codex": None,
            "note": "counted from Claude Code's own logs; the plan limit is not in them, so no percentage; Codex not read"}


def usage(now: "float | None" = None) -> "dict | None":
    """The last count, instantly. A fresh one is computed in the background when it is older than USAGE_TTL_S."""
    import threading
    now = now or time.time()
    if now - _USAGE["at"] > USAGE_TTL_S and not _USAGE["busy"]:
        _USAGE["busy"] = True

        def work():
            try:
                _USAGE["value"] = _compute_usage(time.time())
                _USAGE["at"] = time.time()
            except Exception:  # noqa: BLE001
                pass
            finally:
                _USAGE["busy"] = False
        threading.Thread(target=work, daemon=True).start()
    return _USAGE["value"]
