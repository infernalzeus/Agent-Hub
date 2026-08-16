---
name: ffmpeg-video-captions
description: Working with ffmpeg for video captioning, cropping, and audio mixing (movie-shorts-clipper style pipelines)
keywords: ffmpeg, clipper, movie, captions, srt, whisper, video
---

# ffmpeg video + captions

For projects that render vertical/square shorts with burned-in captions:

- Prefer `ffmpeg` filter chains over re-encoding in multiple passes — each
  extra pass costs render time and a generation of quality.
- Caption timing sources, in priority order: an existing `.srt` file, then
  Whisper transcription as fallback. Don't re-run Whisper if an `.srt`
  already exists for the same source.
- Square/vertical crops: compute the crop rect from the source resolution,
  don't hardcode assumed dimensions — inputs vary.
- Audio ducking (music under narration): apply a sidechain filter keyed to
  the narration track, not a flat volume reduction — a flat reduction either
  over- or under-ducks depending on the scene.
- Test renders on a short clip (first 10–15s) before committing to a full
  render — ffmpeg errors surface late and re-renders are expensive.
