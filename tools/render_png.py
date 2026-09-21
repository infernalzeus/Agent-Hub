"""Render an HTML/SVG file to a PNG with headless Edge or Chrome (no extra dependencies).

    python tools/render_png.py in.html out.png [width=1080] [height=1080]

Used by the `designer` agent. Exit 0 + prints the output path on success; exit 2 if no
browser was found; exit 1 if the render produced no file.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> str | None:
    for c in CANDIDATES:
        if os.path.isfile(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 1
    src, dest = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    w = int(argv[3]) if len(argv) > 3 else 1080
    h = int(argv[4]) if len(argv) > 4 else 1080
    if not src.is_file():
        print(f"input not found: {src}")
        return 1
    exe = find_browser()
    if not exe:
        print("no Edge/Chrome found — deliver the HTML and say a PNG could not be rendered")
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with tempfile.TemporaryDirectory(prefix="render_") as prof:
        cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               f"--user-data-dir={prof}", f"--window-size={w},{h}", "--virtual-time-budget=4000",
               f"--screenshot={dest}", src.as_uri()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("render timed out")
            return 1
    if dest.is_file() and dest.stat().st_size > 500:
        print(str(dest))
        return 0
    print("render produced no image")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
