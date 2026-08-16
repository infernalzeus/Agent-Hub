---
name: testing-conventions
description: Language-agnostic testing philosophy — what to test, test structure, avoiding brittle/useless tests
keywords: test, testing, pytest, jest, unit-test, integration-test, mock, ci
---

# Testing conventions (language-agnostic)

- Test behavior, not implementation — a test should survive a refactor that
  doesn't change what the code does. A test that breaks because a private
  helper got renamed (while the public behavior is unchanged) is testing
  the wrong layer.
- One logical assertion per test, named for what it verifies (`test_push_
  refuses_conflicting_file`, not `test_push_2`) — a failing test name
  should tell you what broke without opening the file.
- Mock at the boundary (network, filesystem, clock, external API), not the
  internals of the thing under test — mocking too deep means the test
  passes even when the real integration is broken, defeating its purpose.
- Prefer a real (in-memory/throwaway) database/filesystem over mocking data
  access entirely when the persistence logic itself is what's being
  tested — a mocked DB layer that returns exactly what the test expects
  can pass while the real query is broken.
- Test the edge first, not just the happy path: empty input, the
  boundary value, the concurrent/conflicting case, the error path — the
  happy path is usually what got tested manually already anyway.
- Flaky tests (pass/fail non-deterministically) get fixed or deleted, not
  retried-until-green — a flaky test in CI trains everyone to ignore CI
  failures, which is worse than not having the test.
- Don't chase 100% coverage as a goal in itself — coverage tells you what's
  UNtested, it doesn't tell you what's WELL tested; a line hit by a test
  with no meaningful assertion still counts as "covered."
