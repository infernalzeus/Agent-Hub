"""Create and revoke the tokens that let automation use the Hub.

Scripts, phone shortcuts and home-automation rules send no Origin header, so the
CSRF check cannot tell them from a forged request. A token is what distinguishes
them. These routes are the only way to mint one, and they are themselves
same-origin-only: a token cannot be used to create another token.
"""
from __future__ import annotations

from aiohttp import web

from .. import integration_tokens as IT

routes = web.RouteTableDef()


async def _json(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _browser_only(request: web.Request) -> None:
    """Minting and revoking are browser-only, even with a valid token.

    Otherwise a narrowly scoped token could widen itself by issuing a new one,
    and revoking would become a way to lock the owner out.
    """
    if request.get("integration") is not None:
        raise web.HTTPForbidden(text="Manage integrations from the Hub in a browser.")


@routes.get("/api/integrations")
async def list_tokens(request: web.Request) -> web.Response:
    """Names, scopes and last-used times. Never the secrets — they are not stored."""
    return web.json_response({"tokens": IT.listing()})


@routes.post("/api/integrations")
async def create_token(request: web.Request) -> web.Response:
    _browser_only(request)
    data = await _json(request)
    name = str(data.get("name") or "").strip()
    if not name:
        raise web.HTTPBadRequest(text="Give the integration a name you will recognise later.")
    scopes = data.get("scopes") or ["/api/"]
    if not isinstance(scopes, list):
        raise web.HTTPBadRequest(text="scopes must be a list of path prefixes")
    record, secret = IT.create(name, scopes)
    # The only time the secret exists outside the caller's hands.
    return web.json_response({"token": record, "secret": secret,
                              "note": "Copy this now — it is stored hashed and cannot be shown again."})


@routes.delete("/api/integrations/{token_id}")
async def revoke_token(request: web.Request) -> web.Response:
    _browser_only(request)
    if not IT.revoke(request.match_info["token_id"]):
        raise web.HTTPNotFound(text="no such integration")
    return web.json_response({"ok": True})
