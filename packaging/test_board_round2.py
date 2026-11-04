"""Dashboard contracts on isolated state; real GPU evidence is opt-in."""
import os
import json
from io import BytesIO
import pytest
from PIL import Image
from test_ui_lifecycle import hub
from test_board_round3 import press
from playwright.sync_api import sync_playwright

@pytest.fixture
def page(hub):
 with sync_playwright() as pw:
  opts={'headless':os.environ.get('AGENTHUB_TEST_HEADED')!='1'}
  if os.environ.get('AGENTHUB_TEST_BROWSER'):opts['channel']=os.environ['AGENTHUB_TEST_BROWSER']
  b=pw.chromium.launch(**opts)
  ctx=b.new_context(viewport={'width':1280,'height':667},service_workers='block')
  ctx.add_init_script("navigator.mediaDevices.getUserMedia=()=>Promise.reject(new Error('Camera and microphone disabled in UI tests'))")
  p=ctx.new_page();p.goto(hub+'/?enter=1');p.wait_for_selector('.hk');p.wait_for_timeout(800)
  yield p
  b.close()

def more(page):
 if not page.locator('.hb-more-menu').is_visible():press(page,'.hb-bar>button:last-child')

@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1440),(834,1112),(390,844),(320,568)])
def test_chrome_controls_have_separate_lanes(page,size):
 page.set_viewport_size({'width':size[0],'height':size[1]});page.wait_for_timeout(700)
 rows=page.evaluate("""()=>{let sels=['body>header','#power-btn','.hb-bar','.hb-map','.hb-right-panel','.hb-tray'];return sels.flatMap(s=>{let e=document.querySelector(s);if(!e||!e.getClientRects().length||!e.children.length&&s==='.hb-tray')return [];let r=e.getBoundingClientRect();if(!r.width||!r.height)return [];return [{s,x:r.x,y:r.y,w:r.width,h:r.height}]})}""")
 for r in rows:
  assert r['x']>=-1 and r['y']>=-1 and r['x']+r['w']<=size[0]+1 and r['y']+r['h']<=size[1]+1,(size,r)
 for i,a in enumerate(rows):
  for b in rows[i+1:]:
   assert min(a['x']+a['w'],b['x']+b['w'])-max(a['x'],b['x'])<1 or min(a['y']+a['h'],b['y']+b['h'])-max(a['y'],b['y'])<1,(size,a,b)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert page.locator('body>header button,body>header a').evaluate_all("es=>es.filter(e=>e.getClientRects().length).every(e=>{let r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})")


def test_setup_dismiss_survives_reload(page):
 page.locator('#setup-card').evaluate('(e)=>e.hidden=false')
 press(page,'.sc-dismiss');assert page.locator('#setup-card').is_hidden()
 page.reload();page.wait_for_selector('.hk');page.wait_for_timeout(500)
 assert page.locator('#setup-card').is_hidden()


def test_more_closes_outside_and_escape(page):
 more(page);page.keyboard.press('Escape');page.wait_for_timeout(220);assert page.locator('.hb-more-menu').is_hidden()
 more(page);page.mouse.click(15,300);page.wait_for_timeout(220);assert page.locator('.hb-more-menu').is_hidden()


def test_bin_drop_hides_and_tray_restores(page):
 a=page.locator('.hk[data-id=runs] .hk-h').bounding_box();b=page.locator('#edit-toggle').bounding_box()
 page.mouse.move(a['x']+12,a['y']+12);page.mouse.down();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2,steps=15)
 assert page.locator('#edit-toggle').evaluate("e=>e.classList.contains('drop-target')")
 page.mouse.up();assert page.locator('.hk[data-id=runs]').is_hidden()
 press(page,'[data-tray=hidden]');page.locator('[data-restore=runs]').click();assert page.locator('.hk[data-id=runs]').is_visible()


def test_sessions_are_keyboard_actions(page):
 page.evaluate("async()=>{let d=await(await fetch('/api/home/state')).json();d.sessions={needs_you:[],working:[{id:'sample',brief:'Code session',project:'Example',status:'working',last:'Review progress'}],idle:[]};__hubBoard.active.update(d)}")
 press(page,'.hb-session')
 assert 'Review progress' in page.locator('.hb-session-detail').inner_text()
 page.keyboard.press('Escape');page.wait_for_timeout(220);assert page.locator('.hb-session-detail').count()==0


def test_duplicate_graphics_chip_is_deduplicated(page):
 page.evaluate("()=>{for(let i=0;i<2;i++){let e=document.createElement('div');e.id='hub-graphics-chip';e.textContent='Software graphics';document.body.appendChild(e)}}")
 page.wait_for_timeout(100);assert page.locator('#hub-graphics-chip').count()==1


def test_back_pane_keeps_iframe_pixels(page):
 page.evaluate("__hubBoard.applyUi({blocks:[{id:'extra:support'},{id:'hlt'}]})");page.wait_for_timeout(650)
 page.locator('.hk[data-id="extra:support"] .hk-app').click();page.wait_for_timeout(900)
 block=page.locator('.hk[data-id="extra:support"]')
 block.locator('iframe').evaluate("f=>{f.removeAttribute('src');f.srcdoc='<body style=\"margin:0;background:#ee22cc;color:#41ebff;font-size:48px\">LIVE EMBEDDED PANE</body>';f.style.opacity=1}")
 page.wait_for_timeout(400)
 page.evaluate("()=>{let v=__hubBoard.active.view();v.setMode('3d')}");page.wait_for_timeout(500)
 page.locator('.gz-tools button').first.click()
 page.evaluate("()=>{let v=__hubBoard.active.view(),t=v.tilt();v.orbitBy((180-t.ry)*4,t.rx*4)}")
 page.wait_for_timeout(300)
 im=Image.open(BytesIO(page.screenshot())).convert('RGB')
 count=sum(r>150 and b>100 and g<100 for r,g,b in im.getdata())
 assert count>10000,count


def test_app_open_sequence_and_stop_keep_both_blocks(page):
 page.route('**/api/start/*',lambda r:r.fulfill(json={'base_path':'/support'}))
 page.route('**/api/stop/*',lambda r:r.fulfill(json={'ok':True}))
 page.evaluate("async()=>{APP_LIST.push({id:'movie-clipper',name:'Movie Clipper',running:true});let d=await(await fetch('/api/home/state')).json();d.health.apps.running=['file-browser','movie-clipper'];__hubBoard.active.update(d)}")
 for id in ['file-browser','movie-clipper']:
  page.evaluate("id=>__hubBoard.applyUi({blocks:[{id:'app:'+id},{id:'hlt'}]})",id);page.wait_for_timeout(650)
  page.locator('.hk[data-id="app:'+id+'"] .hk-app').click();page.wait_for_timeout(800)
 assert page.locator('.hk[data-id="app:file-browser"].exp').count()==1
 assert page.locator('.hk[data-id="app:movie-clipper"].exp').count()==1
 for id in ['file-browser','movie-clipper']:
  assert page.evaluate("id=>{let b=document.querySelector('.hk[data-id=\"app:'+id+'\"]'),r=b.getBoundingClientRect();return (!b.hidden&&r.right>0&&r.left<innerWidth&&r.bottom>120&&r.top<innerHeight)||!!document.querySelector('[data-restore=\"app:'+id+'\"]')}",id)
 page.on('dialog',lambda d:d.accept())
 with page.expect_request('**/api/stop/movie-clipper'):
  page.locator('.hk[data-id="app:movie-clipper"] [data-a=stop]').dispatch_event('click')
 page.wait_for_timeout(250)
 assert page.locator('.hk[data-id="app:movie-clipper"] [data-a=stop]').is_hidden()


def test_applet_icons_use_theme_while_title_controls_keep_original_style(page):
 assert page.locator('.hk-app .gi svg').count()>=4
 assert page.locator('.hk-app .gi svg text').count()==0
 assert page.locator('.hk-app .gi').first.evaluate("e=>getComputedStyle(e).backgroundImage.includes('gradient')")
 assert page.locator('.hk[data-id=runs] [data-a=x]').evaluate("e=>getComputedStyle(e).backgroundImage")=='none'


def test_doctor_selection_is_shown_in_support_block(page):
 page.evaluate("async()=>{let d=await(await fetch('/api/home/state')).json();d.sessions={needs_you:[],working:[],idle:[{id:'doctor-sample',brief:'Doctor session',status:'idle',project:'Example'}]};__hubBoard.active.update(d)}")
 press(page,'.hb-session');press(page,'.hb-session-detail>button');page.wait_for_timeout(500)
 assert 'doctor-sample' in page.locator('.hb-session-context').inner_text()
 assert 'session=doctor-sample' in page.locator('.hk[data-id=\"extra:support\"] iframe').get_attribute('src')


@pytest.mark.parametrize('size',[(1280,667),(390,844)])
def test_typed_talk_keeps_header_clear_and_docks_secondary_overlays(page,size):
 page.set_viewport_size({'width':size[0],'height':size[1]});page.wait_for_timeout(500)
 page.get_by_role('button',name='Talk to the Hub',exact=True).click(modifiers=['Alt']);page.wait_for_timeout(300)
 assert page.locator('#voice').is_visible()
 assert page.locator('.hb-map').is_hidden()
 assert page.evaluate("()=>{let a=document.querySelector('.hb-bar').getBoundingClientRect(),b=document.querySelector('#voice').getBoundingClientRect();return b.top>=a.bottom&&b.left>=0&&b.right<=innerWidth&&b.bottom<=innerHeight}")


def test_resized_health_block_keeps_actions_scrollable(page):
 page.evaluate("async()=>{let b=__hubBoard.active,l=b.state().L.hlt;l.rz=1;l.h=130;b.update(await(await fetch('/api/home/state')).json())}")
 assert page.locator('.hk[data-id=hlt] .hk-i').evaluate("e=>getComputedStyle(e).overflowY")=='auto'
 assert page.locator('.hk[data-id=hlt] .hb-block-actions').get_by_text('RESTART',exact=True).count()==1
