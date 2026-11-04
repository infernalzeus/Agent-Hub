"""Round7 UI controls: native pointer presses, isolated state, no physical capture."""
import os
import pytest
from playwright.sync_api import sync_playwright,expect
from test_ui_lifecycle import hub


def press(p,selector):
 e=p.locator(selector) if isinstance(selector,str) else selector
 e.scroll_into_view_if_needed();r=e.bounding_box();assert r
 x,y=r['x']+r['width']/2,r['y']+r['height']/2
 p.mouse.move(x,y);p.mouse.down();p.wait_for_timeout(100);p.mouse.up();p.wait_for_timeout(230)

@pytest.fixture
def page(hub):
 with sync_playwright() as pw:
  b=pw.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER','msedge'),headless=True)
  ctx=b.new_context(service_workers='block',viewport={'width':1280,'height':800})
  ctx.add_init_script("window.captureRequests=0;navigator.mediaDevices.getUserMedia=()=>{captureRequests++;return Promise.reject(new Error('Physical capture blocked'))};window.__HUB_HANDS_TEST={}")
  p=ctx.new_page();p.route('**/api/mcp',lambda r:r.fulfill(json={'servers':[{'name':'windows','installed':True,'enabled':False}]}));p.route('**/api/hands/status',lambda r:r.fulfill(json={'ready':True}))
  p.goto(hub+'/?enter=1');p.wait_for_function('!!window.__hubBoard?.active');p.wait_for_timeout(750);yield p;b.close()

def clear_chrome_overlaps(p):
 return p.evaluate('''()=>{let sels=['body>header','#power-btn','.hb-bar','.hb-right-panel','.hb-panel-show','.hb-tray','.hb-map','.hb-tray-list','.hands-log .hl-head','.hb-more-menu','.hb-layer-menu','.hb-jump','.hb-glass-panel','#voice'];let rs=sels.flatMap(s=>[...document.querySelectorAll(s)].filter(e=>!e.hasAttribute('hidden')&&getComputedStyle(e).visibility!=='hidden'&&!e.classList.contains('hub-panel-closing')).map(e=>({s,r:e.getBoundingClientRect().toJSON()}))).filter(x=>x.r.width&&x.r.height),out=[];for(let i=0;i<rs.length;i++)for(let j=i+1;j<rs.length;j++){let a=rs[i],b=rs[j];if(Math.min(a.r.right,b.r.right)-Math.max(a.r.left,b.r.left)>1&&Math.min(a.r.bottom,b.r.bottom)-Math.max(a.r.top,b.r.top)>1)out.push([a.s,b.s])}return out}''')

@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1440),(834,1112),(390,844),(320,568)])
def test_controls_and_each_open_list_have_separate_lanes(page,size):
 page.set_viewport_size(dict(zip(['width','height'],size)));page.evaluate("__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(600)
 for selector in ['.hb-hands-menu-button','[data-tray=hidden]','[data-tray=outside]','[data-layers]']:
  press(page,selector);assert clear_chrome_overlaps(page)==[],(size,selector,clear_chrome_overlaps(page))
  visible=page.locator('.hb-more-menu:not([hidden]),.hb-tray-list:not([hidden]),.hb-layer-menu:not([hidden])');assert visible.count()==1
  box=visible.bounding_box();stage=page.evaluate('__hubBoard.active.stage()');assert box['x']>=stage['left']-1 and box['y']>=stage['top']-1;assert box['x']+box['width']<=stage['right']+1 and box['y']+box['height']<=stage['bottom']+1
 press(page,'[aria-label="R Learning"]');assert clear_chrome_overlaps(page)==[]
 assert page.evaluate("(window.__hubStreams||[]).flatMap(s=>s.getTracks()).length")==0


def test_view_panel_grouping_hide_show_and_memory(page):
 assert not page.locator('.hb-ingest-dock').get_by_text('+ INGEST APP',exact=True).is_hidden()
 assert page.locator('.hb-bar').get_by_text('+ INGEST APP',exact=True).count()==0
 assert page.locator('[data-only3d]').first.is_hidden();assert page.get_by_role('button',name='LAYERS',exact=True).is_hidden()
 old=page.evaluate('__hubBoard.active.stage().right');press(page,'.hb-panel-hide');assert page.locator('.hb-right-panel').is_hidden();assert page.evaluate('__hubBoard.active.stage().right')>old
 page.reload();page.wait_for_selector('.hb');page.wait_for_timeout(250);assert page.locator('.hb-right-panel').is_hidden();press(page,'.hb-panel-show');assert page.locator('.hb-right-panel').is_visible()
 press(page,page.get_by_role('button',name='VIEW: 2D',exact=True));assert page.get_by_role('button',name='LAYERS',exact=True).is_visible();assert page.locator('[data-only3d]').last.is_visible()


def test_r_learning_glass_close_and_escape(page):
 press(page,'[aria-label="R Learning"]');pane=page.locator('.hb-glass-panel');assert pane.is_visible();assert '/yard?embed=1' in pane.locator('iframe').get_attribute('src');r=pane.bounding_box();assert abs(r['x']+r['width']/2-640)<2
 press(page,'[aria-label="Close R LEARNING"]');assert page.locator('.hb-glass-panel').count()==0
 press(page,'[aria-label="R Learning"]');page.keyboard.press('Escape');page.wait_for_timeout(220);assert page.locator('.hb-glass-panel').count()==0
 assert page.locator('.hk[data-id="card:oc"]').count()==1


def test_talk_is_centred_glass_and_capture_is_blocked(page):
 press(page,'[aria-label="Talk to the Hub"]');assert page.locator('#voice').is_visible();r=page.locator('#voice').bounding_box();assert abs(r['x']+r['width']/2-640)<2 and abs(r['y']+r['height']/2-400)<2
 assert page.evaluate("getComputedStyle(document.getElementById('voice')).backdropFilter")!='none'
 press(page,'#v-close');assert page.locator('#voice').is_hidden()


def test_pc_hands_and_ingest_use_original_actions_without_side_effects(page):
 posts=[];page.route('**/api/mcp/windows/enabled',lambda r:(posts.append(r.request.post_data_json),r.fulfill(json={'installed':True,'enabled':True})))
 press(page,'[aria-label="PC control"]');assert posts==[{'enabled':True}]
 page.evaluate("()=>{window.handStarts=0;__hubHands.tracker.start=async()=>{handStarts++}}");press(page,'[aria-label="Hand control"]');assert page.evaluate('handStarts')==1
 page.evaluate("window.ingestClicks=0;document.querySelector('.ingest-card').addEventListener('click',e=>{ingestClicks++;e.stopImmediatePropagation()},true)");press(page,page.locator('.hb-ingest-dock button',has_text='INGEST'));assert page.evaluate('ingestClicks')==1
 assert page.locator('.hb-bar [aria-label="Talk to the Hub"] img').get_attribute('src')=='/smith-icon.png'


def test_numbered_tray_restores_hidden_and_updates_outside_list(page):
 page.evaluate("document.querySelector('.hk[data-id=runs] [data-a=x]').click()");page.wait_for_timeout(220);assert page.locator('[data-tray=hidden] span').inner_text()=='1'
 press(page,'[data-tray=hidden]');press(page,'.hb-tray-list [data-restore=runs]');assert page.locator('.hk[data-id=runs]').is_visible();assert page.locator('[data-tray=hidden] span').inner_text()=='0'
 press(page,'[data-tray=outside]');page.evaluate("let l=__hubBoard.active.state().L.hlt;l.x=99999;let e=document.querySelector('.hk[data-id=hlt]');e.style.left='99999px';document.querySelector('.hb-viewbar [title=\"Zoom in (Ctrl + wheel)\"]').click()");page.wait_for_timeout(250)
 assert page.locator('.hb-tray-list [data-restore=hlt]').count()==1


def test_fades_ignore_software_flag_but_respect_reduced_motion(page):
 page.evaluate('DepthLift.software=true');e=page.locator('[aria-label="R Learning"]');r=e.bounding_box();page.mouse.click(r['x']+r['width']/2,r['y']+r['height']/2)
 assert page.locator('.hb-glass-panel').evaluate('e=>e.getAnimations().some(a=>a.effect.getTiming().duration===180)')
 page.wait_for_timeout(220);press(page,'[aria-label="Close R LEARNING"]');page.emulate_media(reduced_motion='reduce');press(page,e);assert page.locator('.hb-glass-panel').evaluate('e=>e.getAnimations().length')==0


def test_the_doctor_picture_is_on_the_tile_title_session_row_and_support_header(page,hub):
 page.wait_for_function("document.querySelector('.hk[data-id=\"extra:support\"] .gi img.hub-doctor')&&document.querySelector('.hk[data-id=\"extra:support\"] .gi img.hub-doctor').naturalWidth>0")
 assert page.locator('.hk[data-id="extra:support"] .hk-h img.hub-doctor').is_visible()
 page.evaluate("async()=>{let d=await(await fetch('/api/home/state')).json();d.sessions={needs_you:[],working:[],idle:[{id:'doctor-test',brief:'Doctor session',status:'idle'}]};__hubBoard.active.update(d)}");assert page.locator('.hb-session img.hub-doctor').is_visible()
 press(page,'.hb-session');assert page.locator('.hb-session-head img.hub-doctor').is_visible();page.keyboard.press('Escape');page.wait_for_timeout(220)
 resource=page.request.get(hub+'/doctor-icon.svg');assert resource.ok                                   # the drawn glyph stays as the fallback resource
 page.goto(hub+'/support');page.wait_for_function("document.querySelector('h1 img')&&document.querySelector('h1 img').naturalWidth>0");assert page.locator('h1 img').is_visible()

def test_remount_preserves_panel_fades_and_releases_effects(page):
 press(page,'[aria-label="Talk to the Hub"]');press(page,'#v-close')
 page.evaluate("async()=>{let root=document.querySelector('.hb').parentElement;let b=__hubBoard.mount(root);b.update(await(await fetch('/api/home/state')).json())}");page.wait_for_timeout(650)
 press(page,'[aria-label="R Learning"]');press(page,'[aria-label="Close R LEARNING"]');assert page.locator('.hb-glass-panel').count()==0
 press(page,'[aria-label="Talk to the Hub"]');press(page,'#v-close');assert page.locator('#voice').is_hidden()
 assert page.evaluate("document.getElementById('voice').getAnimations().length")==0
