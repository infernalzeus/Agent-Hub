"""Hand control browser contracts. Camera calls ALWAYS use a synthetic Y4M device."""
import json
import os
from pathlib import Path
import pytest
from test_ui_lifecycle import hub
sync_playwright=pytest.importorskip('playwright.sync_api').sync_playwright
ROOT=Path(__file__).resolve().parents[1]
MARKS=json.loads((Path(__file__).with_name('hand-landmarks.json')).read_text())['landmarks']

@pytest.fixture
def page(hub,tmp_path):
 clip=tmp_path/'fake.y4m';frame=bytes([16])*(320*240)+bytes([128])*(320*240//2)
 clip.write_bytes(b'YUV4MPEG2 W320 H240 F30:1 Ip A1:1 C420jpeg\n'+(b'FRAME\n'+frame)*4)
 with sync_playwright() as p:
  b=p.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER','msedge'),headless=False,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-video-capture='+str(clip)])
  ctx=b.new_context(viewport={'width':1400,'height':950},service_workers='block',permissions=['camera'])
  ctx.add_init_script("window.__HUB_HANDS_TEST={tracker:{manifest:{ready:true},factory:async()=>({detectForVideo:()=>({landmarks:[]}),close(){}})}}")
  pg=ctx.new_page();pg.goto(hub+'/?enter=1');pg.wait_for_function('!!window.__hubHands')
  pg.evaluate("""marks=>{window.recordedMarks=marks;window.handTime=performance.now();window.handFrame=(x,y,gap=1,open=false)=>{let a=recordedMarks.map(p=>({...p})),dx=1-x/innerWidth-a[8].x,dy=y/innerHeight-a[8].y;a[4].x=a[8].x+gap*.16;if(open)for(let i of [12,16,20])a[i].y=.27;return a.map(p=>({x:p.x+dx,y:p.y+dy,z:0}));};window.feedHands=(poses,n=30)=>{for(let i=0;i<n;i++){handTime+=20;__hubHands.feed({landmarks:poses.map(p=>handFrame(...p)),handedness:poses.map(()=>[{categoryName:'Right'}])},handTime)}}}""",MARKS)
  pg.evaluate("""()=>{
    window.openFrame=(x,y)=>handFrame(x,y,1,true);
    window.midFrame=(x,y)=>{const a=handFrame(x,y,1,true);a[4]={x:a[12].x+.008,y:a[12].y,z:0};return a;};
    window.closeFrame=(x,y,gap,shift)=>{const a=handFrame(x,y,gap,true);for(const i of [4,8])a[i]={...a[i],y:a[i].y+shift/innerHeight};return a;};
    window.fistFrame=(x,y)=>{const a=handFrame(x,y,1);for(const [tip,pip] of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:a[pip].y+.08,z:0};a[4]={x:a[5].x,y:a[5].y+.1,z:0};return a;};
    window.feedWith=(make,pts)=>{for(const p of pts){handTime+=20;__hubHands.feed({landmarks:[make(...p)],handedness:[[{categoryName:'Right'}]]},handTime)}};
    window.still=(x,y,n)=>Array.from({length:n},()=>[x,y]);
    window.counters={click:0,ctx:0};
    const b=document.createElement('button');b.id='tbtn';b.textContent='target';b.style.cssText='position:fixed;left:500px;top:420px;width:120px;height:50px;z-index:60';
    b.onclick=()=>counters.click++;b.oncontextmenu=e=>{counters.ctx++;e.preventDefault();};document.querySelector('.hb').appendChild(b);
  }""")
  yield pg
  b.close()


def test_off_has_no_camera_overlay_or_input(page):
 page.wait_for_timeout(800)
 assert not page.evaluate('__hubHands.tracker.stats.enabled')
 assert page.locator('.hands-overlay').count()==0
 before=page.evaluate('JSON.stringify(__hubBoard.active.state().V)');page.evaluate('feedHands([[500,400,.1]],60)')
 assert page.evaluate('JSON.stringify(__hubBoard.active.state().V)')==before
 assert page.evaluate('__hubHands.stats().pinches')==0


def test_recorded_pinch_drag_moves_a_header_and_loss_releases_it(page):
 page.wait_for_timeout(700);r=page.locator('.hk[data-id=runs] .hk-h').bounding_box();x=r['x']+65;y=r['y']+14
 page.evaluate('__hubHands.testEnable()');before=page.evaluate('({...__hubBoard.active.state().L.runs})')
 page.evaluate('p=>{feedHands([[p.x,p.y,1]]);feedHands([[p.x,p.y,.1]])}',{'x':x,'y':y})
 assert page.evaluate('__hubHands.stats().presses')==1
 page.evaluate('p=>feedHands([[p.x+110,p.y+35,.1]],45)',{'x':x,'y':y});page.wait_for_timeout(80)
 page.evaluate('feedHands([],1)');page.wait_for_timeout(600)
 after=page.evaluate('__hubBoard.active.state().L.runs');assert after['x']>before['x']+75
 assert page.evaluate('__hubHands.stats().presses')==0
 assert not page.locator('.hb').evaluate("e=>e.classList.contains('hb-dragging')")


def test_two_pinches_zoom_and_open_hold_fits(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()');before=page.evaluate('({...__hubBoard.active.state().V})')
 page.evaluate('feedHands([[530,550,1],[870,550,1]]);feedHands([[530,550,.1],[870,550,.1]])')
 page.evaluate('feedHands([[420,550,.1],[980,550,.1]],45)');page.wait_for_timeout(100)
 after=page.evaluate('__hubBoard.active.state().V');assert after['k']>before['k']*1.3
 page.evaluate('feedHands([],1)');page.wait_for_timeout(2700)                     # no fit straight after a gesture
 page.evaluate('feedHands([[700,450,1,true]],90)');page.wait_for_timeout(600)
 assert page.evaluate('__hubHands.stats().fits')==1


def test_native_mouse_cancels_a_hand_press_without_repressing(page):
 page.wait_for_timeout(700);r=page.locator('.hk[data-id=runs] .hk-h').bounding_box();x=r['x']+65;y=r['y']+14
 page.evaluate('__hubHands.testEnable()');page.evaluate('p=>{feedHands([[p.x,p.y,1]]);feedHands([[p.x,p.y,.1]])}',{'x':x,'y':y})
 assert page.evaluate('__hubHands.stats().presses')==1
 page.mouse.click(30,800);page.evaluate('p=>feedHands([[p.x,p.y,.1]],60)',{'x':x,'y':y})
 assert page.evaluate('__hubHands.stats().presses')==0


@pytest.mark.parametrize('exit', ['off','hidden','suspend','dormant','pagehide'])
def test_every_exit_ends_fake_camera_tracks_and_stops_callbacks(page,exit):
 assert page.evaluate('__hubHands.tracker.start()')
 page.wait_for_timeout(250);page.evaluate('window.cameraTracks=__hubHands.tracker.tracks().slice()')
 assert page.evaluate("cameraTracks.length>0&&cameraTracks.every(t=>t.readyState==='live')")
 if exit=='off':page.evaluate("__hubHands.tracker.stop('HANDS off')")
 elif exit=='hidden':page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
 elif exit=='suspend':page.evaluate('__hubSuspendView(false)')
 elif exit=='dormant':page.evaluate('quiesceLivePage()')
 else:page.evaluate("dispatchEvent(new Event('pagehide'))")
 assert page.evaluate("cameraTracks.every(t=>t.readyState==='ended')")
 assert page.evaluate('__hubHands.tracker.stats.callbacks')==0
 frames=page.evaluate('__hubHands.tracker.stats.frames');page.wait_for_timeout(150)
 assert page.evaluate('__hubHands.tracker.stats.frames')==frames


def test_permission_resolving_after_release_cannot_leave_camera_on(page):
 page.evaluate("window.actualOpen=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=(...a)=>new Promise(r=>window.grant=()=>actualOpen(...a).then(r));window.pendingStart=__hubHands.tracker.start();void 0")
 page.wait_for_function('!!window.grant');page.evaluate('__hubReleaseMic()');page.evaluate('grant()');page.wait_for_timeout(400)
 assert page.evaluate('__hubHands.tracker.stats.enabled') is False
 assert page.evaluate("(__hubStreams||[]).flatMap(s=>s.getTracks()).every(t=>t.readyState==='ended')")


def test_no_hand_timeout_stops_the_fake_camera(page):
 page.evaluate("window.idleTracker=HubHandsTracker.create({idleMs:80,manifest:{ready:true},factory:async()=>({detectForVideo:()=>({landmarks:[]}),close(){}})});window.idleTracks=[]")
 assert page.evaluate('idleTracker.start()');page.evaluate('idleTracks=idleTracker.tracks().slice()');page.wait_for_timeout(200)
 assert page.evaluate("idleTracks.every(t=>t.readyState==='ended')")
 assert page.evaluate('idleTracker.stats.enabled') is False
 page.evaluate('idleTracker.destroy()')


def test_missing_assets_only_offers_explicit_download(page):
 page.click('.hb-hands');page.wait_for_selector('.hands-setup',state='visible')
 assert page.locator('.hands-setup').inner_text().find('DOWNLOAD HAND TRACKING')>=0
 assert page.evaluate('__hubHands.tracker.stats.enabled') is False
 assert page.evaluate('(__hubStreams||[]).length')==0


def test_setup_choices_are_kept_at_once_and_do_not_start_the_camera(page):
 page.get_by_role('button',name='HAND SETUP',exact=True).click()
 page.get_by_role('button',name='FIST TILTS 3D: ON',exact=True).click()
 assert 'FIST TILTS 3D: OFF' in page.locator('.hands-setup').inner_text()
 assert json.loads(page.evaluate("localStorage.getItem('hub-hands-profile')"))['orbit'] is False
 page.get_by_role('button',name='CALIBRATE PINCH',exact=True).click()
 assert 'turn HANDS on explicitly' in page.locator('.hands-setup').inner_text()
 assert page.evaluate('__hubHands.tracker.stats.enabled') is False
 page.get_by_role('button',name='RESET TO DEFAULTS',exact=True).click()
 assert 'FIST TILTS 3D: ON' in page.locator('.hands-setup').inner_text()
 page.get_by_role('button',name='CLOSE',exact=True).click()


def test_a_pinch_whose_fingertips_move_is_still_a_click(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(openFrame,still(560,445,20))')
 page.evaluate('feedWith((x,y)=>closeFrame(x,y,.1,60),still(560,445,8))')       # the two fingertips slide 60 px as they meet; the palm does not
 assert page.evaluate('__hubHands.stats().presses')==1
 page.evaluate('feedWith(openFrame,still(560,445,8))')
 assert page.evaluate('counters')=={'click':1,'ctx':0}
 assert page.evaluate('__hubHands.stats().clicks')==1


def test_thumb_to_middle_finger_is_a_right_click_and_not_a_left_one(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(openFrame,still(560,445,20))')
 page.evaluate('feedWith(midFrame,still(560,445,10))')
 page.evaluate('feedWith(openFrame,still(560,445,8))')
 assert page.evaluate('counters')=={'click':0,'ctx':1}


def test_a_relaxed_hand_near_the_thumb_never_presses(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith((x,y)=>handFrame(x,y,.45,true),still(560,445,90))')
 assert page.evaluate('__hubHands.stats().pinches')==0


def test_a_pinch_clicks_a_button_inside_a_blocks_own_page(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate("""()=>{const f=document.createElement('iframe');f.id='tframe';f.style.cssText='position:fixed;left:300px;top:300px;width:300px;height:200px;z-index:60;border:0';
   f.srcdoc='<body style="margin:0"><button style="position:absolute;left:20px;top:20px;width:100px;height:40px" onclick="window.n=(window.n||0)+1">inside</button></body>';document.querySelector('.hb').appendChild(f);}""")
 page.wait_for_function("document.getElementById('tframe').contentDocument&&document.getElementById('tframe').contentDocument.querySelector('button')")
 page.evaluate('feedWith(openFrame,still(370,340,20))')
 page.evaluate('feedWith((x,y)=>closeFrame(x,y,.1,40),still(370,340,8))')
 page.evaluate('feedWith(openFrame,still(370,340,8))')
 assert page.evaluate("document.getElementById('tframe').contentWindow.n")==1


def test_a_closed_fist_tilts_the_board_in_view_3d_and_does_nothing_in_classic(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(fistFrame,still(700,450,25))')
 assert page.evaluate('__hubHands.stats().orbits')==0                             # CLASSIC: a fist is just a fist
 page.evaluate('feedWith(openFrame,still(700,450,25))')                           # open the hand again before switching view
 page.evaluate("__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(900)
 before=page.evaluate('__hubBoard.active.view().tilt()')
 page.evaluate('feedWith(fistFrame,still(700,450,25))')
 page.evaluate('feedWith(fistFrame,Array.from({length:16},(_,i)=>[700+i*14,450]))')
 page.evaluate('feedWith(openFrame,still(900,450,12))')
 after=page.evaluate('__hubBoard.active.view().tilt()')
 assert page.evaluate('__hubHands.stats().orbits')==1
 assert abs(after['ry']-before['ry'])>5


def test_an_open_hand_resting_while_you_type_does_not_refit_the_board(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()');page.keyboard.press('a')
 page.evaluate('feedHands([],1);feedHands([[700,450,1,true]],90)');page.wait_for_timeout(600)
 assert page.evaluate('__hubHands.stats().fits')==0
