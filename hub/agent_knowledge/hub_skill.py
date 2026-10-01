"""Write the "what the Hub can do" skill from the Hub's own routing table.

An agent working in a mission is on the same machine as the Hub but knows nothing
about it. The obvious fix is a hand-written SKILL.md listing the endpoints - and
that file is wrong the first time somebody adds, renames or removes a route, with
nothing to catch it. Worse, being wrong is silent: the agent simply calls
something that is not there and reports that the Hub refused.

So the skill is generated on every start from `capabilities.inventory()`, which is
itself read off the live router. A route that does not exist cannot appear here,
and a new route in an allowed family appears without anybody remembering to write
it down.

It is published like any other skill, so OpenCode finds it by its own progressive
disclosure rather than the Hub injecting a wall of text into every brief.
"""
from __future__ import annotations

from pathlib import Path

from ..config import logger

NAME = "agent-hub-api"
# Its own root, not skills_generated/: that one is rebuilt from the wiki on
# every start and anything else in it would be deleted.
DIR = Path(__file__).parent / "skills_hub" / NAME

_DESCRIPTION = (
    "Use the Agent Hub running on this machine: download or upload video, list "
    "and dispatch missions, start a fronted app, read the project graph, replay a "
    "recorded desktop routine. Use when a task mentions the hub, an app it fronts "
    "(Movie Clipper, File Browser), YouTube downloads or uploads, or when work "
    "needs something already running on this PC rather than something to build."
)


def _body(endpoints: "list[dict]", base: str, token_env: str) -> str:
    gated = [e for e in endpoints if e["consequential"]]
    rows = "\n".join(
        f"| `{e['method']}` | `{e['path']}` | {(e['what'] or '').replace('|', '/')[:90]} |"
        for e in endpoints)
    gated_rows = "\n".join(f"- `{e['method']} {e['path']}`" for e in gated) or "- (none)"
    return f"""# Talking to Agent Hub

Agent Hub is already running on this machine at `{base}`. You do not start it and
you do not need to build any of this - ask it.

## How to call it

Every request needs the Hub's integration token, which is in the environment as
`{token_env}`. Without it the Hub refuses the call as a forged request, which is
the correct behaviour and not something to work around.

```bash
curl -s -X POST "{base}/api/youtube-dl/start" \\
  -H "X-Agent-Hub-Token: ${token_env}" \\
  -H "Content-Type: application/json" \\
  -d '{{"url": "https://...", "mode": "audio"}}'
```

## Stop before these

These change things that are hard to take back - they publish, merge into a real
repository, delete work, or move the mouse on a real desktop. **Do not call one
to see what happens.** If the brief asks for one, do the work up to it, then say
plainly what remains and let a person press the button.

{gated_rows}

## What the Hub offers

| Method | Path | What it is for |
|--------|------|----------------|
{rows}

## When there is no endpoint for it

Some programs have no interface but their own window. The Hub cannot be asked to
drive one from here - that needs a routine recorded once by the person, under PC
control, which they then replay as an automation step. If a task needs one and it
does not exist, stop and say which window needs recording. Do not try to drive
the desktop yourself.

*Generated from the Hub's own routes - if an endpoint is not listed here, it does
not exist on this build.*
"""


def write(endpoints: "list[dict]", base: str, token_env: str = "AGENTHUB_TOKEN") -> Path:
    """(Re)write the skill. Returns its directory."""
    DIR.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        f"name: {NAME}\n"
        f'description: "{_DESCRIPTION}"\n'
        "metadata:\n"
        "  origin: generated\n"
        "  source: hub routing table\n"
        "---\n\n" + _body(endpoints, base, token_env)
    )
    (DIR / "SKILL.md").write_text(text, encoding="utf-8")
    logger.info("hub_skill: wrote %s with %d endpoints", NAME, len(endpoints))
    return DIR


def refresh(app) -> None:
    """Best-effort regeneration at startup; never breaks the boot."""
    try:
        from ..features import capabilities as C
        from ..config import HOST, PORT
        write(C.inventory(app), f"http://{HOST or '127.0.0.1'}:{PORT}")
    except Exception as exc:
        logger.warning("hub_skill: not regenerated: %s", exc)
