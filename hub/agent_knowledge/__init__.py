"""Agent knowledge layer: what an OpenCode session knows before its first turn.

Three parts, composed once per session (see opencode.py::Manager._launch):
  - AGENTS.md: a THIN always-on index (safety rules + a short project summary
    pulled from the LLM wiki entity page, if one exists). Not a place for deep
    per-topic instructions — those are skills.
  - skills/: specialized, on-demand files. Only the frontmatter (name +
    description) is cheap to surface; the body loads when a task matches.
  - lsp/mcp config: dicts merged into the session's opencode.json.

Everything here is READ from the wiki / skills library; nothing here writes
back to either. Best-effort throughout — a missing wiki page or unmatched
skill just means a shorter AGENTS.md, never an error.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import logger

WIKI_ROOT = Path(r"N:\Code\git repositories\_LLM Wiki - Obsidian Second Brain\LLM Wiki")
WIKI_ENTITIES = WIKI_ROOT / "entities"
SKILLS_DIR = Path(__file__).parent / "skills"
# Per-provider/per-model sampling overrides (temperature, top_p, ...), keyed
# exactly like opencode.json's own `provider.<name>.models.<model>.options` —
# deep-merged in, so setting one model's temperature never touches another's
# config. Empty `{}` by default: no policy opinion baked in, just the wiring.
# Edit this file directly to set a project's/model's sampling behavior.
MODEL_OPTIONS_FILE = Path(__file__).parent / "model_options.json"

SAFETY_RULES = """# Project context — READ FIRST

This directory IS the project root and the ONLY place you may work. It is a
disposable working copy. An identical copy of these files exists ELSEWHERE on
this machine (the user's original repo) — you must NEVER find, open, read, or
edit that original. All of your reads and edits must use paths INSIDE this
folder (relative paths, or absolute paths that start with this folder).

Rules:
- Start by listing the current directory (`ls`); everything you need is here.
- NEVER search the whole filesystem/drive: no `find N:\\ ...`, no `dir -Recurse`
  from the drive root, no listing `/`, `/var`, `/home`, `/Users`, `/workspace`.
- NEVER edit a file outside this directory. If a tool would write to a path that
  is not inside this folder, do not do it — the edit belongs in the copy here.
- If you can't find a file, `ls` subfolders HERE. It is not elsewhere.
"""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Repo-naming noise that has nothing to do with the project's identity —
# strip before matching so "LmStudioToCursor-main" still finds
# lmstudio-to-cursor.md instead of missing on the trailing "-main".
_NOISE_SUFFIXES = ("-main", "-master")

# Verified hard cases the automatic matcher can't confidently bridge on its
# own (e.g. a GitHub Pages folder literally named "<user>.github.io" vs. a
# wiki page named for what the site actually is — no shared word to match
# on besides the owner's name). Each entry is confirmed by reading both
# sides, not guessed. project-slug -> wiki-entity-stem-slug.
WIKI_SLUG_OVERRIDES = {
    "infernalzeus-github-io": "infernalzeus-portfolio",
}


def _strip_noise_suffix(slug: str) -> str:
    for suf in _NOISE_SUFFIXES:
        if slug.endswith(suf):
            return slug[: -len(suf)]
    return slug


def _find_wiki_entity(project_name: str) -> Path | None:
    """Match a project folder name to its wiki entity page.

    Authoritative first: an entity page can declare `project_slug: <slug>`
    in its frontmatter (see CLAUDE.md § Page format) — a deterministic link
    the wiki-ingest process sets explicitly, not something to leave for
    name-guessing. Only entities without that field fall through to the
    override table, then to fuzzy slug matching.
    """
    if not WIKI_ENTITIES.is_dir():
        return None
    target = _slugify(project_name)
    candidates = list(WIKI_ENTITIES.glob("*.md"))

    for p in candidates:
        if _parse_frontmatter(p).get("project_slug") == target:
            return p

    target_stripped = _strip_noise_suffix(target)
    override = WIKI_SLUG_OVERRIDES.get(target)
    if override:
        for p in candidates:
            if _slugify(p.stem) == override:
                return p

    # exact slug match (with and without the stripped noise suffix)
    for p in candidates:
        slug = _slugify(p.stem)
        if slug == target or slug == target_stripped:
            return p
    # substring match either direction, hyphens intact
    for p in candidates:
        slug = _slugify(p.stem)
        if slug and (slug in target_stripped or target_stripped in slug):
            return p
    # last resort: dense (hyphens stripped) comparison — catches a
    # CamelCase-squashed folder name against a hyphenated wiki slug for the
    # same words (e.g. "lmstudiotocursor" vs "lmstudio-to-cursor"). Gated on
    # a minimum length so short names can't spuriously substring-match.
    dense_target = target_stripped.replace("-", "")
    if len(dense_target) >= 8:
        for p in candidates:
            dense_cand = _slugify(p.stem).replace("-", "")
            if dense_cand and len(dense_cand) >= 8 and (
                dense_cand == dense_target or dense_cand in dense_target or dense_target in dense_cand
            ):
                return p
    return None


def _wiki_summary(project_name: str, max_chars: int = 1800) -> str | None:
    """A short excerpt of the project's wiki entity page, for AGENTS.md."""
    entity = _find_wiki_entity(project_name)
    if entity is None:
        return None
    try:
        text = entity.read_text(encoding="utf-8")
    except Exception:
        return None
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n… (see the wiki for the rest)"
    return text


def _parse_frontmatter(path: Path) -> dict:
    """Parse a page's minimal `key: value` frontmatter block. Used for both
    skill files (name/description/keywords) and wiki entity pages
    (project_slug, for the graph's wiki-link matching)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm


def list_skills() -> list[dict]:
    """Every skill in the library, as {name, description, keywords, path}."""
    if not SKILLS_DIR.is_dir():
        return []
    out = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        fm = _parse_frontmatter(p)
        if not fm.get("name"):
            continue
        keywords = [k.strip() for k in fm.get("keywords", "").split(",") if k.strip()]
        out.append({"name": fm["name"], "description": fm.get("description", ""),
                    "keywords": keywords, "path": p})
    return out


def relevant_skills(project_name: str, source: Path) -> list[dict]:
    """Skills whose keywords match the project name or its file extensions."""
    haystack = _slugify(project_name)
    try:
        exts = {p.suffix.lower().lstrip(".") for p in source.rglob("*") if p.is_file()}
    except Exception:
        exts = set()
    matched = []
    for skill in list_skills():
        for kw in skill["keywords"]:
            if kw.lower() in haystack or kw.lower() in exts:
                matched.append(skill)
                break
    return matched


def render_agents_md(project_name: str, source: Path) -> str:
    """The full AGENTS.md for a session: safety rules + wiki summary + skill index.

    Deliberately thin — this is the always-loaded index, not the knowledge
    itself. Skill BODIES are not inlined; only name + description, so the
    agent knows what exists and can read the file when a task calls for it.

    The FULL skill catalog is always listed, not just what matches this
    project's name/file extensions — a session is a general coding assistant
    that happens to be pointed at this folder, not a tool scoped to only
    this project's own tech stack. Project-matched skills are just
    highlighted first; a session building in a language/framework outside
    its current folder should reach for those skills just as readily.
    """
    parts = [SAFETY_RULES]

    summary = _wiki_summary(project_name)
    if summary:
        parts.append(f"\n## Project background (from the LLM wiki)\n\n{summary}\n")

    all_skills = list_skills()
    if all_skills:
        matched = relevant_skills(project_name, source)
        matched_names = {s["name"] for s in matched}
        others = [s for s in all_skills if s["name"] not in matched_names]
        lines = ["\n## Available skills\n",
                 "Read the full file when a task actually matches one — don't guess at the "
                 "details from the name alone. Not limited to this project's own tech stack: "
                 "these span many domains (frontend, databases, security, testing, ops, ...) "
                 "so reach for whichever one fits the actual task, not just what matches this "
                 "folder's own language/framework.\n"]
        if matched:
            lines.append("\n**Especially relevant to this project:**")
            for s in matched:
                lines.append(f"- **{s['name']}** ({s['path'].name}): {s['description']}")
        if others:
            lines.append("\n**Also available:**")
            for s in others:
                lines.append(f"- **{s['name']}** ({s['path'].name}): {s['description']}")
        parts.append("\n".join(lines) + "\n")

    return "\n".join(parts)


def lsp_config() -> dict:
    """OpenCode ships its own multi-language LSP; just turn it on.

    No separate pyright/tsserver install needed — `"lsp": true` enables
    OpenCode's built-in servers per-language, auto-detected from the project.
    """
    return {"lsp": True}


def mcp_config() -> dict:
    """MCP servers to wire into every session. Empty for now.

    Extension point for a future wiki-query MCP server (let the agent pull
    from the LLM wiki on demand instead of only the AGENTS.md excerpt) and
    any git/docs-lookup MCP servers — deliberately not built yet: an MCP
    server is a small protocol implementation of its own, and a wrong one
    silently breaks every session that loads it. Ship this empty, add servers
    one at a time, each verified against a real session before trusting it.
    """
    return {}


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into base, in place. Dicts merge; anything
    else in patch overwrites base. Never drops a base key patch doesn't touch."""
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def model_options_patch() -> dict:
    """Sampling-option overrides from model_options.json, ready to deep-merge
    under the config's `provider` key. `{}` (the file's default) is a no-op."""
    try:
        raw = json.loads(MODEL_OPTIONS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def apply_session_config(base_cfg: dict, project_name: str, source: Path) -> dict:
    """The full opencode.json for a session: the shared base config, with the
    knowledge layer's lsp/mcp/model-options merged in additively.

    Never removes or replaces a key the base config already sets (model,
    provider, permission, ...) — only adds `lsp`/`mcp` if absent and deep-
    merges `provider` overrides so unrelated models keep their settings.
    """
    cfg = dict(base_cfg)
    lsp = lsp_config()
    if lsp and "lsp" not in cfg:
        cfg["lsp"] = lsp["lsp"]
    mcp = mcp_config()
    if mcp:
        cfg.setdefault("mcp", {})
        _deep_merge(cfg["mcp"], mcp)
    overrides = model_options_patch()
    if overrides:
        cfg.setdefault("provider", {})
        _deep_merge(cfg["provider"], overrides)
    return cfg
