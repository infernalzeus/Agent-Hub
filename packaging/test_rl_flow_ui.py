"""The yard's flow, on an isolated Hub, headless, processor only: small blocks you can move and hide, the inside of each block behind its i, the settings on the block that owns them,
a session of its own set apart from the menu, and arrows that light as a real short session runs."""
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

FAMILIES = ("direct", "modal", "search", "menu", "long", "unnamed", "tabs", "confirm")


def _post(pg, url, body):
    return pg.evaluate("([u,b])=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(async r=>({status:r.status,body:await r.json().catch(()=>null)}))", [url, body])


def _has(pg, *subs, timeout=6000):
    """The block's card is filled in after a short fetch: wait for what it should say, then report whether it does."""
    try:
        pg.wait_for_function("s=>s.every(x=>document.getElementById('nodebox').innerText.includes(x))", arg=list(subs), timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def _open(pw, hub, w=1300, h=950):
    b = pw.chromium.launch(headless=True)
    pg = b.new_context(service_workers="block", viewport={"width": w, "height": h}).new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(hub + "/yard")
    pg.evaluate("localStorage.removeItem('hub-rl-flow')")
    _post(pg, "/api/yard/knobs/reset", {})
    pg.reload()
    pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===21")
    return b, pg, errors


def test_the_session_is_set_apart_from_the_menu_and_every_setting_sits_on_a_block(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        assert pg.locator(".band #top-shadow").count() == 1 and pg.locator(".band #go").count() == 0           # the menu band holds the switch only
        assert pg.locator(".sess #go").count() == 1 and pg.locator(".sess .flowwrap").count() == 1             # the session card holds the start button and the flow
        assert pg.locator("#more").count() == 0 and pg.locator("details").count() == 0                           # no "more settings" bucket
        assert pg.locator("#flowsvg .fedge").count() == 22 and pg.locator("#nodebox").is_hidden()
        assert pg.locator(".fnode[data-id=actor] rect").evaluate("e=>e.getBoundingClientRect().width") < 170      # small blocks
        assert pg.locator(".fnode.outside").count() == 7                                                       # blocks that do not run inside a session are drawn dashed
        pg.locator(".fnode[data-id=live] rect").click()
        assert _has(pg, "Weight: Windows says it is playing", "Ceiling without Windows confirming")
        pg.locator(".fnode[data-id=router] rect").click()
        assert _has(pg, "Neighbours", "Classifier step size")
        b.close()
    assert errors == []


def test_the_i_on_a_block_shows_its_inside_the_layers_the_numbers_and_the_arithmetic(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        pg.locator(".fnode[data-id=actor] .fi").click()                                                       # the i: the inside, opened
        assert _has(pg, "357", "tanh", "learned numbers", "s = w2", "SETTINGS") and pg.locator("#nodebox .chain .lay").count() == 4
        pg.locator(".fnode[data-id=rew] .fi").click()
        assert _has(pg, "per press", "never-press")
        pg.locator(".fnode[data-id=upd] rect").click()                                                          # a plain click: settings only, INSIDE on request
        assert _has(pg, "Discount") and "G_t" not in pg.inner_text("#nodebox")
        pg.click("#nodebox button:text-is('INSIDE')")
        assert _has(pg, "G_t = r_t", "A_t = G_t - V(z_t)")
        _post(pg, "/api/yard/knobs", {"hidden_units": 8})
        pg.locator(".fnode[data-id=actor] .fi").click()
        assert _has(pg, str(357 * 8 + 16))                                                                         # what is shown follows the live settings
        _post(pg, "/api/yard/knobs/reset", {})
        b.close()
    assert errors == []


def test_blocks_can_be_moved_and_hidden_the_arrows_follow_and_the_layout_is_remembered(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        edge = lambda: pg.locator("#flowsvg .fedge[data-id='upd>actor'] path").get_attribute("d")                  # noqa: E731
        before, tf0 = edge(), pg.locator(".fnode[data-id=actor]").get_attribute("transform")
        box = pg.locator(".fnode[data-id=actor] rect").bounding_box()
        pg.mouse.move(box["x"] + 60, box["y"] + 40)
        pg.mouse.down()
        pg.mouse.move(box["x"] + 60 + 90, box["y"] + 40 + 70, steps=6)
        pg.mouse.up()
        assert pg.locator(".fnode[data-id=actor]").get_attribute("transform") != tf0 and edge() != before         # it moved and the arrow went with it
        assert pg.locator("#nodebox").is_hidden()                                                                  # a drag is not a click
        assert pg.evaluate("JSON.parse(localStorage.getItem('hub-rl-flow')).pos.actor.length") == 2
        pg.reload()
        pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===21")
        assert pg.locator(".fnode[data-id=actor]").get_attribute("transform") != tf0                               # remembered
        pg.locator(".fnode[data-id=hind]").hover()
        pg.locator(".fnode[data-id=hind] .fx").click()                                                             # hide a block
        assert pg.locator(".fnode[data-id=hind]").evaluate("e=>getComputedStyle(e).display") == "none" and pg.locator("#flowsvg .fedge[data-id='hind>rew']").evaluate("e=>getComputedStyle(e).display") == "none"
        assert "1 HIDDEN" in pg.inner_text("#showall")
        pg.click("#showall")
        assert pg.locator(".fnode[data-id=hind]").evaluate("e=>getComputedStyle(e).display") != "none" and pg.locator(".fnode[data-id=actor]").get_attribute("transform") == tf0
        b.close()
    assert errors == []


def test_a_real_short_session_lights_the_arrows_updates_the_blocks_and_offers_the_saved_versions(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        small = {"episodes": 100, "eval_per_cell": 4, **{f"family_{f}": f in ("direct", "modal") for f in FAMILIES}}
        assert _post(pg, "/api/yard/knobs", small)["status"] == 200
        pg.locator(".fnode[data-id=rew] rect").click()
        slider = pg.locator("#nodebox .krow:has(label:text-is('Reward for finishing')) input[type=range]")
        slider.evaluate("e=>{e.value='2.5';e.dispatchEvent(new Event('input'))}")
        pg.wait_for_function("fetch('/api/yard/knobs').then(r=>r.json()).then(j=>j.knobs.find(k=>k.name==='win').value===2.5)", timeout=8000)
        pg.wait_for_function("!document.getElementById('kreset').hidden")
        pg.click("#go")
        pg.wait_for_selector("#flowsvg .fedge.lit", state="attached", timeout=40000)
        pg.wait_for_selector("#flowsvg .fnode.pulse", state="attached", timeout=10000)
        pg.wait_for_function("document.getElementById('result').textContent.includes('Last session')", timeout=90000)
        assert "version" in pg.inner_text("#result") and "forbidden pressed on" in pg.inner_text("#result")
        pg.wait_for_function("document.getElementById('go').hidden===false", timeout=20000)
        assert "moved by" in pg.locator(".fnode[data-id=upd] text.fl").text_content() and "screens picked a forbidden" in pg.locator(".fnode[data-id=safety] text.fl").text_content()
        pg.locator(".fnode[data-id=ver] .fi").click()                                                              # the saved versions, with a way back
        assert _has(pg, "versions:", "IN USE")
        pg.once("dialog", lambda d: d.accept())
        pg.click("#kreset")
        pg.wait_for_function("document.getElementById('kreset').hidden")
        assert pg.evaluate("fetch('/api/yard/knobs').then(r=>r.json()).then(j=>j.knobs.find(k=>k.name==='win').value)") == 1.0
        b.close()
    assert errors == []
