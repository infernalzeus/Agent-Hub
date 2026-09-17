---
name: ci-cd-github-actions
description: "Structuring GitHub Actions workflows that are fast, secure, and don't lie — caching, matrix, least-privilege tokens, required checks, safe deploys. Relevant when the task involves: ci, cd, github-actions, workflow, pipeline, deploy, release, yaml-workflow, runner."
metadata:
  keywords: "ci, cd, github-actions, workflow, pipeline, deploy, release, runner, gha"
  origin: hand-written
---

# CI/CD with GitHub Actions

- **Trigger deliberately.** `on: [push, pull_request]` double-runs every PR
  branch. Usually want `push` on `main` + `pull_request` (any branch), and
  `paths:` filters so a docs-only change doesn't run the full test matrix.
- **Cache the dependency store, keyed on the lockfile.** `actions/setup-*`
  has built-in caching (`cache: pip`/`npm`); otherwise `actions/cache` with
  `key: deps-${{ hashFiles('**/lock') }}`. A cache keyed on nothing (or on
  the branch) is a cache that never hits or never invalidates.
- **Fail the build on real failures.** No `|| true`, no `continue-on-error`
  on the test step, no `-i` flags that swallow lint errors. A green check
  that ran nothing is worse than a red one.
- **Least privilege for `GITHUB_TOKEN`.** Set `permissions:` explicitly at
  the workflow or job level (`contents: read` by default; add `packages:
  write` etc. only where needed). The default token is broad.
- **Never `pull_request_target` + checkout PR head + run its code.** That
  runs fork code with repo secrets — a classic exfiltration hole. Use
  `pull_request` (no secrets on forks) for anything that executes PR code.
- **Pin third-party actions** to a full commit SHA, not a moving tag —
  `uses: foo/bar@<sha>`. A compromised tag runs in your pipeline with your
  token.
- **Separate CI from CD.** Test/lint/build on every push; deploy as a
  distinct job that `needs:` the build, is gated on `main` (or a tag /
  `environment:` with required reviewers), and never on a PR.
- **Make it reproducible locally.** The workflow should mostly call the same
  `make test` / `npm run ci` a developer can run. Logic that only exists in
  YAML can't be debugged without pushing.
- **Secrets are secrets.** Reference via `${{ secrets.X }}`, never `echo`
  them, never pass into `pull_request` from forks, and remember they're
  masked in logs only if referenced exactly (not after string munging).
