"""Hand control browser contracts. Camera calls ALWAYS use a synthetic Y4M device."""
import json
import os
from pathlib import Path
import pytest
from test_ui_lifecycle import hub
sync_playwright=pytest.importorskip('playwright.sync_api').sync_playwright
ROOT=Path(__file__).resolve().parents[1]
MARKS=json.loads((Path(__file__).with_name('hand-landmarks.json')).read_text())['landmarks']

def more(page):
 # HAND SETUP and SAVE TRACE live in the small menu beside HANDS since UI round 5
 if not page.locator('.hb-more-menu').is_visible():page.locator('.hb-hands-menu-button').click()


@pytest.fixture
def page(hub,tmp_path):
 clip=tmp_path/'fake.y4m';frame=bytes([16])*(320*240)+bytes([128])*(320*240//2)
 clip.write_bytes(b'YUV4MPEG2 W320 H240 F30:1 Ip A1:1 C420jpeg\n'+(b'FRAME\n'+frame)*4)
 with sync_playwright() as p:
  b=p.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER','msedge'),headless=os.environ.get('AGENTHUB_TEST_HEADED')!='1',args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-video-capture='+str(clip)])
  ctx=b.new_context(viewport={'width':1400,'height':950},service_workers='block',permissions=['camera'])
  ctx.add_init_script("window.__HUB_HANDS_TEST={traceStepMs:60,tracker:{manifest:{ready:true},factory:async()=>({detectForVideo:()=>({landmarks:[]}),close(){}})}}")
  pg=ctx.new_page();pg.goto(hub+'/?enter=1');pg.wait_for_function('!!window.__hubHands')
  pg.evaluate("""marks=>{window.recordedMarks=marks;window.handTime=performance.now();window.handFrame=(x,y,gap=1,open=false)=>{let a=recordedMarks.map(p=>({...p})),dx=1-x/innerWidth-a[8].x,dy=y/innerHeight-a[8].y;a[4].x=a[8].x+gap*.16;if(open)for(let i of [12,16,20])a[i].y=.27;return a.map(p=>({x:p.x+dx,y:p.y+dy,z:0}));};window.feedHands=(poses,n=30)=>{for(let i=0;i<n;i++){handTime+=20;__hubHands.feed({landmarks:poses.map(p=>handFrame(...p)),handedness:poses.map(()=>[{categoryName:'Right'}])},handTime)}}}""",MARKS)
  pg.evaluate("""()=>{
    window.openFrame=(x,y)=>handFrame(x,y,1,true);
    window.midFrame=(x,y)=>{const a=handFrame(x,y,1,true);a[4]={x:a[12].x+.008,y:a[12].y,z:0};a[8]={...a[8],x:a[8].x-.2};return a;};      // the index finger stays well away: only the middle finger is touching
    window.closeFrame=(x,y,gap,shift)=>{const a=handFrame(x,y,gap,true);a[12]={...a[12],y:a[12].y-.2};for(const i of [4,8])a[i]={...a[i],y:a[i].y+shift/innerHeight};return a;};      // middle finger away, as measured in the real trace
    window.fistFrame=(x,y)=>{const a=handFrame(x,y,1);for(const [tip,pip] of [[8,6],[12,10],[16,14],[20,18]])a[tip]={x:a[pip].x,y:a[pip].y+.08,z:0};a[4]={x:a[5].x,y:a[5].y+.1,z:0};return a;};
    window.pointFrame=(x,y)=>{const a=fistFrame(x,y).map(p=>({...p}));a[8]={x:a[6].x,y:a[6].y-.12,z:0};const dx=(1-x/innerWidth)-a[8].x,dy=y/innerHeight-a[8].y;return a.map(p=>({x:p.x+dx,y:p.y+dy,z:0}));};
    window.flexFrame=(x,y)=>{const a=pointFrame(x,y).map(p=>({...p}));a[8]={x:a[6].x,y:a[6].y+.08,z:0};return a;};
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
 more(page);page.click('.hb-hands');page.wait_for_selector('.hands-setup',state='visible')
 assert page.locator('.hands-setup').inner_text().find('DOWNLOAD HAND TRACKING')>=0
 assert page.evaluate('__hubHands.tracker.stats.enabled') is False
 assert page.evaluate('(__hubStreams||[]).length')==0


def test_setup_choices_are_kept_at_once_and_do_not_start_the_camera(page):
 more(page);page.get_by_role('button',name='HAND SETUP',exact=True).click()
 page.get_by_role('button',name='FIST TILTS 3D: ON',exact=True).click()
 assert 'FIST TILTS 3D: OFF' in page.locator('.hands-setup').inner_text()
 assert json.loads(page.evaluate("localStorage.getItem('hub-hands-profile')"))['orbit'] is False
 page.get_by_role('button',name='SAVE LAST MINUTE',exact=True).click()
 assert 'Turn HANDS on' in page.locator('.hands-setup').inner_text()
 assert page.evaluate('__hubHands.tracker.stats.enabled') is False
 assert page.locator('.hands-setup button').count()==6                               # few choices
 page.get_by_role('button',name='RESET TO DEFAULTS',exact=True).click()
 assert 'FIST TILTS 3D: ON' in page.locator('.hands-setup').inner_text()
 page.get_by_role('button',name='CLOSE',exact=True).click()


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


def test_a_guided_trace_records_numbers_only_and_is_saved(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('__hubHands.startTrace(null)')
 for _ in range(4):
  page.evaluate('feedHands([[600,400,.1,true]],5)');page.wait_for_timeout(60)
 assert page.evaluate('__hubHands.stats().presses')==0                              # actions are paused while it records
 assert 'RECORDING' in page.inner_text('.hands-status')
 for _ in range(10):
  page.evaluate('feedHands([[600,400,1,true]],5)');page.wait_for_timeout(60)
 page.wait_for_function("document.querySelector('.hands-status')&&/TRACE SAVED/.test(document.querySelector('.hands-status').textContent)",timeout=8000)


def test_thumb_to_middle_is_only_a_right_click_and_never_turns_the_board(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()');page.evaluate("__hubBoard.active.view().setMode('3d')");page.wait_for_timeout(900)
 before=page.evaluate('__hubBoard.active.view().tilt()')
 page.evaluate('feedWith(openFrame,still(560,445,20))')
 page.evaluate('feedWith(midFrame,Array.from({length:14},(_,i)=>[560+i*20,445+i*6]))')       # pinched, and the hand moves a long way
 page.evaluate('feedWith(openFrame,still(840,530,8))')
 assert page.evaluate('__hubBoard.active.view().tilt()')==before


def test_three_fingertips_together_zoom_with_one_hand_up_in_and_down_out(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate("window.tripleFrame=(x,y)=>{const a=handFrame(x,y,1,true);const m={x:(a[8].x+a[12].x)/2,y:(a[8].y+a[12].y)/2,z:0};a[4]=m;return a;}")
 k0=page.evaluate('__hubBoard.active.state().V.k')
 page.evaluate('feedWith(openFrame,still(700,500,20))')
 page.evaluate('feedWith(tripleFrame,still(700,500,6))')
 assert page.evaluate('__hubHands.stats().presses')==1                                   # the zoom hold is on, and it pressed nothing on the board
 page.evaluate('feedWith(tripleFrame,Array.from({length:12},(_,i)=>[700,500-i*14]))')    # hand up
 page.wait_for_timeout(500)
 k1=page.evaluate('__hubBoard.active.state().V.k')
 assert k1>k0*1.1,(k0,k1)
 page.evaluate('feedWith(tripleFrame,Array.from({length:20},(_,i)=>[700,332+i*14]))')    # hand down
 page.wait_for_timeout(500)
 assert page.evaluate('__hubBoard.active.state().V.k')<k1
 assert page.evaluate('__hubHands.stats().clicks')==0


def test_the_last_minute_can_be_saved_from_setup(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(openFrame,still(560,445,30))')
 more(page);page.get_by_role('button',name='HAND SETUP',exact=True).click()
 page.get_by_role('button',name='SAVE LAST MINUTE',exact=True).click()
 page.wait_for_function("document.querySelector('.hands-setup').innerText.includes('Saved trace-')",timeout=6000)


def test_thumb_to_middle_on_a_block_opens_its_menu_and_on_the_empty_board_the_board_menu(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()')
 r=page.locator('.hk[data-id=runs] .hk-h').bounding_box();x=r['x']+40;y=r['y']+12
 page.evaluate('p=>feedWith(openFrame,still(p.x,p.y,20))',{'x':x,'y':y})
 page.evaluate('p=>feedWith(midFrame,still(p.x,p.y,10))',{'x':x,'y':y})
 page.evaluate('p=>feedWith(openFrame,still(p.x,p.y,8))',{'x':x,'y':y})
 labels=page.locator('.hb-ctx button').all_inner_texts()
 assert any('MINIMISE' in l for l in labels),labels                       # the right press now DOES something


def test_a_pinch_presses_and_drags_but_never_clicks(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(openFrame,still(560,445,20))')
 page.evaluate('feedWith((x,y)=>closeFrame(x,y,.1,0),still(560,445,8))')
 assert page.evaluate('__hubHands.stats().presses')==1                                   # it pressed (and would drag)
 page.evaluate('feedWith(openFrame,still(560,445,8))')
 assert page.evaluate('counters')=={'click':0,'ctx':0}                                     # but a pinch alone is not a click
 assert page.evaluate('__hubHands.stats().clicks')==0


def test_holding_the_pointing_finger_still_on_a_button_clicks_it_with_a_visible_ring_and_outline(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(pointFrame,still(560,445,22))')                                 # the cursor settles; the ring is filling, the button is outlined, nothing clicked yet
 assert page.locator('.hands-target').count()==1
 assert page.evaluate('counters')=={'click':0,'ctx':0}
 page.evaluate('feedWith(pointFrame,still(560,445,50))')                                 # held still for well over 0.8 s
 assert page.evaluate('counters')=={'click':1,'ctx':0}
 page.evaluate('feedWith(pointFrame,still(560,445,40))');assert page.evaluate('counters')['click']==1      # one click per rest, not a stream
 assert page.evaluate('__hubHands.stats().dwells')==1


def test_pointing_and_moving_never_clicks_and_resting_on_empty_board_never_clicks(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(pointFrame,Array.from({length:60},(_,i)=>[300+i*8,445]))')     # sweeping across: no rest anywhere long enough
 page.evaluate('feedWith(pointFrame,still(150,150,80))')                                 # resting on empty board
 assert page.evaluate('counters')=={'click':0,'ctx':0}


def test_a_click_inside_a_blocks_own_page_by_resting_the_pointing_finger(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate("""()=>{const f=document.createElement('iframe');f.id='tframe';f.style.cssText='position:fixed;left:300px;top:300px;width:300px;height:200px;z-index:60;border:0';
   f.srcdoc='<body style="margin:0"><button style="position:absolute;left:20px;top:20px;width:100px;height:40px" onclick="window.n=(window.n||0)+1">inside</button></body>';document.querySelector('.hb').appendChild(f);}""")
 page.wait_for_function("document.getElementById('tframe').contentDocument&&document.getElementById('tframe').contentDocument.querySelector('button')")
 page.evaluate('feedWith(pointFrame,still(370,340,60))')
 assert page.evaluate("document.getElementById('tframe').contentWindow.n")==1


def test_pointing_with_the_middle_finger_curled_on_the_thumb_is_not_a_right_press(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith((x,y)=>{const a=pointFrame(x,y);a[4]={x:a[12].x+.01,y:a[12].y,z:0};return a},still(150,150,40))')
 assert page.evaluate('__hubHands.stats().rclicks')==0 and page.evaluate('counters')['ctx']==0
 assert page.locator('.hb-ctx').count()==0


def test_a_flat_palm_moves_the_board_and_pushing_it_toward_the_camera_zooms_when_it_is_switched_on(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()');page.evaluate("__hubHands.testOption('palm',true)")
 page.evaluate("window.flatFrame=(x,y,scale=1)=>{const a=handFrame(x,y,1,true);const c=a[9];return a.map(p=>({x:c.x+(p.x-c.x)*scale,y:c.y+(p.y-c.y)*scale,z:0}));}")
 before=page.evaluate('({...__hubBoard.active.state().V})')
 page.evaluate('feedWith((x,y)=>flatFrame(x,y),still(700,450,30))')                       # engage
 page.evaluate('feedWith((x,y)=>flatFrame(x,y),Array.from({length:14},(_,i)=>[700-i*12,450-i*6]))')
 mid=page.evaluate('({...__hubBoard.active.state().V})')
 assert abs(mid['x']-before['x'])+abs(mid['y']-before['y'])>40,(before,mid)              # the board followed the palm
 page.evaluate('feedWith((x,y)=>flatFrame(x,y,1.4),still(530,366,12))')                  # hand pushed toward the camera: bigger
 assert page.evaluate('__hubBoard.active.state().V.k')>mid['k']*1.05
 assert page.evaluate('__hubHands.stats().pans')>=1


def test_thumb_to_middle_on_a_block_opens_its_menu_and_on_the_empty_board_the_board_menu(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()')
 r=page.locator('.hk[data-id=runs] .hk-h').bounding_box();x=r['x']+40;y=r['y']+12
 page.evaluate('p=>feedWith(openFrame,still(p.x,p.y,20))',{'x':x,'y':y})
 page.evaluate('p=>feedWith(midFrame,still(p.x,p.y,10))',{'x':x,'y':y})
 page.evaluate('p=>feedWith(openFrame,still(p.x,p.y,8))',{'x':x,'y':y})
 labels=page.locator('.hb-ctx button').all_inner_texts()
 assert any('MINIMISE' in l for l in labels),labels                       # the right press now DOES something


def test_a_pinch_presses_and_drags_but_never_clicks(page):
 page.wait_for_timeout(600);page.evaluate('__hubHands.testEnable()')
 page.evaluate('feedWith(openFrame,still(560,445,20))')
 page.evaluate('feedWith((x,y)=>closeFrame(x,y,.1,0),still(560,445,8))')
 assert page.evaluate('__hubHands.stats().presses')==1                                   # it pressed (and would drag)
 page.evaluate('feedWith(openFrame,still(560,445,8))')
 assert page.evaluate('counters')=={'click':0,'ctx':0}                                     # but a pinch alone is not a click
 assert page.evaluate('__hubHands.stats().clicks')==0

def test_a_flat_palm_does_nothing_by_default_and_a_noisy_hand_never_moves_the_board(page):
 page.wait_for_timeout(700);page.evaluate('__hubHands.testEnable()')
 page.evaluate("window.flatFrame=(x,y,scale=1)=>{const a=handFrame(x,y,1,true);const c=a[9];return a.map(p=>({x:c.x+(p.x-c.x)*scale,y:c.y+(p.y-c.y)*scale,z:0}));}")
 before=page.evaluate('({...__hubBoard.active.state().V})')
 page.evaluate('feedWith((x,y)=>flatFrame(x,y,1+((x*7)%3)*.01),Array.from({length:60},(_,i)=>[700+(i%3),450+(i%2)]))')      # off: a hand held up with the size and position wobbling
 assert page.evaluate('({...__hubBoard.active.state().V})')==before
 page.evaluate("__hubHands.testOption('palm',true)")
 page.evaluate('feedWith((x,y)=>flatFrame(x,y,1+((x*7)%3)*.01),Array.from({length:80},(_,i)=>[700+(i%3),450+(i%2)]))')      # on: tremor of a few pixels and a few per cent of size is inside the dead band
 after=page.evaluate('({...__hubBoard.active.state().V})')
 assert abs(after['x']-before['x'])<4 and abs(after['y']-before['y'])<4 and abs(after['k']/before['k']-1)<.02,(before,after)
