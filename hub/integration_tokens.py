"""Named, revocable tokens so automation can use the Hub without a browser.

A script, a phone shortcut or a home-automation rule has no Origin header, so
the CSRF check in request_security.py cannot tell it apart from a forged form
post. A token is the thing that distinguishes them: something the caller *has*,
which a hostile web page cannot obtain.

Only the hash is stored. The secret is shown once, at creation, and cannot be
recovered — losing it means issuing a new one, which is the point.

Scope is a list of path prefixes. A token for "/api/youtube-dl/" cannot trigger
a power action, so a token pasted into a script is not a master key.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from aiohttp import web

from .runtime import STATE, write_json

FILE = STATE / "integration_tokens.json"
PREFIX = "ahi_"          # so a leaked secret is recognisable in logs and history


def _load() -> list[dict]:
    try:
        data = json.loads(Path(FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create(name: str, scopes: list[str]) -> tuple[dict, str]:
    """Return (record, secret). The secret is never stored and never shown again."""
    secret = PREFIX + secrets.token_urlsafe(32)
    record = {
        "id": secrets.token_hex(8),
        "name": (name or "unnamed").strip()[:60],
        "hash": _hash(secret),
        "scopes": [s for s in (scopes or []) if isinstance(s, str) and s.startswith("/")] or ["/api/"],
        "created": time.time(),
        "last_used": None,
    }
    tokens = _load()
    tokens.append(record)
    write_json(FILE, tokens)
    return {k: v for k, v in record.items() if k != "hash"}, secret


def revoke(token_id: str) -> bool:
    tokens = _load()
    kept = [t for t in tokens if t.get("id") != token_id]
    if len(kept) == len(tokens):
        return False
    write_json(FILE, kept)
    return True


def listing() -> list[dict]:
    """Metadata only — the hash never leaves this module."""
    return [{k: v for k, v in t.items() if k != "hash"} for t in _load()]


def identify(request: web.Request) -> dict | None:
    """The token authorising this request, or None.

    None means "not authorised", never "authorised by default": every caller
    treats it as a refusal.
    """
    header = request.headers.get("Authorization", "")
    secret = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not secret:
        secret = request.headers.get("X-Agent-Hub-Token", "").strip()
    if not secret:
        return None
    digest = _hash(secret)
    tokens = _load()
    for token in tokens:
        # compare_digest so a wrong token cannot be narrowed down by timing.
        if not hmac.compare_digest(token.get("hash", ""), digest):
            continue
        if not any(request.path.startswith(scope) for scope in token.get("scopes", [])):
            return None                          # real token, wrong scope
        token["last_used"] = time.time()
        try:
            write_json(FILE, tokens)
        except OSError:
            pass                                 # last_used is metadata, not authorisation
        return {k: v for k, v in token.items() if k != "hash"}
    return None
