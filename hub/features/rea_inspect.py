"""Read an Electron / JavaScript app's own files and say what it exposes.

This is the evidence step of app ingestion. REA (github.com/morluto/rea, MIT)
statically reads an app's `app.asar` or unpacked directory and reports its
modules, windows, IPC channels, local endpoints and native add-ons, each with
the evidence for it and a list of what it could not resolve. Nothing is run and
nothing is changed: it is reading files already on this disk.

What the hub does with it: a literal IPC channel or a local endpoint is a
candidate way to *call* the app instead of clicking it. This module only
produces the digest; deciding which candidate becomes a routine is the ingest
agent's job, with the person's approval, like every other routine.

REA needs Node 22.19+. Where it lives is read from `rea.json` in the state
folder (`{"node": "...\\node.exe", "cli": "...\\node_modules\\rea-agents"}`) or
from the `REA_BIN` / `REA_NODE` environment variables.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()

CONFIG = STATE / "rea.json"
TIMEOUT_S = 280


def _config() -> dict:
    try:
        got = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = {}
    return {"node": os.environ.get("REA_NODE") or got.get("node") or shutil.which("node") or "",
            "cli": os.environ.get("REA_BIN") or got.get("cli") or ""}


def _cli_js(cli: str) -> str:
    """The script to hand to node: what the package's own `bin` names, else a file path."""
    p = Path(cli)
    try:
        pkg = json.loads((p / "package.json").read_text(encoding="utf-8"))
        b = pkg.get("bin")
        b = (b.get("rea") or next(iter(b.values()), None)) if isinstance(b, dict) else b
        if b and (p / b).exists():
            return str(p / b)
    except (OSError, ValueError):
        pass
    return str(p) if p.is_file() else ""


def status() -> dict:
    c = _config()
    ok = bool(c["node"] and Path(c["node"]).exists() and c["cli"] and _cli_js(c["cli"]))
    return {"ready": ok, "node": c["node"] or None, "cli": c["cli"] or None,
            "note": "" if ok else "REA is not set up: install rea-agents with Node 22.19+ and point rea.json at it."}


def digest(evidence: dict, limit: int = 40) -> dict:
    """The part of REA's evidence a routine-builder can use, kept small."""
    n = (evidence or {}).get("normalized_result") or {}
    g = n.get("graph") or {}
    s = n.get("summary") or {}
    literal, dynamic = {}, 0
    endpoints, addons = [], []
    for node in g.get("nodes") or []:
        kind = node.get("kind")
        for o in node.get("observations") or []:
            p = o.get("properties") or {}
            if kind in ("ipc-channel", "ipc-handler"):
                ch = p.get("channel")
                if ch:
                    literal.setdefault(str(ch), set()).add(f"{p.get('side')}:{p.get('operation')}")
                else:
                    dynamic += 1
            elif kind == "endpoint" and (p.get("url") or p.get("value")):
                endpoints.append(str(p.get("url") or p.get("value")))
            elif kind == "native-addon":
                addons.append(str(o.get("label") or p.get("name") or ""))
    return {
        "app": (evidence.get("subject") or {}).get("name"),
        "format": n.get("format"),
        "sha256": n.get("root_artifact_sha256"),
        "windows": s.get("browser_windows", 0),
        "preloads": s.get("preload_entrypoints", 0),
        "exposed_api_members": s.get("exposed_api_members", 0),
        "ipc": {"literal_channels": [{"channel": c, "seen_as": sorted(v)} for c, v in sorted(literal.items())][:limit],
                "unresolved_dynamic": dynamic},
        "endpoints": sorted(set(endpoints))[:limit],
        "native_addons": [a for a in addons if a][:limit],
        "limitations": [l if isinstance(l, str) else str(l.get("message", l)) for l in (n.get("limitations") or [])][:4],
        # Electron's own plumbing (its removed `remote` module, for one) is not the app's commands.
        "usable_for_routines": bool([c for c in literal if not c.upper().startswith(("REMOTE_", "ELECTRON_", "ATOM_"))]
                                    or endpoints or s.get("exposed_api_members")),
    }


async def inspect(path: str, run=None) -> dict:
    """Run REA on one app and return its digest. `run` is injectable for tests."""
    p = Path(path)
    if not p.exists() or not (p.suffix.lower() == ".asar" or (p.is_dir() and (p / "package.json").exists())):
        raise ValueError("give the path of an app.asar, or of an unpacked app folder containing package.json")
    if run is None:
        st = status()
        if not st["ready"]:
            raise RuntimeError(st["note"])
        cfg = _config()
        cmd = [cfg["node"], _cli_js(cfg["cli"]), "analyze-javascript-application", str(p),
               "--format", "json", "--integrity-policy", "record-and-continue"]

        async def run(cmd=cmd):
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError("REA did not finish in time")
            return out.decode("utf-8", "replace")
    raw = await run()
    first = raw.lstrip().splitlines()[0] if raw.strip() else ""
    try:
        evidence = json.loads(first)
    except ValueError:
        raise RuntimeError("REA's answer could not be read")
    return digest(evidence)


@routes.get("/api/ingest/rea")
async def api_status(request: web.Request) -> web.Response:
    return web.json_response(status())


@routes.post("/api/ingest/rea")
async def api_inspect(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        return web.json_response(await inspect(str(body.get("path") or "")))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    except RuntimeError as exc:
        logger.info("rea: %s", exc)
        raise web.HTTPBadGateway(text=str(exc))
