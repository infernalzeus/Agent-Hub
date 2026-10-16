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
import difflib
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


def _is_local(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        return (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1", "[::1]")
    except ValueError:
        return False


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
                u = str(p.get("url") or p.get("value"))
                if u.startswith(("http://", "https://", "ws://", "wss://")):      # not a channel name misfiled
                    endpoints.append(u)
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
        "local_endpoints": sorted({u for u in endpoints if _is_local(u)})[:limit],
        "usable_for_routines": bool([c for c in literal if not c.upper().startswith(("REMOTE_", "ELECTRON_", "ATOM_"))]
                                    or [u for u in endpoints if _is_local(u)] or s.get("exposed_api_members")),
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
        # A large app (Pinokio's asar is 60 MB) needs far longer and more memory than a small one.
        try:
            size_mb = (p.stat().st_size if p.is_file() else 0) / 1e6
        except OSError:
            size_mb = 0
        big = size_mb > 20
        timeout = int(min(1800, TIMEOUT_S + size_mb * 20))
        cmd = [cfg["node"], _cli_js(cfg["cli"]), "analyze-javascript-application", str(p),
               "--format", "json", "--integrity-policy", "record-and-continue",
               "--analysis-timeout-ms", str(timeout * 1000), "--max-heap-mb", "4096" if big else "1024"]

        async def run(cmd=cmd, timeout=timeout):
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout)
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


# -- installed apps -------------------------------------------------------------------
EVIDENCE = STATE / "app_evidence"          # one JSON per app: the digest, kept so it is not re-read every time


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:60]


def find_all(name: str) -> "list[str]":
    """Every app.asar (or unpacked app folder) whose install folder matches the name."""
    want = _slug(name).replace("-", "")
    if len(want) < 3:
        return []
    roots = [os.environ.get(k) for k in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)")]
    homes = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":              # a per-drive "Programs" folder is common on this kind of setup
        d = Path(f"{letter}:/Programs")
        try:
            if d.is_dir():
                homes.append(d)
        except OSError:
            pass
    for r in roots:
        if r:
            homes += [Path(r), Path(r) / "Programs"]
    out, seen = [], set()
    for home in homes:
        try:
            kids = [k for k in home.iterdir() if k.is_dir()]
        except OSError:
            continue
        for k in kids:
            have = _slug(k.name).replace("-", "")
            if want not in have and difflib.SequenceMatcher(None, want, have).ratio() < 0.84:
                continue                                  # a letter off ("antigrabity") still finds it
            cands = [k / "resources/app.asar", k / "resources/app"]
            try:
                for sub in k.iterdir():                     # versioned folders, e.g. Discord/app-1.0.9
                    if sub.is_dir():
                        cands += [sub / "resources/app.asar", sub / "resources/app"]
            except OSError:
                pass
            for c in cands:
                key = os.path.normcase(str(c))
                if key not in seen and c.exists():
                    seen.add(key)
                    out.append(str(c))
    return out


def find_installed(name: str) -> "str | None":
    """The install of an app by name. When several match, the one Windows has an address registered for wins."""
    found = find_all(name)
    if not found:
        return None
    return sorted(found, key=lambda p: (not protocols_for(p), found.index(p)))[0]


def protocols_for(app_path: str) -> "list[dict]":
    """URL schemes Windows has registered to this app, read from the registry.

    This is the one callable address REA's static reading cannot supply: an
    Electron app names its scheme in a variable, but Windows knows it exactly
    ("antigravity://" opens that app). Matching is by install folder, so it never
    attributes another program's scheme to this one.
    """
    try:
        import winreg
    except ImportError:
        return []
    folder = str(Path(app_path).parent.parent if Path(app_path).name in ("app.asar", "app") else Path(app_path).parent)
    needle = os.path.normcase(os.path.normpath(folder))
    found = []
    for hive, root in ((winreg.HKEY_CURRENT_USER, r"Software\Classes"), (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes")):
        try:
            with winreg.OpenKey(hive, root) as k:
                n = winreg.QueryInfoKey(k)[0]
                for i in range(n):
                    scheme = winreg.EnumKey(k, i)
                    if scheme.startswith(".") or len(scheme) > 40:
                        continue
                    try:
                        with winreg.OpenKey(k, scheme) as sk:
                            winreg.QueryValueEx(sk, "URL Protocol")
                            with winreg.OpenKey(sk, r"shell\open\command") as ck:
                                cmd = str(winreg.QueryValueEx(ck, "")[0])
                    except OSError:
                        continue
                    if needle and (needle + os.sep) in os.path.normcase(os.path.normpath(cmd.replace('"', ""))):
                        found.append({"scheme": scheme, "uri": f"{scheme}://", "command": cmd[:200]})
        except OSError:
            continue
    seen, out = set(), []
    for f in found:
        if f["scheme"].casefold() not in seen:
            seen.add(f["scheme"].casefold())
            out.append(f)
    return out


def discover_address(name: str) -> "list[dict]":
    """The registered addresses of an installed app, without reading its files.

    Instant and read-only. Keeps a small evidence record (so the address can be
    checked again later) and learns the routines. REA's full read adds to this.
    """
    where = find_installed(name)
    if not where:
        return []
    protos = protocols_for(where)
    if not protos:
        return []
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    folder = Path(where).parent.parent if Path(where).name in ("app.asar", "app") else Path(where).parent
    canon = folder.name
    rec = saved_evidence(canon) or {"name": canon, "path": where, "ipc": {"literal_channels": [], "unresolved_dynamic": 0}}
    rec.update(name=canon, path=where, protocols=protos)
    (EVIDENCE / f"{_slug(canon)}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    try:
        from . import pc_control as PC
        PC.learn_address_routines(name, protos, rec.get("sha256") or "")
        if _slug(canon) != _slug(name):
            PC.learn_address_routines(canon, protos, rec.get("sha256") or "")
    except Exception as exc:
        logger.info("rea: could not store address routines for %s: %s", name, exc)
    return protos


def candidate_routines(d: dict) -> "list[dict]":
    """What could be built from the evidence. Described, not executed: nothing here runs."""
    out = []
    for pr in d.get("protocols") or []:
        out.append({"kind": "open-address", "uri": pr["uri"],
                    "note": f"Windows routes {pr['uri']} to this app, so it can be opened or focused without clicking."})
    for u in (d.get("local_endpoints") if "local_endpoints" in d else d.get("endpoints")) or []:
        out.append({"kind": "http-call", "url": u, "note": "a local address on this PC that the app uses"})
    real = [c["channel"] for c in d["ipc"]["literal_channels"]
            if not c["channel"].upper().startswith(("REMOTE_", "ELECTRON_", "ATOM_"))]
    if real:
        out.append({"kind": "internal-messages", "channels": real[:30],
                    "note": "named messages between the app's own parts; not callable from outside, but they show what it can do"})
    return out


def _fingerprint(where: str) -> str:
    try:
        p = Path(where)
        t = p if p.is_file() else (p / "package.json")
        st = t.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return ""


def saved_evidence(name: str) -> "dict | None":
    try:
        return json.loads((EVIDENCE / f"{_slug(name)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def explain(d: dict) -> str:
    """The digest, in a sentence a person can use."""
    name = d.get("name") or "That app"
    ch = d["ipc"]["literal_channels"]
    ep = d.get("local_endpoints") if "local_endpoints" in d else d["endpoints"]
    if d.get("usable_for_routines"):
        bits = []
        if ep:
            bits.append(f"{len(ep)} local address{'es' if len(ep) != 1 else ''} (such as {ep[0]})")
        real = [c["channel"] for c in ch if not c["channel"].upper().startswith(("REMOTE_", "ELECTRON_", "ATOM_"))]
        if real:
            bits.append(f"{len(real)} named internal message{'s' if len(real) != 1 else ''}")
        if d.get("exposed_api_members"):
            bits.append(f"{d['exposed_api_members']} exposed API members")
        if d.get("protocols"):
            bits.append("Windows address " + ", ".join(p["uri"] for p in d["protocols"][:3]))
        return f"{name} exposes {' and '.join(bits)}. That is a candidate way to drive it without clicking."
    return (f"I read {name}'s own files and found nothing I can use as commands: "
            f"{d['ipc']['unresolved_dynamic']} message names are computed at run time and cannot be read statically. "
            f"Driving it will have to go through its window.")


def _winget_id(name: str) -> str:
    """The winget id of an installed app, if winget knows it. Best effort, short, and read-only."""
    import subprocess
    try:
        out = subprocess.run(["winget", "list", "--name", name, "--accept-source-agreements"],
                             capture_output=True, text=True, timeout=12).stdout
    except Exception:
        return ""
    import re
    for line in out.splitlines():
        m = re.search(r"\s([A-Za-z0-9]+(?:\.[A-Za-z0-9\-_]+)+)\s+\d", line)
        if m and name.casefold().replace(" ", "")[:4] in line.casefold().replace(" ", ""):
            return m.group(1)
    return ""


def keep(name: str, where: str, d: dict) -> dict:
    """Store a digest as this app's evidence and offer it for review. Changes nothing else."""
    d = dict(d)
    d["name"] = name
    d["path"] = where
    d["protocols"] = protocols_for(where)
    d["usable_for_routines"] = bool(d.get("usable_for_routines") or d["protocols"])
    d["candidates"] = candidate_routines(d)
    d["read_at"] = __import__("time").time()
    prior = saved_evidence(name) or {}
    wid = prior.get("reinstall", {}).get("winget") or _winget_id(name)
    d["reinstall"] = {"winget": wid} if wid else {}
    try:                                                   # what was learned becomes routines, kept like any other
        from . import pc_control as PC
        d["routines"] = PC.learn_address_routines(name, d["protocols"], d.get("sha256") or "")
    except Exception as exc:
        logger.info("rea: could not store routines for %s: %s", name, exc)
        d["routines"] = []
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{_slug(name)}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
    d["summary"] = explain(d)
    try:
        from . import proposals as P
        for old_p in P.load():                      # one pending offer per app, the latest reading
            if old_p.get("kind") == "app_evidence" and (old_p.get("wiring") or {}).get("app") == name:
                P.dismiss(old_p["id"])
        P.propose({
            "kind": "app_evidence", "name": f"{name}: what it exposes", "from": "rea",
            "why": d["summary"][:240],
            "confidence": None,
            "wiring": {"app": name, "path": where, "sha256": d.get("sha256"),
                       "endpoints": d.get("endpoints", []), "usable": d["usable_for_routines"],
                       "protocols": d["protocols"], "candidates": d["candidates"],
                       "channels": [c["channel"] for c in d["ipc"]["literal_channels"]]},
        })
    except Exception as exc:
        logger.info("rea: could not offer the evidence for review: %s", exc)
    return d


async def ingest_installed(name: str, run=None, path: str = "") -> dict:
    """Read an installed app, keep what was found, and offer it for review. Changes nothing."""
    where = path or find_installed(name)
    if not where:
        raise ValueError(f"I can't find an installed Electron app called {name}")
    fp = _fingerprint(where)
    prior = saved_evidence(name)
    if run is None and prior and fp and prior.get("path") == where and prior.get("fp") == fp:
        return keep(name, where, prior)            # same files as last time: nothing to read again
    d = await inspect(where, run=run)
    d["fp"] = fp
    return keep(name, where, d)


@routes.post("/api/ingest/installed")
async def api_ingest_installed(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    if not name:
        raise web.HTTPBadRequest(text="which app?")
    try:
        return web.json_response(await ingest_installed(name))
    except ValueError as exc:
        raise web.HTTPNotFound(text=str(exc))
    except RuntimeError as exc:
        raise web.HTTPBadGateway(text=str(exc))


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
