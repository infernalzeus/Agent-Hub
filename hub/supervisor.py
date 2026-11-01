"""Process supervision for singleton proxied apps: start, stop, idle-reap."""
from __future__ import annotations

import asyncio
import os
import time

import aiohttp

from .config import APPS, logger
from .platform_win import _assign_to_job
from . import runtime


# ── Process supervision ─────────────────────────────────────────────────────

class AppProc:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.last_activity: float = 0.0
        self.last_error: str = ""      # why the last start failed, in the app's own words

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


APP_PROCS: dict[str, AppProc] = {aid: AppProc(cfg) for aid, cfg in APPS.items()}


def rebuild_app_procs() -> None:
    """Sync APP_PROCS with the current registry after apps.json is edited:
    stop + drop a removed app, add an AppProc for a new one, refresh cfg for the
    rest. Call after config.reload_apps()."""
    from . import config
    live = config.APPS
    for aid in list(APP_PROCS):
        if aid not in live:
            ap = APP_PROCS.pop(aid)
            if ap.running:
                try:
                    asyncio.get_running_loop().create_task(stop_app(ap))
                except RuntimeError:
                    pass
    for aid, cfg in live.items():
        if aid in APP_PROCS:
            APP_PROCS[aid].cfg = cfg
        else:
            APP_PROCS[aid] = AppProc(cfg)


def _tail(path, since: int = 0, n: int = 600) -> str:
    """The end of an app's own output from this start (not earlier ones), for an error message."""
    try:
        data = open(path, "rb").read()[since:][-n:].decode("utf-8", "replace").strip()
        return ("Its output ended: " + " | ".join(data.splitlines()[-4:])) if data else "It printed nothing."
    except OSError:
        return ""


async def ensure_started(ap: AppProc, timeout: float = 20.0) -> None:
    async with ap.lock:
        if ap.running:
            ap.last_activity = time.monotonic()
            return

        cfg = ap.cfg
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"          # so what an app printed before it died is in its log
        env.update(cfg.get("env", {}))

        logger.info("Starting %s ...", cfg["name"])
        # Same reason as the install step: a command that works in a shell is
        # not necessarily a file CreateProcess can open.
        # The app's output goes to a file, not nowhere: a start that failed used to say only "did not become ready",
        # and there was nothing to read to find out why (the file browser, 1 Nov).
        since = 0
        log_path = runtime.STATE / "app_logs" / f"{cfg.get('id') or cfg['name']}.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            since = log_path.stat().st_size if log_path.exists() else 0
            out = open(log_path, "ab")
        except OSError:
            out = asyncio.subprocess.DEVNULL
        ap.proc = await asyncio.create_subprocess_exec(
            *runtime.resolve_argv0(cfg["cmd"]),
            cwd=str(cfg["cwd"]),
            env=env,
            stdout=out,
            stderr=asyncio.subprocess.STDOUT if out is not asyncio.subprocess.DEVNULL else asyncio.subprocess.DEVNULL,
        )
        _assign_to_job(ap.proc.pid)

        health_url = f"http://127.0.0.1:{cfg['port']}{cfg['health_path']}"
        deadline = time.monotonic() + timeout
        async with aiohttp.ClientSession() as session:
            while time.monotonic() < deadline:
                if ap.proc.returncode is not None:
                    ap.last_error = f"{cfg['name']} exited immediately (code {ap.proc.returncode}). {_tail(log_path, since)}"
                    raise RuntimeError(ap.last_error)
                try:
                    async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            ap.last_activity = time.monotonic()
                            logger.info("%s ready on port %d", cfg["name"], cfg["port"])
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.4)

        ap.last_error = f"{cfg['name']} did not become ready in {int(timeout)} s. {_tail(log_path, since)}"
        await stop_app(ap)
        raise RuntimeError(ap.last_error)


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


