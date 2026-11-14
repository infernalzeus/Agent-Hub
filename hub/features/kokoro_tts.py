"""Kokoro, a speech model that runs on this PC: no internet, no waiting on a cloud service, about a second for a sentence once it is loaded.

It lives in a different Python from the Hub's (the one with Kokoro installed), so the Hub starts `packaging/kokoro_worker.py` there as a child process, keeps it loaded while it is
used and lets it exit after ten idle minutes (it holds a few hundred MB of memory). Nothing is downloaded: only the model and the voice files already in the Hugging Face cache on
this PC can be used. Voice ids are `k:<voice>` (for example `k:am_onyx`).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from ..config import logger

IDLE_EXIT_S = 600
import atexit

_WORKER: dict = {"proc": None, "lock": None, "last": 0.0, "seq": 0, "reaper": None}


def _python() -> "str | None":
    env = os.environ.get("AGENTHUB_KOKORO_PYTHON")
    if env and Path(env).is_file():
        return env
    for name in ("python3.11", "python3.12", "python3.10"):
        w = shutil.which(name)
        if w:
            return w
    wa = Path(os.environ.get("LOCALAPPDATA") or "") / "Microsoft" / "WindowsApps" / "python3.11.exe"
    return str(wa) if wa.is_file() else None


def _snapshot() -> "Path | None":
    root = Path(os.environ.get("HF_HOME") or (Path(os.environ.get("USERPROFILE") or Path.home()) / ".cache" / "huggingface")) / "hub" / "models--hexgrad--Kokoro-82M" / "snapshots"
    if not root.is_dir():
        return None
    for snap in sorted(root.iterdir()):
        if (snap / "kokoro-v1_0.pth").is_file():
            return snap
    return None


def _label(v: str) -> str:
    who = v.split("_", 1)[-1].capitalize()
    accent = "British" if v[:1] == "b" else "American"
    sex = "female" if v[1:2] == "f" else "male"
    return f"{who} · Kokoro, on this PC, {accent} {sex}"


def voices() -> "list[dict]":
    """The Kokoro voices whose files are on this PC: [{"id": "k:am_onyx", "name": ..., "voice": "am_onyx"}]. Empty when Kokoro or its model is not here."""
    snap = _snapshot()
    if not snap or not _python():
        return []
    d = snap / "voices"
    return [{"id": "k:" + p.stem, "name": _label(p.stem), "voice": p.stem} for p in sorted(d.glob("*.pt"))] if d.is_dir() else []


def has_voice(v: str) -> bool:
    return any(x["voice"] == v for x in voices())


async def _start() -> None:
    py = _python()
    if not py:
        raise RuntimeError("no Python with Kokoro was found")
    worker = Path(__file__).resolve().parent.parent.parent / "packaging" / "kokoro_worker.py"
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "KMP_DUPLICATE_LIB_OK": "TRUE", "PYTHONUTF8": "1"}
    proc = await asyncio.create_subprocess_exec(py, str(worker), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env)
    head = await asyncio.wait_for(proc.stdout.readline(), timeout=60)          # {"ready": true} once the libraries are loaded
    if b"ready" not in head:
        proc.kill()
        raise RuntimeError("Kokoro did not start")
    _WORKER["proc"] = proc
    if not _WORKER["reaper"]:
        _WORKER["reaper"] = asyncio.get_running_loop().create_task(_reap())
    logger.info("kokoro: worker started (pid %s)", proc.pid)


async def _reap() -> None:
    while True:
        await asyncio.sleep(60)
        p = _WORKER["proc"]
        if p and p.returncode is None and time.time() - _WORKER["last"] > IDLE_EXIT_S:
            stop()
            logger.info("kokoro: worker stopped after %d idle seconds", IDLE_EXIT_S)


def stop() -> None:
    p = _WORKER["proc"]
    _WORKER["proc"] = None
    if p and p.returncode is None:
        try:
            p.kill()
        except ProcessLookupError:
            pass


async def synth(text: str, voice: str, speed: float = 1.0) -> bytes:
    """WAV bytes (24 kHz, mono) of `text` in a Kokoro voice. One request at a time; the model is loaded on the first call (about 6 seconds) and stays loaded."""
    if not has_voice(voice):
        raise RuntimeError(f"Kokoro voice {voice} is not on this PC")
    if _WORKER["lock"] is None:
        _WORKER["lock"] = asyncio.Lock()
    async with _WORKER["lock"]:
        p = _WORKER["proc"]
        if not p or p.returncode is not None:
            await _start()
            p = _WORKER["proc"]
        _WORKER["seq"] += 1
        rid = _WORKER["seq"]
        try:
            p.stdin.write((json.dumps({"id": rid, "text": text[:600], "voice": voice, "speed": max(0.5, min(1.6, float(speed)))}) + "\n").encode("utf-8"))
            await p.stdin.drain()
            head = json.loads(await asyncio.wait_for(p.stdout.readline(), timeout=45))
            if not head.get("ok"):
                raise RuntimeError(head.get("err") or "Kokoro failed")
            body = await asyncio.wait_for(p.stdout.readexactly(int(head["n"])), timeout=20)
        except Exception:
            stop()                                  # a worker that failed mid-request is not trusted again: the next call starts a fresh one
            raise
        _WORKER["last"] = time.time()
        return body


async def warm() -> bool:
    """Load the model now (when the Talk window or the wake word is switched on) so the first sentence is not the one that waits for it."""
    v = voices()
    if not v:
        return False
    try:
        await synth("Ready.", v[0]["voice"])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("kokoro: warm-up failed: %s", exc)
        return False


atexit.register(stop)                      # the Hub going away takes the worker with it
