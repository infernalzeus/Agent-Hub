"""Process supervision for singleton proxied apps: start, stop, idle-reap."""
from __future__ import annotations

import asyncio
import os
import time

import aiohttp

from .config import APPS, logger
from .platform_win import _assign_to_job


# ── Process supervision ─────────────────────────────────────────────────────

class AppProc:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.last_activity: float = 0.0

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


APP_PROCS: dict[str, AppProc] = {aid: AppProc(cfg) for aid, cfg in APPS.items()}


async def ensure_started(ap: AppProc, timeout: float = 20.0) -> None:
    async with ap.lock:
        if ap.running:
            ap.last_activity = time.monotonic()
            return

        cfg = ap.cfg
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(cfg.get("env", {}))

        logger.info("Starting %s ...", cfg["name"])
        ap.proc = await asyncio.create_subprocess_exec(
            *cfg["cmd"],
            cwd=str(cfg["cwd"]),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        _assign_to_job(ap.proc.pid)

        health_url = f"http://127.0.0.1:{cfg['port']}{cfg['health_path']}"
        deadline = time.monotonic() + timeout
        async with aiohttp.ClientSession() as session:
            while time.monotonic() < deadline:
                if ap.proc.returncode is not None:
                    raise RuntimeError(f"{cfg['name']} exited immediately (code {ap.proc.returncode})")
                try:
                    async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            ap.last_activity = time.monotonic()
                            logger.info("%s ready on port %d", cfg["name"], cfg["port"])
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.4)

        await stop_app(ap)
        raise RuntimeError(f"{cfg['name']} did not become ready in time")


async def stop_app(ap: AppProc) -> None:
    proc = ap.proc
    if proc is None or proc.returncode is not None:
        ap.proc = None
        return
    logger.info("Stopping %s ...", ap.cfg["name"])
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    ap.proc = None


async def _is_busy(ap: AppProc) -> bool:
    """Ask the app's own health endpoint if it's mid-job (e.g. {"busy": true})."""
    if not ap.running:
        return False
    cfg = ap.cfg
    url = f"http://127.0.0.1:{cfg['port']}{cfg['health_path']}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                data = await resp.json()
                return bool(data.get("busy"))
    except Exception:
        return False


async def _idle_reaper() -> None:
    while True:
        await asyncio.sleep(60)
        for ap in APP_PROCS.values():
            if not ap.running:
                continue
            idle_minutes = (time.monotonic() - ap.last_activity) / 60
            if idle_minutes < ap.cfg["idle_minutes"]:
                continue
            if await _is_busy(ap):
                ap.last_activity = time.monotonic()
                continue
            logger.info("%s idle for %.0f min — stopping", ap.cfg["name"], idle_minutes)
            await stop_app(ap)


