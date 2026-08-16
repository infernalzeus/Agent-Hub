---
name: obsidian-wiki-graph-context
description: Working with an Obsidian-based LLM Wiki — markdown knowledge graph as compiled context, not RAG
keywords: obsidian, wiki, markdown, knowledge-graph, wikilink, canvas, second-brain
---

# Obsidian / LLM Wiki graph context

For sessions touching a vault that follows the LLM Wiki pattern (frontmatter'd
markdown pages linked with `[[wikilinks]]`, a top-level `index.md` catalog,
an append-only `log.md`):

- This is **compiled knowledge, not RAG** — the agent writes and curates the
  pages up front, so a query-time read is a lookup over already-synthesized
  claims, not a fresh retrieval-and-summarize pass. Don't re-derive something
  a page already states; read the page and cite it (`([[source-slug]])`).
- `[[wikilinks]]` are the graph's real edges — Obsidian's own graph view (and
  any tool built on top of it) walks these, not folder structure or naming
  similarity. A relationship that matters belongs in the text as a link, not
  just implied by two pages mentioning similar words.
- Respect the vault's own schema doc (usually a `CLAUDE.md` at the vault
  root) for frontmatter fields, page-type conventions, and linking rules
  before writing anything — vaults vary in what they require (e.g. a
  `project_slug` field that ties a page to an on-disk project).
- Never edit files under a vault's `raw/` (or equivalent immutable-source)
  folder — treat it like a git history: read-only, the origin of truth for
  everything else.
- A `.canvas` file (Obsidian Canvas) is JSON: `nodes` (text/file/group,
  each with `x`/`y`/`width`/`height`) and `edges` (`fromNode`/`toNode`,
  optional `label`). Useful for an architecture/relationship diagram a plain
  linked-page graph can't express as clearly — validate as JSON before
  considering it done, Obsidian gives no useful error on malformed canvases.
