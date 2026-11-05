"""Give every agent picture the same neon look: the same cyan, the same stroke width and the same glow, so no one is brighter than the rest.

  python tools/normalize_agent_icons.py            rewrite hub/static/agent-icons/*.png (and smith.png, neo.png) from their sources
  python tools/normalize_agent_icons.py --check    print each picture's measured brightness and exit 1 when any is off the shared level

Why this exists: the pictures came from different sources (Smith's thin line art, Codex's thick glowing ones, Neo cut from a screenshot), so they looked
brighter or dimmer. The recipe reads each picture's LINES only (ink = alpha x brightest channel, normalised by its own 99.5th percentile, halos below a
threshold dropped), brings the average stroke width to the level of the Smith reference, then paints the same core colour and the same soft glow on all.
Sources: the pictures already in hub/static/agent-icons (their own lines), Smith from the embedded 192 px copy in hub/agents_ui.py, Neo from
.internal/neo-icon/neo-outline-preview.png (not tracked; if it is missing the existing neo.png is used as the source).
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "hub" / "static" / "agent-icons"
WORK = 512          # work at twice the final size, then shrink: thin lines stay smooth
OUT = 256
CORE = np.array([0.07, 0.95, 1.00])     # Smith's own line colour
GLOW = np.array([0.00, 0.78, 1.00])
GLOW_STRENGTH = 0.40
GLOW_SIGMA = 7.0


def _ink_from_rgba(im: Image.Image) -> np.ndarray:
    im = im.convert("RGBA").resize((WORK, WORK), Image.LANCZOS)
    a = np.asarray(im).astype(float) / 255
    return a[..., 3] * a[..., :3].max(axis=2)


def _ink_from_rgb_on_dark(im: Image.Image) -> np.ndarray:
    im = im.convert("RGB").resize((WORK, WORK), Image.LANCZOS)
    a = np.asarray(im).astype(float) / 255
    v = a.max(axis=2)
    bg = np.median(np.concatenate([v[:20, :20].ravel(), v[:20, -20:].ravel(), v[-20:, :20].ravel(), v[-20:, -20:].ravel()]))
    return np.clip((v - bg) / max(1e-3, 1 - bg), 0, 1)


def _smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def disk(r: int) -> np.ndarray:
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y) <= r * r


def lines_only(ink: np.ndarray) -> np.ndarray:
    """The pictures differ in halo (some glow broadly, some not): take the broad bright part away, keep the lines, scale to the picture's own peak."""
    broad = ndi.grey_opening(ink, footprint=disk(7))
    line = np.clip(ink - broad, 0, 1)
    seen = line[line > 0.05]
    p = float(np.percentile(seen, 99.5)) if seen.size else 1.0
    return np.clip(line / max(p, 1e-3), 0, 1)


def stroke_width(m: np.ndarray) -> float:
    """Mean stroke width in work pixels: ink area divided by half its edge length, measured on the lines above half strength."""
    b = _smoothstep(m, 0.35, 0.65)
    gy, gx = np.gradient(b)
    return 2.0 * float(b.sum()) / max(float(np.hypot(gx, gy).sum()), 1e-6)


def with_width(m: np.ndarray, want: float) -> np.ndarray:
    """Thicken or thin the lines until their mean width is `want` (blur, then a threshold found by bisection); left alone when already within 8 per cent."""
    cur = stroke_width(m)
    if want * 0.92 <= cur <= want * 1.08:
        return m
    b = ndi.gaussian_filter(m, max(1.2, want * 0.5))
    lo, hi = 0.05, 0.95
    best = m
    for _ in range(14):
        t = (lo + hi) / 2
        best = _smoothstep(b, t - 0.10, t + 0.10)
        if stroke_width(best) > want:
            lo = t
        else:
            hi = t
    return best


def paint(m: np.ndarray) -> Image.Image:
    g = np.clip(ndi.gaussian_filter(m, GLOW_SIGMA) * 1.6, 0, 1) * GLOW_STRENGTH
    alpha = np.clip(m + g * (1 - m), 0, 1)
    wc = (m[..., None] * CORE + (g * (1 - m))[..., None] * GLOW) / np.maximum(alpha[..., None], 1e-4)
    rgba = np.dstack([np.clip(wc, 0, 1), alpha])
    return Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").resize((OUT, OUT), Image.LANCZOS)


def sources() -> "dict[str, np.ndarray]":
    out: "dict[str, np.ndarray]" = {}
    for f in sorted(ICONS.glob("*.png")):
        if f.stem in ("neo", "smith"):
            continue
        out[f.stem] = _ink_from_rgba(Image.open(f))
    sys.path.insert(0, str(ROOT))
    from hub import agents_ui
    out["smith"] = _ink_from_rgba(Image.open(io.BytesIO(base64.b64decode(agents_ui._SMITH_B64))))
    neo_src = ROOT / ".internal" / "neo-icon" / "neo-outline-preview.png"
    out["neo"] = _ink_from_rgb_on_dark(Image.open(neo_src)) if neo_src.is_file() else _ink_from_rgba(Image.open(ICONS / "neo.png"))
    return out


def measure(im: Image.Image) -> dict:
    """What the eye compares: how bright the lines are, how thick, and how much glow sits around them (not how much is drawn)."""
    a = np.asarray(im.convert("RGBA")).astype(float) / 255
    al = a[..., 3]
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    core = al > 0.8
    big = np.asarray(im.convert("RGBA").resize((WORK, WORK), Image.LANCZOS)).astype(float)[..., 3] / 255
    return {"line": float((al * lum)[core].mean()) if core.any() else 0.0, "width": stroke_width(np.clip(big, 0, 1)),
            "halo": float(al[~core].sum() / max(al[core].sum(), 1.0)), "hue": float((a[..., 0] - a[..., 2])[core].mean()) if core.any() else 0.0}


def main(check: bool) -> int:
    if check:
        rows = {f.stem: measure(Image.open(f)) for f in sorted(ICONS.glob("*.png"))}
        bad = []
        for key in ("line", "width"):
            med = float(np.median([r[key] for r in rows.values()]))
            for k, r in rows.items():
                if abs(r[key] - med) / max(med, 1e-6) > 0.25 and k not in bad:
                    bad.append(k)
        for k, r in rows.items():
            print("%-22s line %.3f  width %.1f  halo %.2f  red-minus-blue %.2f" % (k, r["line"], r["width"], r["halo"], r["hue"]))
        print("off the shared look (line brightness or stroke width more than 25%% from the median): %s" % (", ".join(bad) or "none"))
        return 1 if bad else 0
    src = sources()
    want = stroke_width(lines_only(src["smith"]))
    for name, ink in src.items():
        m = lines_only(ink)
        if name != "smith":
            m = with_width(m, want)
        paint(m).save(ICONS / (name + ".png"), optimize=True)
        print("wrote", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
