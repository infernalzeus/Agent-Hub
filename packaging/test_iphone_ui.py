"""Phone presentation regressions. All capture is blocked; only isolated state."""
import os
import asyncio
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

@pytest.fixture(params=['webkit','chromium'])
def phone(request,hub):
 with sync_playwright() as p:
  b=getattr(p,request.param).launch(headless=True,**({'channel':'msedge'} if request.param=='chromium' else {}))
  ctx=b.new_context(**{**p.devices['iPhone 15 Pro'],'service_workers':'block'})
  ctx.add_init_script("window.captureAttempts=0;navigator.mediaDevices.getUserMedia=async()=>{captureAttempts++;throw Error('Capture blocked')};window.__HUB_HANDS_TEST={}")
  pg=ctx.new_page();pg.goto(hub+'/?enter=1');pg.wait_for_function('!!window.__hubBoard?.active');pg.wait_for_timeout(1000)
  yield pg,request.param,hub
  try:b._sync(asyncio.wait_for(b._impl_obj.close(),timeout=5))
  except (asyncio.TimeoutError,Exception):pass

@pytest.mark.parametrize('size',[(320,568),(568,320),(393,852),(852,393),(430,932),(932,430)])
def test_agency_map_stays_inside_page_and_can_scroll_its_table(phone,size):
 p,_,hub=phone;p.set_viewport_size(dict(zip(['width','height'],size)))
 p.goto(hub+'/agents');p.locator('[data-fam=map]').scroll_into_view_if_needed();p.locator('[data-fam=map]').tap();p.wait_for_selector('#list table')
 assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 table=p.locator('#list .persona').last
 assert table.evaluate('(e)=>getComputedStyle(e).overflowX')=='auto'
 assert p.locator('[data-fam=map]').bounding_box()['height']>=44

@pytest.mark.parametrize('path',['/missions','/agents','/setup','/chats','/graph'])
def test_touch_page_controls_and_inputs_have_safe_sizes(phone,path):
 p,_,hub=phone;p.goto(hub+path);p.wait_for_timeout(450)
 bad=p.evaluate("""()=>[...document.querySelectorAll('button,a.btn,a.back-link,select,input[type=text]')].filter(e=>{let r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width&&r.height&&s.visibility!=='hidden'&&s.display!=='none'&& !e.closest('#panel:not(.open)')}).filter(e=>{let r=e.getBoundingClientRect();return r.width<43.5||r.height<43.5}).map(e=>e.id||e.className)""")
 assert bad==[],bad
 assert p.evaluate("[...document.querySelectorAll('input[type=text],textarea')].every(e=>parseFloat(getComputedStyle(e).fontSize)>=16)")


def test_native_log_filter_and_open_chat_do_not_capture(phone):
 p,_,_=phone;p.locator('.hl-head').tap();p.get_by_role('button',name='CHAT',exact=True).tap()
 assert p.locator('.hl-filters [data-kind=chat]').get_attribute('class')=='on'
 p.get_by_role('button',name='OPEN CHAT',exact=True).tap();p.wait_for_timeout(250)
 assert p.locator('#voice').is_visible();assert p.evaluate('captureAttempts')==0
 p.set_viewport_size({'width':393,'height':400});p.wait_for_timeout(300)
 r=p.locator('#voice').bounding_box();assert r['y']>=-1 and r['y']+r['height']<=401
 assert p.locator('#v-in').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=16


def test_direct_chats_open_chat_routes_to_typed_chat(phone):
 p,_,hub=phone;p.goto(hub+'/chats');p.locator('#open-chat').tap();p.wait_for_selector('#voice:not([hidden])')
 assert p.evaluate('captureAttempts')==0


def native_touch(p,kind,points):
 c=getattr(p,'_phone_cdp',None)
 if c is None:c=p.context.new_cdp_session(p);p._phone_cdp=c
 c.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[{'x':x,'y':y,'id':i} for i,(x,y) in enumerate(points)]})


def test_native_touch_hold_opens_chat_without_listening(phone):
 p,engine,_=phone
 if engine!='chromium':pytest.skip('Playwright WebKit exposes tap but no held-touch API')
 r=p.locator('.hb-bar [data-talk]').bounding_box();pt=(r['x']+r['width']/2,r['y']+r['height']/2)
 native_touch(p,'touchStart',[pt]);p.wait_for_timeout(650);native_touch(p,'touchEnd',[]);p.wait_for_timeout(200)
 assert p.locator('#voice').is_visible();assert p.evaluate('captureAttempts')==0
 p.locator('#v-close').tap();p.wait_for_selector('#voice',state='hidden')


def test_scrolling_panel_does_not_pan_board(phone):
 p,engine,_=phone
 if engine!='chromium':pytest.skip('Native continuous-touch API is Chromium-only in Playwright')
 p.evaluate("for(let i=0;i<50;i++)dispatchEvent(new CustomEvent('hub-log',{detail:{kind:'chat',text:'Test line '+i}}))")
 p.locator('.hl-head').tap();p.wait_for_timeout(250)
 before=p.evaluate('JSON.stringify(__hubBoard.active.state().V)');r=p.locator('.hl-body').bounding_box();x=r['x']+r['width']/2;y=r['y']+r['height']-18
 native_touch(p,'touchStart',[(x,y)])
 for i in range(1,15):native_touch(p,'touchMove',[(x,y-i*7)]);p.wait_for_timeout(20)
 native_touch(p,'touchEnd',[]);p.wait_for_timeout(300)
 assert p.evaluate('JSON.stringify(__hubBoard.active.state().V)')==before
 assert p.locator('.hl-body').evaluate('(e)=>e.scrollTop')>0


@pytest.mark.parametrize('size',[(320,568),(568,320),(393,852),(852,393),(430,932),(932,430)])
def test_touch_chrome_stays_in_viewport_and_has_separate_lanes(phone,size):
 p,_,_=phone;p.set_viewport_size(dict(zip(['width','height'],size)));p.wait_for_timeout(450)
 result=p.evaluate("""()=>{let selectors=['body>header','.power-wrap','.hb-bar','.hb-right-panel','.hb-panel-hide','.hb-batch-controls','.hb-tray','.hb-map','.hl-head'];let a=selectors.flatMap(s=>{let e=document.querySelector(s);return e&&!e.hidden&&getComputedStyle(e).visibility!=='hidden'?[{s,r:e.getBoundingClientRect().toJSON()}]:[]}).filter(x=>x.r.width&&x.r.height),bad=[];for(let x of a)if(x.r.left<-.5||x.r.top<-.5||x.r.right>innerWidth+.5||x.r.bottom>innerHeight+.5)bad.push([x.s,'viewport']);for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++){let x=a[i],y=a[j];if(Math.min(x.r.right,y.r.right)>Math.max(x.r.left,y.r.left)+1&&Math.min(x.r.bottom,y.r.bottom)>Math.max(x.r.top,y.r.top)+1)bad.push([x.s,y.s]);}return bad}""")
 assert result==[],(result,p.evaluate("['.hb-batch-controls','.hb-tray'].map(s=>{let e=document.querySelector(s);return [s,e.getBoundingClientRect().toJSON(),getComputedStyle(e).cssText]})"))
 p.get_by_role('button',name='BLOCKS',exact=True).tap();p.wait_for_timeout(220)
 menu=p.locator('.hb-jump');assert menu.is_visible();r=menu.bounding_box();assert r['x']>=0 and r['y']>=0 and r['x']+r['width']<=size[0]+1 and r['y']+r['height']<=size[1]+1


@pytest.mark.parametrize('mode',['cad','3d'])
def test_each_auto_llm_tab_can_be_tapped_and_has_reachable_page(phone,mode):
 p,_,_=phone;p.evaluate('(m)=>__hubBoard.active.view().setMode(m)',mode);p.wait_for_timeout(500)
 p.evaluate("__hubBoard.open('/missions')");p.wait_for_selector('.hk-tabs');p.wait_for_timeout(700)
 for label,path in [('MISSIONS','/missions'),('GRAPH','/graph'),('REINFORCEMENT LEARNING','/yard'),('AGENCY','/agents'),('CHATS','/chats')]:
  p.locator('.hk-tabs button').filter(has_text=label).tap();p.wait_for_timeout(500)
  f=p.locator('.hk[data-id="card:oc"] iframe').content_frame
  assert path in f.locator('html').evaluate('(e)=>location.pathname')
  assert f.locator('html').evaluate('(e)=>e.scrollWidth<=innerWidth+1')
 assert p.evaluate('captureAttempts')==0



def test_native_pinch_on_title_does_not_drag_or_open_the_block(phone):
 p,engine,_=phone
 if engine!='chromium':pytest.skip('Continuous native-touch API unavailable in Playwright WebKit')
 p.evaluate("__hubBoard.active.applyUi({focus:'hlt'})");p.wait_for_timeout(700)
 r=p.locator('.hk[data-id=hlt] .hk-h .t').bounding_box();x=r['x']+r['width']/2;y=r['y']+r['height']/2
 before=p.evaluate('JSON.parse(JSON.stringify(__hubBoard.active.state()))')
 native_touch(p,'touchStart',[(x,y)]);native_touch(p,'touchStart',[(x,y),(x+70,y+30)])
 for i in range(1,12):native_touch(p,'touchMove',[(x-i*2,y),(x+70+i*2,y+30)]);p.wait_for_timeout(20)
 native_touch(p,'touchEnd',[]);p.wait_for_timeout(250)
 after=p.evaluate('__hubBoard.active.state()')
 assert after['V']['k']!=before['V']['k'];assert p.evaluate('visualViewport.scale')==1
 assert (after['L']['hlt']['x'],after['L']['hlt']['y'])==(before['L']['hlt']['x'],before['L']['hlt']['y'])
 assert not after['L']['hlt'].get('exp')


@pytest.mark.parametrize('size',[(393,852),(568,320)])
def test_glass_panel_and_mission_form_have_scrollable_visible_area(phone,size):
 p,_,hub=phone;p.set_viewport_size(dict(zip(['width','height'],size)));p.wait_for_timeout(350)
 p.locator('.hb-learning').tap();p.wait_for_timeout(200)
 r=p.locator('.hb-glass-panel').bounding_box();fr=p.locator('.hb-glass-frame').bounding_box()
 assert r['y']>=0 and r['y']+r['height']<=size[1]+1 and fr['height']>100
 p.get_by_role('button',name='Close REINFORCEMENT LEARNING',exact=True).tap();p.wait_for_timeout(250)
 p.goto(hub+'/missions');p.locator('#btn-new').tap();p.wait_for_timeout(250)
 modal=p.locator('.modal.open').last;r=modal.bounding_box()
 assert r['y']>=0 and r['y']+r['height']<=size[1]+1
 assert modal.evaluate('(e)=>getComputedStyle(e).overflowY')=='auto'


def test_minimised_block_opens_on_native_touch(phone):
 p,_,_=phone;p.get_by_role('button',name='MINIMISE ALL',exact=True).tap();p.wait_for_timeout(800)
 assert p.evaluate("!!__hubBoard.active.state().L['card:oc'].min")
 p.locator('.hk[data-id="card:oc"] .hk-h .t').tap();p.wait_for_timeout(350)
 assert not p.evaluate("!!__hubBoard.active.state().L['card:oc'].min")
 assert p.evaluate('captureAttempts')==0
