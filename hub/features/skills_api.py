"""Save what a finished ask taught the hub as a reusable skill, with the user approving every byte.

  POST /api/missions/{id}/skill-draft     one model call drafts a SKILL.md from the ask -> {name, markdown, exists, existing}
  POST /api/skills/save                   {name, markdown, overwrite?}  writes the skill into the USER's skills dir
  GET  /api/skills                        the installed library plus the catalogue of presets still available
  POST /api/skills/install/{id}           clone one catalogue preset at its pinned tag
  DELETE /api/skills/{name}               remove one of the user's own skills

Nothing is written by the draft. A skill that already exists is never replaced silently: the save is refused (409) with the current text
until the caller repeats it with overwrite=true, which the UI only offers after showing the user both versions.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path

from aiohttp import web

from .. import agent_knowledge, runtime as RT
from ..config import logger
from . import missions as M

routes = web.RouteTableDef()
NAME_RX = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")

_SYSTEM = (
    "You write ONE reusable skill file for an AI agent hub from a finished piece of work. Output only the file: YAML frontmatter with `name` "
    "(kebab-case, 2-4 words) and `description` (one sentence that starts with what it is for and says when to use it), then a body of at most "
    "25 short lines: the rules, limits, formats and steps that made THIS work succeed and would apply to the NEXT similar task. Generalise: no "
    "names of this project's files, no one-off facts. No preamble, no code fences around the file.")


def _unfence(md: str) -> str:
    """Strip a ``` fence a model wrapped the file in, despite being told not to."""
    t = md.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
    if t.rstrip().endswith("```"):
        t = t.rstrip()[:-3]
    return t.strip()


def _skill_dir(name: str) -> Path:
    # Always the user's root. A skill you saved is yours, not part of the build.
    return agent_knowledge.USER_SKILLS_DIR / name


def _parse(md: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", md.strip(), re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"\'')
    return {"fm": fm, "body": m.group(2)}


async def draft_text(m: "M.Mission") -> str:
    steps = "\n".join(f"- {s.get('agent')}: {(s.get('brief') or '')[:200]} => {(s.get('summary') or '')[:200]}" for s in (m.plan or []))
    files = ", ".join(f.get("path", "") for f in (m.changed_files or [])[:8])
    user = f"THE ASK:\n{m.brief[:600]}\n\nHOW IT WAS DONE (agents and their results):\n{steps or '(single agent)'}\n\nFILES PRODUCED: {files or '(none)'}\n"
    chain = [x for x in agent_knowledge.model_chain(m.model or None, None) if x.startswith("ollama/")]
    if not chain:
        raise web.HTTPBadRequest(text="no Ollama model available to draft a skill")
    await M._ensure_ollama()
    last = None
    for mdl in chain[:2]:
        try:
            return await M._direct_chat(mdl, _SYSTEM, user, temperature=0.3, timeout=120)
        except Exception as exc:
            last = exc
    raise web.HTTPBadRequest(text=f"the model could not draft it: {str(last)[:100]}")


_SYSTEM_PLAIN = (
    "You write ONE reusable skill file for an AI agent hub from a plain description. Output only the file: YAML frontmatter with `name` "
    "(kebab-case, 2-4 words), `description` (one sentence saying what it is for and when to use it), and a `metadata:` block containing "
    "`topic:` set to exactly one of: {topics}. Then a body of at most 25 short lines: the rules, limits, formats and steps an agent should "
    "follow. Generalise - no one-off facts, no names of a particular project's files. No preamble, no code fences.")


@routes.post("/api/skills/draft")
async def api_draft_plain(request: web.Request) -> web.Response:
    """Draft a skill from a description. No mission involved.

    Writing a skill is a thing on its own - it borrows an agent to phrase the
    file, which is not the same as needing a mission, a working copy or a diff to
    approve. Sending someone to the mission board to write one made a one-step
    job look like a project.
    """
    try:
        b = await request.json()
    except Exception:
        b = {}
    desc = str(b.get("description") or "").strip()
    if not desc:
        raise web.HTTPBadRequest(text="say what the skill should cover")
    topics = sorted({s.get("topic") for s in agent_knowledge.skills_overview() if s.get("topic")} - {"Other"})
    system = _SYSTEM_PLAIN.format(topics=", ".join(topics))
    chain = [x for x in agent_knowledge.model_chain(None, None) if x.startswith("ollama/")]
    if not chain:
        raise web.HTTPBadRequest(text="no Ollama model available to draft a skill")
    await M._ensure_ollama()
    last = None
    for mdl in chain[:2]:
        try:
            md = (await M._direct_chat(mdl, system, f"The skill should cover: {desc}",
                                       temperature=0.3, timeout=180)).strip()
            md = _unfence(md)
            parsed = _parse(md)
            name = re.sub(r"[^a-z0-9-]+", "-", str(parsed.get("fm", {}).get("name", "")).lower()).strip("-")[:48]
            if not NAME_RX.match(name or ""):
                name = ""
            return web.json_response({"name": name, "markdown": md, "model": mdl,
                                      "ok": bool(parsed and name)})
        except Exception as exc:
            last = exc
            logger.info("skill draft on %s failed: %s", mdl, exc)
    raise web.HTTPBadRequest(text=f"the model could not draft it: {str(last)[:120]}")


@routes.post("/api/missions/{id}/skill-draft")
async def api_draft(request: web.Request) -> web.Response:
    m = M.S.m.get(request.match_info["id"])
    if not m:
        raise web.HTTPNotFound(text="no such ask")
    md = (await draft_text(m)).strip()
    md = re.sub(r"^```[a-z]*\n|\n```$", "", md).strip()
    parsed = _parse(md)
    name = re.sub(r"[^a-z0-9-]+", "-", str(parsed.get("fm", {}).get("name", "")).lower()).strip("-")[:48]
    if not name or not NAME_RX.match(name):
        name = "skill-from-" + m.id
    existing = None
    f = _skill_dir(name) / "SKILL.md"
    if f.is_file():
        existing = f.read_text(encoding="utf-8")
    return web.json_response({"name": name, "markdown": md, "exists": existing is not None, "existing": existing})


@routes.post("/api/skills/save")
async def api_save(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:
        b = {}
    name, md = str(b.get("name", "")).strip(), str(b.get("markdown", "")).strip()
    if not NAME_RX.match(name):
        raise web.HTTPBadRequest(text="name: lower-case letters, digits and dashes, 2-49 characters")
    parsed = _parse(md)
    if not parsed or not parsed["fm"].get("name") or not parsed["fm"].get("description"):
        raise web.HTTPBadRequest(text="the skill needs frontmatter with a name and a description")
    if len(md) > 20000:
        raise web.HTTPBadRequest(text="skill too long (20 000 characters max)")
    d = _skill_dir(name)
    f = d / "SKILL.md"
    if f.exists() and not b.get("overwrite"):
        return web.json_response({"error": "exists", "existing": f.read_text(encoding="utf-8")}, status=409)
    d.mkdir(parents=True, exist_ok=True)
    f.write_text(md + "\n", encoding="utf-8")
    return web.json_response({"ok": True, "path": str(f)})


# ── the catalogue: third-party skills a user can pull on demand ────────────────────────────────────────────────────

CATALOGUE = Path(agent_knowledge.__file__).parent / "skills_catalogue.json"


def catalogue() -> list[dict]:
    """Presets from skills_catalogue.json, each marked with whether it is installed.

    Read fresh every call: a preset added to the JSON should appear without a restart.
    """
    try:
        entries = json.loads(CATALOGUE.read_text(encoding="utf-8-sig")).get("skills", [])
    except (OSError, ValueError) as exc:
        logger.warning("skill catalogue unreadable: %s", exc)
        return []
    have = {s["name"] for s in agent_knowledge.list_skills()}
    out = []
    for e in entries:
        if not isinstance(e, dict) or not e.get("id") or not e.get("repo"):
            continue
        out.append({**e, "installed": e.get("name", e["id"]) in have})
    return out


def _tool_missing(entry: dict) -> str | None:
    """Which prerequisite is absent, phrased for someone who did not read the docs."""
    for tool in entry.get("needs", []):
        if tool == "ffmpeg":
            managed = RT.STATE / "runtimes/media/bin/ffmpeg.exe"
            if managed.is_file() or shutil.which("ffmpeg"):
                continue
            return "ffmpeg. Set up Media Vault, or put ffmpeg on PATH."
        exe = "npx" if tool == "node" else tool
        if not shutil.which(exe):
            return {"git": "Git.", "node": "Node.js."}.get(tool, tool + ".")
    return None


@routes.get("/api/skills")
async def api_skills(request: web.Request) -> web.Response:
    """The whole picture: what is in the library, and what can still be added."""
    return web.json_response({"library": agent_knowledge.skills_overview(),
                              "catalogue": catalogue(),
                              "user_dir": str(agent_knowledge.USER_SKILLS_DIR)})


@routes.post("/api/skills/install/{id}")
async def api_install(request: web.Request) -> web.Response:
    """Clone one catalogue entry at its pinned ref into the user's skills folder.

    A tag, never a branch: `main` is whatever someone pushed this morning, and a
    skill that changes under the user is not a skill they can rely on.
    """
    wanted = request.match_info["id"]
    entry = next((e for e in catalogue() if e["id"] == wanted), None)
    if entry is None:
        raise web.HTTPNotFound(text=f"no catalogue entry {wanted!r}")
    missing = _tool_missing(entry)
    if missing:
        raise web.HTTPBadRequest(text="This skill needs " + missing)

    name = entry.get("name", entry["id"])
    if not NAME_RX.match(name):
        raise web.HTTPBadRequest(text=f"catalogue entry {wanted!r} has an unusable skill name")

    def _clone() -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as tmp:
            run = RT.run(["git", "clone", "--depth", "1", "--branch", entry["ref"],
                          entry["repo"], tmp + "/src"], 900)
            if run.returncode:
                return False, (run.stderr or run.stdout)[-3000:]
            source = Path(tmp) / "src" / entry.get("path", ".")
            if not (source / "SKILL.md").is_file():
                return False, f"{entry['repo']} {entry['ref']} has no {entry.get('path')}/SKILL.md. The upstream layout changed."
            target = agent_knowledge.INSTALLED_SKILLS_DIR / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target)
            return True, str(target)

    ok, detail = await asyncio.to_thread(_clone)
    if not ok:
        raise web.HTTPBadGateway(text=detail)
    try:
        from ..agent_knowledge.skills_sync import publish_skills
        await asyncio.to_thread(publish_skills)
    except Exception as exc:                                  # publishing is best effort
        logger.warning("skill %s installed but not published: %s", name, exc)
    logger.info("installed catalogue skill %s (%s) at %s", name, entry["ref"], detail)
    return web.json_response({"ok": True, "name": name, "ref": entry["ref"], "path": detail})


@routes.delete("/api/skills/{name}")
async def api_remove(request: web.Request) -> web.Response:
    """Remove a skill from the user's folder. Shipped skills are not ours to delete."""
    name = request.match_info["name"]
    if not NAME_RX.match(name):
        raise web.HTTPBadRequest(text="bad skill name")
    target = next((d / name for d in (agent_knowledge.USER_SKILLS_DIR,
                                      agent_knowledge.INSTALLED_SKILLS_DIR)
                   if d != agent_knowledge.SKILLS_DIR and (d / name).is_dir()), None)
    if target is None:
        raise web.HTTPNotFound(text=f"{name} is not one of your skills; shipped skills cannot be removed")
    shutil.rmtree(target)
    try:
        from ..agent_knowledge.skills_sync import publish_skills
        await asyncio.to_thread(publish_skills)
    except Exception:
        pass
    return web.json_response({"ok": True, "name": name})
