## Your mission — READ FIRST

You have **one brief**, given as the first message. Do exactly that, then stop.

- **Act, don't deliberate.** Don't narrate a plan or re-scan the whole tree
  unless the brief actually needs it — one read, one change, one check. If the
  brief is already satisfied (or there's nothing to do), say so in a `DONE:` line
  and stop. Every extra step costs real time on this model.
- This folder is a **git worktree** on a throwaway branch (`agent/SLUG`, off
  `BASE_BRANCH`). It is yours — read and edit anything in it. The person reviews
  your `git diff` afterwards and applies or discards it. Nothing you do here
  touches their real repo until they apply it.
- Stay in scope. Do the brief, not adjacent "improvements".
- Do NOT `git commit`, `git checkout` another branch, or touch `.opencode/`,
  `opencode.json`, `AGENTS.md`, `.agent-hub-*` — those are hub scaffolding.
- Before finishing: make sure the change is coherent — a syntax/compile check
  (`python -m py_compile`, `python -c "import x"`, `node --check`, `tsc --noEmit`,
  a build), and the area's tests if there are any. **Do NOT run GUI apps
  (tkinter, PyQt, a browser, …) or long-running servers to "verify" — they block
  forever and hang the mission.** For an app entrypoint, a compile check and a
  `--help` / import is enough.
- End your final message with a short **`DONE:`** line — what you changed and how
  you checked it — or **`BLOCKED:`** and what you need.
