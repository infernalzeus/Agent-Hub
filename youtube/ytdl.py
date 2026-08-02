"""
YouTube downloader pipeline — extracted from download_yt_link.ipynb.

Usage:
    python ytdl.py --url <url> --format audio|video --outdir <path>

Audio output: MP3 320kbps + embedded SQUARE-cropped thumbnail (album cover art)
Video output: best 1080p30+ MP4 with the thumbnail embedded as the file poster
              (attached_pic cover stream)

Handles single videos and playlists — every downloaded entry gets its own
thumbnail embedded, and loose thumbnail images are swept afterwards.
"""

from __future__ import annotations
import argparse
import glob
import os
import subprocess
import sys

# Force UTF-8 on stdout/stderr — yt-dlp writes Unicode progress characters
# (arrows, symbols) that crash on Windows with the default cp1252 encoding.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yt_dlp


# ── Progress hook ──────────────────────────────────────────────────────────────

def _progress_hook(d: dict) -> None:
    if d["status"] == "downloading":
        pct   = d.get("_percent_str", "?%").strip()
        total = d.get("_total_bytes_str", "?")
        speed = d.get("_speed_str", "?")
        eta   = d.get("_eta_str", "?")
        print(f"\rDownloading: {pct} of {total} at {speed}  ETA {eta}", end="", flush=True)
    elif d["status"] == "finished":
        print("\nDownload complete — post-processing…", flush=True)


# ── Core download + thumbnail pipeline ────────────────────────────────────────

def download(
    url: str,
    output_path: str,
    format_type: str,
    cookiefile: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    """
    Download and post-process a YouTube URL.
    Returns the final file path.
    Raises on failure.

    cookiefile / cookies_from_browser authenticate the request. YouTube now
    rejects a lot of anonymous traffic with a "Sign in to confirm you're not a
    bot" error — supplying cookies is the only way past it.
    """
    os.makedirs(output_path, exist_ok=True)

    if format_type == "audio":
        fmt      = "bestaudio/best"
        postproc = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]
    else:
        fmt      = "bestvideo+bestaudio/best"
        postproc = [
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]

    ydl_opts = {
        "outtmpl":        os.path.join(output_path, "%(title)s.%(ext)s"),
        "format":         fmt,
        "noplaylist":     True,
        "writethumbnail": True,
        "postprocessors": postproc,
        "progress_hooks": [_progress_hook],
        "quiet":          False,
        # Without a JS runtime, yt-dlp can't solve YouTube's current signature/
        # SABR challenges and silently falls back to format 18 (640x360) only —
        # this is what caused downloads to come out at 360p regardless of the
        # format selector above. node is what's actually installed on this
        # machine; the remote component is the challenge-solver script itself.
        "js_runtimes":       {"node": {"path": r"Z:\Programs\NodeJS\node.exe"}},
        "remote_components": ["ejs:github"],
    }

    # Authentication. A cookies.txt file is preferred for an always-on service:
    # browser-cookie extraction fails on Windows while the browser is open (the
    # cookie DB is locked) and modern Chrome/Edge App-Bound Encryption blocks it
    # outright. cookies_from_browser is kept as a fallback for interactive use.
    if cookiefile and os.path.exists(cookiefile):
        ydl_opts["cookiefile"] = cookiefile
    elif cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

    if format_type == "video":
        # bestvideo+bestaudio can select VP9/AV1 streams that only merge cleanly
        # into MKV, not MP4 — but the thumbnail-embed step below uses MP4-style
        # ffmpeg syntax and computes final_filename assuming an .mp4 extension.
        # Pinning the merge container keeps that assumption true regardless of
        # which codecs got selected (ffmpeg remuxes, it doesn't re-encode, so
        # this costs nothing in quality).
        ydl_opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # A playlist URL yields an "entries" list; a single video is wrapped so
        # the same per-entry embed loop handles both cases.
        if info.get("_type") == "playlist" or "entries" in info:
            entries = [e for e in (info.get("entries") or []) if e]
        else:
            entries = [info]

        media_files: list[str] = []
        for entry in entries:
            media = _resolve_media(ydl.prepare_filename(entry), format_type)
            if media:
                media_files.append(media)

    # ── Thumbnail embed (per downloaded file) ──────────────────────────────────
    for media in media_files:
        thumb = _find_sibling_thumb(media)
        if not thumb:
            continue
        if format_type == "audio":
            _embed_audio_cover(media, thumb)
        else:
            _embed_video_poster(media, thumb)

    # Backstop: remove any thumbnail image still sitting next to a media file
    # (partial/failed entries, or a playlist interrupted mid-run).
    _sweep_orphan_thumbs(output_path)

    last = media_files[-1] if media_files else "(nothing downloaded)"
    print(f"\nDone: {len(media_files)} file(s)", flush=True)
    print(f"Saved to: {last}", flush=True)
    return last


# ── Thumbnail helpers ──────────────────────────────────────────────────────────

_IMG_EXTS   = (".webp", ".jpg", ".jpeg", ".png")
_MEDIA_EXTS = (".mp3", ".mp4", ".mkv", ".webm", ".m4a", ".opus")


def _resolve_media(prepared: str, format_type: str) -> str | None:
    """Map yt-dlp's prepared filename to the file that actually landed on disk."""
    if format_type == "audio":
        cand = os.path.splitext(prepared)[0] + ".mp3"
        return cand if os.path.exists(cand) else None
    if os.path.exists(prepared):
        return prepared
    stem = os.path.splitext(prepared)[0]  # merge/remux may have changed the extension
    return next((stem + ext for ext in (".mp4", ".mkv", ".webm", ".m4a") if os.path.exists(stem + ext)), None)


def _find_sibling_thumb(media_path: str) -> str | None:
    """The thumbnail yt-dlp wrote next to a media file (same stem, image ext)."""
    stem = os.path.splitext(media_path)[0]
    return next(
        (f for f in glob.glob(glob.escape(stem) + ".*") if f.lower().endswith(_IMG_EXTS)),
        None,
    )


def _embed_audio_cover(media_path: str, thumb_path: str) -> None:
    """Embed the thumbnail as MP3 cover art, centre-cropped to a SQUARE.

    id3 cover art needs JPEG/PNG, so the webp is converted; the crop filter takes
    the largest centred square (min(width,height)) — commas inside min() are
    escaped so ffmpeg doesn't read them as filtergraph separators.
    """
    jpg_thumb = media_path + ".cover.jpg"
    temp_file = media_path + ".temp.mp3"
    print(f"\nSquare-cropping cover: {os.path.basename(thumb_path)}", flush=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", thumb_path,
         "-vf", "crop=min(iw\\,ih):min(iw\\,ih)", jpg_thumb],
        capture_output=True,
    )
    if not os.path.exists(jpg_thumb):
        return

    print(f"Embedding cover art into {os.path.basename(media_path)}…", flush=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", media_path, "-i", jpg_thumb,
        "-map", "0:0", "-map", "1:0", "-c", "copy",
        "-id3v2_version", "3",
        "-metadata:s:v", "title=Album cover",
        "-metadata:s:v", "comment=Cover (front)",
        temp_file,
    ], capture_output=True)

    if os.path.exists(temp_file):
        os.replace(temp_file, media_path)
    for f in (jpg_thumb, thumb_path):
        if os.path.exists(f):
            os.remove(f)


def _embed_video_poster(media_path: str, thumb_path: str) -> None:
    """Embed the original-aspect thumbnail as the MP4's poster (attached_pic
    cover stream) so players show it as the file's thumbnail."""
    jpg_thumb = media_path + ".cover.jpg"
    temp_file = media_path + ".temp.mp4"
    print(f"\nConverting thumbnail → JPEG: {os.path.basename(thumb_path)}", flush=True)
    subprocess.run(["ffmpeg", "-y", "-i", thumb_path, jpg_thumb], capture_output=True)
    if not os.path.exists(jpg_thumb):
        return

    print(f"Embedding poster into {os.path.basename(media_path)}…", flush=True)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", media_path, "-i", jpg_thumb,
        "-map", "0", "-map", "1", "-c", "copy",
        "-disposition:v:1", "attached_pic",
        temp_file,
    ], capture_output=True)

    if os.path.exists(temp_file):
        os.replace(temp_file, media_path)
    for f in (jpg_thumb, thumb_path):
        if os.path.exists(f):
            os.remove(f)


def _sweep_orphan_thumbs(output_path: str) -> None:
    """Delete any thumbnail image left next to a downloaded media file.

    Only removes an image when a same-stem media file exists, so it can't touch
    unrelated pictures — just the loose .webp/.jpg residue yt-dlp leaves when a
    per-entry embed didn't run (e.g. a playlist stopped part-way through)."""
    for img in glob.glob(os.path.join(output_path, "*")):
        if not img.lower().endswith(_IMG_EXTS):
            continue
        stem = os.path.splitext(img)[0]
        if any(os.path.exists(stem + ext) for ext in _MEDIA_EXTS):
            try:
                os.remove(img)
            except OSError:
                pass


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="yt-dlp pipeline with square thumbnail embed")
    parser.add_argument("--url",    required=True, help="YouTube URL")
    parser.add_argument("--format", required=True, choices=["audio", "video"], dest="fmt")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--cookies", default=None,
                        help="Path to a cookies.txt file (Netscape format) for authentication")
    parser.add_argument("--cookies-from-browser", default=None, dest="cookies_browser",
                        help="Read cookies from an installed browser instead (e.g. edge, chrome, firefox)")
    args = parser.parse_args()

    try:
        download(args.url, args.outdir, args.fmt,
                 cookiefile=args.cookies, cookies_from_browser=args.cookies_browser)
    except Exception as e:
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg or "cookies" in msg.lower():
            print("\nERROR: YouTube is requiring sign-in cookies for this download.",
                  file=sys.stderr, flush=True)
            print("Fix: export your YouTube cookies to a cookies.txt file and point "
                  "YT_DL_COOKIES at it (default N:\\Code\\YT-DLP\\cookies.txt). "
                  "Use a 'Get cookies.txt' browser extension while signed in to YouTube.",
                  file=sys.stderr, flush=True)
        else:
            print(f"\nERROR: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
