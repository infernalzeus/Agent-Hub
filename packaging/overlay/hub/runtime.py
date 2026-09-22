"""Writable per-user state and isolated optional Python environments."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

FROZEN = bool(getattr(sys, 'frozen', False))
ASSETS = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get('AGENTHUB_STATE_DIR') or (
    str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AgentHub' / 'state')
    if FROZEN else str(ASSETS / 'hub')))
_LOCK = threading.RLock()


def python_for(capability: str) -> Path:
    return STATE / 'runtimes' / capability / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, creationflags=0x08000000 if os.name == 'nt' else 0)


def usable_python(path: str) -> bool:
    if not path or (FROZEN and Path(path).resolve() == Path(sys.executable).resolve()):
        return False
    try:
        result = run([path, '-c', 'import sys,venv; assert sys.version_info[:2]==(3,13)'], 15)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_python() -> str | None:
    candidates = [str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Python/Python313/python.exe'),
                  str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Python/Python312/python.exe')]
    if not FROZEN:
        candidates.append(sys.executable)
    candidates += [shutil.which('python') or '']
    launcher = shutil.which('py')
    if launcher:
        for version in ('-3.13',):
            try:
                result = run([launcher, version, '-c', 'import sys;print(sys.executable)'], 15)
                if result.returncode == 0:
                    candidates.append(result.stdout.strip())
            except (OSError, subprocess.SubprocessError):
                pass
    return next((p for p in candidates if usable_python(p)), None)


def install(capability: str, packages: list[str]) -> tuple[bool, str]:
    """Explicit setup action only; never called by a status probe or import."""
    with _LOCK:
        py = python_for(capability)
        if not py.is_file():
            base = find_python()
            if not base:
                winget = shutil.which('winget')
                if not winget:
                    return False, 'Install Python 3.13 from python.org, then retry. Windows App Installer is unavailable.'
                result = run([winget, 'install', '--id', 'Python.Python.3.13', '--exact', '--scope', 'user',
                              '--accept-package-agreements', '--accept-source-agreements'])
                base = find_python()
                if not base:
                    return False, 'Python installation needs attention.\n' + result.stdout[-2000:] + result.stderr[-2000:]
            py.parent.parent.mkdir(parents=True, exist_ok=True)
            result = run([base, '-m', 'venv', str(py.parent.parent)])
            if result.returncode:
                return False, result.stderr[-4000:]
        result = run([str(py), '-m', 'pip', 'install', '--disable-pip-version-check', *packages])
        return result.returncode == 0, (result.stdout + result.stderr)[-4000:]


def modules_ready(capability: str, modules: list[str]) -> bool:
    py = python_for(capability)
    if not py.is_file():
        return False
    try:
        return run([str(py), '-c', ';'.join('import ' + m for m in modules)], 30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def write_json(path: Path, value) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
