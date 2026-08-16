---
name: midi-music-ml
description: Symbolic MIDI ML generation and mastering conventions (cadenza-style projects)
keywords: midi, mido, cadenza, lmms, music, sklearn
---

# Symbolic music ML

- Do generation/classification work in symbolic MIDI space (note events,
  velocities, timing), not raw audio — audio is only the final render step.
- LMMS / DAW rendering happens LAST, as a mastering pass over generated
  MIDI — don't try to shape the sound earlier in the pipeline.
- Pair a generator with a classifier-critic when quality matters: let the
  generator propose candidates, the classifier score them, keep the best —
  a bare generator with no scoring tends to drift into unmusical output.
- `mido` message timing is delta-time by default (ticks since the previous
  event, not absolute) — convert before doing any absolute-time math (e.g.
  "where is beat 3") or the numbers will be wrong.
