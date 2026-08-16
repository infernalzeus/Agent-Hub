---
name: rest-api-design
description: Language-agnostic REST/API design — resource shapes, status codes, versioning, error responses
keywords: api, rest, http, endpoint, json, webhook, graphql
---

# REST / API design (language-agnostic)

- Resources are nouns, actions are HTTP verbs — `POST /sessions`, not
  `POST /createSession`. If an operation doesn't fit CRUD cleanly, model it
  as a sub-resource (`POST /sessions/{id}/stop`) rather than inventing a
  verb-shaped endpoint.
- Status codes carry real meaning, don't default everything to 200 with an
  `{"ok": false}` body — 400 for a bad request the client should fix, 401
  vs 403 for "who are you" vs "you can't do that," 404 for a real missing
  resource, 409 for a conflict (someone else changed it first), 5xx only
  for the server's own fault.
- Error responses need a machine-readable shape (`{"error": "code",
  "message": "..."}`), not just a plain-text string — a client integrating
  against the API needs to branch on the error, not regex the message.
- Idempotency: `PUT`/`DELETE` should be safe to retry (same result on a
  second call); `POST` for creation usually isn't — if a client needs to
  safely retry a POST (e.g. after a timeout with unknown outcome), that
  needs an explicit idempotency key, not an assumption it's safe.
- Pagination on any list endpoint that could grow unbounded — cursor-based
  over offset-based when the underlying data can be inserted/deleted
  concurrently (offset pagination silently skips/duplicates rows under
  concurrent writes).
- Version the contract, not just the code — a breaking change to a
  response shape needs a new version path/header, not a silent change that
  breaks every existing client on deploy.
- Webhooks: sign the payload (HMAC) so the receiver can verify authenticity,
  and make delivery idempotent on the receiving end (a webhook WILL be
  retried and WILL arrive more than once eventually).
