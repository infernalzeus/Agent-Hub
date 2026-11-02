"""What this operating system can actually do, in one place.

Agent Hub grew up on Windows, and some of it is genuinely Windows-shaped: the
power menu shells out to `shutdown.exe`, PC control needs a Windows MCP
provider, and orphan prevention uses a Job Object. The rest — the launcher, the
proxy, File Browser, Missions, Media, the project graph — is ordinary Python and
runs anywhere.

So rather than porting or stubbing feature by feature, each OS declares what it
supports. The UI hides what is not in `CAPABILITIES` instead of offering a
button that fails, and the packaged builds for macOS and Linux ship the same
code as Windows with a smaller surface.

Named `platforms` rather than `platform` so it cannot shadow the standard
library module of that name.
"""
from __future__ import annotations

import os
import shutil
import sys

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")

NAME = "Windows" if WINDOWS else "macOS" if MACOS else "Linux" if LINUX else sys.platform


def _capabilities() -> set[str]:
    caps = {"apps", "missions", "media", "graph", "files", "voice"}
    if WINDOWS:
        # shutdown.exe / rundll32 power actions, and a Windows MCP provider.
        caps |= {"power", "pc_control", "smb_share", "job_objects"}
    return caps


CAPABILITIES = _capabilities()


def supports(capability: str) -> bool:
    return capability in CAPABILITIES


# ── power ────────────────────────────────────────────────────────────────────
# macOS and Linux can do these too, but each needs its own privilege story
# (polkit, sudoers, osascript permissions) that has to be designed rather than
# guessed at, so they stay unsupported until that work is done.
_POWER_COMMANDS = {
    "windows": {
        "shutdown": ["shutdown", "/s", "/t", "30"],
        "restart": ["shutdown", "/r", "/t", "30"],
        "abort": ["shutdown", "/a"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
    },
}


def power_commands() -> dict[str, list[str]]:
    return dict(_POWER_COMMANDS["windows"]) if WINDOWS else {}


def tailscale_exe() -> str:
    """Default location of the Tailscale CLI for this OS."""
    found = shutil.which("tailscale")
    if found:
        return found
    if WINDOWS:
        return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                            "Tailscale", "tailscale.exe")
    if MACOS:
        return "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    return "/usr/bin/tailscale"


