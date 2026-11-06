"""site_check.py [shots] -- every scene at every size: nothing scrolls, nothing is clipped or off screen, every step's text fits, touch targets are big enough."""
import sys
import json
from site_pw import serve, browser
from playwright.sync_api import sync_playwright

SIZES = [(1280, 720), (1440, 900), (1920, 1080), (2560, 1440), (820, 1180), (1180, 820), (393, 852), (852, 393), (360, 640)]
SCENES = ["landing", "talk", "missions", "pc", "media", "graph", "agents", "architecture", "install", "hands"]
SHOTS = {(1440, 900), (1920, 1080), (820, 1180), (393, 852), (852, 393)} if "shots" in sys.argv else set()
import os
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".internal", "website-review")
os.makedirs(S, exist_ok=True)

PROBE = """(touch)=>{
 const sc=document.querySelector('.scene.active'),W=innerWidth,H=innerHeight,bad=[];
 const doc=document.scrollingElement;
 if(doc.scrollHeight>H+1||doc.scrollWidth>W+1)bad.push('document scrolls '+doc.scrollWidth+'x'+doc.scrollHeight);
 const skip=e=>e.closest('.flow,.zoom,.arch-open,.vol,canvas,.mark-host,noscript,.more-static,.architecture-viewport .original-map');
 for(const e of sc.querySelectorAll('*')){
  if(skip(e))continue;const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;
  const cs=getComputedStyle(e);if(cs.visibility==='hidden'||cs.display==='none')continue;
  if(r.left<-1||r.top<-1||r.right>W+1||r.bottom>H+1)bad.push('off-screen '+e.tagName+'.'+e.className+' '+[r.left,r.top,r.right,r.bottom].map(Math.round));
  if(touch&&(e.tagName==='BUTTON'||e.tagName==='A')&&(r.width<43||r.height<43))bad.push('small '+e.tagName+'.'+e.className+' '+Math.round(r.width)+'x'+Math.round(r.height));
 }
 for(const e of sc.querySelectorAll('.blk-b,.small-block,.blk-h')){if(e.closest('.flow'))continue;if(e.scrollHeight>e.clientHeight+2&&getComputedStyle(e).overflow!=='visible')bad.push('clipped '+e.className);}
 const d=sc.querySelector('.auto-detail');
 if(d&&d.offsetParent){const dr=d.getBoundingClientRect(),last=[...d.children].filter(c=>c.offsetParent&&!c.classList.contains('bar')).pop();if(last){const lr=last.getBoundingClientRect();if(lr.bottom>dr.bottom+2)bad.push('detail text overflows its panel by '+Math.round(lr.bottom-dr.bottom));}}
 for(const v of sc.querySelectorAll('[data-visual]')){if(!v.offsetParent)continue;if(v.clientHeight<70||!v.querySelector('.screen-body'))bad.push('blank or undersized demonstration');}
 const sheet=sc.querySelector('.blk');if(sheet){const c=getComputedStyle(sheet);if(c.backgroundColor!=='rgba(8, 12, 40, 0.3)'||c.boxShadow==='none')bad.push('dashboard glass material missing');}
 for(const e of sc.querySelectorAll('.screen-body,.ui-proposal,.screen-body>div')){if(e.offsetParent&&e.scrollHeight>e.clientHeight+3)bad.push('preview content clipped: '+e.className);}
 if(sc.querySelector('.vol,[data-more],[data-limit]'))bad.push('obsolete slab or expanding card remains');
 return bad;}"""

POSE_PROBE = """()=>{
 const sc=document.querySelector('.scene.active'),b=sc.querySelector('[data-tilt]'),bad=[];if(!b)return bad;
 const rx=b.style.getPropertyValue('--rx'),ry=b.style.getPropertyValue('--ry');
 for(const x of [-4,4])for(const y of [-4,4]){
  b.style.setProperty('--rx',x+'deg');b.style.setProperty('--ry',y+'deg');
  for(const e of sc.querySelectorAll('.slabbox,.st,.ui-btn,.screen-toolbar button,.circuit-node,.wishlist-form,.door,.smith-btn,.enlarge')){
   const r=e.getBoundingClientRect();if(!r.width||!r.height||!e.offsetParent)continue;
   if(r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)bad.push('maximum pose '+x+','+y+' off-screen '+e.className);
  }
 }
 b.style.setProperty('--rx',rx);b.style.setProperty('--ry',ry);return [...new Set(bad)];}
"""



def main():
    srv = serve()
    problems = {}
    with sync_playwright() as p:
        b = browser(p)
        for (w, h) in SIZES:
            touch = w < 900 or h < 560
            ctx = b.new_context(viewport={"width": w, "height": h}, service_workers="block", has_touch=touch, is_mobile=touch and min(w, h) < 500, device_scale_factor=1)
            for sid in SCENES:
                pg = ctx.new_page()
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto("http://127.0.0.1:8098/index.html" + ("" if sid == "landing" else "#" + sid))
                pg.wait_for_function("window.SiteBoard")
                pg.wait_for_timeout(1300)
                bad = list(pg.evaluate(PROBE, touch))
                n = pg.evaluate("document.querySelectorAll('.scene.active .st').length")
                for i in range(n):
                    pg.evaluate("(i)=>{const b=document.querySelectorAll('.scene.active .st')[i];if(b&&b.offsetParent)b.click()}", i)
                    pg.wait_for_timeout(60)
                    bad += [x for x in pg.evaluate(PROBE, touch) if x not in bad]
                if sid == "agents":
                    pg.locator('[data-tab=skills]').click()
                    for i in range(pg.locator('[data-panel=skills] .st').count()):
                        pg.locator('[data-panel=skills] .st').nth(i).evaluate('e=>e.click()')
                        bad += [x for x in pg.evaluate(PROBE, touch) if x not in bad]
                bad += pg.evaluate(POSE_PROBE)
                if (w, h) in SHOTS:
                    pg.wait_for_timeout(800)
                    pg.screenshot(path=os.path.join(S, "c-%s-%dx%d.png" % (sid, w, h)))
                if errs:
                    bad.append("js errors " + str(errs))
                if bad:
                    problems["%s %dx%d" % (sid, w, h)] = bad[:6]
                pg.close()
            ctx.close()
            print("Measured layout at %dx%d" % (w, h), flush=True)
        b.close()
    srv.shutdown()
    srv.server_close()
    print(json.dumps(problems, indent=1)[:6000] if problems else "ALL CLEAN", len(problems), "problem combinations")
    if problems: raise SystemExit(1)


if __name__ == "__main__":
    main()
