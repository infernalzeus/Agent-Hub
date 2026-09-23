"""Where the Hub keeps writable state, and the interpreters optional tools run on.

One module for the two things that differ between running from a git clone and
running from an installed build:

* **STATE** — the writable folder. From source that is the repo's own ``hub/``
  folder, so ``apps.json``/``locations.json``/``data/`` stay exactly where they
  have always been. Frozen, it is ``%LOCALAPPDATA%\\AgentHub\\state`` (or
  ``$XDG_STATE_HOME``), because an installed program must not write next to its
  executable.
* **python_for(capability)** — the interpreter an optional capability runs on.
  An installed build gives each capability its own managed environment so the
  Hub never has to pip-install into itself. From source there is nothing to
  manage, so it falls back to the interpreter already running the Hub.

This exists so the release build does not have to *patch* the Hub's source to
change those two answers. Everything else is shared, and ``PACKAGED`` guards the
handful of behaviours that genuinely only apply to an installed build.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

FROZEN = bool(getattr(sys, "frozen", False))
# Set by the installer's launcher. Also honoured from the environment so the
# packaged behaviour can be exercised from source while testing a release.
PACKAGED = FROZEN or os.environ.get("AGENTHUB_PACKAGED") == "1"

# Read-only payload: the folder holding hub/, file-browser/, youtube/ ...
ASSETS = Path(__file__).resolve().parent.parent


def _default_state() -> Path:
    if not PACKAGED:
        # From source: the repo's hub/ folder, where this state already lives.
        return ASSETS / "hub"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "AgentHub" / "state"


STATE = Path(os.environ.get("AGENTHUB_STATE_DIR") or _default_state())

_LOCK = threading.RLock()


def python_for(capability: str) -> Path:
    """Interpreter for an optional capability's managed environment.

    Falls back to the running interpreter when there is no managed environment
    *and* we are not frozen. Frozen, ``sys.executable`` is the Hub's own .exe,
    not a Python — returning it would make ``-m pip`` relaunch the Hub — so the
    (missing) managed path is returned instead and the caller fails visibly.
    """
    managed = STATE / "runtimes" / capability / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if managed.is_file() or FROZEN:
        return managed
    return Path(sys.executable)


def run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)


def usable_python(path: str) -> bool:
    if not path or (FROZEN and Path(path).resolve() == Path(sys.executable).resolve()):
        return False
    try:
        return run([path, "-c", "import sys,venv; assert sys.version_info[:2]==(3,13)"], 15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_python() -> str | None:
    """A real Python 3.13 to build managed environments from."""
    candidates = []
    programs = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    candidates += [str(programs / "Python313" / "python.exe"), str(programs / "Python312" / "python.exe")]
    if not FROZEN:
        candidates.append(sys.executable)
    candidates.append(shutil.which("python") or "")
    launcher = shutil.which("py")
    if launcher:
        try:
            result = run([launcher, "-3.13", "-c", "import sys;print(sys.executable)"], 15)
            if result.returncode == 0:
                candidates.append(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    return next((p for p in candidates if usable_python(p)), None)


def payloads() -> Path | None:
    """The bundled payload tree, wherever this build keeps it.

    Frozen it sits beside the app as ``payloads/``; from source it lives under
    ``packaging/payloads/`` where fetch_payloads.py writes it. Checking both
    means the same code path is exercised in development and in the installer.
    """
    for folder in (ASSETS / "payloads", ASSETS / "packaging" / "payloads"):
        if folder.is_dir():
            return folder
    return None


def manifest() -> dict:
    """payloads.json — what this build carries and what it fetches on request."""
    root = payloads()
    for candidate in ([root / "payloads.json"] if root else []) + [ASSETS / "packaging" / "payloads.json"]:
        try:
            return json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
    return {}


def wheelhouse(capability: str) -> Path | None:
    """Bundled wheels for a capability, when the package shipped with them.

    Only capabilities listed as bundled get one. Others are on-request by
    design — pointing them at the shared wheelhouse would force a guaranteed
    failure before the network retry, which reads to the user as a broken
    install rather than a download.

    One shared wheelhouse serves the bundled capabilities (their dependency
    trees overlap heavily), but a per-capability folder still wins if present.
    """
    root = payloads()
    if not root:
        return None
    bundled = manifest().get("bundled", {}).get("wheels", {})
    if bundled and capability not in bundled:
        return None
    for folder in (root / "wheels" / capability, root / "wheels"):
        if folder.is_dir() and any(folder.glob("*.whl")):
            return folder
    return None


def bundled_python_installer() -> Path | None:
    """The Python installer carried in the package, if any.

    Only used when the machine has no suitable Python: an installed build must
    be able to set its optional tools up without sending the user hunting for a
    runtime, but it should not install one that is already there.
    """
    root = payloads()
    if not root:
        return None
    return next(iter(sorted((root / "python").glob("python-*.exe"))), None)


def install(capability: str, packages: list[str]) -> tuple[bool, str]:
    """Explicit setup action only; never called by a status probe or import."""
    with _LOCK:
        py = python_for(capability)
        if not py.is_file():
            base = find_python()
            if not base:
                installer = bundled_python_installer()
                if installer:
                    # Per-user, no PATH changes, no system-wide side effects.
                    run([str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=0",
                         "Include_launcher=0", "Include_test=0"], 1800)
                    base = find_python()
            if not base:
                return False, ("No Python 3.13 available to build the " + capability
                               + " environment. Install Python 3.13 and retry.")
            py.parent.parent.mkdir(parents=True, exist_ok=True)
            result = run([base, "-m", "venv", str(py.parent.parent)])
            if result.returncode:
                return False, result.stderr[-4000:]
        offline = wheelhouse(capability)
        cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check"]
        if offline:
            # Bundled payloads first: an installed Hub should not need the network.
            cmd += ["--no-index", "--find-links", str(offline)]
        result = run(cmd + packages)
        if result.returncode and offline:
            # A wheel was missing from the bundle; say so rather than failing silently.
            result = run([str(py), "-m", "pip", "install", "--disable-pip-version-check", *packages])
        return result.returncode == 0, (result.stdout + result.stderr)[-4000:]


def modules_ready(capability: str, modules: list[str]) -> bool:
    py = python_for(capability)
    if not py.is_file():
        return False
    try:
        return run([str(py), "-c", ";".join("import " + m for m in modules)], 30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def capability_ready(name: str) -> bool:
    """Has the installed build's first-run setup finished this capability?

    Always True from source: a git clone has no setup wizard, and the developer
    is expected to have their own tools already. Only an installed build gates
    behaviour on this, which is why callers pair it with ``PACKAGED``.
    """
    if not PACKAGED:
        return True
    try:
        from .features.onboarding import state
    except Exception:
        return True          # no onboarding module shipped: do not gate anything
    try:
        return state().get("capabilities", {}).get(name, {}).get("status") == "ready"
    except Exception:
        return False


def write_json(path: Path, value) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
