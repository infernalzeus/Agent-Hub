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

import os
import sys

from aiohttp import web

try:                                                                       # the personal learning layer is optional: the Hub runs without hub/yard/
    from hub.yard import api as yard_api, ui as yard_ui, teach as yard_teach, evidence as yard_evidence, fitness as yard_fitness, knobs as yard_knobs, events as yard_events, flow as yard_flow, candidates as yard_candidates, tev_dataset as yard_tev, explain as yard_explain, routine_data as yard_routine_data, router_tuning as yard_router_tuning, presets as yard_presets, overview as yard_overview
    YARD_FEATURES = [yard_api, yard_ui, yard_teach, yard_evidence, yard_fitness, yard_knobs, yard_events, yard_flow, yard_candidates, yard_tev, yard_explain, yard_routine_data, yard_router_tuning, yard_presets, yard_overview]
except ImportError:
    YARD_FEATURES = []
from hub.features import board_prefs, helpers as hub_helpers, agent_map
from hub import hand_tracking, agents_ui, chats_ui, automations_ui, config, graph_ui, install_move, lifecycle, missions_ui, request_security, setup_ui, theme, ui
from hub.features import run_record, window_mirror, window_video, acp_client, agent_events, support, action_apps, agent_sessions, apps, automations, capabilities, diagnose, harness_tuner, home_state, memory_tiers, probe, proposals, routing, graph, ingest_recipes, integrations, llm_keys, machine_recorder, locations_api, machine_routines, mcp, missions, onboarding, opencode, pc_control, pc_steps, power, schedule, setup_check, skills_api, updates, user_facts, converse, binning, rea_inspect, voice, youtube, learning

# Each feature module exposes `routes` (and optionally a `setup(app)` hook for
# its own background tasks / cleanup). Add a feature = add it to this list.
FEATURES = [run_record, window_mirror, window_video, hand_tracking, *YARD_FEATURES, board_prefs, hub_helpers, agent_map, acp_client, agent_events, support, apps, youtube, opencode, missions, graph, graph_ui, agents_ui, chats_ui, missions_ui,
            ingest_recipes, llm_keys, locations_api, machine_recorder, machine_routines, mcp, pc_control, pc_steps, schedule, skills_api, setup_ui, voice, power, setup_check, onboarding,
            integrations, updates, automations, automations_ui, capabilities, diagnose, harness_tuner, home_state, memory_tiers, probe, routing, action_apps, proposals, theme, install_move, user_facts, converse, binning, rea_inspect, learning, ui]


def create_app() -> web.Application:
    app = web.Application()
    for feature in FEATURES:
        app.add_routes(feature.routes)
        if hasattr(feature, "setup"):
            feature.setup(app)
    # Last registered, first to run: refuse forged state changes before any
    # feature handler sees them.
    request_security.install(app)
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
        "yt-dlp python":      config.YT_DL_PYTHON,
        "yt-dlp script":      config.YT_DL_SCRIPT,
        "yt upload script":   config.YT_UPLOAD_SCRIPT,
        "tailscale.exe":      config.TAILSCALE_EXE,
    }
    # Whichever apps are actually registered — an installed build ships only the
    # packaged File Browser, so naming apps here would make it fail on startup.
    for app_id, manifest in config.APPS.items():
        checks[f"{app_id} dir"] = manifest["cwd"]
    missing = [f"{name} -> {p}" for name, p in checks.items() if not Path(p).exists()]
    if missing:
        for m in missing:
            config.logger.warning("SELF-CHECK: missing %s", m)
        config.logger.warning("SELF-CHECK: %d dependency path(s) missing — those features will fail until fixed", len(missing))
    else:
        config.logger.info("SELF-CHECK: all %d dependency paths present", len(checks))
    from hub import locations as _loc
    for o in _loc.outside_hub():                   # the hub keeps to its own folder; say so loudly for every place it is set to leave it
        config.logger.warning("OUTSIDE THE HUB FOLDER: %s is %s (%s). Move it under %s in LOCATIONS unless you mean it.", o["label"], o["path"], o["source"], _loc.BASE)


def main() -> None:
    _selfcheck()
    app = create_app()
    lifecycle.install_shutdown_watchdog()
    print(f"Agent Hub -> http://{config.HOST}:{config.PORT}")
    print(f"  (from another Tailscale device: http://<this-machine>.<tailnet>.ts.net:{config.PORT})")
    web.run_app(app, host=config.HOST, port=config.PORT, print=None,
                shutdown_timeout=3, handler_cancellation=True)

    # run_app returns after graceful shutdown. Exit 42 = "relaunch me" (the ⟳
    # restart button); the launcher's supervisor loop (Agent Hub.vbs) restarts
    # the hub only on 42. Normal ✕ shutdown returns 0 → stays down.
    code = 42 if apps._restart_requested else 0
    if code:
        print("Restart requested — exiting 42 for the supervisor to relaunch.")
    # Everything is cleaned up by now. Waiting for the interpreter to wind down let a leftover worker thread hold a restart
    # for about 15 s on the real Hub (2.2 s on a clean one); the job object ends the children either way.
    import logging
    logging.shutdown()
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
