"""Command phrases as sentence templates, in a file a person can read and edit.

    (open|show|go to) [the] (missions|asks) [page]
    ask [the] hub [to|for] {arg}
    ... (status|what's waiting|anything needs me) ...

    (a|b)   one of these words or phrases
    [x]     optional
    {name}  whatever is said there, kept under that name
    ...     any number of other words

The syntax is the useful subset of Home Assistant's hassil, written here so the
hub has no new dependency. A template matches the whole sentence; `...` is how
you say "and anything else".

Templates live in `hub/commands.json` (shipped) and, optionally,
`commands_user.json` in the state folder (yours; never overwritten by an
update). Both use the same shape:

    {"open_missions": {"action": ["open_page", {"page": "missions"}],
                       "templates": ["(open|show) [the] missions"]}}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import logger
from .runtime import STATE

SHIPPED = Path(__file__).with_name("commands.json")
USER = STATE / "commands_user.json"


class TemplateError(ValueError):
    pass


def _tokens(s: str) -> "list[str]":
    return re.findall(r"\.\.\.|[()\[\]|]|\{[a-z_]+\}|[^\s()\[\]|{}]+", s.lower())


def _alt(toks: "list[str]", i: int, close: str) -> "tuple[str, int]":
    """Parse alternatives up to `close`; returns (regex, next index)."""
    branches, cur = [], []
    while i < len(toks):
        t = toks[i]
        if t == close:
            branches.append(cur)
            return "(?:" + "|".join(_seq(b) for b in branches) + ")", i + 1
        if t == "|":
            branches.append(cur)
            cur = []
            i += 1
        elif t in ("(", "["):
            inner, i = _alt(toks, i + 1, ")" if t == "(" else "]")
            cur.append(inner if t == "(" else f"(?:{inner})?")
        elif t in (")", "]"):
            raise TemplateError(f"unbalanced {t!r}")
        else:
            cur.append(_atom(t))
            i += 1
    raise TemplateError(f"missing {close!r}")


def _atom(t: str) -> str:
    if t == "...":
        return r"(?:.*?)"
    m = re.fullmatch(r"\{([a-z_]+)\}", t)
    if m:
        return rf"(?P<{m.group(1)}>.+?)"
    return rf"(?<![\w'])" + re.escape(t) + rf"(?![\w'])"


def _seq(parts: "list[str]") -> str:
    # Words carry their own boundaries, so the gap between parts may be empty.
    return r"\s*".join(parts)


def compile_template(template: str) -> str:
    """Template -> regex source (matched against a lower-cased, punctuation-free sentence)."""
    toks = _tokens(template)
    if not toks:
        raise TemplateError("empty template")
    toks = toks + ["\0"]
    body, _ = _alt(toks, 0, "\0")
    return rf"^\s*{body}\s*$"


def load_commands() -> "list[dict]":
    """Every command: {"id", "action": (id, args), "rx": [regex, ...]}. A bad template is skipped, not fatal."""
    merged: "dict[str, dict]" = {}
    for path in (SHIPPED, USER):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.warning("templates: %s is not readable: %s", path.name, exc)
            continue
        for cid, spec in (data or {}).items():
            if isinstance(spec, dict) and spec.get("templates"):
                base = merged.setdefault(cid, {"action": spec.get("action"), "templates": []})
                if spec.get("action"):
                    base["action"] = spec["action"]
                base["templates"] = list(base["templates"]) + list(spec["templates"])
    out = []
    for cid, spec in merged.items():
        rx = []
        for t in spec["templates"]:
            try:
                rx.append(compile_template(t))
            except TemplateError as exc:
                logger.warning("templates: %s: %r skipped (%s)", cid, t, exc)
        act = spec.get("action") or [None, None]
        if rx and act[0]:
            out.append({"id": cid, "action": (act[0], act[1] if len(act) > 1 else None), "rx": rx})
    return out
