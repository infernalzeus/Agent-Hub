"""Project status graph (Phase 3/4): one node per PROJECT, never per file.

GET /api/graph returns the discovered project list with each one's sync
state (see hub/agent_knowledge/status.py for the state model). The UI layer
(hub/ui.py) renders this as a D3 force graph; clicking a node opens a
git-desktop-style detail panel for that project — the per-file diff never
becomes graph nodes of its own.
"""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from ..agent_knowledge import projects as pj
from ..agent_knowledge import status
from .opencode import WORKROOT, resolve_workroot_child

routes = web.RouteTableDef()


@routes.get("/api/graph")
async def graph(request: web.Request) -> web.Response:
    nodes = await status.compute_graph(WORKROOT)
    links = status.compute_project_links(nodes)
    return web.json_response({"nodes": nodes, "project_links": links})


def _project_and_copy(slug: str, copy_folder: str | None):
    """Resolve a slug (+ optional explicit copy folder) to (project, copy_path)."""
    project = pj.find_project(slug)
    if project is None:
        raise web.HTTPNotFound(text=f"no such project: {slug}")
    if project["readonly"]:
        return project, None
    if copy_folder:
        copy = resolve_workroot_child(copy_folder)
        if copy is None:
            raise web.HTTPNotFound(text=f"no such copy: {copy_folder}")
        return project, copy
    copies = status._find_copies_for(Path(project["path"]), WORKROOT)
    return project, (copies[0] if copies else None)


@routes.get("/api/graph/{slug}")
async def graph_detail(request: web.Request) -> web.Response:
    """Git-desktop-style detail for one project: its state + changed file list."""
    slug = request.match_info["slug"]
    project, copy = _project_and_copy(slug, request.query.get("copy"))
    if copy is None:
        return web.json_response({**project, "changed_files": []})
    files = await status.list_changed_files(Path(project["path"]), copy)
    return web.json_response({**project, "copy_folder": copy.name, "changed_files": files})


@routes.get("/api/graph/{slug}/diff")
async def graph_file_diff(request: web.Request) -> web.Response:
    rel_path = request.query.get("path")
    if not rel_path:
        raise web.HTTPBadRequest(text="?path=<file> is required")
    slug = request.match_info["slug"]
    project, copy = _project_and_copy(slug, request.query.get("copy"))
    if copy is None:
        raise web.HTTPNotFound(text="no working copy for this project")
    diff_text = await status.file_diff(Path(project["path"]), copy, rel_path)
    return web.Response(text=diff_text, content_type="text/plain", charset="utf-8")


@routes.post("/api/graph/{slug}/push")
async def graph_push(request: web.Request) -> web.Response:
    """Apply reviewed A/M changes from the copy back onto the source.
    Never touches deletions; refuses a file whose source moved on unless
    force is set. See agent_knowledge.status.push_changes for the full model."""
    slug = request.match_info["slug"]
    project = pj.find_project(slug)
    if project is None:
        raise web.HTTPNotFound(text=f"no such project: {slug}")
    if project["readonly"]:
        raise web.HTTPForbidden(text="this project is read-only")
    try:
        body = await request.json()
    except Exception:
        body = {}
    copy_folder = body.get("copy") or request.query.get("copy")
    _, copy = _project_and_copy(slug, copy_folder)
    if copy is None:
        raise web.HTTPNotFound(text="no working copy for this project")
    result = await status.push_changes(
        Path(project["path"]), copy,
        files=body.get("files"), force=bool(body.get("force")),
    )
    return web.json_response(result)
