# Vendored skills — provenance

These skill directories are **verbatim copies** of the Apache-2.0 skills published in
Anthropic's public skills repository. They are checked into Agent Hub (not gitignored)
so `skills_sync.py` can publish them alongside the hand-written and wiki-compiled skills.

| | |
|---|---|
| Upstream | https://github.com/anthropics/skills |
| Commit | `3b3fad96af16a10759d930941b4520ba0c40edae` |
| Fetched | 2026-08-31 |
| License | **Apache-2.0** for every skill here (repo README + each skill's `LICENSE.txt`). `doc-coauthoring` shipped no per-skill `LICENSE.txt` upstream — a short note file was added in its place; it is Apache-2.0 per the repo README. |

## Included (15 — all Apache-2.0)

`academy-guide`, `algorithmic-art`, `brand-guidelines`, `canvas-design`, `claude-api`,
`discernment-nudge`, `doc-coauthoring`, `frontend-design`, `internal-comms`,
`mcp-builder`, `skill-creator`, `slack-gif-creator`, `theme-factory`,
`web-artifacts-builder`, `webapp-testing`

## Deliberately NOT included

`docx`, `pdf`, `pptx`, `xlsx` — these are **source-available, not open source**
("© 2025 Anthropic, PBC. All rights reserved."). They may not be redistributed, so they
are not vendored here. Anthropic ships them inside Claude Code directly.

## Refreshing

```bash
# from a scratch dir
curl -sL https://github.com/anthropics/skills/archive/refs/heads/main.tar.gz | tar -xz
# copy each of the 15 dirs above over hub/agent_knowledge/skills_vendor/<name>/
# then update the Commit + Fetched rows above and .upstream-sha
```

Nothing here is modified from upstream. `skills_sync.py` tags these `origin: vendored`
by the directory they live in — it does **not** edit the SKILL.md files.
