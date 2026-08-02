"""Reverse-proxy helpers (HTTP + WebSocket), shared by every proxied app."""
from __future__ import annotations

import asyncio

import aiohttp
from aiohttp import web, WSMsgType

from .config import logger


# ── Reverse proxy ────────────────────────────────────────────────────────────

_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}
# Content-Length is intentionally NOT stripped: video needs a real declared length
# (not chunked transfer-encoding) for Safari to treat it as seekable media at all.


async def _proxy_http(request: web.Request, target_base: str, target_path: str) -> web.StreamResponse:
    url = target_base + target_path
    if request.query_string:
        url += "?" + request.query_string
    body = await request.read()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP and k.lower() != "host"}

    # Streamed rather than buffered: a video request can be tens/hundreds of MB,
    # and reading the whole thing into memory before forwarding a single byte
    # is what made playback stall — bytes now flow through as they arrive.
    # No total timeout: aiohttp's default (300s) would kill a large-file range
    # request mid-stream just because it's a multi-GB movie, not because
    # anything's actually stuck — sock_read still catches genuinely dead connections.
    # sock_read must clear the SLOWEST legitimate synchronous backend response,
    # not just video chunk cadence: Movie Clipper's /prepare cuts a 4K clip inline
    # and sends zero bytes until it's done (its own cap is 240s), and the
    # Ollama-backed /suggest-* calls can think for a minute. At 30s the proxy
    # severed those mid-work and the UI showed a bare "prepare failed". 300s sits
    # just above the backend's own 240s cap so that cap stays authoritative while
    # a truly dead connection is still reaped (just less eagerly).
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            request.method, url, headers=headers, data=body or None, allow_redirects=False,
        ) as resp:
            out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _HOP_BY_HOP}
            stream_resp = web.StreamResponse(status=resp.status, headers=out_headers)
            await stream_resp.prepare(request)
            async for chunk in resp.content.iter_chunked(65536):
                await stream_resp.write(chunk)
            await stream_resp.write_eof()
            return stream_resp


async def _proxy_ws(request: web.Request, target_base: str, target_path: str) -> web.WebSocketResponse:
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(request)

    ws_url = "ws" + target_base[len("http"):] + target_path
    session = aiohttp.ClientSession()
    try:
        ws_client = await session.ws_connect(ws_url)
    except Exception as exc:
        logger.warning("proxy ws connect failed: %s", exc)
        await session.close()
        await ws_server.close()
        return ws_server

    async def _pump_backend_to_client() -> None:
        try:
            async for msg in ws_client:
                if msg.type == WSMsgType.TEXT:
                    await ws_server.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await ws_server.send_bytes(msg.data)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR, WSMsgType.CLOSED):
                    break
        except Exception:
            pass

    pump_task = asyncio.create_task(_pump_backend_to_client())

    try:
        async for msg in ws_server:
            if msg.type == WSMsgType.TEXT:
                await ws_client.send_str(msg.data)
            elif msg.type == WSMsgType.BINARY:
                await ws_client.send_bytes(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break
    finally:
        pump_task.cancel()
        await ws_client.close()
        await session.close()

    return ws_server

