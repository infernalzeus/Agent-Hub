"""Round3: native press/hold/release, no capture or external launches."""
import os,json
from io import BytesIO
from PIL import Image
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

def press(page,selector,during=None):
 e=page.locator(selector);r=e.bounding_box();assert r,selector
 x,y=r['x']+r['width']/2,r['y']+r['height']/2
 hit=page.evaluate("p=>{let e=document.elementFromPoint(p.x,p.y);return e?.outerHTML.slice(0,250)}",{'x':x,'y':y})
 assert page.evaluate("p=>{let e=document.querySelector(p.s),h=document.elementFromPoint(p.x,p.y);return e===h||e.contains(h)}",{'x':x,'y':y,'s':selector}),(selector,hit)
 page.mouse.move(x,y);page.mouse.down();page.wait_for_timeout(60)
 if during:during()
 page.wait_for_timeout(60);page.mouse.up();page.wait_for_timeout(150)

@pytest.fixture
def page(hub):
 with sync_playwright() as pw:
  opts={'headless':os.environ.get('AGENTHUB_TEST_HEADED')!='1'}
  if os.environ.get('AGENTHUB_TEST_BROWSER'):opts['channel']=os.environ['AGENTHUB_TEST_BROWSER']
  b=pw.chromium.launch(**opts);ctx=b.new_context(service_workers='block',viewport={'width':1280,'height':800})
  ctx.add_init_script("window.__HUB_HANDS_TEST={};navigator.mediaDevices.getUserMedia=()=>Promise.reject(new Error('Physical capture forbidden'))")
  p=ctx.new_page();p.goto(hub+'/?enter=1');p.wait_for_selector('.hb-session-group,.hb-note');p.wait_for_timeout(650)
  p.evaluate("async()=>{let d=await(await fetch('/api/home/state')).json();d.health.stale_code=false;d.sessions={needs_you:[],working:[{id:'example-session',brief:'Example session',status:'working',kind:'agent-log',cwd:'/example/project',last:'Finished the example check.'}],idle:[]};window.testState=d;__hubBoard.active.update(d)}")
  p.wait_for_timeout(500);yield p;b.close()

@pytest.mark.parametrize('mode',['cad','3d'])
@pytest.mark.parametrize('hands',[False,True])
def test_native_session_click_opens_detail_in_all_modes(page,mode,hands):
 page.evaluate("m=>__hubBoard.active.view().setMode(m)",mode);page.wait_for_timeout(600)
 if hands:page.evaluate('__hubHands.testEnable()')
 press(page,'.hb-session');assert page.locator('.hb-session-detail').is_visible()
 assert page.locator('.hb-session-detail').get_by_text('agent-log',exact=True).count()==1
 assert 'Finished the example check.' in page.locator('.hb-session-detail').inner_text()
 assert page.evaluate("(__hubStreams||[]).flatMap(s=>s.getTracks()).length")==0


def test_open_folder_posts_only_id(page):
 got=[];page.route('**/api/sessions/open-folder',lambda r:(got.append(r.request.post_data_json),r.fulfill(json={'ok':True})))
 press(page,'.hb-session');press(page,'.hb-session-detail>button')
 assert got==[{'id':'example-session'}]


def test_missing_session_fields_are_omitted(page):
 page.evaluate("()=>{testState.sessions.working=[{id:'bare',brief:'Bare session'}];__hubBoard.active.update(testState)}")
 page.wait_for_timeout(500);press(page,'.hb-session')
 assert page.locator('.hb-session-detail h3').count()==0
 assert page.locator('.hb-session-detail').get_by_text('OPEN FOLDER',exact=True).count()==0


def test_native_dismiss_and_more_clicks(page):
 page.locator('#setup-card').evaluate('e=>e.hidden=false');press(page,'.sc-dismiss');assert page.locator('#setup-card').is_hidden()
 press(page,'.hb-hands-menu-button');assert page.locator('.hb-more-menu').is_visible()
 page.keyboard.press('Escape');assert page.locator('.hb-more-menu').is_hidden()


def test_stale_code_chip_delegates_to_existing_restart(page):
 page.evaluate("()=>{window.restartSeen=0;document.getElementById('restart-btn').addEventListener('click',()=>restartSeen++,true);testState.health.stale_code=true;__hubBoard.active.update(testState)}")
 page.on('dialog',lambda d:d.dismiss());page.wait_for_timeout(400)
 assert page.locator('.hb-health-restart').is_visible()
 press(page,'.hb-restart-needed');assert page.evaluate('restartSeen')==1

@pytest.mark.parametrize('size',[(1280,667),(1920,1080),(2560,1440),(834,1112),(390,844),(320,568)])
def test_hands_is_primary_and_on_screen(page,size):
 page.set_viewport_size({'width':size[0],'height':size[1]});page.wait_for_timeout(500)
 h=page.locator('.hb-bar>.hb-hands');assert h.is_visible();r=h.bounding_box();assert 0<=r['x'] and r['x']+r['width']<=size[0]
 assert page.locator('.hb-more-menu').get_by_text('HAND SETUP',exact=True).count()==1

@pytest.mark.parametrize('surface',['slab','glass'])
def test_rear_surface_pixels_and_preference(page,surface):
 page.evaluate("()=>__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(600)
 assert page.locator('.hb').evaluate("e=>e.classList.contains('hb-slab')")
 if surface=='glass':press(page,'[data-surface]')
 press(page,'.gz-tools button:first-child')
 page.locator('.hk[data-id=runs] .hk-i').evaluate("e=>{e.style.background='#ee22cc';e.style.height='100%';e.textContent='REAR CONTENT'}")
 page.evaluate("()=>{let v=__hubBoard.active.view(),t=v.tilt();v.orbitBy((180-t.ry)*4,t.rx*4)}");page.wait_for_timeout(300)
 im=Image.open(BytesIO(page.screenshot())).convert('RGB');n=sum(r>140 and b>100 and g<100 for r,g,b in im.getdata());assert n>2000,n
 assert page.evaluate("localStorage.getItem('agenthub:board:surface')")==('glass' if surface=='glass' else None)


@pytest.mark.parametrize('mode',['cad','3d'])
def test_state_refresh_during_native_press_cannot_replace_target(page,mode):
 page.evaluate("m=>__hubBoard.active.view().setMode(m)",mode);page.wait_for_timeout(600)
 press(page,'.hb-session',lambda:page.evaluate('__hubBoard.active.update(testState)'))
 assert page.locator('.hb-session-detail').is_visible()
