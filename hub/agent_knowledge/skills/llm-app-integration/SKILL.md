---
name: llm-app-integration
description: "Calling an LLM from application code reliably — structured output, retries, context-window budgeting, streaming, cost and latency. Relevant when the task involves: llm, openai, ollama, anthropic, prompt, completion, embedding, rag, agent, tool-call, token."
metadata:
  keywords: "llm, openai, ollama, anthropic, prompt, completion, embedding, rag, agent, tokens, structured-output, litellm"
  origin: hand-written
---

# LLM app integration

- **Never trust the model to return valid JSON.** Ask for it, but wrap the
  parse: local models and even cloud ones truncate mid-object. Salvage what
  parsed, fall back to a locally-derived default for cosmetic fields, and
  raise only when a *structural* field is unrecoverable — see the
  `llm-json-salvage` skill for the recovery recipe. Prefer a provider's
  native JSON/schema mode when it has one.
- **Set the context window explicitly.** With Ollama, `options.num_ctx`
  defaults small — a long prompt is silently truncated and the model answers
  from a cut-off input with no error. Set it per call to match the prompt.
- **Chunk large asks.** A model told "return 30 items" degrades after a
  dozen. Loop N smaller requests and merge; it's slower but actually
  complete.
- **Retry only the transient failures.** Timeouts, 429s, 5xx, connection
  resets → exponential backoff with a cap and a max attempt count. A 400 /
  context-length / content-filter error will fail identically every time —
  don't retry it, surface it.
- **Make prompts deterministic to test.** Pin `temperature: 0` (or low) for
  extraction/classification; keep the prompt in a file or constant, not
  inlined and mutated. Log the exact prompt+response on failure so a bad
  output is reproducible.
- **Treat the model as an untrusted, slow, paid function.** Validate its
  output before acting on it (especially tool-call arguments, file paths,
  SQL, shell). Cache identical calls. Budget tokens — a 32k-context call on
  every request adds real latency and cost; send only what the task needs.
- **Stream for UX, buffer for logic.** Stream tokens to a UI so it feels
  responsive; but parse/act on the *complete* response, never on partial
  streamed text.
- **Keep provider choice swappable.** Route through one thin adapter (or a
  lib like LiteLLM) so local ↔ cloud is a config change, not a rewrite —
  useful for a bandwidth- or cost-sensitive setup that defaults local and
  escalates to cloud only when needed.
- **Fail closed on safety-critical paths.** If the model is deciding
  something irreversible, require a confirmation step or a deterministic
  guard rail; don't let a hallucinated field trigger a delete/spend/send.

## See also

- **`claude-api`** (vendored from Anthropic) — the authoritative Claude/Anthropic
  SDK reference: model ids, pricing, params, streaming, tool use, MCP, caching,
  token counting, migration. Reach for it for anything Anthropic-specific; this
  skill is the provider-agnostic layer above it.
- **`mcp-builder`** (vendored) — when the "external service" you're integrating
  should be exposed to the model as an MCP server rather than called inline.
