"""Kokoro text-to-speech as a small separate process: reads one JSON request per line on stdin, answers with a JSON header line and then the WAV bytes on stdout.

It runs under the Python that has Kokoro installed (not the Hub's own), loads the model once and keeps it loaded, which is what makes a sentence take about a second instead of
a fresh start. Offline only: it never downloads anything (HF_HUB_OFFLINE), so a voice that is not on this PC is an error, not a download.
"""
import io
import json
import os
import sys
import warnings
import wave

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
warnings.filterwarnings("ignore")
OUT = sys.stdout.buffer
sys.stdout = sys.stderr                              # anything the libraries print must not corrupt the audio stream

import numpy as np  # noqa: E402
from kokoro import KPipeline  # noqa: E402

PIPES = {}


def pipe(voice: str):
    lang = "b" if voice[:1] == "b" else "a"          # a = American English, b = British English
    if lang not in PIPES:
        PIPES[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    return PIPES[lang]


def wav_bytes(audio: "np.ndarray") -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue()


def reply(head: dict, body: bytes = b"") -> None:
    OUT.write((json.dumps(head) + "\n").encode("utf-8"))
    if body:
        OUT.write(body)
    OUT.flush()


def main() -> None:
    reply({"ready": True})
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        req = {}
        try:
            req = json.loads(line)
            voice = str(req["voice"])
            chunks = [a.numpy() if hasattr(a, "numpy") else np.asarray(a) for _, _, a in pipe(voice)(str(req["text"]), voice=voice, speed=float(req.get("speed") or 1.0))]
            audio = np.concatenate(chunks) if chunks else np.zeros(2400, dtype="float32")
            body = wav_bytes(audio)
            reply({"id": req.get("id"), "ok": True, "n": len(body)}, body)
        except Exception as exc:  # noqa: BLE001
            reply({"id": req.get("id") if isinstance(req, dict) else None, "ok": False, "err": f"{type(exc).__name__}: {str(exc)[:160]}"})


if __name__ == "__main__":
    main()
