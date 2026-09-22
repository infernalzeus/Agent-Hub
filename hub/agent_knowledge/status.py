"""Per-project sync state for the graph.

Each project's agent work is a **git worktree** on branch `agent/<slug>` under
the configured Missions work folder (see hub/features/opencode.py). State per node:
  red    - read-only project (LLM wiki, Agent Hub); never touched
  blue   - no worktree yet — nothing has been opened for this project
  amber  - the agent branch has diverged from its base (committed or working)
  green  - worktree exists, no diff vs base
  amber + green ring - diff exists and marked ready to push

Diffs come from `git diff <base>...HEAD` + `git status --porcelain` in the
worktree; hub scaffolding is filtered out (see `_is_scaffolding`).
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from . import _find_wiki_entity, WIKI_ENTITIES
from .projects import discover_projects
from ..config import logger

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")

MARKER_NAME = ".agent-hub-source.json"
READY_MARKER_NAME = ".agent-hub-ready-to-push"
NOISE_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache", ".ocdata"}
# Hub-injected scaffolding dropped into a worktree — never "the agent changed
# the project". A linked worktree shares .git/info/exclude with the real repo,
# so we cannot gitignore these there; filter them here instead.
SCAFFOLDING_FILES = {MARKER_NAME, "AGENTS.md", "opencode.json",
                     ".agent-hub-base", ".agent-hub-origin", READY_MARKER_NAME}


def _is_scaffolding(path: str) -> bool:
    p = path.replace("\\", "/")
    return (p in SCAFFOLDING_FILES or p == "serve.log"
            or p.startswith(".ocdata") or p.startswith(".opencode") or p.startswith(".claude") or p.startswith(".hub-ref")
            or "__pycache__/" in p + "/" or p.endswith(".pyc")
            or p.startswith("node_modules/") or p.startswith(".venv/"))


async def _git(cwd: Path, *args: str, timeout: float = 15) -> tuple[int, str]:
    try:
        p = await asyncio.create_subprocess_exec(
            "git", "-c", "core.autocrlf=false", *args, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
        return p.returncode or 0, out.decode("utf-8", "replace").strip()
    except Exception as exc:
        return 1, str(exc)


def _wt_base(wt: Path) -> str:
    try:
        b = (wt / ".agent-hub-base").read_text(encoding="utf-8").strip()
        return b or "HEAD"
    except Exception:
        return "HEAD"


async def _wt_has_changes(wt: Path) -> bool | None:
    """True if the agent branch has diverged from its base (committed OR
    working-tree changes). None on error."""
    base = _wt_base(wt)
    rc, out = await _git(wt, "--no-pager", "diff", "--quiet", f"{base}...HEAD")
    committed = None if rc not in (0, 1) else (rc == 1)
    rc2, dirty = await _git(wt, "status", "--porcelain")
    working = None if rc2 != 0 else bool([l for l in dirty.splitlines()
                                          if not _is_scaffolding(l[3:].strip())])
    if committed is None and working is None:
        return None
    return bool(committed) or bool(working)


async def worktree_changed_files(wt: Path) -> list[dict]:
    """[{status, path}] — committed diff vs base + uncommitted working changes."""
    base = _wt_base(wt)
    seen: dict[str, str] = {}
    rc, out = await _git(wt, "--no-pager", "diff", "--name-status", f"{base}...HEAD")
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                seen[parts[-1]] = parts[0][:1]
    rc2, dirty = await _git(wt, "status", "--porcelain", "-uall")   # -uall: list files, not a collapsed "newdir/"
    if rc2 == 0:
        for line in dirty.splitlines():
            if not line.strip():
                continue
            code = line[:2].strip()
            path = line[2:].strip().strip('"').split(" -> ")[-1].strip().strip('"')
            if path and not _is_scaffolding(path):
                seen[path] = (code[:1] or "M").replace("?", "A")
    return [{"status": s, "path": p} for p, s in sorted(seen.items())]


async def worktree_file_diff(wt: Path, rel_path: str) -> str:
    base = _wt_base(wt)
    await _git(wt, "add", "-N", rel_path)              # show a brand-new file's contents
    rc, out = await _git(wt, "--no-pager", "diff", base, "--", rel_path)
    return out


async def merge_agent_branch(source: Path, wt: Path) -> dict:
    """Commit any pending working changes on agent/<slug>, then merge that
    branch into the source repo's base branch (non-fast-forward)."""
    branch = f"agent/{wt.name}"
    base = _wt_base(wt)
    await _git(wt, "add", "-A")
    await _git(wt, "-c", "user.email=hub@local", "-c", "user.name=Agent Hub",
               "commit", "-m", "agent work", "--allow-empty")
    if not (source / ".git").exists():
        return {"ok": False, "output": "source is not a git repo — nothing to merge into"}
    rc, out = await _git(source, "merge", "--no-ff", "-m", f"merge {branch}", branch)
    return {"ok": rc == 0, "output": out, "branch": branch, "base": base}


async def compute_project_state(project: dict, workroot: Path) -> dict:
    """{**project, state, ring, wiki_entity, copies}. `workroot` is now the
    WORKTREES dir; a project's agent work is the git worktree at
    workroot/<opencode slug>."""
    from ..features.opencode import worktree_for

    path = Path(project["path"])
    entity = _find_wiki_entity(project["name"])
    wiki_entity = entity.stem if entity else None

    if project["readonly"]:
        return {**project, "state": "red", "ring": None, "wiki_entity": wiki_entity, "copies": []}

    wt = worktree_for(path)
    if not wt.exists():
        return {**project, "state": "blue", "ring": None, "wiki_entity": wiki_entity, "copies": []}

    has_diff = await _wt_has_changes(wt)
    ready = (wt / READY_MARKER_NAME).exists()
    if has_diff is None:
        state, ring = "unknown", None
    elif has_diff:
        state, ring = "amber", ("green" if ready else None)
    else:
        state, ring = "green", None

    return {**project, "state": state, "ring": ring, "wiki_entity": wiki_entity,
            "copies": [{"folder": wt.name, "has_diff": bool(has_diff),
                        "ready_to_push": ready, "needs_update": False}]}


async def _orphan_nodes(workroot: Path) -> list[dict]:
    """One node per worktree under `workroot` that no discovered project maps to
    (source folder deleted / moved / never a tracked project). Reuses the
    opencode slug so the graph panel can drive it via /api/opencode/folders/."""
    import re
    from ..features.opencode import slug_for, read_origin, OC
    if not workroot.is_dir():
        return []
    mid_re = re.compile(r"^(?P<slug>.+)--(?P<mid>m[0-9a-f]{8})$")
    known = set()
    for p in discover_projects():
        try:
            known.add(slug_for(p["path"]))
        except Exception:
            pass
    out: list[dict] = []
    dirs = [d for d in sorted(workroot.iterdir())
            if d.is_dir() and d.name not in ("_scratch", "_missions") and d.name not in known]
    gate = asyncio.Semaphore(6)                       # scan in parallel (was one folder at a time), but never 40 gits at once

    async def _scan(d: Path):
        async with gate:
            return await _wt_has_changes(d)
    diffs = await asyncio.gather(*(_scan(d) for d in dirs))
    for d, has_diff in zip(dirs, diffs):
        origin = read_origin(d)
        running = d.name in OC.runtimes and OC.runtimes[d.name].alive
        mm = mid_re.match(d.name)
        base = Path(origin).name if origin else (
            (mm.group("slug") if mm else d.name.rsplit("-", 1)[0]).replace("-", " "))
        # keep state 'orphan' so the graph's existing worktree controls apply;
        # only the category differs so missions cluster on their own.
        out.append({
            "slug": d.name,
            "name": (f"{base} · {mm.group('mid')}" if mm else base) or d.name,
            "path": origin or str(d), "readonly": False,
            "category": "Missions" if mm else "Orphans",
            "state": "orphan", "ring": None,
            "wiki_entity": None, "origin": origin, "worktree": str(d),
            "running": running, "source_missing": not (origin and Path(origin).is_dir()),
            "copies": [{"folder": d.name, "has_diff": bool(has_diff),
                        "ready_to_push": False, "needs_update": False}],
        })
    return out


async def compute_graph(workroot: Path) -> list[dict]:
    projects = discover_projects()
    results = await asyncio.gather(
        *(compute_project_state(p, workroot) for p in projects),
        return_exceptions=True,
    )
    out = []
    for p, r in zip(projects, results):
        if isinstance(r, Exception):
            logger.warning("graph: status failed for %s: %s", p["slug"], r)
            out.append({**p, "state": "unknown", "ring": None, "wiki_entity": None, "copies": []})
        else:
            out.append(r)
    try:
        out.extend(await _orphan_nodes(workroot))
    except Exception as exc:
        logger.warning("graph: orphan scan failed: %s", exc)
    return out


def _wikilinks_in(entity_stem: str) -> set[str]:
    """Raw `[[link]]` targets referenced in a wiki entity page's body, as
    written (Obsidian wikilinks are filename-stem text, not slugs)."""
    path = WIKI_ENTITIES / f"{entity_stem}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    return {m.strip() for m in _WIKILINK_RE.findall(text)}


def compute_project_links(nodes: list[dict]) -> list[dict]:
    """Project-to-project edges (2026-08-15): real `[[wikilinks]]` between two
    projects' OWN wiki entity pages, e.g. agent-hub.md linking to
    [[movie-shorts-clipper]] — the wiki's existing prose cross-references,
    turned into graph edges rather than a second signal invented separately.

    Only edges where BOTH sides resolve to a discovered project surface here;
    a link to a non-project entity (a tool, a person, a concept) is correctly
    invisible to the graph — it isn't a project-to-project relationship.
    """
    stem_to_slug = {n["wiki_entity"]: n["slug"] for n in nodes if n.get("wiki_entity")}
    stem_to_slug_ci = {k.lower(): v for k, v in stem_to_slug.items()}

    seen_pairs: set[frozenset] = set()
    links: list[dict] = []
    for n in nodes:
        stem = n.get("wiki_entity")
        if not stem:
            continue
        for target in _wikilinks_in(stem):
            other_slug = stem_to_slug.get(target) or stem_to_slug_ci.get(target.lower())
            if not other_slug or other_slug == n["slug"]:
                continue
            pair = frozenset((n["slug"], other_slug))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            links.append({"a": n["slug"], "b": other_slug})
    return links
