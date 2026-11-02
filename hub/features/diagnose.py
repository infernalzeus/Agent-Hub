"""One read-only page of facts about this Hub, for whoever is diagnosing it away from the PC.

A person on a phone, or a Claude Code session started remotely, needs the same starting point every time:
what build is running, which services are up, what the last errors were, whether the local model server
and the missions look healthy. This returns that and nothing that changes anything.

* GET only, and GETs are open to anyone who can reach the Hub (tokens guard state changes, not reads: see request_security.py),
  so what this returns must be safe to show to that person. Hence the redaction below, and no environment variables, no settings values.
* Log lines are kept in memory (the Hub logs to the console only), newest last, and every line is passed
  through `redact()` on the way out, so a token, key or password that reached a log line is not handed on.
* Nothing is started or probed beyond a half-second look at the local model port.
"""
from __future__ import annotations

import collections
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

from aiohttp import web

from .. import runtime as RT

routes = web.RouteTableDef()

_STARTED = time.time()
RING_LINES = 600
_ring: "collections.deque[str]" = collections.deque(maxlen=RING_LINES)

_PATTERNS = [
    (re.compile(r"ahi_[A-Za-z0-9_\-]{6,}"), "ahi_[redacted]"),                                     # this Hub's own tokens
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{12,}"), "[redacted-key]"),                         # OpenAI-style keys
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{12,}"), "[redacted-key]"),         # GitHub
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[redacted-key]"),                            # Slack
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "[redacted-key]"),                                  # Google
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"(?i)(://[^/\s:@]+:)[^@\s/]+(@)"), r"\1[redacted]\2"),                           # user:password@host
    (re.compile(r"(?i)\b(api[_\-]?key|access[_\-]?token|auth[_\-]?token|token|secret|password|passwd|cookie|authorization)"
                r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',;&]{4,})"), r"\1\2[redacted]"),
]


def redact(text: str) -> str:
    """Remove anything that looks like a credential. Over-redacting a harmless word is the right way to be wrong."""
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


class _Ring(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _ring.append(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never break the Hub
            pass


_handler = _Ring(level=logging.INFO)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
if not any(isinstance(h, _Ring) for h in logging.getLogger().handlers):
    logging.getLogger().addHandler(_handler)


def _git_head() -> "str | None":
    if RT.PACKAGED:
        return None
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _free_gb(path) -> "float | None":
    try:
        return round(shutil.disk_usage(str(path)).free / 1e9, 1)
    except Exception:  # noqa: BLE001
        return None


def _local_model_server() -> dict:
    """Is something listening where Ollama listens? A half-second connect; never starts it."""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return {"listening": True}
    except OSError:
        return {"listening": False}


def _missions() -> dict:
    out: dict = {}
    try:
        from . import missions as M
        counts = collections.Counter(getattr(m, "status", "?") for m in M.S.m.values())
        out["by_status"] = dict(counts)
        out["stay_local"] = M.stay_local()
        out["skipped_models"] = {k: str(v)[:160] for k, v in (M._health() or {}).items()} if hasattr(M, "_health") else {}
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


def _apps() -> dict:
    try:
        from .. import runtime as R  # noqa: F401
        from .apps import APP_PROCS
        return {aid: {"running": bool(ap.running), **({"last_error": redact(ap.last_error)} if getattr(ap, "last_error", "") else {})} for aid, ap in APP_PROCS.items()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def _build() -> "str | None":
    try:
        from .. import ui
        return getattr(ui, "_DEPTH_LIFT_BUILD", None)
    except Exception:  # noqa: BLE001
        return None


def _work_dir() -> "str | None":
    try:
        from .. import locations
        return locations.get("work_dir")
    except Exception:  # noqa: BLE001
        return None


def recent_errors(now: "float | None" = None, within_s: int = 3600) -> "tuple[int, float, str]":
    """(how many, when the newest one was, a sample) of ERROR lines in the Hub's own in-memory log within `within_s`."""
    now = time.time() if now is None else now
    n, newest, sample = 0, 0.0, ""
    for line in list(_ring):
        if " ERROR " not in line:
            continue
        try:
            t = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if now - t <= within_s:
            n += 1
            newest, sample = max(newest, t), redact(line[20:])[:140]
    return n, newest, sample


def bundle(lines: int = 150) -> dict:
    lines = max(10, min(int(lines), RING_LINES))
    log = [redact(x) for x in list(_ring)]
    problems = [x for x in log if " ERROR " in x or " WARNING " in x or "Traceback" in x]
    work = _work_dir()
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hub": {
            "version": RT.version(), "packaged": RT.PACKAGED, "git": _git_head(), "ui_build": _build(),
            "pid": os.getpid(), "uptime_s": int(time.time() - _STARTED),
            "python": sys.version.split()[0], "platform": platform.platform(),
            "port": os.environ.get("HUB_PORT") or "8081",
        },
        "apps": _apps(),
        "missions": _missions(),
        "local_model_server": _local_model_server(),
        "disk_free_gb": {"state": _free_gb(RT.STATE), "work": _free_gb(work) if work else None},
        "problems": problems[-30:],
        "log_tail": log[-lines:],
        "note": "Credentials are removed from log lines; this endpoint only reads.",
    }


@routes.get("/api/diagnose")
async def api_diagnose(request: web.Request) -> web.Response:
    try:
        lines = int(request.query.get("lines", "150"))
    except ValueError:
        lines = 150
    return web.json_response(bundle(lines))


# --- transition self-test: the page measures its own browser window and reports here -----------------------------------
# Armed only from this side (a state file), so a stranger on the tailnet cannot make anyone's browser run it.
_ARM = RT.STATE / "transition_selftest.arm"
_RESULT = RT.STATE / "transition_selftest_result.json"


@routes.get("/api/diagnose/client/arm")
async def api_client_arm(request: web.Request) -> web.Response:
    try:
        turns = int(_ARM.read_text(encoding="utf-8").strip() or "6")
        return web.json_response({"armed": True, "turns": max(1, min(turns, 20))})
    except (OSError, ValueError):
        return web.json_response({"armed": False})


@routes.post("/api/diagnose/client")
async def api_client_report(request: web.Request) -> web.Response:
    if not _ARM.exists():                      # only accept a report that was asked for
        raise web.HTTPForbidden(text="no self-test armed")
    data = await request.json()
    RT.write_json(_RESULT, data)
    try:
        _ARM.unlink()
    except OSError:
        pass
    return web.json_response({"ok": True})
