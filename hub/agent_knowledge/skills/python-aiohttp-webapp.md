---
name: python-aiohttp-webapp
description: Python aiohttp web app conventions (Agent Hub-style single-process async services)
keywords: aiohttp, python, py, webapp, asyncio
---

# Python / aiohttp web apps

- `aiohttp` route handlers are coroutines — never call a blocking function
  (raw `requests`, unbuffered file I/O on a large file, `time.sleep`) inside
  one without `run_in_executor` or an async equivalent; it stalls every
  other connection on the event loop.
- Prefer `asyncio.create_subprocess_exec` over `subprocess.run` in an async
  app — the latter blocks the loop for the subprocess's full lifetime.
- Route tables (`web.RouteTableDef()`) keep handlers colocated with their
  routes — check for an existing table in the module before adding a new
  registration pattern.
- Graceful shutdown: hook into `app.on_cleanup`, not `atexit` — the latter
  doesn't get an event loop to await async cleanup in.
