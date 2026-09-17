---
name: docker-containers
description: "Writing Dockerfiles and compose setups that build fast, stay small, and run safely — layer caching, multi-stage builds, non-root, .dockerignore. Relevant when the task involves: docker, dockerfile, container, compose, image, build, oci, devcontainer."
metadata:
  keywords: "docker, dockerfile, container, compose, image, oci, devcontainer, containerize"
  origin: hand-written
---

# Docker / containers

- **Order layers by change frequency.** Copy the dependency manifest and
  install deps *before* copying the app source, so a code edit doesn't
  re-run the install. `COPY package.json .` → `RUN npm ci` → `COPY . .` —
  not `COPY . .` then install.
- **Multi-stage to drop build tooling.** Compile / bundle in a `builder`
  stage, then `COPY --from=builder` only the artifact into a slim runtime
  base. The final image shouldn't contain compilers, dev headers, or the
  full node_modules if only `dist/` runs.
- **Pin the base image** to a specific tag/digest (`python:3.12-slim`, not
  `python:latest`) — `latest` makes builds non-reproducible and silently
  changes your runtime.
- **Add a `.dockerignore`.** Exclude `.git`, `node_modules`, `__pycache__`,
  local env files, build output, `*.log`. Without it the whole working tree
  (including secrets and junk) goes into the build context and often the
  image.
- **Run as non-root.** Create a user and `USER app` before the final
  `CMD` — a container process running as root is root on a shared kernel if
  it escapes.
- **One concern per container.** App in one, database in another, wired by
  compose. Don't `apt install` a database into the app image.
- **`CMD` in exec form** (`["node", "server.js"]`, not `node server.js`) so
  signals reach the process and it can shut down cleanly. Add a
  `HEALTHCHECK` if an orchestrator will use it.
- **Never bake secrets in.** No API keys in `ENV` or `ARG` (both leak into
  image history / `docker inspect`). Pass at runtime via env or a mounted
  secret.
- **Bind-mount source for dev, copy for prod.** Compose with a volume mount
  gives live reload locally; the built image must be self-contained with no
  host dependency.
