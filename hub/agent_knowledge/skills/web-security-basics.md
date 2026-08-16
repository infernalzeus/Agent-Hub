---
name: web-security-basics
description: Common web-app security pitfalls — auth, injection, secrets, CORS — for any project handling users/data
keywords: security, auth, authentication, oauth, csrf, xss, cors, secrets, injection
---

# Web app security basics

- Never build SQL/shell/HTML by string-concatenating untrusted input —
  parameterized queries (SQL), `subprocess` argument lists not shell
  strings (shell injection), and templating with auto-escaping on (XSS) —
  each of these is a specific, well-known class of bug with a specific,
  well-known fix; don't hand-roll escaping.
- Secrets (API keys, DB passwords, OAuth client secrets) never go in
  tracked source — env vars or a gitignored local-settings file, and check
  `.gitignore` actually covers them BEFORE the first commit that could
  include them, not after.
- Password storage: a real password-hashing function (bcrypt/argon2/scrypt)
  — never plain SHA-256/MD5 alone (too fast, brute-forceable) and never
  plaintext. If you're touching this at all, use an established library,
  don't write the hashing yourself.
- Auth vs. authorization are different bugs — "is this a valid logged-in
  user" (401) is necessary but not sufficient; every endpoint touching a
  specific user's data needs its own "does THIS user own THIS resource"
  check (403), or user A can read/edit user B's data by just changing an
  ID in the request.
- CORS: `Access-Control-Allow-Origin: *` on anything that reads
  authenticated/cookie-based state is a real hole — scope it to the exact
  origins that should be allowed, not a wildcard "so it stops erroring."
- CSRF: state-changing requests (POST/PUT/DELETE) driven by cookies need a
  CSRF token or `SameSite` cookie protection — a form/fetch on an unrelated
  site can otherwise trigger an action as the logged-in user.
- Rate-limit anything that checks a secret (login, password reset, API
  key) — without it, brute-forcing is just a matter of time and requests.
