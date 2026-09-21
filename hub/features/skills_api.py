"""Save what a finished ask taught the hub as a reusable skill, with the user approving every byte.

  POST /api/missions/{id}/skill-draft     one model call drafts a SKILL.md from the ask -> {name, markdown, exists, existing}
  POST /api/skills/save                   {name, markdown, overwrite?}  writes hub/agent_knowledge/skills/<name>/SKILL.md

Nothing is written by the draft. A skill that already exists is never replaced silently: the save is refused (409) with the current text
until the caller repeats it with overwrite=true, which the UI only offers after showing the user both versions.
"""
from __future__ import annotations

import re
from pathlib import Path

from aiohttp import web

from .. import agent_knowledge
from . import missions as M

routes = web.RouteTableDef()
NAME_RX = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")

_SYSTEM = (
    "You write ONE reusable skill file for an AI agent hub from a finished piece of work. Output only the file: YAML frontmatter with `name` "
    "(kebab-case, 2-4 words) and `description` (one sentence that starts with what it is for and says when to use it), then a body of at most "
    "25 short lines: the rules, limits, formats and steps that made THIS work succeed and would apply to the NEXT similar task. Generalise: no "
    "names of this project's files, no one-off facts. No preamble, no code fences around the file.")


def _skill_dir(name: str) -> Path:
    return agent_knowledge.SKILLS_DIR / name


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
