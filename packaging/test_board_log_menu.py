"""User-reported log/menu regressions, trusted input on isolated state only."""
import json
from test_board_round10 import page,press
from test_ui_lifecycle import hub


def install_mcp(p):
 state={'on':False}
 def reply(r):
  if r.request.method=='POST':state['on']=r.request.post_data_json['enabled']
  r.fulfill(json={'servers':[{'name':'windows','installed':True,'enabled':state['on']}]})
 p.route('**/api/mcp',reply);p.route('**/api/mcp/windows/enabled',reply)
 p.reload();p.wait_for_function('!!window.__hubBoard?.active');p.wait_for_timeout(500)


def test_mcp_on_off_is_logged_only_after_confirmed_result(page):
 p,_=page;install_mcp(p)
 press(p,'.hb-pc');press(p,'.hb-pc');press(p,'.hb-log-toggle');press(p,'.hl-head');press(p,'.hl-filters [data-kind=all]')
 text=p.locator('.hl-rows').inner_text();assert 'MCP / PC control ON' in text and 'MCP / PC control OFF' in text
 assert p.evaluate('captureRequests')==0


def test_chat_filter_does_not_open_chat_and_chat_has_real_history(page):
 p,_=page;press(p,'.hb-log-toggle');press(p,'.hl-head');press(p,'.hl-filters [data-kind=chat]')
 assert not p.locator('#voice').is_visible()
 p.evaluate("dispatchEvent(new CustomEvent('hub-log',{detail:{kind:'chat',text:'You: Earlier example'}}))")
 p.locator('.hb-bar .talk-btn').click(button='right');p.wait_for_timeout(250)
 assert p.locator('#voice').is_visible();press(p,'#hb-chat-history-tab')
 assert 'Earlier example' in p.locator('#hb-chat-history').inner_text()
 assert p.locator('#hb-chat-history').is_visible() and not p.locator('#v-log').is_visible()
 press(p,'#hb-chat-current-tab');assert p.locator('#v-log').is_visible()
 assert p.evaluate('captureRequests')==0


def test_hands_right_click_opens_controls_and_legend_is_interactive(page):
 p,_=page;p.locator('.hb-hands').click(button='right');p.wait_for_timeout(250)
 pane=p.get_by_role('dialog',name='HAND CONTROL',exact=True);assert pane.is_visible()
 assert pane.get_by_role('button',name='START HANDS',exact=True).is_visible()
 press(p,pane.get_by_role('button',name='GESTURE LEGEND',exact=True))
 assert pane.locator('.hb-gesture-guide').is_visible();assert pane.locator('.hb-gesture-guide article').count()>=7
 press(p,pane.get_by_role('button',name='GESTURE LEGEND',exact=True));assert not pane.locator('.hb-gesture-guide').is_visible()
 assert p.evaluate('captureRequests')==0


def test_view_panel_is_bottom_anchored_above_minimap(page):
 p,_=page
 for mode in ['cad','3d']:
  p.evaluate('(mode)=>__hubBoard.active.view().setMode(mode)',mode);p.wait_for_timeout(300)
  r=p.evaluate("""()=>{let a=document.querySelector('.hb-right-panel'),m=document.querySelector('.hb-map'),h=document.querySelector('.hb-panel-hide');return {a:a.getBoundingClientRect().toJSON(),m:m.getBoundingClientRect().toJSON(),h:h.getBoundingClientRect().toJSON(),top:getComputedStyle(a).top,bottom:getComputedStyle(a).bottom}}""")
  assert 0<r['m']['top']-r['a']['bottom']<90,r
  assert r['a']['bottom']<=r['h']['top'] and r['h']['bottom']<=r['m']['top'],r
  if mode=='cad':assert r['a']['top']>200,r


def test_mcp_failure_is_logged_as_failure_not_success(page):
 p,_=page;install_mcp(p);p.route('**/api/mcp/windows/enabled',lambda r:r.fulfill(status=500,body='Test refusal'))
 press(p,'.hb-pc');press(p,'.hb-log-toggle');press(p,'.hl-head')
 text=p.locator('.hl-rows').inner_text();assert 'could not change: Test refusal' in text and 'MCP / PC control ON' not in text


def test_hands_primary_action_keeps_existing_setup_path_without_camera(page):
 p,_=page;p.route('**/api/hands/status',lambda r:r.fulfill(json={'ready':False}))
 press(p,'.hb-hands');assert p.locator('.hands-setup').is_visible()
 assert not p.get_by_role('dialog',name='HAND CONTROL',exact=True).is_visible()
 assert p.evaluate('captureRequests')==0


def test_history_survives_reload_and_can_be_cleared_without_reimport(page):
 p,_=page
 p.evaluate("dispatchEvent(new CustomEvent('hub-log',{detail:{kind:'chat',text:'Smith: Saved example'}}))")
 p.reload();p.wait_for_function('!!__hubBoard.active');p.locator('.hb-bar .talk-btn').click(button='right');p.wait_for_timeout(250);press(p,'#hb-chat-history-tab')
 assert 'Saved example' in p.locator('#hb-chat-history').inner_text()
 press(p,p.locator('#hb-chat-history').get_by_role('button',name='CLEAR HISTORY',exact=True));press(p,p.get_by_role('button',name='CONFIRM CLEAR HISTORY',exact=True))
 assert 'Saved example' not in p.locator('#hb-chat-history').inner_text()
 p.reload();p.wait_for_function('!!__hubBoard.active');p.locator('.hb-bar .talk-btn').click(button='right');p.wait_for_timeout(250);press(p,'#hb-chat-history-tab')
 assert 'Saved example' not in p.locator('#hb-chat-history').inner_text()

def test_history_keeps_full_reply_instead_of_the_short_log_preview(page):
 p,_=page;reply='A detailed example. '*40+'Visible final sentence.'
 p.route('**/api/voice/chat',lambda r:r.fulfill(json={'say':reply}))
 p.locator('.hb-bar .talk-btn').click(button='right');p.wait_for_timeout(250)
 if p.locator('#v-mute').inner_text()=='SOUND ON':press(p,'#v-mute')
 p.locator('#v-in').fill('Explain an example');press(p,'#v-go');press(p,'#hb-chat-history-tab')
 assert reply in p.locator('#hb-chat-history').inner_text()
 assert p.evaluate('captureRequests')==0
