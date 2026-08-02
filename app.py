"""
Agent Hub — single always-on entry point for personal web apps.

Always-on and Tailscale-reachable at one stable address. Individual apps
(Movie Clipper, etc.) are NOT always running — the Hub spawns each one on
demand (first time you open it), reverse-proxies HTTP + WebSocket traffic to
it under /app/<id>/..., and stops it again after a period of inactivity.

Does not modify or import from Agent CORE or any app it fronts — it only
launches them as subprocesses and talks to them over localhost.

Run:  python app.py
Env:  HUB_HOST (default 0.0.0.0), HUB_PORT (default 8081)
"""
from __future__ import annotations

from aiohttp import web

from hub import config, lifecycle, ui
from hub.features import apps, opencode, power, youtube

# Each feature module exposes `routes` (and optionally a `setup(app)` hook for
# its own background tasks / cleanup). Add a feature = add it to this list.
FEATURES = [apps, youtube, opencode, power, ui]


def create_app() -> web.Application:
    app = web.Application()
    for feature in FEATURES:
        app.add_routes(feature.routes)
        if hasattr(feature, "setup"):
            feature.setup(app)
    lifecycle.install(app)
    return app


def _selfcheck() -> None:
    """Warn at startup if any feature's critical external path is missing, so a
    moved/reinstalled dependency shows up in the log NOW instead of failing the
    first time you reach for it (e.g. mid-presentation)."""
    from pathlib import Path
    checks = {
        "opencode.exe":       opencode.OPENCODE_EXE,
        "opencode config":    opencode.OPENCODE_CONFIG,
        "movie-clipper dir":  config.APPS["movie-clipper"]["cwd"],
        "file-browser dir":   config.APPS["file-browser"]["cwd"],
        "yt-dlp python":      config.YT_DL_PYTHON,
        "yt-dlp script":      config.YT_DL_SCRIPT,
        "yt upload script":   config.YT_UPLOAD_SCRIPT,
        "tailscale.exe":      config.TAILSCALE_EXE,
    }
    missing = [f"{name} -> {p}" for name, p in checks.items() if not Path(p).exists()]
    if missing:
        for m in missing:
            config.logger.warning("SELF-CHECK: missing %s", m)
        config.logger.warning("SELF-CHECK: %d dependency path(s) missing — those features will fail until fixed", len(missing))
    else:
        config.logger.info("SELF-CHECK: all %d dependency paths present", len(checks))


def main() -> None:
    _selfcheck()
    app = create_app()
    lifecycle.install_shutdown_watchdog()
    print(f"Agent Hub -> http://{config.HOST}:{config.PORT}")
    print(f"  (from another Tailscale device: http://<this-machine>.<tailnet>.ts.net:{config.PORT})")
    web.run_app(app, host=config.HOST, port=config.PORT, print=None,
                shutdown_timeout=3, handler_cancellation=True)


if __name__ == "__main__":
    main()
