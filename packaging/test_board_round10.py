"""Round 10 presentation and model controls; isolated Hub and trusted browser input."""
import asyncio,json,os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

@pytest.fixture
def page(hub):
 with sync_playwright() as p:
  b=p.chromium.launch(channel='msedge',headless=True)
  c=b.new_context(service_workers='block',viewport={'width':1280,'height':720})
  c.route('**/api/**',lambda r:r.abort() if r.request.method not in ('GET','HEAD','OPTIONS') and not r.request.url.endswith('/api/board/prefs') else r.continue_())
  c.add_init_script("window.captureRequests=0;navigator.mediaDevices.getUserMedia=async()=>{captureRequests++;throw Error('Capture blocked')};window.__HUB_HANDS_TEST={}")
  c.request.put(hub+'/api/board/prefs',data='{}',headers={'Content-Type':'application/json'})
  pg=c.new_page();pg.set_default_timeout(7000);errors=[];pg.on('pageerror',lambda e:errors.append(str(e)))
  pg.goto(hub+'/?enter=1');pg.wait_for_function('!!window.__hubBoard?.active');pg.wait_for_timeout(800)
  yield pg,hub
  assert not errors,errors
  b.close()

def press(p,loc):
 if isinstance(loc,str):loc=p.locator(loc)
 loc.scroll_into_view_if_needed();r=loc.bounding_box();assert r
 p.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2);p.mouse.down();p.wait_for_timeout(120);p.mouse.up();p.wait_for_timeout(220)

@pytest.mark.parametrize('size',[(1280,720),(1440,900),(1920,1080),(2560,1440),(860,600)])
@pytest.mark.parametrize('mode',['cad','3d'])
def test_controls_have_separate_lanes_and_batch_never_covers_blocks(page,size,mode):
 p,_=page;p.set_viewport_size(dict(zip(['width','height'],size)));p.evaluate('(m)=>__hubBoard.active.view().setMode(m)',mode);p.wait_for_timeout(550)
 p.locator('.hb-viewbar').get_by_text('FIT',exact=True).click();p.wait_for_timeout(600)
 result=p.evaluate("""()=>{let sels=['body>header','.power-wrap','.hb-bar','.hb-top-tools','.hb-right-panel','.hb-batch-controls','.hb-tray','.hb-map','.hb-panel-hide'],a=sels.map(s=>({s,e:document.querySelector(s)})).filter(x=>x.e&&!x.e.hidden&&getComputedStyle(x.e).display!=='none').map(x=>({s:x.s,r:x.e.getBoundingClientRect().toJSON()})),bad=[];for(let i=0;i<a.length;i++){let r=a[i].r;if(r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)bad.push([a[i].s,'viewport']);for(let j=i+1;j<a.length;j++){let t=a[j].r;if(Math.min(r.right,t.right)>Math.max(r.left,t.left)+1&&Math.min(r.bottom,t.bottom)>Math.max(r.top,t.top)+1)bad.push([a[i].s,a[j].s]);}}let b=document.querySelector('.hb-batch-controls').getBoundingClientRect();for(let e of document.querySelectorAll('.hk:not([hidden])')){let r=e.getBoundingClientRect();if(Math.min(r.right,b.right)>Math.max(r.left,b.left)+1&&Math.min(r.bottom,b.bottom)>Math.max(r.top,b.top)+1)bad.push(['batch',e.dataset.id]);}return {bad,stage:__hubBoard.active.stage(),batch:b.toJSON()}}""")
 assert result['bad']==[],result
 assert result['stage']['bottom']<=result['batch']['top']
 p.locator('.hb-batch-controls').evaluate("e=>e.style.visibility='hidden'");other=p.evaluate('__hubBoard.active.stage().bottom');assert other==result['stage']['bottom']
 p.locator('.hb-batch-controls').evaluate("e=>e.style.visibility='visible'")
 for command,flag in [('minimise',True),('maximise',False)]:
  press(p,'[data-batch='+command+']');p.wait_for_timeout(650)
  assert p.evaluate('(min)=>Object.entries(__hubBoard.active.state().L).filter(([k])=>!__hubBoard.active.state().hid[k]).every(([k,l])=>!!l.min===min)',flag)


def test_log_is_off_by_default_collects_lines_and_remembers_device_choice(page):
 p,_=page;assert not p.locator('.hl-head').is_visible();assert p.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hb-log').trim()")=='0px'
 p.evaluate("dispatchEvent(new CustomEvent('hub-log',{detail:{kind:'hub',text:'Background test line'}}))")
 press(p,'.hb-log-toggle');assert p.locator('.hl-head').is_visible();press(p,'.hl-head');assert 'Background test line' in p.locator('.hl-rows').inner_text()
 p.reload();p.wait_for_selector('.hb-log-toggle');p.wait_for_timeout(350);assert p.locator('.hl-head').is_visible()
 press(p,'.hb-log-toggle');p.reload();p.wait_for_selector('.hb-log-toggle');assert not p.locator('.hl-head').is_visible()
 assert p.evaluate('captureRequests')==0


def test_left_cluster_order_and_pc_indicator_size(page):
 p,_=page
 boxes=[p.locator(s).bounding_box() for s in ['.hb-bar .talk-btn','.hb-pc','.hb-learning']]
 assert abs(boxes[0]['y']-boxes[1]['y'])<1 and boxes[1]['x']>boxes[0]['x']
 assert abs(boxes[2]['x']-boxes[0]['x'])<1 and boxes[2]['y']>boxes[0]['y']
 assert p.locator('.hb-pc').evaluate("e=>getComputedStyle(e,'::after').width")=='4px'
 assert p.locator('.hb-top-tools').locator('.hb-hands').count()==1
 assert p.locator('.hb-top-tools').get_by_text('+ INGEST APP',exact=True).count()==1

@pytest.mark.parametrize('size',[(393,852),(852,393),(320,568),(568,320)])
def test_touch_actions_are_44px_and_do_not_overlap(hub,size):
 with sync_playwright() as pw:
  b=pw.chromium.launch(channel='msedge',headless=True)
  try:
   c=b.new_context(**{**pw.devices['iPhone 15 Pro'],'viewport':dict(zip(['width','height'],size)),'service_workers':'block'})
   c.add_init_script("navigator.mediaDevices.getUserMedia=async()=>{throw Error('Blocked')};window.__HUB_HANDS_TEST={}")
   p=c.new_page();p.set_default_timeout(7000);p.goto(hub+'/?enter=1');p.wait_for_function('!!window.__hubBoard?.active');p.wait_for_timeout(650)
   bad=p.evaluate("""()=>[...document.querySelectorAll('.hb-bar button,.hb-top-tools button,.hb-right-panel button,.hb-batch-controls button,.hb-tray button')].filter(e=>!e.hidden&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden').filter(e=>{let r=e.getBoundingClientRect();return r.width<43.5||r.height<43.5}).map(e=>e.className)""")
   assert bad==[],bad
   p.locator('[data-batch=minimise]').tap();p.wait_for_timeout(750)
   assert p.evaluate("Object.values(__hubBoard.active.state().L).every(l=>l.min)")
  finally:b.close()

@pytest.fixture
def agency(page):
 p,hub=page;state={'policy':'auto','own':{},'posts':[],'names':['coder','tester'],'skills':[{'name':'code-check','topic':'Code','description':'Code quality checks','origin':'built-in'},{'name':'sound-mix','topic':'Media','description':'Mixes sound with a clear method','origin':'built-in'}],'installed':False}
 models=[{'id':'model-a','name':'Model A'},{'id':'model-b','name':'Model B'},{'id':'model-c','name':'Model C'}]
 def resolved():return {'auto':'model-a','free-cloud':'model-b','local':'model-c'}.get(state['policy'],state['policy'])
 def persona(n):return {'name':n,'mode':'subagent','origin':'built-in' if n=='coder' else 'user','description':n+' handles a concise task. Long details appear only on demand.','body':'Full instructions for '+n,'frontmatter':{'skills':'*'},'settings':{'model':{'value':state['own'].get(n,resolved()),'source':'override' if n in state['own'] else 'all'},'temperature':{'value':0.37,'source':'override'}}}
 def agents(r):r.fulfill(json={'personas':[persona(n) for n in state['names']],'models':models,'team':{},'workspace_model':resolved()})
 def policy(r):
  if r.request.method=='POST':state['policy']=r.request.post_data_json['policy'];state['posts'].append(('all',r.request.post_data_json))
  r.fulfill(json={'policy':state['policy'],'resolved':resolved(),'local':'model-c','fast_free':'model-b','has_paid_key':False})
 def settings(r):
  n=r.request.url.split('/agents/')[1].split('/')[0];data=r.request.post_data_json;state['posts'].append((n,data))
  if data.get('model'):state['own'][n]=data['model']
  else:state['own'].pop(n,None)
  r.fulfill(json={'ok':True})
 p.route('**/api/agents',agents);p.route('**/api/model-policy',policy);p.route('**/api/opencode/agents/*/settings',settings)
 p.route('**/api/model-recommendations',lambda r:r.fulfill(json={'roles':{}}))
 p.route('**/api/profiles',lambda r:r.fulfill(json={'profiles':{'code':{'label':'Code & build','roster':['coder','tester']}}}))
 p.route('**/api/hub/helpers',lambda r:r.fulfill(json={'helpers':[]}))
 p.route('**/api/hub/agent-map',lambda r:r.fulfill(json={'nodes':[{'id':'coder','name':'Coder'},{'id':'tester','name':'Tester'}],'edges':[{'from':'coder','to':'tester','why':'checks'}],'coverage':{'coder':{'state':'logged','note':'Recorded'},'tester':{'state':'gap','note':'Needs a policy'}},'complete':True,'gaps':[]}))
 p.route('**/api/skills',lambda r:r.fulfill(json={'library':state['skills'],'catalogue':[{'id':'pack-test','name':'Test pack','title':'Test pack','summary':'Example installable skill pack','description':'A safe test catalogue entry','repo':'https://example.com/test','publisher':'Example','licence':'MIT','ref':'test-ref','installed':state['installed']}]}))
 p.goto(hub+'/agents');p.wait_for_selector('[data-agent-model=coder]');p.evaluate("window.noReloadToken='same-document'")
 yield p,state


def choose(p,selector,index):
 # Native dropdown interaction after a real pointer press; no select_option or dispatched clicks.
 p.locator(selector).click();p.keyboard.press('Home')
 for _ in range(index):p.keyboard.press('ArrowDown')
 p.keyboard.press('Enter');p.wait_for_timeout(350)


def test_global_model_updates_followers_override_survives_and_reset_follows(agency):
 p,s=agency;choose(p,'#agency-all-model',1)
 p.wait_for_function("document.querySelector('#agency-resolved').textContent.includes('model-b')")
 assert 'model-b' in p.locator('[data-agent-model=coder] option').first.inner_text()
 choose(p,'[data-agent-model=tester]',1);p.wait_for_function("document.querySelector('[data-agent-model=tester]').value==='model-a'")
 assert p.locator('[data-model-reset=tester]').is_visible()
 choose(p,'#agency-all-model',2);p.wait_for_function("document.querySelector('#agency-resolved').textContent.includes('model-c')")
 assert p.locator('[data-agent-model=tester]').input_value()=='model-a'
 assert p.locator('[data-agent-model=coder]').input_value()=='' and 'model-c' in p.locator('[data-agent-model=coder] option').first.inner_text()
 press(p,'[data-model-reset=tester]');p.wait_for_function("document.querySelector('[data-agent-model=tester]').value===''")
 assert not p.locator('[data-model-reset=tester]').is_visible();assert p.evaluate('noReloadToken')=='same-document'
 own=[d for n,d in s['posts'] if n=='tester'];assert own==[{'model':'model-a'},{'model':''}]
 assert all(set(d)=={'model'} for n,d in s['posts'] if n!='all')


def test_two_tabs_expand_details_search_and_skill_search_across_topics(agency):
 p,_=agency;assert p.get_by_role('tab').all_inner_texts()==['AGENTS','SKILLS']
 assert not p.locator('[data-agent=coder] .ag-full').is_visible();press(p,'[data-ag-expand=coder]');assert p.locator('[data-agent=coder] .ag-full').is_visible()
 assert 'Tester' in p.locator('[data-agent=coder] .ag-relationships').inner_text()
 p.locator('#agency-search').fill('tester');assert p.locator('[data-agent=coder]').count()==0;assert p.locator('[data-agent=tester]').count()==1
 p.get_by_role('tab',name='SKILLS',exact=True).click();assert p.locator('#skl-modal').is_visible() and not p.locator('#agents-view').is_visible()
 p.locator('#skill-search').fill('sound');p.wait_for_selector('#skills .nm:text-is("sound-mix")');assert p.locator('#skills .skl:visible .nm').all_inner_texts()==['sound-mix']
 p.locator('#skills .skl:visible summary').click();assert 'Available to:' in p.locator('#skills').inner_text()
 p.locator('#skill-search').fill('coder');p.wait_for_function("document.querySelectorAll('#skills .nm').length===2")
 p.get_by_role('tab',name='AGENTS',exact=True).click();assert p.locator('#agents-view').is_visible()


def test_create_and_edit_with_neo_remain_available(agency):
 p,_=agency;press(p,'#btn-create');assert p.locator('#modal.open').is_visible();press(p,'#c-cancel')
 press(p,'[data-ag-expand=coder]');press(p,p.locator('[data-agent=coder]').get_by_text('EDIT WITH NEO',exact=False))
 assert p.locator('#modal.open').is_visible();assert p.locator('#c-name').input_value()=='coder';assert 'Full instructions for coder' in p.locator('#c-body').input_value()


def test_global_model_failure_is_visible_and_rolls_back(agency):
 p,_=agency
 def fail(r):r.fulfill(status=503,json={'error':'test unavailable'}) if r.request.method=='POST' else r.fallback()
 p.route('**/api/model-policy',fail);choose(p,'#agency-all-model',1)
 assert 'not saved' in p.locator('#agency-model-error').inner_text();assert p.locator('#agency-all-model').input_value()=='auto'



def test_existing_settings_and_delete_actions_remain_reachable(agency):
 p,s=agency;press(p,'[data-ag-expand=tester]')
 card=p.locator('[data-agent=tester]');press(p,card.get_by_text('SETTINGS',exact=True))
 p.locator('#e-temp-tester').fill('0.55');press(p,card.get_by_text('SAVE SETTINGS',exact=True));p.wait_for_timeout(300)
 assert any(n=='tester' and d.get('temperature')=='0.55' for n,d in s['posts'])
 def remove(r):s['names'].remove('tester');r.fulfill(json={'ok':True})
 p.route('**/api/opencode/agents/tester',remove);p.on('dialog',lambda d:d.accept())
 press(p,p.locator('[data-agent=tester]').get_by_text('DELETE',exact=True));p.wait_for_selector('[data-agent=tester]',state='detached')



def test_create_with_neo_and_skill_install_create_remove_preserve_actions(agency):
 p,s=agency
 p.route('**/api/agents/draft',lambda r:r.fulfill(json={'markdown':'---\ndescription: A test agent\nmode: subagent\n---\nOriginal test instructions'}))
 def save_agent(r):s['names'].append('new-agent');s['posts'].append(('create',r.request.post_data_json));r.fulfill(json={'ok':True})
 p.route('**/api/opencode/agents',save_agent)
 press(p,'#btn-create');p.locator('#c-name').fill('new-agent');p.locator('#c-desc').fill('A test agent')
 press(p,'#c-draft');p.wait_for_function("document.querySelector('#c-body').value.includes('Original test instructions')")
 press(p,'#c-save');p.wait_for_selector('[data-agent=new-agent]')
 p.get_by_role('tab',name='SKILLS',exact=True).click();p.locator('#skills .skl.add summary').click()
 def install(r):s['installed']=True;r.fulfill(json={'ok':True})
 p.route('**/api/skills/install/pack-test',install)
 press(p,p.get_by_role('button',name='ADD TO MY AGENTS',exact=True));p.wait_for_timeout(300);assert s['installed']
 def save_skill(r):
  data=r.request.post_data_json;s['skills'].append({'name':data['name'],'description':'A saved test skill','topic':'Code','origin':'yours'});r.fulfill(json={'ok':True})
 p.route('**/api/skills/save',save_skill)
 press(p,p.get_by_role('button',name='NEW SKILL',exact=True));p.locator('#sk-name').fill('sample-skill');p.locator('#sk-md').fill('---\nname: sample-skill\ndescription: A saved test skill\n---\nTest method')
 press(p,p.locator('#skills').get_by_role('button',name='SAVE',exact=True));p.wait_for_selector('#skills .nm:text-is("sample-skill")')
 def remove_skill(r):s['skills'][:]=[x for x in s['skills'] if x['name']!='sample-skill'];r.fulfill(json={'ok':True})
 p.route('**/api/skills/sample-skill',remove_skill)
 item=p.locator('.skl').filter(has=p.locator('.nm:text-is("sample-skill")'));item.locator('summary').click();press(p,item.get_by_role('button',name='REMOVE',exact=True));p.wait_for_selector('.nm:text-is("sample-skill")',state='detached')



def test_webkit_touch_layout_and_agency_tabs(hub):
 with sync_playwright() as pw:
  b=pw.webkit.launch(headless=True)
  try:
   c=b.new_context(**{**pw.devices['iPhone 15 Pro'],'service_workers':'block'})
   c.add_init_script("navigator.mediaDevices.getUserMedia=async()=>{throw Error('Blocked')};window.__HUB_HANDS_TEST={}")
   p=c.new_page();p.set_default_timeout(7000)
   for w,h in [(393,852),(852,393),(320,568),(568,320)]:
    p.set_viewport_size({'width':w,'height':h});p.goto(hub+'/?enter=1');p.wait_for_function('!!window.__hubBoard?.active');p.wait_for_timeout(500)
    assert not p.locator('.hl-head').is_visible()
    bad=p.evaluate("""()=>{let sels=['body>header','.power-wrap','.hb-bar','.hb-top-tools','.hb-right-panel','.hb-batch-controls','.hb-tray','.hb-map','.hb-panel-hide'];let a=sels.map(s=>({s,e:document.querySelector(s)})).filter(x=>x.e&&!x.e.hidden&&x.e.getClientRects().length).map(x=>({s:x.s,r:x.e.getBoundingClientRect()})),bad=[];for(let i=0;i<a.length;i++){let r=a[i].r;if(r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)bad.push([a[i].s,'viewport']);for(let j=i+1;j<a.length;j++){let t=a[j].r;if(Math.min(r.right,t.right)>Math.max(r.left,t.left)+1&&Math.min(r.bottom,t.bottom)>Math.max(r.top,t.top)+1)bad.push([a[i].s,a[j].s]);}}return bad}""")
    assert bad==[],(w,h,bad)
   p.set_viewport_size({'width':393,'height':852});p.goto(hub+'/agents');p.wait_for_selector('.ag-entry')
   p.get_by_role('tab',name='SKILLS',exact=True).tap();assert p.locator('#skl-modal').is_visible()
   p.get_by_role('tab',name='AGENTS',exact=True).tap();assert p.locator('#agents-view').is_visible()
   assert p.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  finally:
   try:b._sync(asyncio.wait_for(b._impl_obj.close(),5))
   except Exception:pass

def test_loaded_chat_messages_remain_visible_without_legacy_history_toggle(page):
 p,_=page;p.locator('.hb-bar .talk-btn').click(button='right');p.wait_for_timeout(250)
 assert p.locator('#voice').is_visible() and p.locator('#voice').count()==1
 assert not p.locator('#v-history').is_visible()
 p.route('**/api/voice/chat',lambda r:r.fulfill(json={'say':'Test response'}))
 if p.locator('#v-mute').inner_text()=='SOUND ON':press(p,'#v-mute')
 for text in ['Explain this example','Explain another example']:
  p.locator('#v-in').fill(text);press(p,'#v-go');p.wait_for_timeout(200)
 assert p.locator('#v-log .v-msg:not([hidden])').count()>=4
 press(p,'#hb-chat-history-tab');assert 'Test response' in p.locator('#hb-chat-history').inner_text()
 assert p.evaluate('captureRequests')==0


def test_dynamic_layers_add_reorder_assign_remove_and_persist(page):
 p,_=page;p.evaluate("__hubBoard.active.view().setMode('3d')");p.wait_for_timeout(300)
 press(p,'[data-layers]');p.get_by_label('New layer name').fill('Workbench');press(p,'.hb-layer-add button')
 layers=p.evaluate('__hubBoard.active.layers()');key=layers['order'][-1];assert layers['labels'][key]=='Workbench'
 section=p.locator('[data-layer='+key+']');press(p,section.get_by_role('button',name='Move backward Workbench',exact=True))
 assert p.evaluate('(k)=>__hubBoard.active.layers().order.indexOf(k)',key)==2
 pick=p.locator('[data-layer-block]').first;block=pick.get_attribute('data-layer-block')
 press(p,pick);p.keyboard.press('Home');p.keyboard.press('Enter');p.wait_for_timeout(250)
 # Reopen after menu redraw and verify selection was stored.
 assert p.evaluate('(id)=>!!__hubBoard.active.layers().members[id]',block)
 p.reload();p.wait_for_selector('[data-layers]');p.evaluate("__hubBoard.active.view().setMode('3d')");p.wait_for_timeout(300);press(p,'[data-layers]')
 assert key in p.evaluate('__hubBoard.active.layers().order')
 section=p.locator('[data-layer='+key+']');press(p,section.get_by_role('button',name='Remove layer Workbench',exact=True));press(p,section.get_by_text('MOVE BLOCKS AND REMOVE',exact=True))
 assert key not in p.evaluate('__hubBoard.active.layers().order')
 assert len(p.evaluate('__hubBoard.active.layers().order'))==3

def test_3d_tidy_repackages_visible_blocks_in_ordered_layer_bands(page):
 p,_=page;p.evaluate("__hubBoard.active.view().setMode('3d')");p.wait_for_timeout(350)
 # Scatter current blocks, then use the actual TIDY control.
 p.evaluate("()=>{let s=__hubBoard.active.state();Object.values(s.L).forEach((l,i)=>{l.x=i%3*37;l.y=i%2*53});}")
 press(p,p.locator('.hb-viewbar').get_by_text('TIDY',exact=True));p.wait_for_timeout(700)
 bands=p.evaluate("""()=>{let s=__hubBoard.active.state(),groups={};for(let b of document.querySelectorAll('.hk[data-id]')){let id=b.dataset.id,l=s.L[id];if(!l||s.hid[id]||b.hidden)continue;let z=parseFloat(b.style.getPropertyValue('--hb-dz'))||0;(groups[z]??=[]).push([l.y,l.y+b.offsetHeight]);}return Object.entries(groups).sort((a,b)=>+a[0]-b[0]).map(([z,rows])=>({z:+z,top:Math.min(...rows.map(r=>r[0])),bottom:Math.max(...rows.map(r=>r[1]))}));}""")
 assert len(bands)>=2,bands
 assert all(a['bottom']<b['top'] for a,b in zip(bands,bands[1:])),bands
 # Each pack is saved on the same layout path; reload preserves exact coordinates.
 before=p.evaluate('__hubBoard.active.state().L');p.reload();p.wait_for_function('!!__hubBoard.active');p.wait_for_timeout(500);after=p.evaluate('__hubBoard.active.state().L')
 assert all(after[k]['x']==v['x'] and after[k]['y']==v['y'] for k,v in before.items() if k in after)
