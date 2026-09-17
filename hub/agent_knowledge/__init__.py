"""Agent knowledge layer: what an OpenCode session knows before its first turn.

Three parts, composed once per session (see opencode.py::Manager._launch):
  - AGENTS.md: a THIN always-on index (safety rules + a short project summary
    pulled from the LLM wiki entity page, if one exists) + a one-line pointer
    at the skills that match this project. Not a place for deep per-topic
    instructions — those are skills.
  - skills/: standard Agent Skills, one <name>/SKILL.md directory each
    (agentskills.io format). Published to OpenCode's global skills dir by
    agent_knowledge.skills_sync, then discovered and progressively disclosed
    by OpenCode's own native `skill` tool — their names/bodies are NOT
    inlined into AGENTS.md any more.
  - lsp/mcp/permission config: dicts merged into the session's opencode.json.

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
    SKILL.md files (name/description/metadata) and wiki entity pages
    (project_slug, for the graph's wiki-link matching).

    Understands one level of nesting for the Agent Skills spec's `metadata:`
    block, and YAML block scalars (`>`, `|`, `>-`, `|-`, ...) on any top-level
    key — several vendored skills write `description: >` across many lines.
    Every other key stays a flat string, so existing wiki-frontmatter callers
    are unaffected."""
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
    in_metadata = False
    lines = text[3:end].strip("\n").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        indented = raw[:1].isspace()
        key, _, val = raw.partition(":")
        key = key.strip()
        val = val.strip()

        # YAML block scalar: value is just `>` / `|` (+ optional chomp/indent
        # indicator). Consume the following more-indented lines as the value.
        if val and val[0] in "|>" and val.rstrip("+-0123456789") in ("|", ">"):
            folded = val[0] == ">"
            base_indent = len(raw) - len(raw.lstrip())
            block: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= base_indent:
                    break
                block.append(nxt.strip())
                i += 1
            joined = (" ".join(b for b in block if b) if folded
                      else "\n".join(block)).strip()
            if indented and in_metadata:
                fm.setdefault("metadata", {})[key] = joined
            else:
                fm[key] = joined
                in_metadata = False
            continue

        val = val.strip('"').strip("'")
        if indented and in_metadata:
            meta = fm.setdefault("metadata", {})
            if isinstance(meta, dict):
                meta[key] = val
        elif key == "metadata" and val == "":
            fm.setdefault("metadata", {})
            in_metadata = True
        else:
            fm[key] = val
            in_metadata = False
    return fm


def list_skills() -> list[dict]:
    """Every skill in the library, as {name, description, keywords, path, dir}.

    Standard Agent Skills layout: one directory per skill, each holding a
    SKILL.md (YAML frontmatter + body). `keywords` is Hub's own relevance
    hint, carried under the spec's free-form `metadata:` block; it has no
    effect on OpenCode's native matcher, which keys off `description`."""
    roots = [SKILLS_DIR,
             SKILLS_DIR.parent / "skills_vendor",
             SKILLS_DIR.parent / "skills_generated"]
    out: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            fm = _parse_frontmatter(skill_md)
            name = fm.get("name") or skill_md.parent.name
            if not name or name in seen:
                continue
            seen.add(name)
            meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
            kw_raw = meta.get("keywords", "") or fm.get("keywords", "")
            keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]
            out.append({"name": name, "description": fm.get("description", ""),
                        "keywords": keywords, "path": skill_md, "dir": skill_md.parent})
    return out


# Extensions too generic to signal a stack on their own.
_GENERIC_EXTS = {
    "", "md", "txt", "rst", "json", "yml", "yaml", "toml", "ini", "cfg", "conf",
    "lock", "log", "csv", "tsv", "env", "example", "gitignore", "editorconfig",
    "bak", "tmp", "png", "jpg", "jpeg", "gif", "svg", "ico", "pdf",
}


def skills_overview() -> list[dict]:
    """The whole library as plain dicts for the /graph UI + APIs: name,
    description, keyword list, and origin ('hand-written' | 'wiki-concept' |
    'vendored'), inferred from which source root the SKILL.md lives in."""
    gen_root = SKILLS_DIR.parent / "skills_generated"
    vendor_root = SKILLS_DIR.parent / "skills_vendor"
    out = []
    for s in list_skills():
        fm = _parse_frontmatter(s["path"])
        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        if gen_root in s["path"].parents:
            origin = "wiki-concept"
        elif vendor_root in s["path"].parents:
            origin = "vendored"
        else:
            origin = meta.get("origin") or "hand-written"
        entry = {"name": s["name"], "description": s["description"],
                 "keywords": s["keywords"], "origin": origin}
        if meta.get("source_page"):
            entry["source_page"] = meta["source_page"]
        out.append(entry)
    return out


def relevant_skills(project_name: str, source: Path, limit: int = 4) -> list[dict]:
    """The few skills that plausibly fit THIS project — a whole-word hit on the
    project name, or a file extension that shows up often enough to signal the
    stack (not one stray file). Deliberately conservative and capped: this only
    drives a one-line hint in AGENTS.md, and a hint that fires for a third of
    the library is noise. Best matches first.

    Old behaviour was `keyword substring-in-name OR keyword in any extension`,
    which tagged ~6 skills onto any mixed-language repo (a single `.sql` or
    `.tsx` file was enough). Now: name match must be a whole token, and an
    extension must be non-generic and appear >= 3 times."""
    name = project_name.lower()
    ext_counts: dict[str, int] = {}
    try:
        for p in source.rglob("*"):
            if p.is_file():
                e = p.suffix.lower().lstrip(".")
                ext_counts[e] = ext_counts.get(e, 0) + 1
    except Exception:
        pass
    strong_exts = {e for e, n in ext_counts.items()
                   if e and e not in _GENERIC_EXTS and n >= 3}

    scored: list[tuple[int, str, dict]] = []
    for skill in list_skills():
        score = 0
        for kw in skill["keywords"]:
            k = kw.lower().strip()
            if not k:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", name):
                score += 3
            elif k in strong_exts:
                score += 2
        if score:
            scored.append((score, skill["name"], skill))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [s for _, _, s in scored[:limit]]


def render_agents_md(project_name: str, source: Path) -> str:
    """The full AGENTS.md for a session: safety rules + wiki summary + a short
    skills pointer.

    Deliberately thin. Skill names/descriptions are no longer inlined here at
    all — the library is published to OpenCode's global skills dir (see
    agent_knowledge.skills_sync), so every session already gets the whole
    catalog through the native `skill` tool with real progressive disclosure
    (name + description at startup, body only on activation). AGENTS.md just
    adds a one-line nudge naming the skills that match this project, which
    helps weaker local models that won't reach for the tool unprompted.
    """
    parts = [SAFETY_RULES]

    summary = _wiki_summary(project_name)
    if summary:
        parts.append(f"\n## Project background (from the LLM wiki)\n\n{summary}\n")

    all_skills = list_skills()
    if all_skills:
        matched = relevant_skills(project_name, source)
        block = [
            "\n## Skills\n",
            f"{len(all_skills)} domain skills are installed and available on demand "
            "through the `skill` tool — each carries its own instructions that load "
            "only when a task matches. Reach for it whenever a task touches a "
            "specific stack or workflow (APIs, databases, frontend, security, "
            "testing, data science, video, Windows automation, ...); they are not "
            "limited to this project's own tech stack.",
        ]
        if matched:
            names = ", ".join(f"`{s['name']}`" for s in matched)
            block.append(f"\nMost likely relevant to this project: {names}.")
        parts.append("\n".join(block) + "\n")

    return "\n".join(parts)


# ── agent team (personas materialized into a worktree's .opencode/agent/) ──
AGENTS_DIR = Path(__file__).parent / "agents"                # baseline, in the repo
USER_AGENTS_DIR = Path(__file__).parent / "agents_user"      # yours, gitignored
OVERRIDES_FILE = Path(__file__).parent / "agent_overrides.json"   # LLM-settings, gitignored
# always materialised + always available as a chat target, but not "on the team"
UTILITY_AGENTS = ("agent-smith", "app-ingestor")


def _agent_md(name: str) -> Path | None:
    """The .md for a persona — a user agent shadows a baseline one of the same name."""
    for d in (USER_AGENTS_DIR, AGENTS_DIR):
        p = d / f"{name}.md"
        if p.is_file():
            return p
    return None


def is_user_agent(name: str) -> bool:
    return (USER_AGENTS_DIR / f"{name}.md").is_file()


def _load_persona(name: str) -> dict | None:
    """{frontmatter, body} for one persona file, or None if it doesn't exist."""
    md = _agent_md(name)
    if md is None:
        return None
    try:
        text = md.read_text(encoding="utf-8")
    except Exception:
        return None
    fm = _parse_frontmatter(md)
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
    return {"frontmatter": fm, "body": body.strip()}


def list_agents() -> list[dict]:
    """Every persona (baseline + user), as {name, description, mode, origin}."""
    out: list[dict] = []
    seen: set[str] = set()
    for origin, d in (("user", USER_AGENTS_DIR), ("baseline", AGENTS_DIR)):
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            if md.name.startswith("_") or md.stem in seen:
                continue
            seen.add(md.stem)
            fm = _parse_frontmatter(md)
            out.append({"name": md.stem, "description": fm.get("description", ""),
                        "mode": fm.get("mode", "subagent"), "origin": origin,
                        "rationale": fm.get("rationale", "")})
    return out


# ── model policy ─────────────────────────────────────────────────────────────
POLICY_FILE = Path(__file__).parent / "model_policy.json"
FAST_FREE_MODEL = "opencode/nemotron-3.5-lightning-free"
LOCAL_MODEL = "ollama/gemma4:e4b"
# free cloud models to fall back through on a transient (502 / overloaded) failure
MODEL_FALLBACKS = ["opencode/mimo-v2.5-free", LOCAL_MODEL]
_PAID_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
             "GROQ_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY")


def model_policy() -> str:
    """'auto' | 'free-cloud' | 'local' | an explicit model id. From
    model_policy.json ({"policy": "..."}); defaults to 'auto'."""
    try:
        v = json.loads(POLICY_FILE.read_text(encoding="utf-8")).get("policy")
        return v.strip() if isinstance(v, str) and v.strip() else "auto"
    except Exception:
        return "auto"


def set_model_policy(policy: str) -> None:
    POLICY_FILE.write_text(json.dumps({"policy": (policy or "auto").strip()}, indent=2),
                           encoding="utf-8")


def _paid_provider_model() -> str | None:
    """A model id for the first paid provider whose key is in the environment, or
    None. Best-effort — the user can always pin one via model_policy."""
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic/claude-sonnet-4"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai/gpt-4.1-mini"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter/anthropic/claude-3.7-sonnet"
    if os.environ.get("GROQ_API_KEY"):
        return "groq/llama-3.3-70b-versatile"
    return None


def resolved_default_model(workspace_model: str | None = None) -> str:
    """The model a mission uses when none is pinned, per the current policy."""
    pol = model_policy()
    if pol == "local":
        return LOCAL_MODEL
    if pol == "free-cloud":
        return FAST_FREE_MODEL
    if pol not in ("auto", ""):
        return pol                                   # an explicit id
    return _paid_provider_model() or workspace_model or FAST_FREE_MODEL


def model_chain(primary: str | None, workspace_model: str | None = None) -> list[str]:
    """Ordered models to try for a mission: the pinned/policy model first, then
    the free-cloud + local fallbacks, deduped."""
    first = primary or resolved_default_model(workspace_model)
    chain = [first, FAST_FREE_MODEL, *MODEL_FALLBACKS]
    seen: set[str] = set()
    return [m for m in chain if m and not (m in seen or seen.add(m))]


def effective_settings(name: str) -> dict:
    """The LLM knobs actually in effect for a persona: user override → persona
    frontmatter → sensible default. Never blank, so the settings UI can show real
    values. `*_source` is 'override' | 'persona' | 'default'."""
    fm = (_load_persona(name) or {}).get("frontmatter", {})
    ov = load_overrides().get(name, {})

    def pick(key, dflt, dflt_note=""):
        if ov.get(key) not in (None, ""):
            return {"value": ov[key], "source": "override"}
        if fm.get(key) not in (None, ""):
            return {"value": fm[key], "source": "persona"}
        return {"value": dflt, "source": "default", "note": dflt_note}

    return {
        "model": pick("model", None, "workspace default (opencode.json)"),
        "temperature": pick("temperature", None, "model default (~0.7)"),
        "top_p": pick("top_p", None, "model default"),
        "variant": pick("variant", None, "model default"),
        "steps": pick("steps", None, "unbounded"),
    }


def load_overrides() -> dict:
    """Per-agent LLM-setting overrides {name: {model, temperature, top_p, variant,
    steps, options}} from agent_overrides.json (gitignored). {} if absent."""
    try:
        raw = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def save_override(name: str, patch: dict) -> None:
    data = load_overrides()
    cur = data.get(name, {})
    for k, v in (patch or {}).items():
        if v in (None, ""):
            cur.pop(k, None)
        else:
            cur[k] = v
    if cur:
        data[name] = cur
    else:
        data.pop(name, None)
    try:
        OVERRIDES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("agent_knowledge: could not save overrides: %s", exc)


def save_user_agent(name: str, text: str) -> Path:
    USER_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    p = USER_AGENTS_DIR / f"{_slugify(name)}.md"
    p.write_text(text, encoding="utf-8")
    return p


def delete_user_agent(name: str) -> bool:
    p = USER_AGENTS_DIR / f"{name}.md"
    if p.is_file():
        p.unlink()
        save_override(name, {})            # drop any stale override
        return True
    return False


def default_team() -> dict:
    """{primary, roster} — team.json order, plus every user agent appended."""
    agents = list_agents()
    have = {a["name"] for a in agents}
    try:
        raw = json.loads((AGENTS_DIR / "team.json").read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    roster = [n for n in (raw.get("roster") or []) if n in have]
    for a in agents:                       # user agents (and any not in team.json)
        if a["name"] not in roster and a["name"] not in UTILITY_AGENTS:
            roster.append(a["name"])
    primary = raw.get("primary")
    if primary not in roster:
        primary = next((n for n in roster
                        if (_load_persona(n) or {}).get("frontmatter", {}).get("mode") == "primary"),
                       roster[0] if roster else None)
    return {"primary": primary, "roster": roster}


def _skill_patterns(spec: str) -> dict:
    pats = [p.strip() for p in (spec or "*").split(",") if p.strip()]
    return {p: "allow" for p in pats} or {"*": "allow"}


def render_agent_file(name: str, *, subdir: str, roster: list[str],
                       base_branch: str, slug: str, headless: bool = False,
                       mission: bool = False) -> str | None:
    """The full `.opencode/agent/<name>.md` for a worktree.

    `mission=True` (a one-shot `opencode run` mission — one agent, its own
    throwaway worktree, one brief): `edit: allow` over the whole worktree, no
    path-scoping, no `task`. Otherwise (the shared-worktree team model):
    path-scoped `permission.edit` so a worker can only write its own subdir +
    `shared/`. `headless=True` upgrades a persona's `bash`/`webfetch` `ask` →
    `allow` (nobody to answer a prompt)."""
    persona = _load_persona(name)
    if persona is None:
        return None
    fm = persona["frontmatter"]
    is_primary = fm.get("mode") == "primary"   # the orchestrator specifically, not any mode:all worker

    def _gate(v: str | None, default: str) -> str:
        v = (v or default)
        return "allow" if ((headless or mission) and v == "ask") else v

    perm: dict = {"skill": _skill_patterns(fm.get("skills", "*"))}
    perm["bash"] = _gate(fm.get("bash"), "ask")
    if fm.get("webfetch"):
        perm["webfetch"] = _gate(fm.get("webfetch"), "ask")
    if mission and is_primary:
        # the orchestrator coordinates even alone in a one-shot mission worktree —
        # it may write shared/ notes, never project code. Found live: with blanket
        # edit:allow (the plain "mission" case below), a weak/free model just
        # implemented the task itself instead of planning it — permission
        # enforcement, not the prompt alone, is what makes "plan only" hold.
        perm["edit"] = {"*": "deny", "shared/**": "allow"}
        perm["task"] = "deny"
    elif mission:
        perm["edit"] = "allow"          # its own worktree — full write
        perm["task"] = "deny"
    elif fm.get("mode") == "primary":
        # the orchestrator coordinates: it may write shared/ notes, not project code
        perm["edit"] = {"*": "deny", "shared/**": "allow"}
        perm["task"] = "allow"
    else:
        perm["edit"] = {"*": "deny", "shared/**": "allow", f"{subdir}/**": "allow"}
        perm["task"] = "deny"          # workers do not spawn workers

    out_fm: dict = {"description": fm.get("description", f"{name} agent"),
                    "mode": fm.get("mode", "subagent")}
    if fm.get("color"):
        out_fm["color"] = fm["color"]

    # LLM knobs: persona frontmatter, then the user's agent_overrides.json on top
    ov = load_overrides().get(name, {})
    for key in ("model", "variant"):
        v = ov.get(key) or fm.get(key)
        if v:
            out_fm[key] = v
    # a worker mission defaults to minimal reasoning — free models waste minutes
    # "thinking" about trivial tasks. The orchestrator keeps normal reasoning.
    if mission and "variant" not in out_fm and fm.get("mode") != "primary":
        out_fm["variant"] = "low"
    for key in ("temperature", "top_p"):
        v = ov.get(key, fm.get(key))
        if v not in (None, ""):
            try:
                out_fm[key] = float(v)
            except Exception:
                pass
    steps = ov.get("steps", fm.get("steps"))
    if steps not in (None, ""):
        try:
            out_fm["steps"] = int(steps)
        except Exception:
            pass
    if isinstance(ov.get("options"), dict) and ov["options"]:
        out_fm["options"] = ov["options"]

    out_fm["permission"] = perm

    lines = ["---"]
    for k, v in out_fm.items():
        if isinstance(v, (dict, list)):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {json.dumps(str(v), ensure_ascii=False)}")
    lines.append("---")

    base_file = "_base_mission.md" if mission else "_base.md"
    try:
        base = (AGENTS_DIR / base_file).read_text(encoding="utf-8")
    except Exception:
        base = ""
    base = (base.replace("AGENT_NAME", name)
                .replace("AGENT_SUBDIR", subdir)
                .replace("BASE_BRANCH", base_branch)
                .replace("SLUG", slug)
                .replace("TEAMMATES", ", ".join(n for n in roster if n != name) or "(none)"))
    return "\n".join(lines) + "\n\n" + base.strip() + "\n\n" + persona["body"] + "\n"


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
    # Auto-approve the native `skill` tool so progressive-disclosure skill
    # loads don't each raise a permission prompt. Only fills in the default
    # if the base config hasn't already taken a position on `permission.skill`.
    perm = cfg.get("permission")
    if isinstance(perm, dict):
        perm.setdefault("skill", {"*": "allow"})
    elif "permission" not in cfg:
        cfg["permission"] = {"skill": {"*": "allow"}}
    return cfg
