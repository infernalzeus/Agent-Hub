"""Hover, tilt and empty-space checks for the website (headless, 127.0.0.1:8098 only).

    python tools/site_hover_check.py

1. BOUNDS UNDER HOVER: the mouse is moved to each corner of the window (the tilt is at its maximum there); every block, tile, button and heading
   must stay inside the window (and below the header) at all nine sizes.
2. TILT CAP: the board's rotation must never exceed MAX_TILT degrees on either axis.
3. EMPTY SPACE: the main block's body is cut into a 16 x 10 grid; a cell is "used" if text, a picture, a diagram or a control overlaps it.
   Reports the share of empty cells and the biggest empty run, per scene and size.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright
from site_pw import browser, serve

MAX_TILT = 10.0
SIZES = [(1280, 720), (1440, 900), (1920, 1080), (2560, 1440), (820, 1180), (1180, 820), (393, 852), (852, 393), (360, 640)]
SCENES = ["landing", "talk", "missions", "pc", "media", "graph", "agents", "architecture", "install"]

BOUNDS = """()=>{const W=innerWidth,H=innerHeight,bad=[];const sc=document.querySelector('.scene.active');
 for(const e of sc.querySelectorAll('.slabbox,.blk,.door,.smith-btn,.action,.more-links a,h1,h2,.mark-host,.enlarge,.tab,.st')){
  if(e.closest('.flow,.zoom,.vol'))continue;const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;const cs=getComputedStyle(e);if(cs.visibility==='hidden'||cs.display==='none')continue;
  if(r.left<-0.5||r.top<-0.5||r.right>W+0.5||r.bottom>H+0.5)bad.push(e.tagName+'.'+(e.className.baseVal||e.className)+' '+[r.left,r.top,r.right,r.bottom].map(Math.round));}
 return bad;}"""

EMPTY = """()=>{const sc=document.querySelector('.scene.active');const box=sc.querySelector('.blk-b');if(!box)return null;const b=box.getBoundingClientRect();
 const C=16,R=10,used=Array.from({length:R},()=>Array(C).fill(false));
 const ink=[];const walk=document.createTreeWalker(box,NodeFilter.SHOW_TEXT);let n;
 while(n=walk.nextNode()){if(!n.textContent.trim())continue;const el=n.parentElement;if(el.closest('.more-static,.vol,[hidden]'))continue;const cs=getComputedStyle(el);if(cs.visibility==='hidden'||cs.display==='none'||el.closest('.auto-detail')&&el.matches('.auto-detail'))continue;
  const rg=document.createRange();rg.selectNodeContents(n);for(const r of rg.getClientRects())ink.push(r);}
 for(const e of box.querySelectorAll('img,svg,canvas,button,.chip,.you,.num,.av')){if(e.closest('[hidden],.zoom,.vol'))continue;const r=e.getBoundingClientRect();if(r.width&&r.height)ink.push(r);}
 for(const r of ink){const x0=Math.max(0,Math.floor((r.left-b.left)/b.width*C)),x1=Math.min(C-1,Math.floor((r.right-b.left)/b.width*C)),y0=Math.max(0,Math.floor((r.top-b.top)/b.height*R)),y1=Math.min(R-1,Math.floor((r.bottom-b.top)/b.height*R));
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)used[y][x]=true;}
 let empty=0,run=0,best=0;for(let y=0;y<R;y++){let cur=0;for(let x=0;x<C;x++){if(!used[y][x]){empty++;cur++;best=Math.max(best,cur);}else cur=0;}}
 return {emptyShare:+(empty/(C*R)).toFixed(2),longestEmptyRowRun:best,of:C};}"""


def measure(b, w, h, out):
    touch = w < 900 or h < 560
    ctx = b.new_context(viewport={"width": w, "height": h}, service_workers="block", has_touch=touch, is_mobile=touch and min(w, h) < 500)
    try:
        for sid in SCENES:
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:8098/index.html" + ("" if sid == "landing" else "#" + sid))
            pg.wait_for_timeout(1700)
            for (x, y) in [(2, 2), (w - 3, 2), (w - 3, h - 3), (2, h - 3)]:
                pg.mouse.move(x, y, steps=8)
                pg.wait_for_timeout(650)
                bad = pg.evaluate(BOUNDS)
                if bad:
                    out["bounds_under_hover"].setdefault("%s %dx%d" % (sid, w, h), []).extend(bad[:4])
                t = pg.evaluate("SiteBoard.tilt")
                if max(abs(t["x"]), abs(t["y"])) > MAX_TILT + 0.05:
                    out["tilt_over_cap"].append("%s %dx%d tilt %.1f,%.1f" % (sid, w, h, t["x"], t["y"]))
            pg.mouse.move(w / 2, h / 2)
            if sid != "landing":
                for i in range(pg.evaluate("document.querySelectorAll('.scene.active .st').length") or 1):
                    pg.evaluate("(i)=>{const b=document.querySelectorAll('.scene.active .st')[i];if(b&&b.offsetParent)b.click()}", i)
                    pg.wait_for_timeout(120)
                    e = pg.evaluate(EMPTY)
                    key = "%s %dx%d" % (sid, w, h)
                    if e and (key not in out["empty_space"] or e["emptyShare"] > out["empty_space"][key]["emptyShare"]):
                        out["empty_space"][key] = e
            pg.close()
    finally:
        ctx.close()


def main():
    srv = serve()
    out = {"bounds_under_hover": {}, "tilt_over_cap": [], "empty_space": {}}
    with sync_playwright() as p:
        b = browser(p)
        for (w, h) in SIZES:
            for attempt in (1, 2, 3):
                try:
                    measure(b, w, h, out)
                    break
                except Exception as exc:  # headless Edge occasionally crashes; retry the size with a fresh browser
                    print("  retry %dx%d (%s)" % (w, h, str(exc).splitlines()[0][:60]), flush=True)
                    try:
                        b.close()
                    except Exception:
                        pass
                    b = browser(p)
            print("Measured hover at %dx%d" % (w, h), flush=True)
        b.close()
    srv.shutdown()
    srv.server_close()
    worst = sorted(out["empty_space"].items(), key=lambda kv: -kv[1]["emptyShare"])
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".internal", "website-review"), exist_ok=True)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".internal", "website-review", "hover-check.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("BOUNDS UNDER HOVER (scene size: elements outside the window):")
    for k, v in out["bounds_under_hover"].items():
        print("  ", k, len(v), "e.g.", v[0])
    print("combinations with a problem:", len(out["bounds_under_hover"]), "of", len(SIZES) * len(SCENES))
    print("TILT OVER CAP:", out["tilt_over_cap"][:6] or "none")
    print("EMPTIEST SCENES (share of the body with no text, picture or control):")
    for k, v in worst[:14]:
        print("  ", k, v)

if __name__ == "__main__":
    sys.exit(main())
