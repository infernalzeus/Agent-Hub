# Agent Hub — install test in a VM

Hand this whole file to Codex inside the VM. It is written to be run by an agent
that has a shell on that machine, not by one driving the VM's window from outside.

**Why it is shaped this way.** An installer test is mostly not a visual question.
Where files landed, what the registry says, where shortcuts point, and what was
left alone are all text — and text can be asserted, re-run and diffed. Only one
thing genuinely needs eyes, and it is called out at the end.

---

## What you need in the VM

- Windows 10/11, a normal user account, **no administrator rights needed** — if
  anything asks for elevation, that is itself a finding.
- `Agent-Hub-Setup.exe` (from the release, or handed to you).
- `verify_install.ps1` (beside this file).
- PowerShell 5.1 is fine.

Do not install anything else first. A clean box is the point.

---

## Run it in this order

### 1. Baseline, before touching anything

```
pwsh -File verify_install.ps1 -Phase before -Report C:\hub-verify.json
```

Everything should PASS or SKIP. A FAIL here means the box is not clean.

### 2. Install silently, then look at it once by hand

Inno Setup takes switches, so the install itself is repeatable without clicking:

```
.\Agent-Hub-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /LOG=C:\hub-install.log
```

Then **once, by hand**, run it again normally (`.\Agent-Hub-Setup.exe`) on a fresh
snapshot and read the wizard. This is the only part needing eyes. Check:

- the page asking **"Where should Agent Hub keep your data?"** appears, explains
  why it is separate, and says it can be changed later;
- the final page before installing lists **"Changes outside these folders"**,
  naming the data-folder registry value and the `agenthub://` registration, and
  saying both are per-user and removed on uninstall;
- nothing requests administrator rights.

Say plainly whether each was there. If the wizard differs from the above, quote
what it actually said.

### 3. Verify the install

```
pwsh -File verify_install.ps1 -Phase after -AppDir "$env:LOCALAPPDATA\Agent Hub" -Report C:\hub-verify.json
```

Adjust `-AppDir` if you chose a different folder.

### 4. Does it do what the notes say?

Open the hub (it should already be running; otherwise launch it from the Start
menu) and work through the checklist in **"Patch-note claims"** below. One line
per item: what you did, what happened.

### 5. The folder move

In the hub: **Settings → This hub → Install folder** → choose an empty folder on
another drive → **MOVE ON NEXT RESTART**. Then close the hub completely and wait
for it to come back.

```
pwsh -File verify_install.ps1 -Phase moved -AppDir "D:\Hub" -OldAppDir "$env:LOCALAPPDATA\Agent Hub" -Report C:\hub-verify.json
```

Then do these by hand, because they are the ones that break quietly:

- **Sign out and back in.** Does the hub start by itself? (The startup shortcut is
  the thing most likely to have been left pointing at a folder that is gone.)
- **Open an `agenthub://` link.** Does it launch from the new folder?
- **Control Panel → Programs.** Is Agent Hub still listed, and does Uninstall
  start? *(Do not complete it until the end.)*

### 6. Deliberately interrupt a move

This is the test that matters most, because it is the one that could leave
someone with no working app.

Queue another move, close the hub, and **kill the mover while it is copying**
(`agent-hub-move.cmd` in `%TEMP%`, or the `robocopy` it spawns). Then:

- Is the **old** folder still intact and does the hub still start from it?
- Is the partial copy left behind, rather than the old one deleted?

The rule being tested: **copy, verify, then delete.** The old install must survive
an interruption at any point. If it does not, stop and report that first — nothing
else in this list matters as much.

### 7. Uninstall

Run the uninstaller. Then check that both registry values are gone
(`AGENTHUB_WORK_ROOT`, `agenthub://`) and say whether the **data** folder was left
alone — it should be. Deleting someone's project copies on uninstall is a bug.

---

## Patch-note claims

Check what the release claims against what the app does. One line each: **yes**,
**no**, or **could not tell**, with what you saw.

| # | Claim | How to check |
|---|---|---|
| 1 | Installs without administrator rights | Nothing elevated in step 2 |
| 2 | First run asks one question: set up now, or set each tool up on first use | Watch the first launch |
| 3 | Every setup step says what it downloads and how big | Start one; read the text |
| 4 | Files and media work with no network | Disconnect the VM's network, open File Browser and Media |
| 5 | Desktop control is Windows-only and hidden elsewhere, not broken | Settings → Tools → PC control is present here |
| 6 | Binds to loopback only | `Get-NetTCPConnection -LocalPort 8081` shows `127.0.0.1`, not `0.0.0.0` |
| 7 | A fresh install has no YouTube channels | Settings → Tools → YouTube channels is empty |
| 8 | Agents work in a private copy; nothing is written until you approve | Run a small mission; confirm the project is untouched until APPLY |
| 9 | Settings is a menu with seven sections, all reachable on a phone-width window | Resize to ~380px wide |
| 10 | The theme applies immediately, no restart | Settings → Appearance → Custom, change the accent |

---

## How to report back

Two things, both written to `C:\` so they can be copied out:

1. **`C:\hub-verify.json`** — produced by the script. Do not edit it.
2. **`C:\hub-report.md`** — written by you, in exactly this shape:

```markdown
# Agent Hub install test — <date>
VM: <Windows version>  ·  Installer: <file name>  ·  Build: <version the hub reports>

## Summary
<two or three sentences: did it install, run, move, survive interruption, uninstall>

## Script results
before: X passed / Y failed
after:  X passed / Y failed
moved:  X passed / Y failed

## Failures
<for each FAIL: the check id, what was expected, what was actually there.
 If there were none, write "none".>

## Wizard (step 2, by hand)
data-folder page: <yes/no + what it said>
changes-listed page: <yes/no + what it said>
asked for admin: <yes/no>

## Patch-note claims
<the table, one row per claim, with yes/no/could not tell and what you saw>

## Interrupted move (step 6)
old install survived: <yes/no>
hub still started from the old folder: <yes/no>
<what was left on disk>

## Anything else
<surprises, slowness, confusing wording. Quote exact text where you can.>
```

**Be specific about failures.** "Shortcut was wrong" is not usable; "link.startup
pointed at `C:\Users\me\AppData\Local\Agent Hub\AgentHub.exe` after the move to
`D:\Hub`" is. Quote the value you actually saw.

**Do not fix anything.** If something is broken, record it and carry on. A test
run that repaired what it found tells us nothing about what a user would hit.

If a step cannot be done at all, say so and why, rather than skipping it quietly.
