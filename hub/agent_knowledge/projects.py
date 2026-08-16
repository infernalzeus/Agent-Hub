"""Project discovery: the node list for the status graph (Phase 3/4).

Auto-discovered from the folder layout under `git repositories/` rather than
a hand-maintained list — a static registry goes stale the moment a repo is
added or renamed. Two fixed exceptions are marked read-only by name (the LLM
wiki and Agent Hub itself); everything else is discovered.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPOS_ROOT = Path(r"N:\Code\git repositories")

# Duplicated from hub/features/opencode.py's WORKROOT (not imported directly,
# to avoid a features->agent_knowledge->features import cycle) — must be kept
# in sync if that path ever moves.
DEFAULT_WORKROOT = Path(r"N:\Code\opencode") / "Agent Code"

# Top-level entries that are single projects in their own right, not
# categories to descend into.
TOP_LEVEL_PROJECTS = {
    "_LLM Wiki - Obsidian Second Brain": {"slug": "llm-wiki", "name": "LLM Wiki", "readonly": True},
    "Agent Hub": {"slug": "agent-hub", "name": "Agent Hub", "readonly": True},
}

# Category folders to descend into one level (each child = one project).
CATEGORY_DIRS = ["Collab Projects", "My Repo", "Open Source", "_unsorted projects"]

# Children of a category dir that are themselves a category / archive, not a
# single project — represented as one collapsed node instead of descending
# into every archived sub-version. NOT read-only: "retired" is a name, not a
# reason to treat it as infrastructure OpenCode must never touch — it's an
# ordinary project like any other, just archived, with its own real state.
COLLAPSED = {
    "JARVIS Attempts": {"slug": "agent-core", "name": "agent-core (retired)"},
}

SKIP_DIRS = {".claude", ".git"}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def discover_projects() -> list[dict]:
    """One entry per project: {slug, name, path, readonly}."""
    projects: list[dict] = []
    seen_slugs: set[str] = set()

    def add(name: str, path: Path, slug: str | None = None, readonly: bool = False,
            category: str = "Read-only") -> None:
        s = slug or _slugify(name)
        if s in seen_slugs:
            s = f"{s}-{_slugify(str(path))[-6:]}"  # disambiguate a rare name clash
        seen_slugs.add(s)
        projects.append({"slug": s, "name": name, "path": str(path), "readonly": readonly,
                          "category": category})

    for folder_name, meta in TOP_LEVEL_PROJECTS.items():
        p = REPOS_ROOT / folder_name
        if p.is_dir():
            add(meta.get("name", folder_name), p, slug=meta["slug"], readonly=meta["readonly"])

    for category in CATEGORY_DIRS:
        cat_path = REPOS_ROOT / category
        if not cat_path.is_dir():
            continue
        try:
            children = sorted(cat_path.iterdir())
        except Exception:
            continue
        for child in children:
            if not child.is_dir() or child.name in SKIP_DIRS:
                continue
            if child.name in COLLAPSED:
                meta = COLLAPSED[child.name]
                add(meta.get("name", child.name), child, slug=meta["slug"], readonly=False,
                    category=category)
                continue
            add(child.name, child, category=category)

    return projects


def discover_local_projects(workroot: Path | None = None) -> list[dict]:
    """Projects that live ONLY under Agent Code/projects/ — no matching
    external source under git-repositories, either because they were
    started from scratch inside Agent Code (e.g. a quick experiment that
    hasn't been "added to my work" as a real repo yet) or their marker's
    source no longer resolves (moved/deleted). Still real projects — same
    projects/+chats/ shape as every other one — just not yet documented in
    the wiki or backed by an external source to diff against."""
    root = (workroot or DEFAULT_WORKROOT) / "projects"
    if not root.is_dir():
        return []
    known_sources = {str(Path(p["path"]).resolve()) for p in discover_projects()}
    out: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        marker = child / ".agent-hub-source.json"
        source = None
        if marker.exists():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                source = str(Path(data.get("source", "")).resolve())
            except Exception:
                source = None
        if source and source in known_sources:
            continue  # a normal source-backed copy, already covered via discover_projects()
        out.append({
            "slug": f"local-{_slugify(child.name)}", "name": child.name,
            "path": str(child), "readonly": False, "category": "Local",
        })
    return out


def find_project(slug: str) -> dict | None:
    for p in discover_projects():
        if p["slug"] == slug:
            return p
    for p in discover_local_projects():
        if p["slug"] == slug:
            return p
    return None
