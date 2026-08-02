"""Startup/shutdown lifecycle: idle reaper, Taildrop watcher, graceful
cleanup, and the last-resort force-exit watchdog."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from aiohttp import web, WSCloseCode

from .config import TAILSCALE_EXE, TAILDROP_DIR, HOST, PORT, logger
from .platform_win import _assign_to_job
from .supervisor import APP_PROCS, stop_app, _idle_reaper
from .features.youtube import yt_state, ytdl_state


async def _start_taildrop_watcher() -> asyncio.subprocess.Process | None:
    """Continuously pull incoming Taildrop files (phone -> this PC) into TAILDROP_DIR.
    Lives and dies with the Hub itself instead of being a separately-run process."""
    if not Path(TAILSCALE_EXE).exists():
        logger.warning("tailscale.exe not found at %s — Taildrop watcher not started", TAILSCALE_EXE)
        return None
    TAILDROP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting Taildrop watcher -> %s", TAILDROP_DIR)
    proc = await asyncio.create_subprocess_exec(
        TAILSCALE_EXE, "file", "get", "--wait", "--loop", "--conflict=rename", str(TAILDROP_DIR),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    _assign_to_job(proc.pid)
    return proc



def install(app: web.Application) -> None:
    async def _on_startup(app: web.Application) -> None:
        app["reaper"] = asyncio.create_task(_idle_reaper())
        app["taildrop"] = await _start_taildrop_watcher()
        # Suppress the harmless ProactorEventLoop ConnectionResetError traceback
        # (a client — the phone, or a relayed opencode socket — dropping abruptly).
        # MUST be set on the running loop: web.run_app creates its own, so the
        # handler installed at create_app() time was on the wrong loop.
        loop = asyncio.get_running_loop()
        prev = loop.get_exception_handler()

        def _suppress(lp, ctx):
            if isinstance(ctx.get("exception"), (ConnectionResetError, ConnectionAbortedError)):
                return
            if prev:
                prev(lp, ctx)
            else:
                lp.default_exception_handler(ctx)

        loop.set_exception_handler(_suppress)

    async def _stop_taildrop(taildrop: asyncio.subprocess.Process | None) -> None:
        if not taildrop or taildrop.returncode is not None:
            return
        logger.info("Stopping Taildrop watcher ...")
        try:
            taildrop.kill()
            # Short reap only — the job object kills it regardless, so there's
            # no reason to let this wait dominate the shutdown critical path.
            await asyncio.wait_for(taildrop.wait(), timeout=0.5)
        except Exception:
            pass

    async def _stop_yt_job(state) -> None:
        # Covers both yt_state (upload) and ytdl_state (download) — same shape.
        if state.task and not state.task.done():
            state.task.cancel()
        if state.proc and state.proc.returncode is None:
            try:
                state.proc.kill()
            except Exception:
                pass
        if state.task:
            try:
                await asyncio.wait_for(state.task, timeout=2)
            except Exception:
                pass

    async def _on_shutdown(app: web.Application) -> None:
        # Runs BEFORE aiohttp's connection-drain phase. An open websocket never
        # finishes on its own, so any subscriber socket still connected (a card
        # left expanded somewhere) would make the drain burn its full
        # shutdown_timeout before force-closing — close them proactively
        # instead. The page treats a server-initiated close like any drop.
        ws_all = list(yt_state.subscribers) + list(ytdl_state.subscribers)
        if ws_all:
            logger.info("Shutdown: closing %d live websocket subscriber(s)", len(ws_all))
        await asyncio.gather(
            *(ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown") for ws in ws_all),
            return_exceptions=True,
        )

    async def _on_cleanup(app: web.Application) -> None:
        t0 = time.monotonic()
        app["reaper"].cancel()
        # The job object (see top of file) guarantees no orphaned children no
        # matter how this shutdown goes, so there's no need to be patient here
        # — everything below runs concurrently with short timeouts instead of
        # stacking sequential 5s waits, which is what made Ctrl+C feel slow.
        await asyncio.gather(
            *(stop_app(ap) for ap in APP_PROCS.values()),
            _stop_taildrop(app.get("taildrop")),
            _stop_yt_job(yt_state),
            _stop_yt_job(ytdl_state),
            return_exceptions=True,
        )
        logger.info("Cleanup finished in %.1fs", time.monotonic() - t0)

    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)
    app.on_cleanup.append(_on_cleanup)

    # Windows ProactorEventLoop logs a ConnectionResetError traceback whenever a
    # client drops the socket instead of closing cleanly — harmless noise.
    try:
        loop = asyncio.get_event_loop()
        _prev = loop.get_exception_handler()

        def _exc_handler(lp: asyncio.AbstractEventLoop, ctx: dict) -> None:
            if isinstance(ctx.get("exception"), ConnectionResetError):
                return
            if _prev:
                _prev(lp, ctx)
            else:
                lp.default_exception_handler(ctx)

        loop.set_exception_handler(_exc_handler)
    except Exception:
        pass


def _install_shutdown_watchdog(grace_seconds: float = 15.0) -> None:
    """Last-resort exit guarantee. With websocket subscribers closed proactively
    in on_shutdown, graceful shutdown should finish in a few seconds — the
    grace period is deliberately far above that, so this only ever fires on a
    genuine wedge (a blocked pipe read, a stuck executor thread, a transport
    that won't close), never on a normal-but-slow shutdown. Without it, a
    wedge means the terminal never frees and children stay alive, because the
    job object only fires when Hub's process handle closes. os._exit closes
    that handle, so Windows kills every child too — no orphans, ever. The
    timer thread is a daemon: when graceful shutdown finishes in time (the
    normal case) it dies with the process and adds zero delay. It also dumps
    every thread's stack before exiting, so if it ever fires the log shows
    exactly what was stuck."""
    import faulthandler
    import signal
    import threading

    prev = signal.getsignal(signal.SIGINT)

    def _force_exit() -> None:
        logger.warning("Shutdown didn't finish within %.0fs — dumping stacks and force-exiting (job object kills children)", grace_seconds)
        faulthandler.dump_traceback(file=sys.stderr)
        os._exit(1)

    def _on_sigint(sig, frame):
        logger.info("Ctrl+C — shutting down (force-exit watchdog armed: %.0fs)", grace_seconds)
        timer = threading.Timer(grace_seconds, _force_exit)
        timer.daemon = True
        timer.start()
        if callable(prev):
            prev(sig, frame)
        else:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)


install_shutdown_watchdog = _install_shutdown_watchdog
