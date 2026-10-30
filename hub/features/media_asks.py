"""Asks about a person's videos (or tracks, streams ...), answered with the Hub's own tools instead of clicking a web page.

"Open Trick2G's latest video", "download their second latest video", "download it". Clicking through a
browser page for this is slow and brittle, and the Hub already has what it needs: yt-dlp (the same one the
Media Vault uses) lists a channel's videos newest first, and the Media Vault downloads one. So:

    channel + which one   ->  yt-dlp lists the channel's videos        (no browser, no clicks)
    open / watch          ->  open that video's address in Edge
    download              ->  ask first, showing the title and length, then the Media Vault downloads it

Which sites, and what they call their items, is DATA (`hub/media_sources.json`, overridable from the state folder):
adding a site is a new row there, not new code. Ordinals are generic ("latest", "third latest", "5th newest").
The channel is remembered for a while, so "search YouTube for Trick2G" followed by "open their latest video"
or "download it" means the same person. Nothing here downloads without a YES, and a missing channel is asked
about rather than guessed.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time

from pathlib import Path

from ..config import YT_DL_PYTHON, logger
from ..runtime import STATE

TTL = 900.0                                   # seconds a remembered channel or video stays "the one"
RESOLVE_TIMEOUT = 25.0
CTX: dict = {"channel": "", "video": None, "at": 0.0}

SOURCES_FILE = Path(__file__).resolve().parent.parent / "media_sources.json"
_DEFAULT_SOURCES = [{"id": "youtube", "label": "YouTube", "nouns": ["video", "upload", "clip", "stream", "short"],
                     "sites": ["youtube"], "channel_urls": ["https://www.youtube.com/@{handle}/videos"],
                     "search": "ytsearch1:{name}", "format": "video"}]

_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
        "ninth": 9, "tenth": 10}
_LATEST = r"(?:latest|newest|most recent|last)"
_VERB = r"(?P<verb>open|play|watch|listen to|download|get|grab|save)"
_OWNER = r"(?:(?:their|his|her|its|the|that channel'?s?)\s+|(?P<owner>[a-z0-9][a-z0-9 ._-]{0,40}?)'?s\s+)"
_VERBS_OPEN = {"open", "play", "watch", "listen to"}
_MAX_N = 20


def sources() -> "list[dict]":
    """The sites this knows, from the state folder's copy if there is one, else the shipped table, else YouTube."""
    for path in (STATE / "media_sources.json", SOURCES_FILE):
        try:
            rows = json.loads(path.read_text(encoding="utf-8")).get("sources") or []
            rows = [r for r in rows if isinstance(r, dict) and r.get("id") and r.get("nouns")]
            if rows:
                return rows
        except (OSError, ValueError):
            continue
    return _DEFAULT_SOURCES


def _which_rx() -> str:
    words = "|".join(sorted(_ORD, key=len, reverse=True))
    return (rf"(?:(?:(?P<nth>\d{{1,2}})(?:st|nd|rd|th)|(?P<word>{words}))\s+{_LATEST}|(?P<one>{_LATEST}|previous))")


def _n_of(m: "re.Match") -> int:
    if m.group("nth"):
        return max(1, min(_MAX_N, int(m.group("nth"))))
    if m.group("word"):
        return _ORD[m.group("word").lower()]
    return 2 if (m.group("one") or "").lower() == "previous" else 1


def _patterns() -> dict:
    nouns = sorted({n.lower() for s in sources() for n in s["nouns"]}, key=len, reverse=True)
    noun = "(?P<noun>" + "|".join(re.escape(n) for n in nouns) + ")s?"
    which = _which_rx()
    sites = "|".join(re.escape(w) for s in sources() for w in s.get("sites", [])) or "youtube"
    return {
        "compound": re.compile(rf"(?:search(?: (?:on|in))? (?P<site>{sites}) for|find|look up)\s+(?P<ch>.+?)\s*(?:,|\band then\b|\bthen\b|\band\b)\s*"
                               + _VERB + rf"\s+(?:(?:their|his|her|its|the)\s+)?{which}\s+{noun}\b", re.I),
        "plain": re.compile(r"^(?:please\s+|can you\s+|could you\s+)?" + _VERB + r"\s+(?:up\s+)?" + _OWNER + "?" + which
                            + rf"\s+{noun}(?:\s+(?:of|from|by)\s+(?P<ch>.+?))?(?:\s+on\s+(?P<site>{sites}))?\s*[.!?]*$", re.I),
        "it": re.compile(r"^(?:please\s+|can you\s+|could you\s+)?(?P<verb>download|get|grab|save)\s+(?:it|that|this|that (?:video|track|song)|the (?:video|track|song))\s*[.!?]*$", re.I),
        "url": re.compile(r"^(?:please\s+)?(?:download|get|grab|save)\s+(?P<url>https?://\S+)\s*[.!?]*$", re.I),
    }


def _source_for(site: "str | None", noun: "str | None") -> dict:
    rows = sources()
    for s in rows:
        if site and site.lower() in [w.lower() for w in s.get("sites", [])]:
            return s
    for s in rows:
        if noun and noun.lower() in [n.lower() for n in s["nouns"]]:
            return s
    return rows[0]


def _clean(text: str) -> str:
    return " ".join((text or "").strip().split())


def _channel(raw: str) -> str:
    c = re.sub(r"^(?:youtuber|channel|the channel|the youtuber)\s+", "", (raw or "").strip(" '\".,!?"), flags=re.I)
    return re.sub(r"'s$", "", c).strip()


def parse(text: str) -> "dict | None":
    """What kind of media ask this is, or None. `channel` is None when the sentence did not say whose."""
    t = _clean(text)
    rx = _patterns()
    m = rx["url"].match(t)
    if m:
        return {"verb": "download", "url": m.group("url"), "channel": None, "n": 0}
    if rx["it"].match(t):
        return {"verb": "download", "channel": None, "n": 0, "it": True}
    for kind in ("compound", "plain"):
        m = rx[kind].search(t) if kind == "compound" else rx[kind].match(t)
        if m:
            src = _source_for(m.groupdict().get("site"), m.group("noun"))
            ch = _channel(m.groupdict().get("owner") or m.group("ch") or "") or None
            return {"verb": m.group("verb").lower(), "channel": ch, "n": _n_of(m), "source": src["id"], "noun": m.group("noun").lower()}
    return None


def remember(channel: str = "", video: "dict | None" = None) -> None:
    if channel:
        CTX["channel"] = channel
    if video is not None:
        CTX["video"] = video
    CTX["at"] = time.time()


def remembered(now: "float | None" = None) -> dict:
    fresh = ((now if now is not None else time.time()) - CTX["at"]) <= TTL
    return {"channel": CTX["channel"] if fresh else "", "video": CTX["video"] if fresh else None}


# yt-dlp lives in the interpreter the downloader uses (the managed "media" environment in an installed build,
# not necessarily the Hub's own Python), so it is asked there, in a short subprocess, and answers in JSON.
_YT_SCRIPT = (
    "import json, sys\n"
    "import yt_dlp\n"
    "url, opts = sys.argv[1], json.loads(sys.argv[2])\n"
    "with yt_dlp.YoutubeDL(opts) as y:\n"
    "    info = y.extract_info(url, download=False) or {}\n"
    "keep = ('id','title','url','duration','channel','uploader','channel_url','uploader_url','filesize_approx','filesize')\n"
    "slim = lambda i: {k: i.get(k) for k in keep}\n"
    "out = slim(info)\n"
    "out['entries'] = [slim(e) for e in (info.get('entries') or []) if e]\n"
    "print('@@JSON@@' + json.dumps(out))\n"
)


def _yt(url: str, opts: dict, timeout: float = 30.0) -> dict:
    """Run yt-dlp's extract_info in the downloader's interpreter. Raises RuntimeError on any failure."""
    py = str(YT_DL_PYTHON or sys.executable)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run([py, "-c", _YT_SCRIPT, url, json.dumps({"quiet": True, "no_warnings": True, "skip_download": True,
                                                                     "socket_timeout": 15, "noprogress": True, **opts})],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           env=env, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not run yt-dlp: {exc}") from exc
    line = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith("@@JSON@@")), "")
    if r.returncode or not line:
        raise RuntimeError((r.stderr or r.stdout or "yt-dlp gave no answer").strip().splitlines()[-1][:200])
    return json.loads(line[len("@@JSON@@"):])


def _extract(url: str, n: int) -> dict:
    return _yt(url, {"extract_flat": "in_playlist", "playlistend": n})


def _entry(e: dict, channel: str, info: dict) -> dict:
    vid = e.get("id") or ""
    return {"id": vid, "title": e.get("title") or "(untitled)",
            "url": e.get("url") if str(e.get("url") or "").startswith("http") else f"https://www.youtube.com/watch?v={vid}",
            "duration": e.get("duration"), "channel": e.get("channel") or info.get("channel") or info.get("uploader") or channel}


def resolve_latest(channel: str, n: int = 1, source: "dict | str | None" = None) -> "dict | None":
    """The n-th newest item of a channel, by name. Blocking (network): call it from a thread."""
    src = source if isinstance(source, dict) else next((s for s in sources() if s["id"] == source), sources()[0])
    handle = re.sub(r"[^A-Za-z0-9._-]", "", channel)
    attempts = [u.format(handle=handle) for u in src.get("channel_urls", [])] if handle else []
    for url in attempts:
        try:
            info = _extract(url, n)
        except Exception as exc:  # noqa: BLE001
            logger.info("media_asks: %s: %s", url, str(exc)[:160])
            continue
        entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
        if len(entries) >= n:
            return _entry(entries[n - 1], channel, info)
    search = (src.get("search") or "").format(name=channel)
    suffix = "/" + src["channel_urls"][0].rstrip("/").rsplit("/", 1)[-1].split("?")[0] if src.get("channel_urls") else "/videos"
    try:                                                      # no channel by that handle: let a search name it
        if not search:
            return None
        found = _extract(search, 1)
        first = next((e for e in (found.get("entries") or []) if e), None)
        chan_url = (first or {}).get("channel_url") or (first or {}).get("uploader_url")
        if chan_url:
            info = _extract(chan_url.rstrip("/") + suffix, n)
            entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
            if len(entries) >= n:
                return _entry(entries[n - 1], channel, info)
    except Exception as exc:  # noqa: BLE001
        logger.info("media_asks: search for %r failed: %s", channel, str(exc)[:160])
    return None


def video_size(url: str) -> "int | None":
    """yt-dlp's estimate of the download size in bytes, or None. Blocking (network): call it from a thread."""
    try:
        info = _yt(url, {})
        size = info.get("filesize_approx") or info.get("filesize")
        return int(size) if size else None
    except Exception as exc:  # noqa: BLE001
        logger.info("media_asks: no size for %s: %s", url, str(exc)[:120])
        return None


async def _how_big(url: str) -> str:
    try:
        size = await asyncio.wait_for(asyncio.to_thread(video_size, url), timeout=15.0)
    except Exception:  # noqa: BLE001
        size = None
    return f", about {round(size / 1e6)} MB" if size else ", size not known until it starts"


def _length(seconds) -> str:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "length unknown"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _ordinal(n: int) -> str:
    if n <= 1:
        return "latest"
    word = next((w for w, v in _ORD.items() if v == n), None)
    return f"{word} latest" if word else f"{n}th latest"


async def handle(text: str, resolver=None) -> "dict | None":
    """A reply spec {say, action} for a video ask, or None when this is not one.

    `resolver(channel, n)` is injectable so this can be tested without the network.
    """
    ask = parse(text)
    if not ask:
        return None
    if ask.get("url"):
        remember(video={"url": ask["url"], "title": ask["url"]})
        return {"say": f"Download {ask['url'][:70]}? It goes to your video downloads folder.",
                "action": ("ytdl_download", {"url": ask["url"], "format": "video", "title": ask["url"][:60]})}
    if ask.get("it"):
        vid = remembered()["video"]
        if not vid:
            return {"say": "Download what? Open a video first, or give me its link, "
                           "or say for example “download Trick2G's latest video”.", "action": None}
        return {"say": f"Download “{vid['title']}” ({_length(vid.get('duration'))}{await _how_big(vid['url'])})? "
                       "It goes to your video downloads folder.",
                "action": ("ytdl_download", {"url": vid["url"], "format": vid.get("format", "video"), "title": vid["title"][:80]})}
    src = next((s for s in sources() if s["id"] == ask.get("source")), sources()[0])
    noun = ask.get("noun") or src["nouns"][0]
    channel = ask.get("channel") or remembered()["channel"]
    if not channel:
        return {"say": f"Whose {noun}? Say the channel, for example “open Trick2G's latest {noun}”, "
                       f"or search for them on {src.get('label', 'the site')} first.", "action": None}
    remember(channel=channel)
    try:
        call = (lambda: resolver(channel, ask["n"])) if resolver else (lambda: resolve_latest(channel, ask["n"], src))
        vid = await asyncio.wait_for(asyncio.to_thread(call), timeout=RESOLVE_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.info("media_asks: could not list %r: %s", channel, exc)
        vid = None
    which = _ordinal(ask["n"])
    if not vid:
        return {"say": f"I couldn't get {channel}'s {which} {noun}. Check the channel name, or I can search {src.get('label', 'the site')} for it.",
                "action": None}
    vid = {**vid, "format": src.get("format", "video")}
    remember(video=vid)
    who = vid.get("channel") or channel
    if ask["verb"] in _VERBS_OPEN:
        return {"say": f"Opening {who}'s {which} {noun}: {vid['title']}.",
                "action": ("pc_direct", {"kind": "url", "value": vid["url"], "label": f"{who}'s {which} {noun}"})}
    return {"say": f"Download {who}'s {which} {noun} “{vid['title']}” ({_length(vid.get('duration'))}{await _how_big(vid['url'])})? "
                   "It goes to your downloads folder.",
            "action": ("ytdl_download", {"url": vid["url"], "format": vid["format"], "title": vid["title"][:80]})}
