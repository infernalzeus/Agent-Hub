"""Capture the screen and find an anchor in it, as a child process.

The hub's core is aiohttp alone, so an installed build has no numpy and no
Pillow in-process. Optional tools live in their own managed runtime instead
(`runtime.python_for`), which the hub cannot import from — only run. This script
is that runtime's side of the wall: it grabs a frame, scores one anchor against
it, and prints a single JSON line.

    vision_worker.py <anchor.png> [frame.png]

With no frame it captures the screen itself. Output:
    {"ok": true, "x": 812, "y": 455, "score": 0.97}
    {"ok": false, "error": "..."}

Kept deliberately small and dependency-light: numpy and Pillow, nothing else.
The matching maths is the same normalised cross-correlation the in-process path
uses, so a routine recorded on one scores identically on the other.
"""
import json
import sys


def match(frame, anchor):
    """See hub/features/machine_routines.py::match_anchor — same formulation."""
    import numpy as np
    frame = np.asarray(frame, dtype=np.float64)
    anchor = np.asarray(anchor, dtype=np.float64)
    fh, fw = frame.shape
    ah, aw = anchor.shape
    if ah > fh or aw > fw or ah == 0 or aw == 0:
        return None
    a_zero = anchor - anchor.mean()
    a_ss = float((a_zero ** 2).sum())
    if a_ss <= 1e-9:
        return None

    shape = (fh + ah - 1, fw + aw - 1)
    fsize = tuple(1 << int(np.ceil(np.log2(s))) for s in shape)
    corr = np.fft.irfft2(np.fft.rfft2(frame, fsize) * np.fft.rfft2(a_zero[::-1, ::-1], fsize),
                         fsize)[ah - 1:fh, aw - 1:fw]

    s1 = np.pad(frame, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s2 = np.pad(frame ** 2, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def window(t):
        return t[ah:, aw:] - t[:-ah, aw:] - t[ah:, :-aw] + t[:-ah, :-aw]

    n = ah * aw
    win_sum, win_sq = window(s1), window(s2)
    den = np.sqrt(np.maximum(win_sq - (win_sum ** 2) / n, 0.0) * a_ss)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(den > 1e-9, corr / den, 0.0)

    idx = int(np.argmax(score))
    top, left = divmod(idx, score.shape[1])
    return left + aw // 2, top + ah // 2, float(np.clip(score[top, left], -1.0, 1.0))


def main() -> int:
    try:
        import numpy as np
        from PIL import Image, ImageGrab
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"imaging runtime incomplete: {exc}"}))
        return 1
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: vision_worker.py <anchor.png> [frame.png]"}))
        return 2
    try:
        anchor = Image.open(sys.argv[1])
        frame = Image.open(sys.argv[2]) if len(sys.argv) > 2 else ImageGrab.grab()
        gray = lambda im: np.asarray(im.convert("L"), dtype=np.float64)  # noqa: E731
        found = match(gray(frame), gray(anchor))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:300]}))
        return 1
    if not found:
        print(json.dumps({"ok": False, "error": "anchor does not fit the frame, or is featureless"}))
        return 0
    x, y, score = found
    print(json.dumps({"ok": True, "x": int(x), "y": int(y), "score": round(score, 6)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
