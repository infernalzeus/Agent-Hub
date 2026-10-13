"""Has the person finished their sentence? Two small local models answer that.

* Silero VAD (MIT, ~2 MB): is there speech in this audio at all? It rejects room
  noise before Whisper is asked to "transcribe" it.
* Smart Turn v3.2 (BSD-2, ~8 MB): given the last 8 seconds of the person's turn,
  how likely is it that they are done, from pace and intonation. A pause inside
  a sentence scores low; a finished command scores high.

Both run on CPU through onnxruntime. Neither is bundled: they are fetched once,
on an explicit request, into the hub's state folder. Without them, or without
onnxruntime, every function here reports "no model" and the caller falls back to
its own heuristic - turn-taking never depends on a download having happened.

Smart Turn expects the whole current turn, so audio is kept per turn id and only
the last 8 s are shown to the model.
"""
from __future__ import annotations

import io
import threading
import time
import urllib.request
from pathlib import Path

from .config import logger
from .runtime import STATE

MODELS = STATE / "models"
SMART = MODELS / "smart-turn-v3.2-cpu.onnx"
VAD = MODELS / "silero_vad.onnx"
SOURCES = {
    SMART: ("https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/main/smart-turn-v3.2-cpu.onnx", 8_679_182),
    VAD: ("https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx", 2_327_524),
}
SR = 16000
TURN_SECONDS = 8
COMPLETE_AT = 0.5
SPEECH_AT = 0.5
KEEP_TURNS_S = 120

_lock = threading.Lock()
_sessions: dict = {}
_turns: "dict[str, dict]" = {}
_fe = None


def _ort():
    try:
        import onnxruntime as ort
        return ort
    except Exception:
        return None


def status() -> dict:
    return {"runtime": _ort() is not None,
            "smart_turn": SMART.exists(), "vad": VAD.exists(),
            "ready": _ort() is not None and SMART.exists(),
            "download_mb": round(sum(s for _, s in SOURCES.values()) / 1e6, 1)}


def install(progress=None) -> dict:
    """Fetch both models. Called only from an explicit request; never at start-up."""
    MODELS.mkdir(parents=True, exist_ok=True)
    for path, (url, size) in SOURCES.items():
        if path.exists() and path.stat().st_size == size:
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        if tmp.stat().st_size != size:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"{path.name} came back the wrong size")
        tmp.replace(path)
        if progress:
            progress(path.name)
    _sessions.clear()
    return status()


def _session(path: Path):
    ort = _ort()
    if ort is None or not path.exists():
        return None
    with _lock:
        if str(path) not in _sessions:
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            _sessions[str(path)] = ort.InferenceSession(str(path), sess_options=opts,
                                                        providers=["CPUExecutionProvider"])
        return _sessions[str(path)]


def decode(blob: bytes):
    """Any browser recording -> 16 kHz mono float32."""
    from faster_whisper.audio import decode_audio
    return decode_audio(io.BytesIO(blob), sampling_rate=SR)


# ── voice activity ───────────────────────────────────────────────────────────
def speech_fraction(audio) -> "float | None":
    """Share of 32 ms windows holding speech, or None when the model is not there."""
    import numpy as np
    sess = _session(VAD)
    if sess is None or len(audio) < 512:
        return None
    state = np.zeros((2, 1, 128), dtype="float32")
    context = np.zeros((1, 64), dtype="float32")
    sr = np.array(SR, dtype="int64")
    hits = total = 0
    for i in range(0, len(audio) - 511, 512):
        chunk = audio[i:i + 512].astype("float32")[None, :]
        x = np.concatenate([context, chunk], axis=1)
        out, state = sess.run(None, {"input": x, "state": state, "sr": sr})
        context = x[:, -64:]
        total += 1
        hits += int(float(out.reshape(-1)[0]) >= SPEECH_AT)
    return hits / total if total else None


# ── end of turn ──────────────────────────────────────────────────────────────
def _features(audio):
    import numpy as np
    global _fe
    from faster_whisper.feature_extractor import FeatureExtractor
    if _fe is None:
        _fe = FeatureExtractor(feature_size=80, sampling_rate=SR, hop_length=160,
                               chunk_length=TURN_SECONDS, n_fft=400)
    n = SR * TURN_SECONDS
    a = np.asarray(audio, dtype="float32")[-n:]
    if len(a) < n:                                   # silence in front, so the speech sits at the end
        a = np.concatenate([np.zeros(n - len(a), dtype="float32"), a])
    a = (a - a.mean()) / np.sqrt(a.var() + 1e-7)     # the model was trained on normalised waveforms
    mel = _fe(a, padding=0)
    return mel[None, :, :800].astype("float32")


def probability_complete(audio) -> "float | None":
    import numpy as np
    sess = _session(SMART)
    if sess is None or audio is None or len(audio) < SR // 5:
        return None
    out = sess.run(None, {"input_features": _features(audio)})[0]
    v = float(np.asarray(out).reshape(-1)[0])
    if not 0.0 <= v <= 1.0:                          # a raw logit, not a probability
        v = 1.0 / (1.0 + np.exp(-v))
    return v


def judge(turn_id: str, blob: bytes, reset: bool = False) -> dict:
    """One more segment of the person's turn. Says whether the turn looks finished."""
    now = time.time()
    for k in [k for k, v in _turns.items() if now - v["at"] > KEEP_TURNS_S]:
        _turns.pop(k, None)
    try:
        audio = decode(blob)
    except Exception as exc:
        logger.info("turn: could not decode a segment: %s", exc)
        return {"model": False, "why": "audio could not be decoded"}
    import numpy as np
    speech = speech_fraction(audio)
    t = _turns.get(turn_id)
    if reset or t is None:
        t = _turns[turn_id] = {"audio": np.zeros(0, dtype="float32"), "at": now}
    t["audio"] = np.concatenate([t["audio"], audio])[-SR * 20:]
    t["at"] = now
    p = probability_complete(t["audio"])
    if p is None:
        return {"model": False, "speech": speech, "why": "turn model not installed"}
    return {"model": True, "p": round(p, 3), "complete": p >= COMPLETE_AT, "speech": speech,
            "seconds": round(len(t["audio"]) / SR, 1)}


def end_turn(turn_id: str) -> None:
    _turns.pop(turn_id, None)
