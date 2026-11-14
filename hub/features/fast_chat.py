"""The fast lane for plain conversation: a short prompt, no thinking, streamed from a small local model, sentence by sentence.

Measured on this PC (14 Nov): with thinking off and a short prompt gemma4:e2b answers in about 0.15 s and gemma4:e4b in 2.6 to 4.1 s with the first word at 0.2 s. The long route
(rules, understanding model, then an answer) took 8 to 35 s for the same sentences in the Hub's own log. Anything that is not plain conversation (opening an app, a question about the
dashboard, a mission, an agent request, a yes or no) never comes here: it takes the long route, which knows how to do those.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import AsyncIterator

import aiohttp

from ..config import logger

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
PREFERRED = ("gemma4:e2b", "gemma4:e4b-32k", "gemma4:e4b")
_TAGS: dict = {"at": 0.0, "names": []}


async def _installed() -> "list[str]":
    if time.time() - _TAGS["at"] < 60 and _TAGS["names"]:
        return _TAGS["names"]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            async with s.get(OLLAMA + "/api/tags") as r:
                names = [m["name"] for m in (await r.json()).get("models", [])]
        _TAGS.update({"at": time.time(), "names": names})
    except Exception:  # noqa: BLE001
        pass
    return _TAGS["names"]


async def pick_model() -> "str | None":
    """The model for quick talk: AGENTHUB_FAST_MODEL, else the smallest preferred one that is installed. None when Ollama is not answering (the long route then handles it)."""
    want = os.environ.get("AGENTHUB_FAST_MODEL")
    names = await _installed()
    if want and want in names:
        return want
    return next((m for m in PREFERRED if m in names), None)


SYSTEM = ("You are {name}, {role} of Agent Hub, a voice assistant on the user's own PC. You are speaking aloud, so answer in one to three short sentences of plain words: no lists, no markdown, no emoji. "
          "Be warm and direct. If the user asks you to do something on the PC or in the Hub, say briefly that you will, and do not pretend it is done. If you do not know, say so in one sentence.")


def split_sentences(buf: str, final: bool = False) -> "tuple[list[str], str]":
    """Complete sentences in `buf` and the unfinished rest. A long run with no stop is cut at a comma, so speech can start before the sentence ends."""
    out, rest = [], buf
    while True:
        m = re.search(r"[.!?]\s+", rest)
        cut = m.end() if m else 0
        if not cut and len(rest) > 150:
            c = rest.rfind(", ", 40, 150)
            cut = c + 2 if c > 0 else 0
        if not cut:
            break
        s = rest[:cut].strip()
        rest = rest[cut:]
        if s:
            out.append(s)
    if final and rest.strip():
        out.append(rest.strip())
        rest = ""
    return out, rest


async def stream(text: str, history: "list | None", name: str, role: str, model: str) -> AsyncIterator[str]:
    """Yield the answer one sentence at a time as the model writes it."""
    msgs = [{"role": "system", "content": SYSTEM.format(name=name, role=role)}]
    for h in (history or [])[-6:]:
        r = "assistant" if h.get("role") in ("assistant", "hub") else "user"
        t = str(h.get("text") or "")[:300]
        if t:
            msgs.append({"role": r, "content": t})
    msgs.append({"role": "user", "content": text[:500]})
    body = {"model": model, "stream": True, "think": False, "messages": msgs, "keep_alive": "10m", "options": {"num_predict": 140, "temperature": 0.6}}
    buf = ""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60, sock_read=30)) as s:
        async with s.post(OLLAMA + "/api/chat", json=body) as r:
            if r.status != 200:
                raise RuntimeError(f"Ollama answered {r.status}")
            async for raw in r.content:
                if not raw.strip():
                    continue
                j = json.loads(raw)
                buf += (j.get("message") or {}).get("content", "")
                sents, buf = split_sentences(buf)
                for sent in sents:
                    yield sent
                if j.get("done"):
                    break
    sents, _ = split_sentences(buf, final=True)
    for sent in sents:
        yield sent
