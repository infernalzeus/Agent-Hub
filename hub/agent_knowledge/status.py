"""Per-project sync state for the graph (Phase 3/4).

State model (revised 2026-08-15, matching the agent-core node-color language —
blue means "available/inactive", not "has changes"):
  red    - read-only project (LLM wiki, Agent Hub, agent-core); never touched
  blue   - available/potential: no Agent Code copy exists yet — nothing has
           been opened into a chat for this project
  amber  - has a diff vs source (a session exists and OpenCode made changes;
           nothing decided yet) — amber/gold to match agent-core's own
           "active work" color, since blue no longer means that here
  green  - in sync: a copy exists and has no diff (untouched since creation,
           or successfully pushed back)
  amber + green ring - diff exists and has been marked ready to push
  amber + orange ring - diff exists and the SOURCE has moved on since the
                        copy was created (approximate: newest-file mtime
                        compare — a real "did source change" signal needs the
                        clone-on-branch upgrade noted in the design; this is
                        the honest version of that signal until then)

Diffing uses `git diff --no-index` between the two plain directories — this
works whether or not `source` itself is a git repo, and needs no shared
history (today's copies are `git init` + copytree, not a clone).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from . import _find_wiki_entity, WIKI_ENTITIES
from .projects import discover_projects, discover_local_projects
from ..config import logger

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")

MARKER_NAME = ".agent-hub-source.json"
READY_MARKER_NAME = ".agent-hub-ready-to-push"
NOISE_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}
# Hub-injected scaffolding at the copy root — never part of "did the agent
# change the project". opencode.json is rewritten on every launch regardless
# of what source has, so it's never a genuine project diff either way.
SCAFFOLDING_FILES = {MARKER_NAME, "AGENTS.md", "opencode.json"}


def _find_copies_for(source: Path, workroot: Path) -> list[Path]:
    """Every Agent Code copy whose marker points at this source. Source-backed
    copies live under `workroot/projects/` (see hub/features/opencode.py) —
    that's the only place the diff/comparison engine ever needs to look."""
    root = workroot / "projects"
    if not root.is_dir():
        return []
    resolved_source = str(source.resolve())
    out = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        marker = child / MARKER_NAME
        if not marker.exists():
            continue
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if str(Path(data.get("source", "")).resolve()) == resolved_source:
                out.append(child)
        except Exception:
            continue
    return out


def _find_chats_for(project_dir: Path, workroot: Path) -> list[Path]:
    """Every chats/ entry that links to this ONE project copy — a junction
    whose target resolves to project_dir (the normal case, one per open/
    resumable chat), or, defensively, a standalone chat folder that somehow
    shares the exact same path (shouldn't happen, but never miss a chat
    over it). Used for the graph panel's Resume/Open buttons — there can be
    several chats for one project, all sharing the same underlying files."""
    root = workroot / "chats"
    if not root.is_dir():
        return []
    target = project_dir.resolve()
    return [c for c in root.iterdir() if c.is_dir() and c.resolve() == target]


async def _git_diff_has_changes(source: Path, copy: Path, timeout: float = 15.0) -> bool | None:
    """True if there's any real (non-noise) difference between source and copy.

    Delegates to `list_changed_files` rather than running its own separate
    `git diff --no-index --name-only` — found and fixed a real bug where the
    two had diverged: `--name-only` mode, for a DELETION with no rename
    pairing, apparently reports the change as bare "/dev/null" and never
    the actual filename (confirmed empirically — the same repo where
    `--name-status` correctly names the deleted file). Since "/dev/null" is
    exactly the noise token this function already had to filter out, a
    delete-only diff was silently invisible here even though the file list
    endpoint (which already used `--name-status`) saw it correctly the whole
    time. One source of truth now — these two can't disagree again.

    None on error/timeout (state becomes 'unknown', never a false green).
    """
    changed = await _raw_changed_files(source, copy, timeout=timeout)
    return bool(changed) if changed is not None else None


def _filter_diff_line(rel: str) -> bool:
    """True if this path is real project content — not scaffolding/noise."""
    if not rel or rel == "/dev/null":
        return False
    parts = Path(rel).parts
    if any(p in NOISE_DIRS for p in parts):
        return False
    if parts and parts[-1] in SCAFFOLDING_FILES:
        return False
    return True


async def _raw_changed_files(source: Path, copy: Path, timeout: float = 15.0) -> list[dict] | None:
    """[{path, status}] via `git diff --no-index --name-status -z`, or None
    on error/timeout (distinct from "no changes" — callers must not treat
    an error as a false "in sync").

    Two Windows-specific gotchas, both load-bearing:
      - Backslash paths (esp. with the space in "Agent Code") make Git-for-
        Windows quote/escape the output unpredictably — pass forward-slash
        paths instead, which git accepts natively on Windows.
      - `--name-status` (not `--name-only`) is required, not a style choice:
        for a DELETION with no rename pairing, `--name-only`'s `-z` output
        apparently reports bare "/dev/null" and never the actual filename
        (confirmed empirically) — indistinguishable from the noise tokens
        this already has to filter, so a delete-only diff went invisible.
        `--name-status` pairs a real status letter with the path and doesn't
        have this problem.
    """
    src_arg, copy_arg = str(source).replace("\\", "/"), str(copy).replace("\\", "/")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--no-index", "--name-status", "-z", src_arg, copy_arg,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except Exception:
        return None
    tokens = [t for t in out.decode("utf-8", errors="replace").split("\x00") if t]
    out_list: list[dict] = []
    i = 0
    while i < len(tokens):
        code = tokens[i]
        if code and code[0] in "AMD" and i + 1 < len(tokens):
            path_token = tokens[i + 1]
            i += 2
        elif code and code[0] == "R" and i + 2 < len(tokens):
            # rename: status\told-path\tnew-path — report the new path
            path_token = tokens[i + 2]
            i += 3
        else:
            i += 1
            continue
        rel = path_token[len(copy_arg):].lstrip("/") if path_token.startswith(copy_arg) \
            else path_token[len(src_arg):].lstrip("/")
        if _filter_diff_line(rel):
            out_list.append({"path": rel, "status": code[0]})
    return out_list


async def list_changed_files(source: Path, copy: Path, timeout: float = 15.0) -> list[dict]:
    """[{path, status}] for the git-desktop-style detail panel. status is
    git's single-letter code: A (added), M (modified), D (deleted). Error/
    timeout is silently [] here — the file-list UI has no separate "unknown"
    state to show, unlike `_git_diff_has_changes`, which calls
    `_raw_changed_files` directly to keep that distinction."""
    changed = await _raw_changed_files(source, copy, timeout=timeout)
    return changed if changed is not None else []


async def file_diff(source: Path, copy: Path, rel_path: str, timeout: float = 10.0) -> str:
    """Unified diff text for one file — for the detail panel's diff view."""
    src_file = str(source / rel_path).replace("\\", "/")
    copy_file = str(copy / rel_path).replace("\\", "/")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--no-index", "--no-color", src_file, copy_file,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except Exception:
        return ""
    return out.decode("utf-8", errors="replace")


def _source_newer_than_copy(source: Path, copy_created_at: float) -> bool:
    """Approximate 'source moved on since this copy was made' — newest
    mtime under source vs the copy's creation timestamp. See module docstring."""
    try:
        newest = max((p.stat().st_mtime for p in source.rglob("*")
                      if p.is_file() and not any(part in NOISE_DIRS for part in p.parts)),
                     default=0.0)
    except Exception:
        return False
    return newest > copy_created_at


async def compute_project_state(project: dict, workroot: Path) -> dict:
    """{slug, name, path, readonly, state, ring, wiki_entity, copies: [...]}

    wiki_entity: the LLM wiki entity page's slug, if one declares this project
    via `project_slug` frontmatter (see CLAUDE.md) or matches by name — the
    graph draws an edge to the wiki node only when this is set, so projects
    with no wiki page are visibly disconnected from it (a documentation-gap
    signal, not just decoration).
    """
    slug, path = project["slug"], Path(project["path"])
    entity = _find_wiki_entity(project["name"])
    wiki_entity = entity.stem if entity else None

    if project["readonly"]:
        return {**project, "state": "red", "ring": None, "wiki_entity": wiki_entity, "copies": []}

    copies = _find_copies_for(path, workroot)
    if not copies:
        return {**project, "state": "blue", "ring": None, "wiki_entity": wiki_entity, "copies": []}

    # Exactly ONE real copy per project now (hub/features/opencode.py reuses
    # it for every chat rather than re-copying) — diff/ready/needs-update are
    # a single project-level state, not one per chat. `copies` in the
    # returned dict stays a list of CHATS though (junctions into this one
    # copy) — that's what the graph panel's Resume/Open buttons act on, and
    # there can genuinely be several of those for one project.
    project_dir = copies[0]
    has_diff = await _git_diff_has_changes(path, project_dir)
    ready = (project_dir / READY_MARKER_NAME).exists()
    try:
        created_at = project_dir.stat().st_ctime
    except Exception:
        created_at = 0.0
    needs_update = _source_newer_than_copy(path, created_at) if has_diff else False

    chats = _find_chats_for(project_dir, workroot) or [project_dir]
    copy_infos = [{
        "folder": c.name, "has_diff": bool(has_diff), "ready_to_push": ready,
        "needs_update": needs_update,
    } for c in chats]

    if has_diff is None:
        state, ring = "unknown", None
    elif has_diff:
        state = "amber"
        ring = "green" if ready else ("orange" if needs_update else None)
    else:
        state, ring = "green", None

    return {**project, "state": state, "ring": ring, "wiki_entity": wiki_entity, "copies": copy_infos}


def _copy_created_at(copy: Path) -> float:
    marker = copy / MARKER_NAME
    try:
        return marker.stat().st_ctime
    except Exception:
        try:
            return copy.stat().st_ctime
        except Exception:
            return 0.0


async def push_changes(source: Path, copy: Path, files: list[str] | None = None,
                        force: bool = False) -> dict:
    """Apply reviewed changes from `copy` back onto `source`. Phase 5.

    Deliberately conservative given today's architecture (a plain copytree,
    not a clone with shared history — see the design notes in the module
    docstring): only A(dded)/M(odified) files are ever written to source.
    D(eleted) files are NEVER auto-deleted from source — reported back for
    the user to remove by hand, since a deletion is the one push action that
    can't be undone by re-diffing.

    Conflict check: if `source`'s file was modified after this copy was
    created (mtime-based — the same approximate signal as the graph's
    "needs update" ring), the push is refused for that file unless
    `force=True`. This is the "review-first, conflict-aware" behavior from
    the design: never silently overwrite a source that moved on.
    """
    all_changed = await list_changed_files(source, copy)
    wanted = set(files) if files is not None else None
    created_at = _copy_created_at(copy)

    pushed, skipped_deletions, conflicts, errors = [], [], [], []
    for entry in all_changed:
        rel, code = entry["path"], entry["status"]
        if wanted is not None and rel not in wanted:
            continue
        if code == "D":
            skipped_deletions.append(rel)
            continue
        src_file = source / rel
        copy_file = copy / rel
        if not force:
            try:
                if src_file.exists() and src_file.stat().st_mtime > created_at:
                    conflicts.append(rel)
                    continue
            except Exception:
                pass
        try:
            src_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_bytes(copy_file.read_bytes())
            pushed.append(rel)
        except Exception as exc:
            errors.append({"path": rel, "error": str(exc)})
            logger.warning("push_changes: failed to write %s: %s", src_file, exc)

    return {"pushed": pushed, "skipped_deletions": skipped_deletions,
            "conflicts": conflicts, "errors": errors}


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
    for local in discover_local_projects(workroot):
        chats = _find_chats_for(Path(local["path"]), workroot) or [Path(local["path"])]
        out.append({
            **local, "state": "blue", "ring": None, "wiki_entity": None,
            "copies": [{"folder": c.name, "has_diff": False,
                        "ready_to_push": False, "needs_update": False} for c in chats],
        })
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
