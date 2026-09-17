"""Project status graph: one node per PROJECT, never per file.

GET /api/graph returns the discovered project list with each one's state (see
hub/agent_knowledge/status.py). Each project's agent work now lives in a git
worktree on branch `agent/<slug>` (hub/features/opencode.py); "changed files"
and diffs come from `git diff <base>...HEAD` in that worktree, and the panel's
former "push" action is now "merge the agent branch".
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from .. import agent_knowledge
from ..agent_knowledge import projects as pj
from ..agent_knowledge import status
from .opencode import WORKTREES, worktree_for

routes = web.RouteTableDef()


@routes.get("/api/graph")
async def graph(request: web.Request) -> web.Response:
    nodes = await status.compute_graph(WORKTREES)
    links = status.compute_project_links(nodes)
    return web.json_response({"nodes": nodes, "project_links": links})


@routes.get("/api/graph/skills")
async def graph_skills(request: web.Request) -> web.Response:
    lib = agent_knowledge.skills_overview()
    payload = {"skills": lib, "count": len(lib),
               "targets": ["~/.config/opencode/skills", "~/.claude/skills"]}
    slug = request.query.get("project")
    if slug:
        project = pj.find_project(slug)
        if project is not None:
            matched = agent_knowledge.relevant_skills(project["name"], Path(project["path"]))
            payload["project"] = slug
            payload["relevant"] = [m["name"] for m in matched]
    return web.json_response(payload)


def _project_and_worktree(graph_slug: str):
    """(project dict, worktree Path | None) for a graph node slug."""
    project = pj.find_project(graph_slug)
    if project is None:
        raise web.HTTPNotFound(text=f"no such project: {graph_slug}")
    if project["readonly"]:
        return project, None
    wt = worktree_for(project["path"])
    return project, (wt if wt.exists() else None)


@routes.get("/api/graph/{slug}")
async def graph_detail(request: web.Request) -> web.Response:
    project, wt = _project_and_worktree(request.match_info["slug"])
    if wt is None:
        return web.json_response({**project, "changed_files": []})
    files = await status.worktree_changed_files(wt)
    return web.json_response({**project, "copy_folder": wt.name, "changed_files": files})


@routes.get("/api/graph/{slug}/diff")
async def graph_file_diff(request: web.Request) -> web.Response:
    rel_path = request.query.get("path")
    if not rel_path:
        raise web.HTTPBadRequest(text="?path=<file> is required")
    project, wt = _project_and_worktree(request.match_info["slug"])
    if wt is None:
        raise web.HTTPNotFound(text="no worktree for this project")
    return web.Response(text=await status.worktree_file_diff(wt, rel_path),
                        content_type="text/plain", charset="utf-8")


@routes.post("/api/graph/{slug}/push")
async def graph_push(request: web.Request) -> web.Response:
    """Merge the project's `agent/<slug>` branch into its base branch."""
    project, wt = _project_and_worktree(request.match_info["slug"])
    if project["readonly"]:
        raise web.HTTPForbidden(text="this project is read-only")
    if wt is None:
        raise web.HTTPNotFound(text="no worktree for this project")
    result = await status.merge_agent_branch(Path(project["path"]), wt)
    return web.json_response(result, status=200 if result.get("ok") else 409)
