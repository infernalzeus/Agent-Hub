---
name: debugging-methodology
description: "Language-agnostic method for finding the root cause of a bug fast — reproduce, isolate, bisect, instrument — and knowing when a fix is really a fix. Relevant when the task involves: debug, bug, crash, regression, stack-trace, repro, flaky, root-cause, investigate."
metadata:
  keywords: "debug, bug, crash, regression, stacktrace, repro, flaky, root-cause, investigate, heisenbug"
  origin: hand-written
---

# Debugging methodology (language-agnostic)

- **Reproduce it first, on the smallest input.** A bug you can't trigger on
  demand you can't verify you've fixed. Strip the failing case down to the
  fewest steps / smallest file that still breaks — the reduction usually
  points at the cause on its own.
- **Read the actual error, all of it.** The bottom of a stack trace is where
  it was raised; the top (or the first line in *your* code) is usually where
  it went wrong. A wrapped/re-raised exception hides the original — find the
  `caused by` / `__cause__` / inner exception.
- **Bisect the change, not just the code.** If it worked before, `git bisect`
  (or binary-search the diff / the config / the input) finds the breaking
  commit far faster than reasoning about the whole system. "What changed"
  beats "what's wrong" when there's a known-good point.
- **Instrument, don't guess.** Add a log/print of the exact values at the
  boundary you suspect (inputs, the branch taken, the value just before the
  failing line). One well-placed log beats an hour of staring. Remove them
  after, or gate behind a debug flag.
- **Check your assumptions explicitly.** Most stuck debugging is a belief
  that isn't true: the function isn't being called, the config isn't the one
  loaded, the two paths aren't the same file, the cache is stale, you're
  editing code that isn't running (wrong venv / not restarted / HMR didn't
  pick it up). Verify each with a print, not a hunch.
- **A fix you don't understand isn't a fix.** If the bug "went away" after a
  change you can't explain, you've probably moved it, not killed it. You
  should be able to say *why* the old code failed and *why* the new code
  can't.
- **Flaky = a real bug.** Non-deterministic failure is almost always a race,
  an ordering dependency, a shared/global state, a clock, or an unseeded
  random. "Re-run until green" trains everyone to ignore the signal.
- **Reproduce the fix failing.** Before closing it, re-break it (revert the
  fix, confirm the repro returns) so you know the fix is what did it — then
  re-apply. Add a test at the smallest reproducing layer.
