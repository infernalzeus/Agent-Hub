"""Project discovery: the node list for the status graph.

The user chooses WHERE projects live (hub/locations.py, edited on /setup); the projects inside a chosen collection folder are still
discovered automatically, so adding a repo there needs no registry edit.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import locations

SKIP_DIRS = {".claude", ".git"}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def discover_projects() -> list[dict]:
    """One entry per project: {slug, name, path, readonly, category}. Sources come from the user's saved locations (hub/locations.py):
    a "project" source is one project, a "collection" source is a folder whose sub-folders are the projects (its name is the category)."""
    projects: list[dict] = []
    seen_slugs: set[str] = set()

    def add(name: str, path: Path, slug: str | None = None, readonly: bool = False, category: str = "Read-only") -> None:
        s = slug or _slugify(name)
        if s in seen_slugs:
            s = f"{s}-{_slugify(str(path))[-6:]}"  # disambiguate a rare name clash
        seen_slugs.add(s)
        projects.append({"slug": s, "name": name, "path": str(path), "readonly": readonly, "category": category})

    srcs = locations.sources()

    # Two folders the Hub already knows where to find, so neither has to be added
    # by hand as if it were one of your repositories. Both are read-only: they are
    # here to be read for context and shown in the graph, never worked on.
    # Added first so a slug clash resolves in their favour, and skipped when the
    # same path is already a source, so nothing appears twice.
    known = {str(Path(p).resolve()).lower() for p in
             [x.get("path") for x in srcs if x.get("path")]}
    for path, name, cat in _known_folders():
        if path.is_dir() and str(path.resolve()).lower() not in known:
            add(name, path, readonly=True, category=cat)

    for src in [x for x in srcs if x.get("kind") == "project"] + [x for x in srcs if x.get("kind") == "collection"]:
        base = Path(src["path"])
        if not base.is_dir():
            continue
        ro = bool(src.get("readonly"))
        if src.get("kind") == "project":
            add(src.get("name") or base.name, base, slug=src.get("slug"), readonly=ro,
                category=src.get("category") or ("Read-only" if ro else "Projects"))
            continue
        cat = src.get("category") or base.name
        collapsed = src.get("collapsed") or {}
        try:
            children = sorted(base.iterdir())
        except Exception:
            continue
        for child in children:
            if not child.is_dir() or child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            if child.name in collapsed:
                meta = collapsed[child.name]
                add(meta.get("name", child.name), child, slug=meta.get("slug"), readonly=False, category=cat)
                continue
            add(child.name, child, readonly=ro, category=cat)
    return projects


def _known_folders() -> "list[tuple[Path, str, str]]":
    """(path, name, category) for the folders the Hub can locate without being told.

    The install folder is wherever this file is, so it is correct on any machine
    and whatever the folder is called. The vault is wherever Locations says, and
    is simply absent when nobody set one.
    """
    out = []
    try:
        from ..config import HERE
        out.append((Path(HERE), "Agent Hub", "The hub itself"))
    except Exception:
        pass
    try:
        vault = locations.get("wiki_root")
        if vault:
            out.append((Path(vault), Path(vault).name or "Second brain", "Second brain"))
    except Exception:
        pass
    return out


def discover_local_projects(workroot: Path | None = None) -> list[dict]:
    """Retired. The old copytree layout (`Agent Code/projects/` + `.agent-hub-
    source.json` markers) is gone — every project's agent work is now a git
    worktree under the configured Missions work folder keyed by the deterministic
    opencode slug (see hub/features/opencode.py). Kept as an importable no-op
    so callers don't need conditional imports."""
    return []


def find_project(slug: str) -> dict | None:
    for p in discover_projects():
        if p["slug"] == slug:
            return p
    for p in discover_local_projects():
        if p["slug"] == slug:
            return p
    return None
