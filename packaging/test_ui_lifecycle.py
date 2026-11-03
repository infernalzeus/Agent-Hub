"""Browser release checks. Uses only isolated state and ports; never the user's Hub."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import pytest
sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def hub(tmp_path_factory):
 port=int(os.environ.get('AGENTHUB_TEST_PORT','8097'))
 assert port in (8097,8099), 'Only isolated test ports are allowed'
 base=f'http://127.0.0.1:{port}'
 def up():
  try:urllib.request.urlopen(base+'/api/status',timeout=.5).close();return True
  except Exception:return False
 if up():pytest.skip('Isolated test port is already in use')
 state=tmp_path_factory.mktemp('ui-lifecycle')
 env={**os.environ,'AGENTHUB_STATE_DIR':str(state),'AGENTHUB_NO_LEGACY':'1','HUB_PORT':str(port),'TAILDROP_DIR':str(state/'inbox'),'TAILSCALE_EXE':str(state/'unavailable.exe'),'PYTHONUTF8':'1'}
 proc=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(150):
   if up():break
   time.sleep(.2)
  else:pytest.fail('Isolated Hub did not start')
  yield base
 finally:
  if proc.poll() is None:
   try:urllib.request.urlopen(urllib.request.Request(base+'/api/shutdown',method='POST',headers={'Origin':base}),timeout=3).close()
   except Exception:proc.terminate()
   try:proc.wait(10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()

@pytest.fixture
def browser():
 pw=pytest.importorskip('playwright.sync_api').sync_playwright().start()
 opts={'headless':not bool(os.environ.get('HUB_TEST_GPU'))}
 channel=os.environ.get('AGENTHUB_TEST_BROWSER')
 if channel:opts['channel']=channel
 b=pw.chromium.launch(**opts)
 try:yield b
 finally:b.close();pw.stop()


def test_pending_microphone_cannot_open_after_release(browser,hub):
 ctx=browser.new_context(service_workers='block')
 ctx.add_init_script("navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>window.resolveCapture=resolve)")
 pg=ctx.new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk')
 result=pg.evaluate("""async()=>{let p=navigator.mediaDevices.getUserMedia({audio:true}).then(()=> 'opened',e=>e.name);__hubReleaseMic();let t={readyState:'live',stop(){this.readyState='ended'}};resolveCapture({getTracks:()=>[t]});return {result:await p,track:t.readyState}}""")
 assert result=={'result':'AbortError','track':'ended'}
 ctx.close()


def test_home_first_paint_never_shows_legacy_cards(browser,hub):
 for width,height in [(390,844),(834,1108),(1280,900)]:
  ctx=browser.new_context(service_workers='block',viewport={'width':width,'height':height})
  ctx.add_init_script("localStorage.setItem('agenthub:homeview','list');window.legacyPaints=[];requestAnimationFrame(function tick(){for(let id of ['apps-before','opencode-app-area','ytdl-app-area','yt-app-area','filebrowser-area']){let e=document.getElementById(id);if(e&&getComputedStyle(e).display!=='none'&&e.getBoundingClientRect().height)legacyPaints.push(id)}if(!document.querySelector('.hb'))requestAnimationFrame(tick)})")
  pg=ctx.new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk');assert pg.evaluate('legacyPaints')==[]
  assert pg.locator('.hb-btn',has_text='LIST').count()==0
  ctx.close()


def test_rewritten_dormant_disposes_header_and_responds_to_hover(browser,hub):
 pg=browser.new_context(service_workers='block',viewport={'width':1440,'height':960}).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk')
 pg.evaluate('window.oldHeader=orbMark;prepareDormant()');pg.evaluate('enterDormant()');pg.wait_for_selector('#dormant-globe');pg.wait_for_function('!!window.dormantGlobe')
 assert pg.evaluate('!oldHeader.globe || !oldHeader.globe.running()')
 r=pg.locator('#dormant-globe').bounding_box();x=r['x']+r['width']*.3;y=r['y']+r['height']*.5
 pg.mouse.move(x,y);a=pg.evaluate('dormantGlobe.globe.getQuaternion()')
 pg.mouse.move(x+200,y+35,steps=20);b=pg.evaluate('dormantGlobe.globe.getQuaternion()')
 assert sum(abs(x-y) for x,y in zip(a,b))>.1
 pg.context.close()


def test_retaining_home_releases_the_microphone(hub):
 with sync_playwright() as p:
  b=p.chromium.launch(headless=False,channel='msedge',args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
  try:
   pg=b.new_context(service_workers='block',permissions=['microphone']).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk')
   pg.evaluate("async()=>{window.tracks=(await navigator.mediaDevices.getUserMedia({audio:true})).getTracks();}")
   assert pg.evaluate("tracks.every(t=>t.readyState==='live')")
   pg.evaluate('__hubSuspendView(false)')
   assert pg.evaluate("tracks.every(t=>t.readyState==='ended')")
  finally:b.close()


def test_orbit_gizmo_never_pans_the_board(hub):
 with sync_playwright() as p:
  b=p.chromium.launch(headless=False,channel='msedge')
  try:
   pg=b.new_context(service_workers='block',viewport={'width':1400,'height':950}).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk');pg.wait_for_timeout(1000)
   pg.click('.hb-btn:has-text("VIEW")');pg.click('.hb-btn:has-text("VIEW")');pg.wait_for_timeout(600)
   before=pg.evaluate('({...__hubBoard.active.state().V})');g=pg.locator('.hb-gizmo svg').bounding_box();x=g['x']+25;y=g['y']+70
   pg.mouse.move(x,y);pg.mouse.down();pg.mouse.move(x+40,y-20,steps=12);pg.mouse.up();pg.wait_for_timeout(600)
   after=pg.evaluate('__hubBoard.active.state().V');assert before==after
   assert pg.evaluate('__hubBoard.active.view().tilt().ry')>-20
  finally:b.close()


def test_loaded_graph_has_no_pulsing_loading_sheet(hub):
 with sync_playwright() as p:
  b=p.chromium.launch(headless=False,channel='msedge')
  try:
   pg=b.new_context(service_workers='block',viewport={'width':1400,'height':950}).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk')
   pg.evaluate("__hubBoard.open('/graph')")
   fr=pg.locator('.hk-fr');fr.wait_for(state='visible');pg.wait_for_function("document.querySelector('.hk-fr')?.dataset.ready==='1'")
   for _ in range(3):
    pg.evaluate("__hubBoard.open('/agents');__hubBoard.open('/graph')")
    pg.wait_for_function("document.querySelector('.hk-fr')?.dataset.ready==='1'")
   pg.wait_for_timeout(250)
   assert pg.locator('.hk-loading').count()==0
  finally:b.close()


def test_narrow_tool_fills_available_width_without_miniaturizing(browser,hub):
 pg=browser.new_context(service_workers='block',viewport={'width':390,'height':844}).new_page()
 pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk');pg.evaluate("__hubBoard.open('/graph')");pg.wait_for_timeout(1200)
 b=pg.locator('.hk.exp').bounding_box();assert b['x']>=8 and b['x']+b['width']<=382
 assert pg.evaluate('__hubBoard.active.state().V.k')>=.8
 pg.context.close()


def test_moved_media_controls_are_visible_only_inside_their_pane(browser,hub):
 pg=browser.new_context(service_workers='block',viewport={'width':1400,'height':950}).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk')
 for key,area in [('ytdl','ytdl-app-area'),('yt','yt-app-area')]:
  assert not pg.locator('#'+area).is_visible()
  pg.evaluate("key=>document.querySelector(`.hk[data-id='card:${key}']`)._open()",key);pg.wait_for_timeout(500)
  assert pg.locator('.hk.exp #'+area).is_visible()
  pg.evaluate("key=>document.querySelector(`.hk[data-id='card:${key}']`)._open()",key);pg.wait_for_timeout(600)
  assert not pg.locator('#'+area).is_visible()
 pg.context.close()


def test_dragging_a_solid_pane_preserves_3d_orientation(browser,hub):
 pg=browser.new_context(service_workers='block',viewport={'width':1400,'height':950}).new_page();pg.goto(hub+'/?enter=1');pg.wait_for_selector('.hb .hk');pg.wait_for_timeout(700)
 pg.evaluate("__hubBoard.active.view().setMode('3d')");pg.wait_for_timeout(600)
 before=pg.evaluate('__hubBoard.active.view().tilt()');r=pg.locator('.hk[data-id=runs] .hk-h').bounding_box();x=r['x']+r['width']/2;y=r['y']+r['height']/2
 pg.mouse.move(x,y);pg.mouse.down();pg.mouse.move(x+60,y+25,steps=12);pg.mouse.up();pg.wait_for_timeout(600)
 assert pg.evaluate('__hubBoard.active.view().tilt()')==before
 assert pg.locator('.hk-solid i').count()>=25
 pg.context.close()
