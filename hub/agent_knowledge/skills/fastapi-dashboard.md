---
name: fastapi-dashboard
description: FastAPI conventions for data pipeline dashboards (compliance checks, threshold review UIs)
keywords: fastapi, dashboard, pydantic, uvicorn, api, threshold
---

# FastAPI pipeline dashboards

For a FastAPI app fronting a data-processing pipeline (e.g. a compliance
pipeline: source data → checks → reviewable dashboard):

- Define request/response shapes as `pydantic` models, not raw dicts — a
  dashboard's whole value is trustworthy structure; an endpoint that returns
  `dict` invites silent shape drift between backend and frontend.
- Long-running checks (a full pipeline pass) belong in a background task
  (`BackgroundTasks`, or a real job queue past a certain size) — never block
  a request handler on a multi-second-plus computation, or the dashboard
  itself becomes unresponsive while a check runs.
- Threshold/config values that reviewers tune (pass/fail cutoffs, calibration
  constants) should be readable AND writable through the API, not hardcoded
  — a dashboard whose thresholds require a code change to adjust isn't
  actually serving its reviewer.
- Keep the check logic (pure functions over the data) separate from the
  route handlers — makes the checks independently testable and reusable
  from a CLI/cron path outside the dashboard.
- Serve static frontend assets and API routes from the same app only if the
  dashboard is meant to be single-origin; otherwise keep the API on its own
  path prefix so a separate frontend build can point at it without a proxy.
