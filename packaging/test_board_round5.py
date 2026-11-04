"""Free stage, non-destructive organising, hand menu and remembered 3D layers."""
import os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

@pytest.fixture
def page(hub):
 with sync_playwright() as pw:
  opts={'headless':os.environ.get('AGENTHUB_TEST_HEADED')!='1','channel':os.environ.get('AGENTHUB_TEST_BROWSER','msedge')}
  browser=pw.chromium.launch(**opts);ctx=browser.new_context(service_workers='block',viewport={'width':1280,'height':800})
  ctx.add_init_script("navigator.mediaDevices.getUserMedia=()=>Promise.reject(new Error('Capture forbidden'))")
  p=ctx.new_page();p.goto(hub+'/?enter=1');p.wait_for_function('!!window.__hubBoard?.active');p.wait_for_timeout(900);yield p;browser.close()

@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1440),(834,1112),(390,844),(320,568)])
@pytest.mark.parametrize('mode',['cad','3d'])
def test_fit_uses_measured_free_stage(page,size,mode):
 page.set_viewport_size(dict(zip(['width','height'],size)));page.evaluate('m=>__hubBoard.active.view().setMode(m)',mode);page.wait_for_timeout(550)
 page.get_by_role('button',name='FIT',exact=True).click();page.wait_for_timeout(900)
 bad=page.evaluate('''()=>{const s=__hubBoard.active.stage();return [...document.querySelectorAll('.hk:not([hidden])')].map(e=>({id:e.dataset.id,r:e.getBoundingClientRect().toJSON()})).filter(({r})=>r.left<s.left-2||r.top<s.top-2||r.right>s.right+2||r.bottom>s.bottom+2)}''')
 assert not bad,bad
 assert page.evaluate("getComputedStyle(document.querySelector('.hb-stage')).clipPath")!='none'

def test_tidy_keeps_sizes_visibility_and_minimised_state(page):
 before=page.evaluate('''async()=>{let b=__hubBoard.active,s=b.state();s.hid.runs=1;s.L.ses.min=1;Object.keys(s.L).forEach((id,i)=>{Object.assign(s.L[id],{x:i%3*17,y:i*23,u:1,rz:1});});s.L.hlt.w=332;let d=await(await fetch('/api/home/state')).json();b.update(d);return JSON.parse(JSON.stringify(s));}''')
 page.locator('.hb-viewbar').get_by_text('TIDY',exact=True).click();page.wait_for_timeout(850)
 after=page.evaluate('__hubBoard.active.state()');assert after['hid']==before['hid']
 for key,l in before['L'].items():
  assert after['L'][key]['w']==l['w'];assert after['L'][key]['h']==l['h'];assert after['L'][key]['min']==l['min']
  if not after['hid'].get(key):assert after['L'][key]['x']%16==0 and after['L'][key]['y']%16==0
 boxes=[(k,l) for k,l in after['L'].items() if not after['hid'].get(k)]
 for i,(a,l) in enumerate(boxes):
  for b,r in boxes[i+1:]:assert not(l['x']<r['x']+r['w'] and r['x']<l['x']+l['w'] and l['y']<r['y']+(32 if r['min'] else r['h']) and r['y']<l['y']+(32 if l['min'] else l['h'])),(a,b)

def test_hand_tools_live_in_the_log_without_starting_capture(page):
 assert page.get_by_role('button',name='MORE',exact=True).count()==0
 assert page.get_by_role('button',name='Hand control options',exact=True).count()==0       # the chevron that did nothing is gone
 page.locator('.hands-log .hl-head').click();page.wait_for_timeout(250)
 assert page.get_by_role('button',name='HAND SETUP',exact=True).is_visible()
 page.get_by_role('button',name='GESTURE LEGEND',exact=True).click();page.wait_for_timeout(300)
 assert page.locator('.hl-legend').is_hidden()                                              # the legend button shows or hides the legend in the log
 page.get_by_role('button',name='GESTURE LEGEND',exact=True).click();page.wait_for_timeout(300);assert page.locator('.hl-legend').is_visible()

@pytest.mark.parametrize('surface',['slab','glass'])
def test_layer_order_hide_and_persistence(page,surface):
 page.evaluate("__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(550)
 if page.locator('[data-surface]').inner_text().lower()!=surface:page.locator('[data-surface]').click()
 page.get_by_role('button',name='LAYERS',exact=True).click()
 row=page.locator('.hb-layer-row').filter(has_text='SYSTEM')
 before=page.locator('.hk[data-id=att]').evaluate("e=>parseFloat(getComputedStyle(e).getPropertyValue('--hb-dz'))")
 row.get_by_role('button',name='FORWARD',exact=True).click();page.wait_for_timeout(400)
 after=page.locator('.hk[data-id=att]').evaluate("e=>parseFloat(getComputedStyle(e).getPropertyValue('--hb-dz'))");assert after-before==140
 row.get_by_title('Show/hide layer',exact=True).click();assert page.locator('.hk[data-id=att]').is_hidden();assert page.locator('.hk-volume[data-id=att]').is_hidden()
 page.reload();page.wait_for_selector('.hb');assert page.locator('.hk[data-id=att]').is_hidden();assert page.evaluate("__hubBoard.active.layers().order.indexOf('system')")==1

def test_tool_windows_keep_their_layer_and_existing_stack_step(page):
 page.evaluate("__hubBoard.active.openTool('/support')");page.wait_for_timeout(650)
 page.locator('.hk[data-id="extra:support"] [data-a=dup]').click();page.wait_for_timeout(650)
 page.locator('.hk[data-id="extra:support#2"] [data-a=dup]').click();page.wait_for_timeout(650)
 values=page.locator('.hk.exp').evaluate_all("es=>es.map(e=>parseFloat(e.style.getPropertyValue('--hb-dz'))).sort((a,b)=>a-b)")
 assert values==[-40,50,140]
 assert page.evaluate("__hubBoard.active.layers().order")==['system','tools','apps']
 page.locator('.hk[data-id="extra:support#3"] .hk-h').click(button='right')
 page.get_by_role('menuitem',name='MOVE TO LAYER: SYSTEM',exact=True).click()
 assert page.locator('.hk.exp').evaluate_all("es=>es.every(e=>parseFloat(e.style.getPropertyValue('--hb-dz'))<=0)")
 page.reload();page.wait_for_selector('.hb');assert page.evaluate("__hubBoard.active.layers().members['extra:support']")=='system'


@pytest.mark.parametrize('mode',['cad','3d'])
def test_separate_reset_layout_restores_defaults_from_background_menu(page,mode):
 page.evaluate("m=>{let b=__hubBoard.active;b.view().setMode(m);b.state().hid.runs=1;b.state().L.ses.min=1}",mode);page.wait_for_timeout(550)
 point=page.evaluate("()=>{let s=__hubBoard.active.stage();for(let y=s.top+20;y<s.bottom-10;y+=20)for(let x=s.left+10;x<s.right-10;x+=20){let e=document.elementFromPoint(x,y);if(e&&e.classList.contains('hb'))return[x,y]}return null}")
 assert point
 page.mouse.click(*point,button='right');page.get_by_role('menuitem',name='RESET LAYOUT',exact=True).click();page.wait_for_timeout(900)
 assert not page.evaluate('__hubBoard.active.state().hid.runs');assert not page.evaluate('__hubBoard.active.state().L.ses.min')


def test_explicit_tool_open_restores_its_hidden_layer(page):
 page.evaluate("__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(550);page.get_by_role('button',name='LAYERS',exact=True).click();page.locator('.hb-layer-row').filter(has_text='TOOLS').get_by_title('Show/hide layer',exact=True).click()
 assert page.locator('.hk[data-id="extra:support"]').is_hidden()
 page.evaluate("__hubBoard.active.openTool('/support')");page.wait_for_timeout(650)
 assert page.locator('.hk[data-id="extra:support"]').is_visible();assert not page.evaluate("!!__hubBoard.active.layers().hidden.tools")
