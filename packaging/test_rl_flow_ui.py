"""The yard's flow and the settings each block owns, on an isolated Hub, headless, processor only: a short real session is run and the arrows light as it works."""
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

FAMILIES = ("direct", "modal", "search", "menu", "long", "unnamed", "tabs", "confirm")


def _post(pg, url, body):
    return pg.evaluate("([u,b])=>fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(async r=>({status:r.status,body:await r.json().catch(()=>null)}))", [url, body])


def test_the_yard_draws_small_blocks_each_with_its_own_settings_and_lights_the_arrows_during_a_real_session(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1300, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/yard")
        small = {"episodes": 100, "eval_per_cell": 4, **{f"family_{f}": f in ("direct", "modal") for f in FAMILIES}}
        assert _post(pg, "/api/yard/knobs", small)["status"] == 200
        pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===16")
        assert pg.locator("#flowsvg .fedge").count() == 16 and pg.locator("#stop").is_hidden()
        assert pg.locator(".fnode[data-id=actor] rect").evaluate("e=>e.getBoundingClientRect().width") < 200       # small blocks
        assert pg.locator("#nodebox").is_hidden()
        pg.locator(".fnode[data-id=actor] rect").click()                                                  # click a block: one sentence and its own settings
        assert pg.locator("#nodebox").is_visible() and "Actor" in pg.inner_text("#nodebox") and "Hidden layer size" in pg.inner_text("#nodebox") and "Actor step size" in pg.inner_text("#nodebox")
        assert "Reward for finishing" not in pg.inner_text("#nodebox")
        pg.locator(".fnode[data-id=rew] rect").click()
        slider = pg.locator("#nodebox .krow:has(label:text-is('Reward for finishing')) input[type=range]")
        slider.evaluate("e=>{e.value='2.5';e.dispatchEvent(new Event('input'))}")
        pg.wait_for_function("fetch('/api/yard/knobs').then(r=>r.json()).then(j=>j.knobs.find(k=>k.name==='win').value===2.5)", timeout=8000)
        pg.locator(".fnode[data-id=demos] rect").click()
        assert "Nothing to adjust" in pg.inner_text("#nodebox")
        pg.click("#go")
        pg.wait_for_selector("#flowsvg .fedge.lit", state="attached", timeout=40000)               # information travelling along an arrow
        pg.wait_for_selector("#flowsvg .fnode.pulse", state="attached", timeout=10000)
        pg.wait_for_function("document.getElementById('result').textContent.includes('Last session')", timeout=90000)
        assert "version" in pg.inner_text("#result") and "learned" in pg.inner_text("#result")
        pg.wait_for_function("document.getElementById('go').hidden===false", timeout=20000)
        assert "moved by" in pg.locator(".fnode[data-id=upd] text.fl").text_content()
        assert pg.locator("#flog").inner_text().strip() != ""
        _post(pg, "/api/yard/knobs/reset", {})
        b.close()
    assert errors == []


def test_the_other_settings_sit_under_more_settings_and_a_reset_puts_them_back(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/yard")
        _post(pg, "/api/yard/knobs/reset", {})
        _post(pg, "/api/yard/knobs", {"hide_forbidden": True})
        pg.reload()
        pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===16")
        assert pg.locator("#knobbox").is_hidden()                                                   # collapsed until opened
        pg.click("#more summary")
        txt = pg.inner_text("#knobbox")
        for word in ("TASK CONFIDENCE", "LEARNERS", "ROUTER YARDSTICK", "SEARCH", "CANDIDATE ROUTINES", "NOT ADJUSTABLE", "Never-press list", "Hide forbidden controls"):
            assert word in txt, word
        assert "Reward for finishing" not in txt and "Hidden layer size" not in txt                 # those belong to their blocks
        pg.wait_for_function("!document.getElementById('kreset').hidden")
        pg.once("dialog", lambda d: d.accept())
        pg.click("#kreset")
        pg.wait_for_function("document.getElementById('kreset').hidden")
        assert pg.evaluate("fetch('/api/yard/knobs').then(r=>r.json()).then(j=>j.knobs.find(k=>k.name==='hide_forbidden').value)") is False
        b.close()
    assert errors == []
