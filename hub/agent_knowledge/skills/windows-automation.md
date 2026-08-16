---
name: windows-automation
description: General Windows automation — PowerShell, Task Scheduler, services, VBScript, registry, path/process gotchas
keywords: windows, powershell, vbs, vbscript, registry, reg, batch, cmd, task-scheduler, service
---

# Windows automation (general)

- **Default to PowerShell** for anything beyond a one-liner — it has real
  data types, error handling (`try/catch`, `-ErrorAction Stop`), and object
  pipelines (`Get-Process | Where-Object ...`), where batch/cmd only gives
  you text munging. Reach for VBScript specifically only when you need a
  genuinely hidden child process with no console flash (`WScript.Shell.Run`
  style `0`) — PowerShell's own windows are harder to fully suppress.
- **Recurring/scheduled work**: Task Scheduler (`schtasks` or the
  `ScheduledTasks` PowerShell module), not a `while` loop with `sleep` in a
  script left running — it survives reboots, has retry/missed-run policy,
  and shows up in a place the user can actually find and manage it.
- **A background/always-on process** on Windows has no native "run forever,
  restart on crash" primitive like a Linux systemd unit — options in order
  of weight: a scheduled task set to run at logon (simplest), NSSM/WinSW to
  wrap it as a real Windows service (more robust, more setup), or a small
  supervisor script that loops on the child's exit code (lightest, but only
  as reliable as the thing launching the supervisor itself).
- **Registry writes**: prefer `HKEY_CURRENT_USER` (no admin, per-user) over
  `HKEY_LOCAL_MACHINE` (admin required, machine-wide) unless the change
  genuinely needs to apply system-wide — and always say exactly which key a
  `.reg` file or `New-Item -Path HKCU:\...` touches before running it.
- **Path gotchas**: backslash paths with spaces need careful quoting across
  cmd/PowerShell/subprocess boundaries — a path breaking a tool that expects
  forward slashes (common with tools ported from Unix, e.g. `git diff
  --no-index`) is worth checking for before assuming a deeper bug.
- **Never hardcode a real, identifying value** (a Tailscale/VPN hostname, a
  real device name, an API key, a personal file path with a username in it)
  directly in a script meant to be shared or committed — route it through a
  gitignored local-override file with a safe generic fallback.
- **Elevation**: a script needing admin should check/relaunch itself
  elevated explicitly (`Start-Process -Verb RunAs` from a non-elevated
  wrapper, or a manifest for a compiled tool) rather than assuming the user
  remembered to "Run as Administrator" — a silent permission failure deep
  in a script is a worse experience than an explicit elevation prompt.
