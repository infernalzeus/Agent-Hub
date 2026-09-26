# Agent Hub launch video — the brief

Not part of the product. This is the input you hand an agent when you run `/brag`
against this repository, so the video says what Agent Hub actually is rather than what
a generic marketing prompt assumes.

Keep this file out of the skill library. `brag` is a general skill for any app; the
Agent-Hub-specific part is this brief.

---

## Before anything renders

| | |
|---|---|
| **Prerequisites** | Node 22+, ffmpeg, Git — all present on this machine |
| **Get the skill** | Agents page → *Skills you can add* → **Launch videos** → ADD TO MY AGENTS |
| **First render** | HyperFrames downloads its own headless Chromium (~200 MB) via npx |
| **Where it runs** | Entirely on this PC. Your source is never uploaded |
| **Output** | `brag-output-<timestamp>/` — `brag.mp4`, `brag.jpg`, `brag-plan.md`, `share-copy.txt` |

Render into a scratch folder, **not** into either repository. The skill drags ~15 MB of
music with it and the output is another few MB; neither belongs in git.

## The forbidden list

- **Never "AI".** The capability is **AUTONOMOUS LLM**. This is the rule most likely to
  be broken by a generic marketing instinct, and the one that matters most.
- **No "Private Control Plane"** — retired phrase.
- **No version numbers, file sizes, install counts or benchmarks.** They go stale and
  nothing re-renders the video.
- **No claims about auto-updating to a cloud, accounts, or syncing.** None exist.

## What it is, in the product's own words

> Your most powerful PC tools. At your fingertips, any device.

One app on your own PC that your phone, tablet and laptop reach over Tailscale. Nothing
runs on anyone else's server.

| Capability | The words that go on screen |
|---|---|
| **AUTONOMOUS LLM** | Agentic pipeline · Missions · Dispatch · Git worktrees · Review and apply |
| **MCP CONTROL** | Voice commands · Learned routines · App launch · Approved actions |
| **MEDIA VAULT** | yt-dlp · ffmpeg · Drive browser · Phone inbox |
| **GIT GRAPH** | Repo status · Auto-discovery · Live from git · Project map |

## The one mechanism worth 15 seconds

Everything else is a feature list. The story is the **loop closing**:

```
ask → Mission → Dispatch → git worktree → Review → Apply
                    ↑                                │
                    └──────── re-plan ───────────────┘
```

An ask becomes a Mission and dispatches into a **git worktree** — a private copy of the
repo — where the orchestrator runs a team of agents. You review the diff and apply or
discard. That same diff is what the Git Graph draws, so an agent's work appears on the
project map *while it is happening*.

A one-way arrow sells a pipeline. **Show the return edge** — that is what sells autonomy.

## Shot list (15–25s, landscape)

1. **Phone in hand, Hub open.** Establishes the premise in two seconds without a word.
2. **Type an ask.** Real typing, real text. Not a mock.
3. **The pipeline lights up.** Missions → Dispatch → Worktree, live.
4. **Cut to the Git Graph** updating on its own. This is the beat that lands.
5. **Review the diff, press Apply.**
6. **End card:** the hero line, then `infernalzeus.github.io/Agent-Hub/`.

Screen recordings beat stock footage and beat text cards. If a step will not record
cleanly, cut it rather than faking it.

## Look

Near-black background, one green accent `#00e676`, Orbitron for component labels, thin
strokes. Matches the site and the app, so the video, the page and the product read as one
thing. No voiceover unless you ask for it (`--voice` adds Kokoro TTS).

## Before you publish

Check every claim against the download page. If a viewer could not verify it in a minute,
cut it. Then watch it once with the sound off — if the loop closing is not legible without
narration, the edit is wrong, not the copy.
