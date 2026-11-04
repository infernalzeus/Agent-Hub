"""Round 8 batch layout: native pointer clicks, isolated Hub, no real sensors."""
import os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

@pytest.fixture
def page(hub):
    with sync_playwright() as p:
        b=p.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER','msedge'),headless=True)
        ctx=b.new_context(service_workers='block',viewport={'width':1280,'height':800})
        ctx.add_init_script("""navigator.mediaDevices.getUserMedia=async()=>{throw Error('Sensors blocked')};
          localStorage.setItem('agenthub:board:layers',JSON.stringify({order:['system','tools','apps'],hidden:{},members:{'card:oc':'apps'}}));""")
        ctx.request.put(hub+'/api/board/prefs',data='{}',headers={'Content-Type':'application/json'})                 # every test starts from a Hub with no saved board
        pg=ctx.new_page();errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
        pg.goto(hub+'/?enter=1');pg.wait_for_function('!!window.__hubBoard?.active');pg.wait_for_timeout(900)
        yield pg
        assert errors==[]
        ctx.close();b.close()

def press(pg,selector,wait=750):
    e=pg.locator(selector);r=e.bounding_box();assert r
    pg.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2)
    pg.mouse.down();pg.wait_for_timeout(120);pg.mouse.up();pg.wait_for_timeout(wait)

def state(pg):
    return pg.evaluate("JSON.parse(JSON.stringify(__hubBoard.active.state()))")

def scatter(pg):
    pg.evaluate("""()=>{let s=__hubBoard.active.state();Object.entries(s.L).forEach(([id,l],i)=>{l.x=(i%3)*550+31;l.y=(11-i)*190+47;l.u=1;l.rz=1;let e=document.querySelector('.hk[data-id="'+id+'"]');if(e){e.style.left=l.x+'px';e.style.top=l.y+'px'}});s.hid.runs=1;document.querySelector('.hk[data-id=runs]').hidden=true;}""")

def bands(pg,expected_min=None):
    return pg.evaluate("""expected=>{let s=__hubBoard.active.state(),ls=__hubBoard.active.layers(),groups={},fail=[];
      let layer=id=>ls.members[id.split('#')[0]]||(['att','runs','ses','hlt','use'].includes(id)?'system':id.startsWith('act:')?'apps':id.startsWith('app:')&&!['app:movie-clipper','app:file-browser'].includes(id)?'apps':'tools');
      for(let [id,l] of Object.entries(s.L)){let k=layer(id);if(s.hid[id]||ls.hidden[k])continue;
        if(expected!==null&&!!l.min!==!!expected)fail.push(id+' min');if(l.x%16||l.y%16)fail.push(id+' grid');
        (groups[k]||=[]).push({id,x:l.x,y:l.y,r:l.x+l.w,b:l.y+(l.min?32:l.h)});}
      let bottom=-Infinity;for(let k of ls.order){let a=groups[k]||[];if(!a.length)continue;
        if(Math.min(...a.map(v=>v.y))<=bottom)fail.push(k+' band');bottom=Math.max(...a.map(v=>v.b));
        for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++)if(Math.min(a[i].r,a[j].r)>Math.max(a[i].x,a[j].x)&&Math.min(a[i].b,a[j].b)>Math.max(a[i].y,a[j].y))fail.push(a[i].id+' overlaps '+a[j].id);}
      return {fail,groups:Object.keys(groups)};}""",expected_min)

def fitted(pg):
    return pg.evaluate("""()=>{let r=__hubBoard.active.stage(),s=__hubBoard.active.state();return [...document.querySelectorAll('.hk')].filter(e=>!s.hid[e.dataset.id]&&!e.hidden).filter(e=>{let b=e.getBoundingClientRect();return b.left<r.left-2||b.top<r.top-2||b.right>r.right+2||b.bottom>r.bottom+2}).map(e=>e.dataset.id)}""")

@pytest.mark.parametrize('mode',['cad','3d'])
def test_native_batch_restore_tidy_and_persistence(page,mode):
    page.evaluate('(m)=>__hubBoard.active.view().setMode(m)',mode);page.wait_for_timeout(600)
    scatter(page);before=state(page);layers=page.evaluate('JSON.stringify(__hubBoard.active.layers())')
    press(page,'[data-batch=minimise]')
    result=bands(page,True);assert result['fail']==[];assert set(result['groups'])=={'system','tools','apps'}
    assert fitted(page)==[]
    assert state(page)['L']['runs']==before['L']['runs'];assert state(page)['hid']==before['hid']
    press(page,'[data-batch=maximise]');assert bands(page,False)['fail']==[]
    assert fitted(page)==[]
    after=state(page)
    for id,l in before['L'].items():assert (after['L'][id]['w'],after['L'][id]['h'])==(l['w'],l['h'])
    assert page.evaluate('JSON.stringify(__hubBoard.active.layers())')==layers
    scatter(page);press(page,'.hb-btn:text-is("TIDY")');assert [x for x in bands(page)['fail'] if 'band' not in x]==[]       # TIDY neatens in place: grid, no overlaps; it does not deal the layers into bands
    press(page,'[data-batch=minimise]');saved=page.evaluate("JSON.parse(localStorage.getItem('agenthub:board:v2'))")
    page.reload();page.wait_for_function('!!window.__hubBoard?.active');page.wait_for_timeout(900)
    assert bands(page,True)['fail']==[]
    for id,l in saved['L'].items():
        now=state(page)['L'][id];assert (now['x'],now['y'],now['w'],now['h'],bool(now.get('min')))==(l['x'],l['y'],l['w'],l['h'],bool(l.get('min')))
    assert state(page)['hid']==saved['hid']

def test_glide_uses_only_reduced_motion_and_hidden_layer_untouched(page):
    page.evaluate("__hubBoard.active.layers().hidden.tools=true");scatter(page);before=state(page)
    page.evaluate("if(window.DepthLift)DepthLift.software=true")
    press(page,'[data-batch=minimise]',wait=100);mid=state(page)
    page.wait_for_timeout(650);after=state(page)
    assert mid['L']['att']['y']!=before['L']['att']['y'] and mid['L']['att']['y']!=after['L']['att']['y']
    assert mid['V']!=after['V']
    for id in ['card:ytdl','card:yt']: 
        if id in before['L']:assert before['L'][id]==after['L'][id]
    page.emulate_media(reduced_motion='reduce');scatter(page);press(page,'[data-batch=maximise]',wait=10)
    assert bands(page,False)['fail']==[]

@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1440),(834,1112),(390,844),(320,568)])
def test_footer_buttons_have_own_lane(page,size):
    page.set_viewport_size(dict(zip(['width','height'],size)));page.wait_for_timeout(350)
    assert page.locator('.hb-right-panel [data-batch]').count()==0
    result=page.evaluate("""()=>{let b=document.querySelector('.hb-batch-controls'),r=b.getBoundingClientRect(),out=[];for(let q of ['.hb-map','.hb-panel-hide','.hb-tray','.hands-log .hl-head','.hb-right-panel']){let e=document.querySelector(q);if(!e||!e.getClientRects().length)continue;let t=e.getBoundingClientRect();if(Math.min(r.right,t.right)>Math.max(r.left,t.left)+1&&Math.min(r.bottom,t.bottom)>Math.max(r.top,t.top)+1)out.push(q)}return {out,inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,style:getComputedStyle(b.firstChild).borderRadius}}""")
    assert result['out']==[];assert result['inside'];assert result['style']=='7px'
    press(page,'.hb-panel-hide');assert page.locator('[data-batch=minimise]').is_visible()
    press(page,'[data-batch=minimise]');assert bands(page,True)['fail']==[]


def test_open_window_keeps_its_size_and_rapid_commands_settle(page):
    page.evaluate("__hubBoard.open('/support')")
    page.wait_for_selector('.hk[data-id="extra:support"].exp iframe')
    before=state(page)['L']['extra:support']
    press(page,'[data-batch=minimise]',wait=10)
    press(page,'[data-batch=maximise]',wait=10)
    press(page,'[data-batch=minimise]',wait=750)
    assert bands(page,True)['fail']==[]
    press(page,'[data-batch=maximise]')
    after=state(page)['L']['extra:support']
    assert after['exp'] and (after['w'],after['h'])==(before['w'],before['h'])
    assert page.locator('.hk[data-id="extra:support"] iframe').is_visible()
    assert bands(page,False)['fail']==[]


def test_empty_board_batch_commands_do_not_reveal_hidden_layers(page):
    page.evaluate("()=>{let l=__hubBoard.active.layers();l.hidden={system:true,tools:true,apps:true}}")
    before=state(page)
    press(page,'[data-batch=minimise]');press(page,'[data-batch=maximise]')
    assert state(page)==before


def test_tidy_keeps_things_where_they_were_left(page):
    page.evaluate("""()=>{let s=__hubBoard.active.state();Object.entries(s.L).forEach(([id,l],i)=>{l.x=(i%5)*480+48;l.y=Math.floor(i/5)*720+64;l.u=1;let e=document.querySelector('.hk[data-id="'+id+'"]');if(e){e.style.left=l.x+'px';e.style.top=l.y+'px'}})}""")
    before={k:(v['x'],v['y'],v['w'],v['h']) for k,v in state(page)['L'].items()}
    layers=page.evaluate('JSON.stringify(__hubBoard.active.layers())')
    press(page,'.hb-btn:text-is("TIDY")')
    after=state(page)['L']
    moved=[k for k,v in before.items() if (after[k]['x'],after[k]['y'])!=(v[0],v[1])]
    assert len(moved)<=2,moved                                              # already grid-aligned and apart: nothing needs to move
    assert all((after[k]['w'],after[k]['h'])==(v[2],v[3]) for k,v in before.items())
    assert page.evaluate('JSON.stringify(__hubBoard.active.layers())')==layers
    xs={round(after[k]['x']) for k in after if not state(page)['hid'].get(k)}
    assert len(xs)>3                                                       # not squeezed into three columns

def test_layout_is_kept_on_the_hub_and_comes_back_without_local_storage(page,hub):
    page.evaluate("""()=>{let s=__hubBoard.active.state();s.L.hlt.x=1232;s.L.hlt.y=640;s.L.hlt.u=1;let e=document.querySelector('.hk[data-id=hlt]');e.style.left='1232px';e.style.top='640px'}""")
    press(page,'.hb-btn:text-is("TIDY")',wait=1800)                           # any save pushes the layout to the Hub after a short pause
    want=state(page)['L']['hlt']
    got=page.evaluate("fetch('/api/board/prefs').then(r=>r.json())")
    assert got['board']['L']['hlt']['x']==want['x'] and got['board']['L']['hlt']['y']==want['y']
    page.evaluate("()=>{localStorage.removeItem('agenthub:board:v2');localStorage.removeItem('agenthub:board:at')}")
    page.reload();page.wait_for_function('!!window.__hubBoard?.active');page.wait_for_timeout(1500)
    now=state(page)['L']['hlt'];assert (now['x'],now['y'])==(want['x'],want['y'])


def test_blocks_menu_names_are_plain_sentences_and_a_minimised_block_opens_when_clicked(page):
    press(page,'.hb-btn:text-is("BLOCKS")')
    names=page.evaluate("[...document.querySelectorAll('.hb-jump button')].map(b=>b.textContent)")
    assert 'Needs attention' in names and 'Claude Code usage' in names and 'Runs' in names, names
    assert not [n for n in names if n==n.upper() and len(n)>3 and n not in ('Auto-LLM',)], names
    page.keyboard.press('Escape');page.wait_for_timeout(300)
    page.evaluate("()=>{let s=__hubBoard.active.state();s.L.hlt.min=1;let e=document.querySelector('.hk[data-id=hlt]');e.classList.add('min');e.style.height='32px'}")
    t=page.locator('.hk[data-id=hlt] .hk-h .t');r=t.bounding_box()
    page.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2);page.mouse.down();page.wait_for_timeout(80);page.mouse.up();page.wait_for_timeout(500)
    assert not state(page)['L']['hlt'].get('min')                           # a click on a minimised block opens it again, even with nothing inside to open
