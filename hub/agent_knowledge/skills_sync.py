"""Publish the skill library into the dirs OpenCode (and Claude Code) already
scan, so EVERY agent session on this machine — Hub-launched or not — gets the
skills through the native `skill` tool with real progressive disclosure. Agent
Hub does not invent a skill mechanism here; it only keeps those global dirs in
sync with what lives under `agent_knowledge/`.

Three sources feed the publish:
  1. `skills/`            — hand-written standard Agent Skills (one
                            <name>/SKILL.md dir each).
  2. `skills_vendor/`     — verbatim Apache-2.0 skills copied from
                            github.com/anthropics/skills (see PROVENANCE.md).
                            Committed, not modified; tagged origin 'vendored'.
  3. `skills_generated/`  — SKILL.md dirs compiled on each run from LLM-wiki
                            pages that opt in with `skill: true` frontmatter
                            (see compile_wiki_skills). The wiki page stays the
                            editable source; the SKILL.md is a build artifact.

On a name clash: hand-written > vendored > wiki-compiled.

Publish targets (created if absent, only ever touching dirs we marked):
  - ~/.config/opencode/skills/<name>/   (OpenCode global — all origins)
  - ~/.claude/skills/<name>/            (Claude Code personal — hand-written +
                                         wiki only; Claude Code ships most of
                                         the vendored ones as plugins already)

Everything here is best-effort: a missing home dir, a permission error, or an
unparseable wiki page is logged and skipped, never raised — a sync failure must
never block hub startup.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from ..config import logger
from . import SKILLS_DIR, WIKI_ROOT, list_skills

GENERATED_DIR = Path(__file__).parent / "skills_generated"
VENDOR_DIR = Path(__file__).parent / "skills_vendor"

# (target dir, origins allowed in it). Vendored skills go to OpenCode only —
# Claude Code already ships equivalents as plugins and canvas-design alone is
# ~5 MB of bundled fonts.
PUBLISH_TARGETS = [
    (Path.home() / ".config" / "opencode" / "skills",
     {"hand-written", "vendored", "wiki-concept"}),
    (Path.home() / ".claude" / "skills",
     {"hand-written", "wiki-concept"}),
]

# Files at/above this size are hashed by (path, size) instead of by content,
# so a skill that bundles fonts/images doesn't make every sync re-read MBs.
_DIGEST_FULL_MAX = 131072

# Dropped into every dir we publish so a later sync only ever overwrites or
# removes skills THIS module created — a hand-made skill the user put in one of
# the target dirs is left untouched. Second line is the source content hash,
# used to skip unchanged skills on the next run.
MARKER = ".agent-hub-managed"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# LLM-wiki pages compile to a skill only when their frontmatter says so
# explicitly (`skill: true`). Optional `skill_description:` overrides the
# auto-extracted description.
WIKI_SKILL_DIRS = ("concepts", "entities", "analyses")


# ── wiki → SKILL.md ─────────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm: dict = {}
    for line in text[3:end].strip("\n").splitlines():
        if ":" in line and not line[:1].isspace():
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, text[end + 4:].lstrip("\n")


def _first_paragraph(body: str) -> str:
    para: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if not s:
            if para:
                break
            continue
        para.append(s)
    return " ".join(para)


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("true", "yes", "1", "on")


def compile_wiki_skills() -> int:
    """(Re)build GENERATED_DIR from every opted-in LLM-wiki page. Returns the
    count written. GENERATED_DIR is fully rebuilt each call so un-opting a page
    (or deleting it) removes its compiled skill on the next hub start."""
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR, ignore_errors=True)
    if not WIKI_ROOT.is_dir():
        return 0
    written = 0
    for sub in WIKI_SKILL_DIRS:
        d = WIKI_ROOT / sub
        if not d.is_dir():
            continue
        for page in sorted(d.glob("*.md")):
            try:
                fm, body = _split_frontmatter(page.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("skills_sync: cannot read wiki page %s: %s", page, exc)
                continue
            if not _truthy(fm.get("skill", "")):
                continue
            # Obsidian wikilinks don't resolve outside the vault — flatten
            # [[target|label]] -> label and [[target]] -> target so both the
            # extracted description and the skill body read cleanly.
            body = re.sub(r"\[\[[^\]|]*\|([^\]]+)\]\]", r"\1", body)
            body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)
            name = page.stem.lower()
            if not NAME_RE.match(name):
                logger.warning("skills_sync: wiki page %s has a non-conforming skill name %r — skipped",
                               page.name, name)
                continue
            desc = (fm.get("skill_description") or _first_paragraph(body)
                    or f"LLM-wiki knowledge on {name.replace('-', ' ')}.").strip()
            desc = re.sub(r"\s+", " ", desc)
            if len(desc) > 1024:
                desc = desc[:1000].rsplit(" ", 1)[0] + " …"
            suffix = f" (Compiled from the LLM-wiki '{sub}' page {page.name}.)"
            if len(desc) + len(suffix) <= 1024:
                desc += suffix

            # Obsidian wikilinks don't resolve outside the vault — flatten
            # [[target|label]] -> label and [[target]] -> target so the skill
            # body reads cleanly to an agent.
            body = re.sub(r"\[\[[^\]|]*\|([^\]]+)\]\]", r"\1", body)
            body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)

            out_dir = GENERATED_DIR / name
            out_dir.mkdir(parents=True, exist_ok=True)
            # Always double-quote the description: a bare scalar containing
            # ": " (colon-space) is invalid YAML and strict loaders fall back
            # to the H1 title. Escape backslashes and quotes for the quoted form.
            desc_yaml = '"' + desc.replace("\\", "\\\\").replace('"', '\\"') + '"'
            front = (
                "---\n"
                f"name: {name}\n"
                f"description: {desc_yaml}\n"
                "metadata:\n"
                "  origin: wiki-concept\n"
                f"  source_page: {sub}/{page.name}\n"
                "---\n"
            )
            (out_dir / "SKILL.md").write_text(front + "\n" + body.rstrip() + "\n", encoding="utf-8")
            written += 1
    if written:
        logger.info("skills_sync: compiled %d skill(s) from LLM-wiki pages", written)
    return written


# ── publish ────────────────────────────────────────────────────────────────

def _dir_digest(root: Path, *, skip: set[str] = frozenset()) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in skip):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(b"\0")
        try:
            size = f.stat().st_size
            if size >= _DIGEST_FULL_MAX:
                h.update(f"<size:{size}>".encode())
            else:
                h.update(f.read_bytes())
        except Exception:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


# source root -> origin tag, in precedence order (earlier wins a name clash).
_SOURCE_ROOTS = [
    (lambda: SKILLS_DIR, "hand-written"),
    (lambda: VENDOR_DIR, "vendored"),
    (lambda: GENERATED_DIR, "wiki-concept"),
]


def _source_skill_dirs() -> list[tuple[Path, str]]:
    """Every source skill dir as (path, origin), deduped by name with
    hand-written > vendored > wiki-compiled precedence."""
    by_name: dict[str, tuple[Path, str]] = {}
    for get_root, origin in _SOURCE_ROOTS:
        root = get_root()
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file() and d.name not in by_name:
                by_name[d.name] = (d, origin)
    return list(by_name.values())


def publish_skills() -> dict:
    """Mirror every source skill dir into each publish target. Idempotent:
    unchanged skills are skipped via the hash in their MARKER file; skills we
    previously published that no longer exist in source are removed; anything
    in a target dir without our MARKER is left alone."""
    sources = _source_skill_dirs()  # [(path, origin), ...]
    summary: list[dict] = []

    for target, allowed in PUBLISH_TARGETS:
        want = {p.name: (p, origin) for p, origin in sources if origin in allowed}
        written = skipped = removed = 0
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("skills_sync: cannot create %s: %s — skipping this target", target, exc)
            summary.append({"target": str(target), "error": str(exc)})
            continue

        # prune skills we used to manage that are gone from source (or no
        # longer allowed in this target)
        for child in target.iterdir():
            if child.is_dir() and (child / MARKER).is_file() and child.name not in want:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1

        for name, (src, _origin) in want.items():
            digest = _dir_digest(src, skip={MARKER})
            dst = target / name
            marker = dst / MARKER
            if dst.exists():
                if not marker.is_file():
                    logger.warning("skills_sync: %s exists and is not Hub-managed — left untouched", dst)
                    continue
                try:
                    if marker.read_text(encoding="utf-8").strip().splitlines()[-1:] == [digest]:
                        skipped += 1
                        continue
                except Exception:
                    pass
                shutil.rmtree(dst, ignore_errors=True)
            try:
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(MARKER))
                marker.write_text(f"agent-hub\n{digest}\n", encoding="utf-8")
                written += 1
            except Exception as exc:
                logger.warning("skills_sync: failed to publish %s -> %s: %s", name, dst, exc)

        summary.append({"target": str(target), "written": written,
                        "skipped": skipped, "removed": removed})

    logger.info("skills_sync: publish summary %s", summary)
    return {"skills": len(sources), "targets": summary}


def sync_all() -> dict:
    """compile wiki skills, then publish the whole library. Safe to call at
    every hub start; best-effort, never raises."""
    try:
        compile_wiki_skills()
    except Exception as exc:
        logger.warning("skills_sync: wiki compile failed: %s", exc)
    try:
        result = publish_skills()
    except Exception as exc:
        logger.warning("skills_sync: publish failed: %s", exc)
        return {"error": str(exc)}
    # a quick, cheap re-list so the log shows what a session will actually see
    try:
        names = [s["name"] for s in list_skills()]
        logger.info("skills_sync: %d skill(s) live in the library: %s",
                    len(names), ", ".join(names))
    except Exception:
        pass
    return result
