"""Locations ("pointers"): every folder and tool the hub reads or writes, in one place, editable from the UI (/setup).

Precedence for each key: hub/locations.json (what the user saved) > this machine's pre-existing layout (only while it really exists on disk,
so an upgrade changes nothing) > a default derived under <home>/AgentHub. Nothing here imports the rest of the hub, so config.py, projects.py,
opencode.py and agent_knowledge can all read it at import time.

Project folders are a LIST of sources, each either
  {"kind": "project",    "path": ...}   one project (the folder itself)
  {"kind": "collection", "path": ...}   every sub-folder is a project (a "category" in the graph)
with optional "readonly", "slug"/"name" (project) and "collapsed" {folder: {slug, name}} (collection: shown as ONE node).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

FILE = Path(__file__).resolve().parent / "locations.json"          # per machine, gitignored
HOME = Path(os.environ.get("USERPROFILE") or Path.home())


def _default_base() -> Path:
    """Choose the writable drive with the most free space; Locations remains editable."""
    candidates = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        try:
            if root.is_dir() and os.access(root, os.W_OK):
                candidates.append((shutil.disk_usage(root).free, root))
        except OSError:
            pass
    return max(candidates, default=(0, HOME), key=lambda item: item[0])[1] / "AgentHub"


BASE = _default_base()

# key, label, group, kind (folder | file | sources), required, needs-restart, purpose
REGISTRY = [
    dict(key="project_sources", label="Project folders", group="PROJECTS", kind="sources", required=True, restart=False,
         purpose="Git projects the hub may read and run missions on. Add as many folders as you like; a collection holds many projects."),
    dict(key="work_dir", label="Missions work folder", group="MISSIONS", kind="folder", required=True, restart=True,
         purpose="Private working copies, mission records and scratch. APPLY merges into your project; DISCARD deletes only the copy."),
    dict(key="opencode_home", label="OpenCode install folder", group="MISSIONS", kind="folder", required=True, restart=True,
         purpose="Where OpenCode (the agent runtime) is installed: its exe and opencode.json."),
    dict(key="wiki_root", label="LLM Wiki vault", group="KNOWLEDGE", kind="folder", required=False, restart=True,
         purpose="Optional. The wiki agents can read as a reference library and the graph links to. Empty = off."),
    dict(key="dl_audio", label="YouTube audio downloads", group="FILES", kind="folder", required=False, restart=True,
         purpose="Where audio downloads are saved."),
    dict(key="dl_video", label="YouTube video downloads", group="FILES", kind="folder", required=False, restart=True,
         purpose="Where video downloads are saved."),
    dict(key="dl_cookies", label="YouTube cookies file", group="FILES", kind="file", required=False, restart=True,
         purpose="Optional cookies.txt so downloads work while signed in. Empty = read Firefox cookies live."),
    dict(key="inbox", label="Phone inbox (Taildrop)", group="FILES", kind="folder", required=False, restart=True,
         purpose="Files you send from your phone land here."),
    dict(key="outputs", label="Finished videos (for upload)", group="FILES", kind="folder", required=False, restart=True,
         purpose="Where the clipper writes finished videos; the YouTube uploader picks them from here."),
    dict(key="tailscale_exe", label="Tailscale program", group="TOOLS", kind="file", required=False, restart=True,
         purpose="Used for the phone inbox. Found automatically on PATH when possible."),
    dict(key="yt_python", label="Python that has yt-dlp", group="TOOLS", kind="file", required=False, restart=True,
         purpose="The Python interpreter used for YouTube downloads."),
]
_BY_KEY = {r["key"]: r for r in REGISTRY}

# ── this machine's layout from before this module existed (migration aid only; ignored once saved, or when the folder is gone) ─────────
_R = Path(r"N:\Code\git repositories")
_LEGACY_PATHS = {
    "opencode_home": r"N:\Code\opencode", "work_dir": r"N:\Code\opencode\worktrees",
    "wiki_root": str(_R / "_LLM Wiki - Obsidian Second Brain" / "LLM Wiki"),
    "dl_audio": r"N:\Code\YT-DLP\1", "dl_video": r"N:\Code\YT-DLP\2", "dl_cookies": r"N:\Code\YT-DLP\cookies.txt",
    "inbox": r"N:\Taildrop", "outputs": str(_R / "My Repo" / "movie-shorts-clipper" / "output"),
    "tailscale_exe": r"C:\Program Files\Tailscale\tailscale.exe",
}


def _legacy_sources() -> list[dict]:
    if not _R.is_dir():
        return []
    out = [{"kind": "project", "path": str(_R / "_LLM Wiki - Obsidian Second Brain"), "readonly": True, "slug": "llm-wiki", "name": "LLM Wiki"},
           {"kind": "project", "path": str(_R / "Agent Hub"), "readonly": True, "slug": "agent-hub", "name": "Agent Hub"}]
    for cat in ("Collab Projects", "My Repo", "Open Source", "_unsorted projects"):
        e: dict = {"kind": "collection", "path": str(_R / cat)}
        if cat == "_unsorted projects":
            e["collapsed"] = {"JARVIS Attempts": {"slug": "agent-core", "name": "agent-core (retired)"}}
            e["new_projects_here"] = True
        out.append(e)
    return out


def _default(key: str):
    return {"project_sources": [], "opencode_home": str(BASE / "opencode"), "work_dir": str(BASE / "work"), "wiki_root": "",
            "dl_audio": str(BASE / "downloads" / "audio"), "dl_video": str(BASE / "downloads" / "video"),
            "dl_cookies": "", "inbox": str(BASE / "inbox"), "outputs": str(BASE / "outputs"),
            "tailscale_exe": shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe",
            "yt_python": sys.executable}[key]


# ── storage ───────────────────────────────────────────────────────────────────────────────────────────────────────────
_CACHE: dict = {"stamp": None, "data": {}}


def saved() -> dict:
    try:
        st = FILE.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _CACHE["stamp"] != stamp:
        try:
            _CACHE["data"] = json.loads(FILE.read_text(encoding="utf-8"))
        except Exception:
            _CACHE["data"] = {}
        _CACHE["stamp"] = stamp
    return _CACHE["data"]


def configured() -> bool:
    return FILE.is_file()


def _legacy(key: str):
    if key == "project_sources":
        return _legacy_sources() or None
    p = _LEGACY_PATHS.get(key)
    return p if p and Path(p).exists() else None


def source(key: str) -> str:
    """saved | legacy | default — where the current value comes from."""
    if key in saved():
        return "saved"
    return "legacy" if _legacy(key) else "default"


def get(key: str):
    d = saved()
    if key in d:
        return d[key]
    lg = _legacy(key)
    return lg if lg is not None else _default(key)


def sources() -> list[dict]:
    v = get("project_sources")
    return [x for x in v if isinstance(x, dict) and x.get("path")] if isinstance(v, list) else []


def new_project_parent() -> Path:
    """Where a brand-new project (created from a mission or an ingest) is made: the collection flagged for it, else the first collection."""
    cols = [s for s in sources() if s.get("kind") == "collection" and not s.get("readonly")]
    flagged = [s for s in cols if s.get("new_projects_here")]
    pick = (flagged or cols or [None])[0]
    return Path(pick["path"]) if pick else BASE / "projects"


def apply_to_config(g: dict) -> None:
    """config.py calls this last: a location the user saved wins over env vars and local_settings.py."""
    d = saved()
    m = {"inbox": ("TAILDROP_DIR", Path), "outputs": ("MC_OUTPUT_DIR", Path), "dl_audio": ("YT_DL_AUDIO_DIR", str), "dl_video": ("YT_DL_VIDEO_DIR", str),
         "dl_cookies": ("YT_DL_COOKIES", str), "tailscale_exe": ("TAILSCALE_EXE", str), "yt_python": ("YT_DL_PYTHON", str)}
    for key, (name, cast) in m.items():
        if key in d and str(d[key]).strip():
            g[name] = cast(d[key])


# ── validation ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _forbidden(p: Path) -> str:
    if p.parent == p:
        return "a drive root is too broad, pick a folder inside it"
    win = os.environ.get("SystemRoot")
    if win and (p == Path(win) or Path(win) in p.parents):
        return "not inside the Windows folder"
    return ""


def _count_git(p: Path, limit: int = 400) -> tuple[int, int]:
    dirs = repos = 0
    try:
        for i, c in enumerate(p.iterdir()):
            if i >= limit:
                break
            if c.is_dir() and not c.name.startswith("."):
                dirs += 1
                repos += int((c / ".git").exists())
    except OSError:
        pass
    return dirs, repos


def _validate_path(key: str, value: str, meta: dict) -> dict:
    v = (value or "").strip()
    if not v:
        return {"level": "error" if meta["required"] else "ok", "msg": "required" if meta["required"] else "off (not set)"}
    if meta["kind"] == "file":
        if Path(v).is_file() or shutil.which(v):
            return {"level": "ok", "msg": "found"}
        return {"level": "warn", "msg": "not found"}
    p = Path(v)
    if not p.is_absolute():
        return {"level": "error", "msg": "use a full path (like C:\\Users\\you\\Projects)"}
    bad = _forbidden(p)
    if bad:
        return {"level": "error", "msg": bad}
    if p.is_file():
        return {"level": "error", "msg": "this is a file, not a folder"}
    if not p.exists():
        return {"level": "warn", "msg": "missing: it is created when you save", "create": True}
    if key in ("work_dir", "dl_audio", "dl_video", "inbox", "opencode_home") and not os.access(p, os.W_OK):
        return {"level": "error", "msg": "not writable"}
    try:
        free = shutil.disk_usage(p).free / 2**30
        return {"level": "ok", "msg": f"ok · {free:.0f} GB free"}
    except OSError:
        return {"level": "ok", "msg": "ok"}


def validate_source(s: dict) -> dict:
    p = Path(str(s.get("path", "")).strip())
    if s.get("kind") not in ("project", "collection"):
        return {"level": "error", "msg": "kind must be project or collection"}
    if not str(p) or not p.is_absolute():
        return {"level": "error", "msg": "use a full path"}
    bad = _forbidden(p)
    if bad:
        return {"level": "error", "msg": bad}
    if not p.is_dir():
        return {"level": "warn", "msg": "folder not found"}
    if s["kind"] == "collection":
        dirs, repos = _count_git(p)
        return {"level": "ok" if dirs else "warn", "msg": f"{dirs} folders, {repos} git repos" if dirs else "empty: nothing to list yet"}
    return {"level": "ok" if (p / ".git").exists() else "warn", "msg": "git repo" if (p / ".git").exists() else "not a git repo (missions need one)"}


def validate(key: str, value) -> dict:
    meta = _BY_KEY.get(key)
    if not meta:
        return {"level": "error", "msg": "unknown location"}
    if meta["kind"] == "sources":
        if not isinstance(value, list) or (meta["required"] and not value):
            return {"level": "warn" if isinstance(value, list) else "error", "msg": "add at least one project folder"}
        worst = [validate_source(x) for x in value if isinstance(x, dict)]
        bad = [w for w in worst if w["level"] == "error"]
        return {"level": "error" if bad else "ok", "msg": bad[0]["msg"] if bad else f"{len(value)} source(s)"}
    return _validate_path(key, str(value or ""), meta)


def save(values: dict) -> dict:
    """Validate and store. Returns {key: message} for rejected keys; on any error NOTHING is written. Missing folders that were
    saved are created (folders only, never files)."""
    errors = {}
    clean: dict = {}
    for key, val in values.items():
        meta = _BY_KEY.get(key)
        if not meta:
            errors[key] = "unknown location"
            continue
        if meta["kind"] == "sources":
            val = [{k: v for k, v in x.items() if k in ("kind", "path", "readonly", "slug", "name", "collapsed", "new_projects_here", "category")}
                   for x in (val or []) if isinstance(x, dict)]
        else:
            val = str(val or "").strip()
        r = validate(key, val)
        if r["level"] == "error":
            errors[key] = r["msg"]
        clean[key] = val
    if errors:
        return errors
    for key, val in clean.items():
        if _BY_KEY[key]["kind"] == "folder" and val:
            try:
                Path(val).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                errors[key] = f"could not create: {exc}"
    if errors:
        return errors
    merged = dict(saved())
    merged.update(clean)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(FILE.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)
    _CACHE["stamp"] = None
    return {}


def recent_downloads() -> list[str]:
    v = saved().get("recent_downloads")
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def remember_download(path: str) -> None:
    """Keep the last few folders a download was sent to, newest first, so the SAVE TO list can offer them again."""
    recents = [path] + [x for x in recent_downloads() if x != path]
    merged = dict(saved())
    merged["recent_downloads"] = recents[:6]
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(FILE.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)
    _CACHE["stamp"] = None


def suggest_sources() -> list[dict]:
    """Folders under the usual places that already hold several git repos, with counts."""
    cands = [HOME, HOME / "Documents", HOME / "Documents" / "GitHub", HOME / "source" / "repos", HOME / "Projects", HOME / "dev", HOME / "code", HOME / "repos"]
    for d in "DEFGHN":
        cands += [Path(f"{d}:\\Code"), Path(f"{d}:\\Projects"), Path(f"{d}:\\dev")]
    seen, out = set(), []
    for c in cands:
        try:
            if str(c) in seen or not c.is_dir():
                continue
        except OSError:
            continue
        seen.add(str(c))
        dirs, repos = _count_git(c, 200)
        if repos:
            out.append({"path": str(c), "kind": "collection", "dirs": dirs, "repos": repos})
    return out


