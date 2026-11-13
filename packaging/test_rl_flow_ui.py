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
    pg.click("[data-tab=yard]")                                                                  # the panel opens on the overview; these tests are about the flow
    pg.evaluate("localStorage.removeItem('hub-rl-flow')")
    _post(pg, "/api/yard/knobs/reset", {})
    pg.reload()
    pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===22")
    return b, pg, errors


def test_the_session_is_set_apart_from_the_menu_and_every_setting_sits_on_a_block(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        assert pg.locator(".band #top-shadow").count() == 1 and pg.locator(".band #go").count() == 0           # the menu band holds the switch only
        assert pg.locator(".sess #go").count() == 1 and pg.locator(".sess .flowwrap").count() == 1             # the session card holds the start button and the flow
        assert pg.locator("#more").count() == 0 and pg.locator("details").count() == 0                           # no "more settings" bucket
        assert pg.locator("#flowsvg .fedge").count() == 23 and pg.locator("#nodebox").is_hidden()
        assert pg.locator(".fnode[data-id=actor] rect").evaluate("e=>e.getBoundingClientRect().width") < 0.15 * pg.viewport_size["width"]      # small blocks (the drawing scales with the panel)
        assert pg.locator(".fnode.outside").count() == 8                                                       # blocks that do not run inside a session are drawn dashed
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
        edge = lambda: pg.locator("#flowsvg .fedge[data-id='upd>actor'] path:not(.hit)").get_attribute("d")                  # noqa: E731
        before, tf0 = edge(), pg.locator(".fnode[data-id=actor]").get_attribute("transform")
        box = pg.locator(".fnode[data-id=actor] rect").bounding_box()
        pg.mouse.move(box["x"] + 60, box["y"] + 40)
        pg.mouse.down()
        pg.mouse.move(box["x"] + 60 + 90, box["y"] + 40 + 70, steps=6)
        pg.mouse.up()
        pg.wait_for_function("(d)=>document.querySelector(\"#flowsvg .fedge[data-id='upd>actor'] path:not(.hit)\").getAttribute('d')!==d", arg=before)      # the arrows are re-routed on the next frame
        assert pg.locator(".fnode[data-id=actor]").get_attribute("transform") != tf0 and edge() != before         # it moved and the arrow went with it
        assert pg.locator("#nodebox").is_hidden()                                                                  # a drag is not a click
        assert pg.evaluate("JSON.parse(localStorage.getItem('hub-rl-flow')).pos.actor.length") == 2
        pg.reload()
        pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===22")
        assert pg.locator(".fnode[data-id=actor]").get_attribute("transform") != tf0                               # remembered
        pg.locator(".fnode[data-id=hind]").hover()
        pg.locator(".fnode[data-id=hind] .fx").click()                                                             # hide a block
        pg.wait_for_function("getComputedStyle(document.querySelector(\"#flowsvg .fedge[data-id='hind>rew']\")).display==='none'")
        assert pg.locator(".fnode[data-id=hind]").evaluate("e=>getComputedStyle(e).display") == "none"
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


def test_arrows_run_around_the_blocks_never_through_one_and_each_arrow_explains_itself(hub):
    with sync_playwright() as pg_:
        b, pg, errors = _open(pg_, hub)
        crossed = pg.evaluate(r"""()=>{const svg=document.getElementById('flowsvg'),bad=[];
          const rects=[...svg.querySelectorAll('.fnode')].map(g=>{const t=g.getAttribute('transform').match(/translate\(([-\d.]+) ([-\d.]+)\)/),r=g.querySelector('rect');return {id:g.dataset.id,x:+t[1]+2,y:+t[2]+2,w:+r.getAttribute('width')-4,h:+r.getAttribute('height')-4};});
          svg.querySelectorAll('.fedge').forEach(e=>{const p=e.querySelector('path:not(.hit)'),L=p.getTotalLength(),[a,z]=e.dataset.id.split('>');
            for(let s=6;s<L-6;s+=3){const q=p.getPointAtLength(s);for(const r of rects){if(q.x>r.x&&q.x<r.x+r.w&&q.y>r.y&&q.y<r.y+r.h)bad.push(e.dataset.id+' through '+r.id);}}});
          return [...new Set(bad)];}""")
        assert crossed == []
        assert pg.locator("#flowsvg .fedge .hit").count() == 23
        for eid, words in (("enc>actor", ("357", "only thing the actor")), ("upd>actor", ("A_t", "pressed control")), ("safety>gate", ("zero",))):
            pg.evaluate("id=>document.querySelector(`#flowsvg .fedge[data-id='${id}'] .hit`).dispatchEvent(new MouseEvent('click',{bubbles:true}))", eid)     # an elbow's middle is not on the line, so click the arrow itself
            assert _has(pg, *words, "since the Hub started")
        pg.locator(".fnode[data-id=actor] rect").click()
        assert _has(pg, "SETTINGS") and "since the Hub started" not in pg.inner_text("#nodebox")                # a block click replaces the arrow card
        b.close()
    assert errors == []


def test_the_picture_reads_as_a_reinforcement_learning_system_frames_names_for_each_block_and_td3_marked_not_built(hub):
    with sync_playwright() as pw:
        b, pg, errors = _open(pw, hub)
        frames = pg.evaluate("[...document.querySelectorAll('#flowsvg .fgl')].map(e=>e.textContent)")
        assert frames == ["DATA AND SETTINGS", "AGENT: what learns", "ENVIRONMENT", "EVALUATION AND RELEASE", "OTHER LEARNERS (not part of the session)"]
        kinds = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#flowsvg .fnode')].map(g=>[g.dataset.id,g.querySelector('.fk').textContent]))")
        assert kinds["actor"] == "policy network (actor)" and kinds["crit"] == "value network (critic)" and kinds["env"] == "environment" and kinds["repl"] == "replay buffer"
        assert all(kinds.values())
        # a frame really surrounds its blocks: the actor sits inside the AGENT frame, the environment block inside ENVIRONMENT
        pg.wait_for_function("[...document.querySelectorAll('#flowsvg .fgroup')].every(e=>+e.getAttribute('width')>0)")                  # frames are placed on the next frame
        inside = pg.evaluate("""()=>{const r=n=>document.querySelector('.fnode[data-id='+n+'] rect').getBoundingClientRect(),f=[...document.querySelectorAll('#flowsvg .fgroup')].map(e=>e.getBoundingClientRect());
          const within=(a,o)=>a.left>=o.left&&a.right<=o.right&&a.top>=o.top&&a.bottom<=o.bottom;return [f.filter(o=>within(r('actor'),o)).length,f.filter(o=>within(r('env'),o)).length]}""")
        assert inside == [1, 1]
        assert pg.locator(".fnode[data-id=actor] .fgly circle").count() >= 8 and pg.locator(".fnode[data-id=crit] .fgly").count() == 1    # the networks are drawn as networks
        assert pg.locator(".fnode.todo[data-id=td3]").count() == 1 and pg.locator("#flowsvg .fedge.todo").count() == 1                     # TD3: red, dashed arrow
        pg.locator(".fnode[data-id=td3] rect").click()
        assert _has(pg, "continuous actor-critic", "NOT BUILT", "DDPG")
        pg.locator(".fnode[data-id=td3] .fi").click()
        assert _has(pg, "min(Q1", "replaces DDPG")
        b.close()
    assert errors == []
