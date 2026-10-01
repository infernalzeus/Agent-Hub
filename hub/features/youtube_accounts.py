"""The YouTube channels this install can upload to, listed and edited in Settings.

A channel used to be a hand-edited entry in hub/local_settings.py, so adding one
meant editing Python and restarting. The tag also had to match a folder name by
hand, and nothing told you when it didn't.

An account here IS its credential folder:

    youtube/credentials/<tag>/
        client_secrets.json     the Google OAuth client you provide
        youtube_token.pickle    written after you authorize, on first upload

Nothing lists accounts except the disk, so a list cannot drift from what the
uploader will actually find, and a fresh install shows an empty list rather than
somebody else's channel tag. The folder sits outside the release payload and the
installer never deletes it, so an update leaves your channels signed in.

hub/local_settings.py is still read for anyone who configured channels the old
way — its entries appear in the list and keep working, at their own paths.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from ..config import logger, YT_CRED_DIR

SECRETS = "client_secrets.json"
TOKEN = "youtube_token.pickle"

# A tag names a folder, so it has to be a plain name and nothing else: no
# separators, no parent hops, no device names. Anything else is refused rather
# than sanitised, because silently renaming someone's channel tag would hide
# which account an upload went to.
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$")
_RESERVED = {"con", "prn", "aux", "nul", "clock$"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def bad_tag(tag: str) -> str:
    """Why this tag is unusable as a folder name, or "" if it is fine."""
    tag = (tag or "").strip()
    if not tag:
        return "a channel needs a name"
    if not _TAG.match(tag):
        return "use letters, numbers, spaces, dots, dashes and underscores (max 40)"
    if tag != tag.strip(" ."):
        return "cannot start or end with a space or a dot"
    if tag.split(".")[0].lower() in _RESERVED:
        return f"{tag} is a reserved name on Windows"
    return ""


def _dir(tag: str) -> Path:
    """The folder a tag means. Trims first, so looking a channel up finds the
    same folder that adding it created rather than one with a stray space."""
    why = bad_tag(tag)
    if why:
        raise ValueError(why)
    return Path(YT_CRED_DIR) / tag.strip()


def _legacy() -> dict:
    """Channels configured the old way, in hub/local_settings.py."""
    try:
        from .. import local_settings                      # type: ignore[attr-defined]
        got = getattr(local_settings, "YOUTUBE_ACCOUNTS", {})
        return got if isinstance(got, dict) else {}
    except Exception:
        return {}


def paths(tag: str) -> dict | None:
    """Where this channel's credentials are, or None if it has none.

    The folder wins over local_settings, so moving an old channel into the
    standard layout needs no edit to local_settings to take effect.
    """
    try:
        d = _dir(tag)
    except ValueError:
        return None
    if (d / SECRETS).is_file():
        return {"secrets_file": str(d / SECRETS), "token_file": str(d / TOKEN)}
    old = _legacy().get(tag)
    if isinstance(old, dict) and old.get("secrets_file"):
        return {"secrets_file": str(old["secrets_file"]), "token_file": str(old.get("token_file") or "")}
    return None


def accounts() -> list[dict]:
    """Every channel this install can upload to, whichever way it was added."""
    out: dict[str, dict] = {}
    root = Path(YT_CRED_DIR)
    if root.is_dir():
        for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if d.is_dir() and (d / SECRETS).is_file() and not bad_tag(d.name):
                out[d.name] = {"tag": d.name, "authorized": (d / TOKEN).is_file(), "where": "folder"}
    for tag, cfg in _legacy().items():
        if tag in out or bad_tag(tag):
            continue
        secrets = str((cfg or {}).get("secrets_file") or "")
        if secrets and Path(secrets).is_file():
            token = str((cfg or {}).get("token_file") or "")
            out[tag] = {"tag": tag, "authorized": bool(token) and Path(token).is_file(),
                        "where": "local_settings.py"}
    return [out[k] for k in sorted(out, key=str.lower)]



def _check_secrets(text: str) -> dict:
    """Confirm this really is a Google OAuth *desktop* client, before storing it.

    Google hands out several JSON files that look alike. A service-account key or
    an API key saved here would fail only later, mid-upload, with an error from
    deep inside the Google client - so it is rejected now, by name.
    """
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f"that file is not valid JSON ({exc.__class__.__name__})")
    if not isinstance(data, dict):
        raise ValueError("that file is not a Google client_secrets.json")
    if data.get("type") == "service_account":
        raise ValueError("that is a service-account key; YouTube uploads need an OAuth "
                         "client ID of type Desktop app")
    body = data.get("installed") or data.get("web")
    if not isinstance(body, dict) or not body.get("client_id"):
        raise ValueError("that is not a client_secrets.json - download the OAuth client ID "
                         "(Desktop app) from Google Cloud Console")
    if "web" in data and "installed" not in data:
        raise ValueError("that is a Web application client; create the OAuth client as "
                         "type Desktop app instead")
    return data


def add(tag: str, secrets_text: str) -> dict:
    """Register a channel by storing the OAuth client you downloaded from Google."""
    why = bad_tag(tag)
    if why:
        raise ValueError(why)
    tag = tag.strip()
    _check_secrets(secrets_text)
    d = _dir(tag)
    if (d / SECRETS).is_file():
        raise ValueError(f"{tag} already has credentials - remove it first to replace them")
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secrets_text)
    os.replace(tmp, d / SECRETS)
    try:                                  # best effort on Windows; owner-only on POSIX
        os.chmod(d / SECRETS, 0o600)
    except OSError:
        pass
    logger.info("youtube: added the channel %s", tag)       # never the secret
    return {"tag": tag, "authorized": False, "where": "folder"}


def forget(tag: str) -> bool:
    """Remove a channel from this PC, credentials and sign-in together.

    Nothing is uploaded or revoked at Google's end - this only forgets locally,
    which is what the button says.
    """
    try:
        d = _dir(tag)
    except ValueError:
        return False
    if not d.is_dir():
        return False
    shutil.rmtree(d, ignore_errors=True)
    logger.info("youtube: forgot the channel %s", tag)
    return not d.exists()
