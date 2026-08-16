---
name: git-workflow-conventions
description: Safe git usage inside an OpenCode session — commits, remotes, and what never to do unattended
keywords: git, commit, branch, remote, push, github
---

# Git workflow conventions

- Never run a destructive git command (`reset --hard`, `checkout -- .`,
  `clean -f`, `push --force`, `branch -D`) without the user's explicit
  go-ahead for that specific action — these discard work that can't be
  recovered from the working tree alone.
- Before anything that could discard uncommitted work, run `git status`
  first. If there's anything there, stash it (`-u` for untracked too) or
  commit it — don't assume a dirty tree is disposable scratch.
- Stage specific files by name, not `git add -A`/`git add .` — a broad add
  can sweep in a stray secret, credential file, or large binary that
  happened to be sitting in the working tree.
- Never commit anything a `.gitignore` is clearly trying to keep out
  (credentials, `local_settings.py`-style overrides, `.env`, tokens/cookies)
  even if asked to force-add it — flag it back to the user instead.
- New commits over amends, by default — amending rewrites history, which is
  surprising if the user didn't ask for it. Only amend on explicit request.
- Never push to a remote (especially `main`/`master`) without the user
  confirming first — a push is visible to others and not something to do
  as a side effect of "finishing" a task.
