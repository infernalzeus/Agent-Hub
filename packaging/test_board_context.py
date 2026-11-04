"""Right click: a menu on a block (its own title-bar actions) and on the empty board; the end of a right-drag orbit is not a menu."""
import sys
sys.path.insert(0, "packaging")
from test_board_round2 import hub, page  # noqa: E402,F401


def test_right_click_on_a_block_title_lists_its_actions_and_minimise_works(page):
    t = page.locator(".hk[data-id=ses] .hk-h").bounding_box()
    page.mouse.click(t["x"] + 30, t["y"] + 12, button="right"); page.wait_for_timeout(300)
    labels = page.locator(".hb-ctx button").all_inner_texts()
    assert any("MINIMISE" in l for l in labels) and any("HIDE" in l or "CLOSE" in l for l in labels), labels
    page.locator(".hb-ctx button", has_text="MINIMISE").click(); page.wait_for_timeout(300)
    assert page.locator(".hb-ctx").count() == 0
    assert page.evaluate("document.querySelector('.hk[data-id=ses]').classList.contains('min')")
    assert page.evaluate("getComputedStyle(document.querySelector('.hk[data-id=ses] .hk-b')).display") == "none"      # the title bar alone: no fade, no peek


def test_right_click_on_the_empty_board_offers_board_actions(page):
    r = page.evaluate("""()=>{const hk=[...document.querySelectorAll('.hk')].map(e=>e.getBoundingClientRect());for(let y=130;y<innerHeight-120;y+=20)for(let x=20;x<innerWidth-140;x+=20)if(!hk.some(b=>x>b.left-8&&x<b.right+8&&y>b.top-8&&y<b.bottom+8))return [x,y];return null}""")
    assert r
    page.mouse.click(r[0], r[1], button="right"); page.wait_for_timeout(300)
    labels = page.locator(".hb-ctx button").all_inner_texts()
    assert "TIDY" in labels and "FIT EVERYTHING" in labels, labels
    page.keyboard.press("Escape"); page.wait_for_timeout(220); assert page.locator(".hb-ctx").count() == 0


def test_a_right_drag_orbit_does_not_end_in_a_menu(page):
    page.evaluate("__hubBoard.active.view().setMode('3d')"); page.wait_for_timeout(900)
    r = page.evaluate("""()=>{const hk=[...document.querySelectorAll('.hk')].map(e=>e.getBoundingClientRect());for(let y=130;y<innerHeight-120;y+=20)for(let x=20;x<innerWidth-300;x+=20)if(!hk.some(b=>x>b.left-8&&x<b.right+8&&y>b.top-8&&y<b.bottom+8))return [x,y];return null}""")
    page.mouse.move(r[0], r[1]); page.mouse.down(button="right"); page.mouse.move(r[0] + 90, r[1] + 40, steps=6); page.mouse.up(button="right"); page.wait_for_timeout(300)
    assert page.locator(".hb-ctx").count() == 0


def test_a_menu_that_a_page_handles_itself_is_left_alone(page):
    page.evaluate("""()=>{const b=document.createElement('button');b.id='own';b.textContent='x';b.style.cssText='position:fixed;left:300px;top:300px;z-index:60';b.oncontextmenu=e=>{e.preventDefault();window.__own=1};document.querySelector('.hb').appendChild(b)}""")
    page.mouse.click(305, 305, button="right"); page.wait_for_timeout(200)
    assert page.evaluate("window.__own") == 1 and page.locator(".hb-ctx").count() == 0


def test_hiding_a_block_takes_its_slab_with_it_and_3d_opens_nearly_flat(page):
    page.evaluate("__hubBoard.active.view().setMode('3d')"); page.wait_for_timeout(900)
    t = page.evaluate("__hubBoard.active.view().tilt()")
    assert abs(t["rx"]) <= 6 and abs(t["ry"]) <= 6, t                                  # flat to the eye, the slab edge just showing
    page.evaluate("document.querySelector('.hk[data-id=runs] button[data-a=x]').click()"); page.wait_for_timeout(500)
    assert page.evaluate("[...document.querySelectorAll('.hk-solid')].filter(s=>getComputedStyle(s).display!=='none'&&s.hidden).length") == 0
    assert page.locator("[data-tray=hidden] span").inner_text() == "1"


def test_view_controls_are_one_group_on_the_right_and_actions_stay_on_top(page):
    r = page.evaluate("""()=>{const vb=document.querySelector('.hb-viewbar').getBoundingClientRect(),bar=document.querySelector('.hb-bar').getBoundingClientRect();
      const inside=t=>[...document.querySelectorAll('.hb-viewbar .hb-btn')].some(b=>b.textContent.trim().startsWith(t));
      const top=t=>[...document.querySelectorAll('.hb-bar > .hb-btn')].some(b=>b.textContent.trim().includes(t));
      return {right:vb.right>innerWidth-20,below:vb.top>=bar.bottom-1,view:inside('VIEW'),fit:inside('FIT'),blocks:inside('BLOCKS'),tidy:inside('TIDY'),talk:!!document.querySelector('.hb-bar [aria-label=\"Talk to the Hub\"]'),ingest:!!document.querySelector('.hb-ingest-dock button'),pc:!!document.querySelector('.hb-bar [aria-label=\"PC control\"]')}}""")
    assert all(r.values()), r


def test_minimise_leaves_only_the_title_bar_and_an_offscreen_chip_carries_a_question_mark(page):
    page.evaluate("document.querySelector('.hk[data-id=hlt] button[data-a=min]').click()"); page.wait_for_timeout(400)
    s = page.evaluate("(()=>{const e=document.querySelector('.hk[data-id=hlt]');return [e.getBoundingClientRect().height,getComputedStyle(e).opacity,getComputedStyle(e.querySelector('.hk-b')).display,getComputedStyle(e.querySelector('.hk-b')).filter]})()")
    assert s[0] < 40 and s[1] == "1" and s[2] == "none", s
    page.evaluate("__hubBoard.active.view().setMode('cad');for(let i=0;i<8;i++)document.querySelectorAll('.hb-viewbar .hb-zoomrow button')[1].click()"); page.wait_for_timeout(700)
    chips = page.locator(".hb-tray .hb-btn")
    assert chips.count() > 0 and not any("FIND" in t for t in chips.all_inner_texts())
    assert chips.first.locator("svg").count() == 1


def test_tidy_and_fit_glide_instead_of_jumping(page):
    page.evaluate("for(const id of ['runs','ses']){const l=__hubBoard.active.state().L[id];l.x+=300;l.y+=150;}")
    before = page.evaluate("JSON.stringify(Object.fromEntries(Object.entries(__hubBoard.active.state().L).map(([k,l])=>[k,[l.x,l.y]])))")
    page.locator(".hb-viewbar .hb-btn", has_text="TIDY").click()
    page.wait_for_timeout(120)
    mid = page.evaluate("JSON.stringify(Object.fromEntries(Object.entries(__hubBoard.active.state().L).map(([k,l])=>[k,[l.x,l.y]])))")
    page.wait_for_timeout(1000)
    end = page.evaluate("JSON.stringify(Object.fromEntries(Object.entries(__hubBoard.active.state().L).map(([k,l])=>[k,[l.x,l.y]])))")
    assert before != mid != end, "TIDY moved the blocks in one frame"                  # a frame in the middle that is neither the start nor the end
    k0 = page.evaluate("__hubBoard.active.state().V.k")
    page.locator(".hb-viewbar .hb-btn", has_text="FIT").click()
    page.wait_for_timeout(100)
    k1 = page.evaluate("__hubBoard.active.state().V.k")
    page.wait_for_timeout(900)
    k2 = page.evaluate("__hubBoard.active.state().V.k")
    assert k0 == k2 or k1 != k2                                                         # FIT is mid-glide at 100 ms unless it was already fitted


def test_an_app_can_be_moved_to_another_layer_from_the_layers_list(page):
    page.evaluate("__hubBoard.active.view().setMode('3d')"); page.wait_for_timeout(900)
    page.locator(".hb-btn[data-layers]").click()
    assert page.locator(".hb-layer-block").count() > 3
    before = page.evaluate("getComputedStyle(document.querySelector(\".hk[data-id='card:oc'],.hk[data-id='card:movie']\")||document.body).getPropertyValue('--hb-dz')")
    row = page.locator(".hb-layer-block", has_text="Auto-LLM").first
    assert row.count() == 1
    row.locator(".hb-btn", has_text="TO APPS").click(); page.wait_for_timeout(500)
    assert page.locator(".hb-layer-block", has_text="Auto-LLM").locator("..").count() >= 1
    saved = page.evaluate("JSON.parse(localStorage.getItem('agenthub:board:layers')).members")
    assert any(v == "apps" for v in saved.values()), saved                                # the move is remembered
