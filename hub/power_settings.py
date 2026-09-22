"""The power-menu PIN: stored hashed, read at use, changeable without a restart.

Three things this fixes about the old `HUB_POWER_PIN` constant:

* It was read once at import, so changing it meant restarting the Hub.
* It lived in a settings file as plain text.
* "No PIN" and "PIN not configured yet" were the same state, so a config
  mistake silently removed the gate instead of announcing it.

An empty PIN remains a supported choice — some setups are on a trusted network
and want one-tap power control — but it is now an explicit saved decision
("off"), not an accident, and the UI says which state it is in.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

from .runtime import STATE, write_json

FILE = STATE / "power_settings.json"
_ROUNDS = 240_000                    # PBKDF2-HMAC-SHA256; a PIN is short, so cost matters
_MAX_ATTEMPTS = 8
_LOCKOUT_S = 60.0

_attempts: dict[str, float] = {"count": 0, "until": 0.0}


def _read() -> dict:
    try:
        data = json.loads(Path(FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _derive(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), _ROUNDS).hex()


def _legacy_pin() -> str:
    """The pre-settings value from config, used until a choice is saved here."""
    try:
        from .config import HUB_POWER_PIN
        return str(HUB_POWER_PIN or "")
    except Exception:
        return ""


def configured() -> bool:
    """Is a PIN required right now?"""
    data = _read()
    if data.get("mode") == "off":
        return False                 # an explicit "off" beats any legacy value
    if data.get("hash"):
        return True
    return bool(_legacy_pin())


def status() -> dict:
    """Safe to send to a browser: says whether a PIN exists, never what it is."""
    data = _read()
    return {"configured": configured(),
            "source": "saved" if (data.get("hash") or data.get("mode") == "off") else
                      ("legacy" if _legacy_pin() else "none"),
            "locked_out": _locked_out()}


def _locked_out() -> bool:
    return time.time() < _attempts["until"]


def verify(pin: str) -> bool:
    """Check a PIN. Throttled, so a 4-digit PIN cannot simply be enumerated."""
    if not configured():
        return True
    if _locked_out():
        return False
    data = _read()
    if data.get("hash"):
        ok = hmac.compare_digest(data["hash"], _derive(str(pin or ""), data["salt"]))
    else:
        ok = hmac.compare_digest(_legacy_pin(), str(pin or ""))
    if ok:
        _attempts.update(count=0, until=0.0)
        return True
    _attempts["count"] += 1
    if _attempts["count"] >= _MAX_ATTEMPTS:
        _attempts.update(count=0, until=time.time() + _LOCKOUT_S)
    return False


def set_pin(new_pin: str, confirm: str, current: str) -> tuple[bool, str]:
    new_pin, confirm = str(new_pin or ""), str(confirm or "")
    if configured() and not verify(current):
        return False, "Current PIN is not correct."
    if not new_pin:
        # Refusing this is the point: an empty box is a typo, not a decision.
        return False, "Enter a PIN, or use Remove PIN to turn the gate off."
    if new_pin != confirm:
        return False, "The two PINs do not match."
    if len(new_pin) < 4:
        return False, "Use at least 4 digits."
    salt = secrets.token_bytes(16).hex()
    write_json(FILE, {"mode": "on", "salt": salt, "hash": _derive(new_pin, salt),
                      "updated": time.time()})
    return True, "PIN updated."


def remove_pin(current: str) -> tuple[bool, str]:
    if configured() and not verify(current):
        return False, "Current PIN is not correct."
    # Recorded as an explicit choice so a legacy value cannot quietly come back.
    write_json(FILE, {"mode": "off", "updated": time.time()})
    return True, "PIN removed. Anyone who can reach the Hub can use its power controls."
