"""Who is allowed to make the Hub *do* something.

The network boundary (Tailscale) decides which devices can reach the Hub. It
cannot decide whether *you* meant to send a request: any page open in a browser
on an allowed device can POST to the Hub, and the browser will attach the
session automatically. That is the cross-site request forgery case, and it is
what this module closes.

The rule, applied only to state-changing methods:

* Same-origin browser requests are allowed. Origin (or, when absent, Referer)
  must match a host the Hub actually answers on.
* Non-browser clients — scripts, shortcuts, home automation — send no Origin.
  They are allowed only with an integration token (see integration_tokens.py).
  A missing Origin is *not* on its own a pass: that is exactly what a forged
  form post can look like.
* GET/HEAD/OPTIONS are never blocked here. Any GET with a side effect is a bug
  to fix in the route, not something to paper over with a token.

Everything is deliberately fail-closed on the method, and fail-open on reads, so
a mistake here degrades to "a button stops working", never to "the Hub is open".
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from aiohttp import web

from .config import logger

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Paths that must stay reachable without a token or an Origin, because they are
# how a client bootstraps in the first place, or are read-only by nature.
EXEMPT_PREFIXES = ("/api/onboarding/",)


def _allowed_hostnames() -> set[str]:
    """Hostnames the Hub legitimately answers on — no ports.

    The port is pinned separately by the same-origin comparison below, so this
    only has to answer "is this a name for this machine?". That is what stops a
    DNS-rebinding host from counting as same-origin just because the browser
    sent matching Origin and Host headers.
    """
    hosts = {"localhost", "127.0.0.1", "::1"}
    for extra in (os.environ.get("HUB_PUBLIC_HOST", ""), _tailscale_host()):
        if extra:
            hosts.add(extra.lower())
    return hosts


def _hostname(netloc: str) -> str:
    """Strip the port and any IPv6 brackets from a netloc."""
    netloc = netloc.lower()
    if netloc.startswith("["):
        return netloc[1:netloc.index("]")] if "]" in netloc else netloc
    return netloc.rsplit(":", 1)[0] if ":" in netloc else netloc


def _tailscale_host() -> str:
    """This machine's tailnet DNS name, when Tailscale is up. Cached after the
    first lookup: it does not change while the Hub is running."""
    # Only a successful lookup is cached: Tailscale may start after the Hub,
    # and caching the failure would leave phone access refused until a restart.
    if not _tailscale_host.value:
        try:
            import json
            from .config import TAILSCALE_EXE
            from .runtime import run
            result = run([TAILSCALE_EXE, "status", "--json"], 10)
            if result.returncode == 0:
                name = json.loads(result.stdout).get("Self", {}).get("DNSName", "")
                _tailscale_host.value = name.rstrip(".").lower()
        except Exception:
            pass
    return _tailscale_host.value


_tailscale_host.value = ""


def _origin_ok(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    if origin == "null":
        # What a sandboxed iframe or a file:// page sends. Never trust it.
        return False
    source = origin or request.headers.get("Referer")
    if not source:
        return False
    netloc = urlsplit(source).netloc.lower()
    if not netloc:
        return False
    # Same origin: the page's host:port must be the host:port it is calling.
    # This pins the port without the Hub having to know which one it is serving.
    if netloc != (request.host or "").lower():
        return False
    # ... and that host must be a name for this machine, so a rebound DNS name
    # cannot satisfy the comparison above just by matching itself.
    return _hostname(netloc) in _allowed_hostnames()


def ensure_ws_origin(request: web.Request) -> None:
    """Refuse a cross-origin WebSocket upgrade.

    A WS upgrade is a GET, so the middleware below lets it through — but a
    hostile page can still open a socket to the Hub and the browser will send
    the request. Browsers always set Origin on a WS handshake, so an Origin that
    is not ours is decisive. A missing Origin means a non-browser client, which
    is the same trust position as any other local tool.
    """
    if request.headers.get("Origin") and not _origin_ok(request):
        logger.warning("Refused WebSocket upgrade on %s from origin %s",
                       request.path, request.headers.get("Origin"))
        raise web.HTTPForbidden(text="Cross-origin WebSocket connections are not accepted.")


@web.middleware
async def middleware(request: web.Request, handler):
    if request.method in SAFE_METHODS or request.path.startswith(EXEMPT_PREFIXES):
        return await handler(request)

    if _origin_ok(request):
        return await handler(request)

    from .integration_tokens import identify
    token = identify(request)
    if token is not None:
        request["integration"] = token
        return await handler(request)

    origin = request.headers.get("Origin") or request.headers.get("Referer") or "(none)"
    logger.warning("Refused %s %s: origin %s is not this Hub and no integration token was sent",
                   request.method, request.path, origin)
    raise web.HTTPForbidden(
        text="This request did not come from Agent Hub itself. Open the Hub and try again, "
             "or use an integration token for automation.")


def install(app: web.Application) -> None:
    app.middlewares.append(middleware)
