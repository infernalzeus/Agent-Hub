"""Safely-local, reversible install actions for the fresh-install setup banner.

Companion to setup_check.py's detection: a small, deliberately short list of
issues the hub is willing to fix *itself* on a click — a local `npm install`
under OPENCODE_ROOT, a `pip install` into an interpreter already on this
machine. Nothing here touches system state (no services, no elevated
installers, no writing outside this repo / an existing interpreter's
site-packages) — Node.js and Tailscale stay show-command-only issues in
setup_check.py, never auto-run.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .opencode import OPENCODE_EXE, OPENCODE_ROOT

HERE = Path(__file__).resolve().parent.parent.parent  # Agent Hub/
_YT_REQ_FILE = HERE / "requirements-youtube.txt"


def _read_yt_deps() -> list[str]:
    """requirements-youtube.txt is the single source of truth for what
    install-yt-deps runs — read it fresh rather than hand-duplicating the
    list here, so the two can never drift apart."""
    try:
        return [ln.strip() for ln in _YT_REQ_FILE.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return ["yt-dlp", "mutagen", "google-api-python-client",
                 "google-auth-oauthlib", "google-auth-httplib2"]


def _run(cmd: list[str], cwd: str | Path | None = None, timeout: float = 180) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                            text=True, timeout=timeout)
        log = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, log[-4000:]
    except Exception as exc:
        return False, str(exc)


def yt_python_target() -> str:
    """Which interpreter YT deps should install into: the configured
    YT_DL_PYTHON if it actually resolves to something on this machine,
    else the Hub's own interpreter (the common case on a fresh install,
    where the default "python3.11" name resolves to nothing)."""
    from ..config import YT_DL_PYTHON
    if Path(YT_DL_PYTHON).is_file():
        return YT_DL_PYTHON
    return shutil.which(YT_DL_PYTHON) or sys.executable


def _install_opencode() -> tuple[bool, str]:
    npm = shutil.which("npm")
    if not npm:
        return False, "npm not found on PATH — install Node.js first, then retry."
    OPENCODE_ROOT.mkdir(parents=True, exist_ok=True)
    pkg = OPENCODE_ROOT / "package.json"
    if not pkg.is_file():
        pkg.write_text('{"name": "opencode-root", "private": true}\n', encoding="utf-8")
    ok, log = _run([npm, "install", "opencode-ai"], cwd=OPENCODE_ROOT)
    if ok and not Path(OPENCODE_EXE).is_file():
        ok = False
        log += "\n\nnpm install finished but opencode.exe still wasn't found at the expected path."
    return ok, log


def _install_yt_deps() -> tuple[bool, str]:
    target = yt_python_target()
    ok, log = _run([target, "-m", "pip", "install", *_read_yt_deps()], timeout=300)
    return ok, f"installed into: {target}\n\n{log}"


@dataclass
class InstallAction:
    id: str
    label: str
    run: Callable[[], tuple[bool, str]]


ACTIONS: dict[str, InstallAction] = {
    a.id: a for a in [
        InstallAction("install-opencode", "Install OpenCode now", _install_opencode),
        InstallAction("install-yt-deps", "Install YouTube dependencies now", _install_yt_deps),
    ]
}
