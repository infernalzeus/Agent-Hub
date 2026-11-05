import sys
sys.path.insert(0, "tools")
from playwright.sync_api import sync_playwright
from site_pw import browser, serve
JS = """()=>{const sc=document.querySelector('.scene.active');const els=[...sc.querySelectorAll('a,button,.chip,.smith-card,.enlarge,.tab')].filter(e=>{if(e.closest('.vol,[hidden],.zoom,.flow'))return false;const r=e.getBoundingClientRect();const cs=getComputedStyle(e);return r.width>2&&r.height>2&&cs.visibility!=='hidden'&&cs.display!=='none'});
const out=[];for(let i=0;i<els.length;i++)for(let j=i+1;j<els.length;j++){const a=els[i],b=els[j];if(a.contains(b)||b.contains(a))continue;const p=a.getBoundingClientRect(),q=b.getBoundingClientRect();const ox=Math.min(p.right,q.right)-Math.max(p.left,q.left),oy=Math.min(p.bottom,q.bottom)-Math.max(p.top,q.top);if(ox>3&&oy>3)out.push((a.className||a.tagName)+' x '+(b.className||b.tagName)+' '+Math.round(ox)+'x'+Math.round(oy));}
return out.slice(0,5);}"""
SIZES=[(1280,720),(1440,900),(1920,1080),(820,1180),(1180,820),(393,852),(852,393),(360,640)]
SC=["talk","missions","pc","media","graph","agents","architecture","install"]
srv=serve()
with sync_playwright() as p:
    b=browser(p)
    for w,h in SIZES:
        touch=w<900 or h<560
        ctx=b.new_context(viewport={"width":w,"height":h},service_workers="block",has_touch=touch,is_mobile=touch and min(w,h)<500)
        for sid in SC:
            pg=ctx.new_page();pg.goto("http://127.0.0.1:8098/index.html#"+sid);pg.wait_for_timeout(1500)
            r=pg.evaluate(JS)
            if r:print(sid,w,h,r)
            pg.close()
        ctx.close()
    b.close()
srv.shutdown()
print("done")
