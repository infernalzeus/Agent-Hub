"""Cut short skeleton-hand clips for the website out of saved hand traces.

A trace (hub/data/hands/trace-*.json, written by the Hub's HANDS > SAVE) holds 21 joint positions per frame and what the engine decided; no
camera pictures. This script replays them through the real gesture engine (node), picks one clean window per gesture and writes
docs/assets/hand-clips.js, which the website's hand section plays back as an animated skeleton beside an illustrative board.

    python tools/build_hand_clips.py

The traces are the owner's own and stay out of git; only the output (joint numbers, no pictures) is committed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACES = sorted((ROOT / "hub" / "data" / "hands").glob("trace-*.json"))
OUT = ROOT / "docs" / "assets" / "hand-clips.js"
NODE = r"""
const G=require(process.argv[2]);const fs=require('fs');
const out=[];
for(const file of process.argv.slice(3)){
  const t=JSON.parse(fs.readFileSync(file,'utf8'));const e=new G.Engine({tripleZoom:true});const frames=[];
  for(const f of t.frames){
    const o=e.update({landmarks:f.hands.map(h=>h.lm.map(q=>({x:q[0],y:q[1],z:q[2]}))),handedness:f.hands.map(()=>[{categoryName:'Right',score:.9}])},f.t,1280,667,{w:640,h:480});
    const h=o.hands[0];
    frames.push(h?{t:f.t,g:h.gesture,p:h.pinched?1:0,r:h.rpinched?1:0,tr:h.triple?1:0,px:h.palm.x,py:h.palm.y,d:h.depth,tw:h.twist,ro:h.roll,pi:h.pitch,fm:h.fistMax,lm:f.hands[0].lm}:null);
  }
  out.push({file:require('path').basename(file),events:t.events,frames});
}
console.log(JSON.stringify(out));
"""


def replay() -> list:
    js = ROOT / "tools" / "_replay_tmp.cjs"
    js.write_text(NODE, encoding="utf-8")
    try:
        r = subprocess.run(["node", str(js), str(ROOT / "hub" / "static" / "hand-gestures.js"), *map(str, TRACES)],
                           capture_output=True, text=True, check=True, timeout=120)
    finally:
        js.unlink(missing_ok=True)
    return json.loads(r.stdout)


def windows(frames, n):
    """every run of n consecutive frames that all have a hand"""
    for i in range(0, len(frames) - n):
        w = frames[i:i + n]
        if all(w):
            yield i, w


def span(vals):
    return max(vals) - min(vals)


def pick(all_traces, n, score, ok):
    best = None
    for tr in all_traces:
        for i, w in windows(tr["frames"], n):
            if not ok(w):
                continue
            s = score(w)
            if best is None or s > best[0]:
                best = (s, tr["file"], i, w)
    return best


def main() -> int:
    if not TRACES:
        print("no traces in hub/data/hands")
        return 1
    data = replay()
    N = 34
    travel = lambda w: ((w[-1]["px"] - w[0]["px"]) ** 2 + (w[-1]["py"] - w[0]["py"]) ** 2) ** .5
    allp = lambda w, k, v: all(f[k] == v for f in w)
    share = lambda w, fn: sum(1 for f in w if fn(f)) / len(w)
    spec = {
        # name: (score, ok, label for the on-screen chip)
        "point": (lambda w: span([f["px"] for f in w]) + span([f["py"] for f in w]), lambda w: share(w, lambda f: f["g"] == "point") > .9 and not any(f["p"] or f["r"] or f["tr"] for f in w), "POINT"),
        "pinch": (lambda w: travel(w), lambda w: share(w, lambda f: f["p"]) > .6 and share(w, lambda f: not f["p"]) > .08 and not any(f["tr"] for f in w), "PINCH · DRAG"),
        "fist": (lambda w: -span([f["d"] for f in w]), lambda w: share(w, lambda f: f["g"] == "fist") > .9 and span([f["tw"] for f in w]) < .15, "FIST · TAKE CONTROL"),
        "pan": (lambda w: travel(w), lambda w: share(w, lambda f: f["g"] in ("open", "none")) > .9 and not any(f["p"] or f["r"] or f["tr"] for f in w) and span([f["d"] for f in w]) < 9, "PALM · PAN"),
        "zoom": (lambda w: span([f["d"] for f in w]) - .02 * travel(w), lambda w: share(w, lambda f: f["g"] in ("open", "none")) > .9 and not any(f["p"] or f["r"] or f["tr"] for f in w) and travel(w) < 110, "PUSH / PULL · ZOOM"),
        "turn": (lambda w: span([f["tw"] for f in w]) + span([f["ro"] for f in w]), lambda w: share(w, lambda f: f["g"] == "fist") > .9, "FIST · TURN THE WRIST"),
    }
    clips, report = {}, {}
    for name, (score, ok, label) in spec.items():
        b = pick(data, N, score, ok)
        if not b:
            report[name] = "none found"
            continue
        s, file, i, w = b
        report[name] = f"{file} frame {i} score {s:.2f}"
        # mirror like the dashboard overlay, then fit the whole clip into the unit square so the hand fills the view
        xs = [1 - p[0] for f in w for p in f["lm"]]
        ys = [p[1] for f in w for p in f["lm"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        side = max(x1 - x0, y1 - y0) * 1.12
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        def norm(p):
            return [round(((1 - p[0]) - cx) / side * 1000 + 500), round((p[1] - cy) / side * 1000 + 500)]
        d0 = w[0]["d"]
        frames = []
        for f in w:
            frames.append({"j": [v for p in f["lm"] for v in norm(p)],
                           "px": round((f["px"] - w[0]["px"]) / 1280, 3), "py": round((f["py"] - w[0]["py"]) / 667, 3),
                           "k": round(f["d"] / d0, 3), "tw": round(f["tw"], 3), "ro": round(f["ro"], 3), "pi": round(f["pi"], 3),
                           "on": f["p"] or f["tr"] or f["r"], "fist": 1 if f["g"] == "fist" else 0})
        dt = (w[-1]["t"] - w[0]["t"]) / (len(w) - 1)
        clips[name] = {"label": label, "ms": round(dt), "frames": frames}
    OUT.write_text("/* Skeleton clips cut from the owner's own hand recordings (joint numbers only, no pictures). Built by tools/build_hand_clips.py. */\n"
                   "window.HAND_CLIPS=" + json.dumps(clips, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(OUT, OUT.stat().st_size // 1024, "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
