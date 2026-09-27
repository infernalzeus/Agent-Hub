"""Provider API keys, held by the Hub and handed to OpenCode in its environment.

Why this module exists at all, because it is not obvious:

The Hub runs every mission and every project runtime with `XDG_DATA_HOME` pointed
at a **per-worktree** data folder, so two projects never share one "current
project" row. OpenCode reads its credential file from
`$XDG_DATA_HOME/opencode/auth.json` and — verified by experiment, not assumed —
falls back to **nothing** when it is absent:

    XDG_DATA_HOME=<empty dir>   with a key in the user's real home  ->  0 credentials

So `opencode auth login` typed in a terminal writes a key into the user's default
data home, which **no mission ever reads**. The instruction to log in that way was
therefore advice that could not work. That is the bug this module closes.

The fix uses OpenCode's own hook: `Auth.all()` honours `OPENCODE_AUTH_CONTENT`,
and returns it in place of reading any file. So the keys live here, in the Hub's
own state folder, and are injected into every OpenCode process:

  * one place to add a key — a field in the Hub, not a terminal command;
  * nothing is written inside a worktree, where a secret would be caught by
    `git diff` and merged into the user's project on APPLY;
  * a key the user *did* add with `auth login` still counts, because their own
    auth file is merged in underneath.

The key is write-only over HTTP: it can be stored, verified and forgotten, and
never read back. Verification asks the provider directly, so a typo is caught at
the moment of typing rather than five minutes into a mission.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()

FILE = STATE / "provider_keys.json"     # gitignored state; never inside a project

# provider id -> (label, where to create a key, how to verify it)
# The verify entry is (url, header-name or "" for a query key, prefix).
PROVIDERS = {
    "google": ("Google AI Studio", "https://aistudio.google.com/apikey",
               ("https://generativelanguage.googleapis.com/v1beta/models?key={key}", "", "")),
    "groq": ("Groq", "https://console.groq.com/keys",
             ("https://api.groq.com/openai/v1/models", "Authorization", "Bearer ")),
    "openrouter": ("OpenRouter", "https://openrouter.ai/keys",
                   ("https://openrouter.ai/api/v1/key", "Authorization", "Bearer ")),
    "mistral": ("Mistral", "https://console.mistral.ai/api-keys",
                ("https://api.mistral.ai/v1/models", "Authorization", "Bearer ")),
    "anthropic": ("Anthropic", "https://console.anthropic.com/settings/keys",
                  ("https://api.anthropic.com/v1/models", "x-api-key", "")),
    "openai": ("OpenAI", "https://platform.openai.com/api-keys",
               ("https://api.openai.com/v1/models", "Authorization", "Bearer ")),
}


# ── storage ───────────────────────────────────────────────────────────────────
def _read() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(FILE.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FILE)
    try:                                  # best effort on Windows; owner-only on POSIX
        os.chmod(FILE, 0o600)
    except OSError:
        pass


def store(provider: str, key: str) -> None:
    data = _read()
    # `type` and `key` are opencode's shape and are passed through untouched; the
    # two extra fields are the hub's own and are what the panel shows back.
    data[provider] = {"type": "api", "key": key,
                      "checked": int(time.time()), "tail": key[-4:]}
    _write(data)
    logger.info("llm_keys: stored a credential for %s", provider)   # never the key


def forget(provider: str) -> bool:
    data = _read()
    if provider not in data:
        return False
    data.pop(provider)
    _write(data)
    logger.info("llm_keys: forgot the credential for %s", provider)
    return True


def _own_auth_file() -> dict:
    """Whatever the user added themselves with `opencode auth login`.

    Merged in underneath the Hub's own keys so an existing terminal login is not
    silently ignored — it simply starts working everywhere instead of nowhere.
    """
    home = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    try:
        data = json.loads((home / "opencode" / "auth.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def merged() -> dict:
    """Every credential OpenCode should see. Hub keys win: they were typed last.

    `checked` and `tail` are stripped: they are the panel's, not opencode's, and
    an unexpected field in an auth entry is not worth the risk.
    """
    out = _own_auth_file()
    for pid, entry in _read().items():
        out[pid] = {k: v for k, v in entry.items() if k in ("type", "key")}
    return out


def providers() -> list[str]:
    """Which providers have a credential — names only, never keys."""
    return sorted(merged())


def inject(env: dict) -> dict:
    """Give an OpenCode subprocess its credentials. Call this wherever the Hub
    sets XDG_DATA_HOME, because that is exactly where the file lookup breaks."""
    creds = merged()
    if creds:
        env["OPENCODE_AUTH_CONTENT"] = json.dumps(creds)
    return env


# ── verification ──────────────────────────────────────────────────────────────
def verify(provider: str, key: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Ask the provider whether this key works. (ok, message for the user)."""
    meta = PROVIDERS.get(provider)
    if not meta:
        return False, "unknown provider"
    url, header, prefix = meta[2]
    req = urllib.request.Request(url.format(key=urllib.parse.quote(key)))
    if header:
        req.add_header(header, prefix + key)
    if provider == "anthropic":
        req.add_header("anthropic-version", "2023-06-01")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "the provider rejected this key"
        if exc.code == 429:
            return True, "the key works, but you are rate limited right now"
        return False, f"the provider answered {exc.code}"
    except Exception as exc:
        return False, f"could not reach the provider: {exc}"
    n = 0
    try:
        data = json.loads(body)
        n = len(data.get("data") or data.get("models") or [])
    except Exception:
        pass
    return True, f"key works · {n} models visible" if n else "key works"


# ── HTTP ──────────────────────────────────────────────────────────────────────
# Deliberately NOT under /api/onboarding/, which request_security.py exempts from
# the CSRF check so a browser can bootstrap. Writing a credential is not a
# bootstrap read, so it goes through the guard like every other write.
@routes.get("/api/llm/keys")
async def api_list(request: web.Request) -> web.Response:
    """Which providers are configured, and where to get a key. No keys returned."""
    have = set(providers())
    mine = _read()
    def shown(pid: str) -> dict:
        """What a connected provider shows: that it is connected, and just enough
        of the key to tell which one it is. Never the key."""
        entry = mine.get(pid) or {}
        tail = entry.get("tail")
        return {"hint": ("•" * 8 + tail) if tail else "",
                "checked": entry.get("checked")}

    return web.json_response({
        "providers": [
            dict(id=pid, label=label, create=create,
                 configured=pid in have, in_hub=pid in mine, **shown(pid))
            for pid, (label, create, _v) in PROVIDERS.items()
        ],
        "other": sorted(have - set(PROVIDERS)),
    })


@routes.post("/api/llm/keys")
async def api_save(request: web.Request) -> web.Response:
    body = await request.json()
    provider = str(body.get("provider") or "").strip().lower()
    key = str(body.get("key") or "").strip()
    if provider not in PROVIDERS:
        raise web.HTTPBadRequest(text="unknown provider")
    if len(key) < 8:
        raise web.HTTPBadRequest(text="that does not look like an API key")
    ok, msg = await asyncio.to_thread(verify, provider, key)
    if not ok:
        # Not stored. A key that cannot be verified is worse than no key: it
        # turns a clear "no provider" into a mission that fails mid-run.
        return web.json_response({"ok": False, "msg": msg}, status=400)
    store(provider, key)
    return web.json_response({"ok": True, "msg": msg, "providers": providers()})


@routes.delete("/api/llm/keys/{provider}")
async def api_forget(request: web.Request) -> web.Response:
    gone = forget(request.match_info["provider"])
    return web.json_response({"ok": gone, "providers": providers()})
