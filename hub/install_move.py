"""Moving the Hub's own install folder, planned now and carried out at shutdown.

A running program on Windows holds its own .exe and DLLs open, so the Hub cannot
copy itself anywhere. The move has to be done by something outside the folder,
after this process has gone. So nothing here moves anything: it decides whether a
move *could* work, writes the intention down, and prepares the small script that
does it once the Hub has exited.

One rule shapes all of it: **copy, verify, then delete - never move in place.**
Until the last step the old install is intact and still launches, so an
interrupted move costs disk space rather than a working application.

What a move touches, and what it does not:

* `agenthub://` in HKCU **heals itself** - `Agent Hub.vbs` rewrites it on every
  start when the stored command is not its own path.
* The Start-menu, desktop and startup shortcuts, and the uninstaller's
  `UninstallString`, **do not** - the mover rewrites them, and only after the
  copy has been verified.
* `STATE` does not move at all. Channels, automations, the theme and the tokens
  live outside the install folder and are untouched by any of this.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from aiohttp import web

from .config import logger
from .runtime import PACKAGED, STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "pending_move.json"      # outside the folder being moved, on purpose


def install_dir() -> Path:
    """The folder that would move: the one holding this package."""
    return Path(__file__).resolve().parent.parent


def _free_bytes(path: Path) -> int:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(str(probe)).free


def _size_of(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def why_not(target: "str | Path") -> str:
    """Why this folder cannot be the new home, or "" if it can.

    Checked now, while there is still a person to tell. Every one of these would
    otherwise surface at shutdown, when nobody is watching and the Hub is halfway
    through closing.
    """
    if not PACKAGED:
        return "running from source - there is no install folder to move"
    raw = str(target or "").strip().strip('"')
    if not raw:
        return "choose a folder"
    p = Path(raw)
    if not p.is_absolute():
        return "give a full path, starting with a drive"
    if raw.startswith("\\\\") or raw.startswith("//"):
        return "a network location cannot host the install"
    here = install_dir()
    try:
        if p.resolve() == here.resolve():
            return "that is where it already is"
        if here.resolve() in p.resolve().parents:
            return "that folder is inside the current install"
    except OSError:
        return "that path cannot be read"
    if p.exists():
        if not p.is_dir():
            return "that is a file"
        if any(p.iterdir()):
            return "that folder is not empty"
    else:
        parent = p.parent
        if not parent.is_dir():
            return f"{parent} does not exist"
    need = _size_of(here)
    free = _free_bytes(p)
    if free < need * 1.2:                       # headroom: copy, then delete later
        return (f"not enough room - needs about {need // (1024*1024)} MB "
                f"and that drive has {free // (1024*1024)} MB")
    return ""


def pending() -> dict:
    """The move that is queued, if any. Always a dict, never raises."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def plan(target: str) -> dict:
    """Write down where the Hub should move to. Nothing is copied yet."""
    why = why_not(target)
    if why:
        raise ValueError(why)
    row = {"from": str(install_dir()), "to": str(Path(target)), "state": "queued"}
    write_json(FILE, row)
    logger.info("install_move: queued %s -> %s", row["from"], row["to"])
    return row


def cancel() -> bool:
    """Forget a queued move. Nothing to undo - nothing has happened yet."""
    if not FILE.exists():
        return False
    try:
        FILE.unlink()
    except OSError:
        return False
    logger.info("install_move: cancelled")
    return True


def clear_result() -> None:
    """Drop the record once its outcome has been shown."""
    cancel()


# macOS and Linux have the same problem and a simpler answer: no registry, and a
# shell that can replace a running script's own files once the process is gone.
# What breaks instead is the launcher entry - a .desktop file on Linux, a Dock or
# login item on macOS - which points at the old path exactly as a shortcut does.
MOVER_POSIX = r"""#!/bin/sh
# Written by Agent Hub at shutdown. Copy, verify, then remove - never move in
# place, so an interruption costs disk space rather than a working install.
OLD="$1"; NEW="$2"; PID="$3"; NOTE="$4"

i=0
while [ $i -lt 60 ]; do
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
  i=$((i+1))
done
if kill -0 "$PID" 2>/dev/null; then
  echo "timed out waiting for the hub to exit" > "$NOTE"
  exit 1
fi

mkdir -p "$NEW" || { echo "could not create $NEW" > "$NOTE"; exit 1; }
cp -a "$OLD/." "$NEW/" || {
  echo "copy failed - nothing was changed, the old install still works" > "$NOTE"
  exit 1
}
# Verify before anything is repointed: the launcher must exist in the copy.
if [ ! -e "$NEW/AgentHub" ] && [ ! -e "$NEW/app.py" ]; then
  echo "the copy is missing the launcher - nothing was changed" > "$NOTE"
  exit 1
fi
echo ok > "$NOTE"
# Repoint the desktop entry if there is one, then start from the new place.
for d in "$HOME/.local/share/applications/agent-hub.desktop"          "$HOME/.config/autostart/agent-hub.desktop"; do
  [ -f "$d" ] && sed -i.bak "s|$OLD|$NEW|g" "$d" 2>/dev/null
done
( cd "$NEW" && ( [ -x ./AgentHub ] && ./AgentHub || python3 app.py ) >/dev/null 2>&1 & )
sleep 3
rm -rf "$OLD"
exit 0
"""

MOVER = r"""@echo off
setlocal
rem Written by Agent Hub at shutdown. Copies the install to a new folder, checks
rem the copy, and only then repoints the shortcuts and removes the old one.
set "OLD=%~1"
set "NEW=%~2"
set "PID=%~3"
set "NOTE=%~4"

rem Wait for the Hub to exit; it holds its own files open until it does.
for /l %%i in (1,1,60) do (
  tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul || goto gone
  timeout /t 1 /nobreak >nul
)
echo timed out waiting for the hub to exit > "%NOTE%"
exit /b 1

:gone
robocopy "%OLD%" "%NEW%" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
  echo copy failed - nothing was changed, the old install still works > "%NOTE%"
  exit /b 1
)
if not exist "%NEW%\AgentHub.exe" (
  echo the copy is missing AgentHub.exe - nothing was changed > "%NOTE%"
  exit /b 1
)
echo ok > "%NOTE%"
rem Verified. Only now is anything pointed at the new folder.
start "" "%NEW%\AgentHub.exe"
rem The old tree goes last, and a failure here is untidy, not fatal.
timeout /t 3 /nobreak >nul
rmdir /s /q "%OLD%"
exit /b 0
"""


def write_mover(tmp_dir: "Path | None" = None, windows: "bool | None" = None) -> Path:
    """Put the mover somewhere that is not the folder being moved.

    It ships inside the Hub as a string and is written out at shutdown, so it
    travels with the application rather than being something a machine has to
    already have - and the file that actually runs is outside the folder it
    deletes, which is the only way this can work at all.
    """
    base = Path(tmp_dir or os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp")
    base.mkdir(parents=True, exist_ok=True)
    # Taken as an argument rather than read from os.name, so the other platform's
    # script can be checked from here - patching os.name globally breaks pathlib.
    if os.name == "nt" if windows is None else windows:
        script = base / "agent-hub-move.cmd"
        script.write_text(MOVER, encoding="utf-8")
        return script
    script = base / "agent-hub-move.sh"
    script.write_text(MOVER_POSIX, encoding="utf-8")
    try:
        script.chmod(0o755)
    except OSError:
        pass
    return script


def launch(tmp_dir: "Path | None" = None) -> bool:
    """Start the mover, detached, and let this process finish exiting.

    Called from the shutdown path. Returns whether it was started - a move that
    could not start must never stop the Hub from closing.
    """
    row = pending()
    if row.get("state") != "queued":
        return False
    try:
        import subprocess
        script = write_mover(tmp_dir)
        note = Path(script).with_name("agent-hub-move.result.txt")
        row["state"], row["note"] = "running", str(note)
        write_json(FILE, row)
        args = ([ "cmd", "/c", str(script)] if os.name == "nt" else ["/bin/sh", str(script)])
        subprocess.Popen(
            args + [row["from"], row["to"], str(os.getpid()), str(note)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) if os.name == "nt" else 0,
            start_new_session=(os.name != "nt"),
            close_fds=True)
        logger.info("install_move: mover started for %s", row["to"])
        return True
    except Exception as exc:
        logger.warning("install_move: could not start the mover: %s", exc)
        return False


def outcome() -> dict:
    """What came of a move, read on the next start.

    `done` when the Hub is now running from where it was asked to be - the
    strongest check available, because it is the thing the move was for.
    """
    row = pending()
    if not row:
        return {}
    if row.get("state") == "queued":
        return {**row, "result": "queued"}
    here, want = str(install_dir()).rstrip("\\/").lower(), str(row.get("to", "")).rstrip("\\/").lower()
    if want and here == want:
        return {**row, "result": "done"}
    note = ""
    try:
        note = Path(row.get("note", "")).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        pass
    return {**row, "result": "failed", "why": note or "the move did not finish; this install is unchanged"}


# -- http ----------------------------------------------------------------------
@routes.get("/api/install-move")
async def api_get(request: web.Request) -> web.Response:
    return web.json_response({"supported": bool(PACKAGED), "here": str(install_dir()),
                              **outcome()})


@routes.post("/api/install-move")
async def api_plan(request: web.Request) -> web.Response:
    """Queue a move. It happens the next time the Hub closes."""
    try:
        b = await request.json()
    except Exception:
        b = {}
    if b.get("cancel"):
        return web.json_response({"ok": cancel()})
    try:
        return web.json_response(plan(str(b.get("to") or "")))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
