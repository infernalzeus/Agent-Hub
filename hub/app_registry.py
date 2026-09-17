"""The writable app registry — the ordered list of hub-fronted apps.

`config.APPS` is built from here on startup. `apps.json` (gitignored) is the live
list the user + the auto-ingest flow edit; `apps.default.json` (committed) is the
built-in baseline used to seed it on first run and to restore a removed built-in.

Manifest = one JSON object per app. Tokens resolved at load:
  `$PYTHON` anywhere in `cmd`  → sys.executable
  `$HUB`    at the start of `cwd` → the hub repo root

Shape (only `id`, `cmd`, `port` are required; the rest have defaults):
  id, name, emoji, cwd, cmd[list], port, serve("direct"|"proxy"),
  base_path, health_path, idle_minutes, install[list|null], env{},
  builtin(bool), source("wired-in"|<git url>), hidden(bool)

The HTTP surface (GET/reorder/hide/DELETE/ingest) lives in hub/features/apps.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # hub/
_ROOT = _HERE.parent                             # repo root
LIVE = _HERE / "apps.json"
DEFAULT = _HERE / "apps.default.json"
INGESTED = _HERE / "ingested_apps"               # where auto-ingested app clones live


def _read(p: Path) -> list[dict]:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def seed_if_missing() -> None:
    if LIVE.exists():
        return
    try:
        LIVE.write_text(json.dumps(_read(DEFAULT), indent=2, ensure_ascii=True),
                        encoding="utf-8")
    except Exception:
        pass


def load_raw() -> list[dict]:
    """The manifests exactly as stored (for editing / the /api/apps response)."""
    seed_if_missing()
    return _read(LIVE)


def save(apps: list[dict]) -> None:
    LIVE.write_text(json.dumps(apps, indent=2, ensure_ascii=True), encoding="utf-8")


def _resolve(m: dict) -> dict:
    """A raw manifest → the shape supervisor / the proxy expect (Path cwd, real
    interpreter in cmd)."""
    cwd = str(m.get("cwd") or ".")
    if cwd.startswith("$HUB"):
        cwd = str(_ROOT / cwd[4:].lstrip("/\\"))
    cmd = [sys.executable if a == "$PYTHON" else str(a) for a in (m.get("cmd") or [])]
    aid = str(m["id"])
    return {
        "id": aid,
        "name": m.get("name") or aid,
        "emoji": m.get("emoji") or "\U0001F4E6",
        "cwd": Path(cwd),
        "cmd": cmd,
        "port": int(m["port"]),
        "serve": m.get("serve") or "direct",
        "base_path": m.get("base_path") or f"/app/{aid}",
        "health_path": m.get("health_path") or "/",
        "idle_minutes": int(m.get("idle_minutes", 20)),
        "install": list(m["install"]) if m.get("install") else None,
        "env": dict(m.get("env") or {}),
        "builtin": bool(m.get("builtin", False)),
        "source": m.get("source") or "wired-in",
        "hidden": bool(m.get("hidden", False)),
    }


def load() -> "dict[str, dict]":
    """Ordered {id: resolved manifest} — this is what `config.APPS` becomes."""
    out: dict[str, dict] = {}
    for m in load_raw():
        if "id" not in m or "port" not in m or "cmd" not in m:
            continue
        try:
            out[str(m["id"])] = _resolve(m)
        except Exception:
            continue
    return out


# ── mutations (each rewrites apps.json; callers then reload_apps + rebuild procs) ──
def reorder(order: "list[str]") -> "list[dict]":
    apps = load_raw()
    by_id = {m["id"]: m for m in apps}
    seen = set(order)
    new = [by_id[i] for i in order if i in by_id] + [m for m in apps if m["id"] not in seen]
    save(new)
    return new


def set_hidden(app_id: str, hidden: bool) -> None:
    apps = load_raw()
    for m in apps:
        if m["id"] == app_id:
            m["hidden"] = bool(hidden)
    save(apps)


def remove(app_id: str) -> "dict | None":
    apps = load_raw()
    dropped = next((m for m in apps if m["id"] == app_id), None)
    save([m for m in apps if m["id"] != app_id])
    return dropped


def add(manifest: dict) -> None:
    apps = [m for m in load_raw() if m.get("id") != manifest.get("id")]
    apps.append(manifest)
    save(apps)


def default_manifest(app_id: str) -> "dict | None":
    return next((m for m in _read(DEFAULT) if m.get("id") == app_id), None)
