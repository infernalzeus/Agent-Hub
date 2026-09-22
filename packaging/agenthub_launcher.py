"""Entry point for the packaged Agent Hub build.

A frozen build has no separate Python, so it cannot spawn `python app.py` for the
apps it fronts. Instead the same executable re-launches itself in a child mode:
`AgentHub.exe --file-browser` *is* the File Browser process. `$HUB_EXE` in an app
manifest resolves to this (see hub/app_registry._resolve).

Run from source this is an ordinary script, so the same manifest works either way.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

# The payload root: the folder holding hub/, file-browser/, youtube/.
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _run_file_browser() -> None:
    """Become the File Browser process. Configured entirely through the
    environment (FB_ROOT / FB_WEB_HOST / FB_WEB_PORT / FB_BASE_PATH), which the
    Hub sets when it spawns this child."""
    target = ASSETS / "file-browser" / "app.py"
    if not target.is_file():
        raise SystemExit("File Browser is missing from this build: " + str(target))
    sys.path.insert(0, str(target.parent))
    runpy.run_path(str(target), run_name="__main__")


CHILD_MODES = {"--file-browser": _run_file_browser}


def main() -> None:
    mode = next((a for a in sys.argv[1:] if a in CHILD_MODES), None)
    if mode:
        CHILD_MODES[mode]()
        return
    sys.path.insert(0, str(ASSETS))
    from app import main as hub_main
    hub_main()


if __name__ == "__main__":
    main()
