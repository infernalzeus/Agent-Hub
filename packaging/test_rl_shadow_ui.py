"""The R button (EXPERIMENTAL): a small light that is on only while shadow mode is on, and a panel with the switch and a PC TASKS tab. Isolated Hub, headless."""
import pytest
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)


def _post(pg, body):
    return pg.evaluate("b=>fetch('/api/yard/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(r=>r.json())", body)


def _light(p):
    return p.locator(".hb-learning").evaluate("e=>getComputedStyle(e,'::after').backgroundColor")


def test_the_r_light_is_off_by_default_and_follows_the_panels_switch(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        c = b.new_context(service_workers="block", viewport={"width": 1280, "height": 720})
        pg = c.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard?.active")
        _post(pg, {"experimental": False})
        pg.reload()
        pg.wait_for_function("!!window.__hubBoard?.active")
        pg.wait_for_selector(".hb-learning", state="attached")
        assert pg.locator(".hb-learning").is_hidden()                                     # the whole layer is hidden until it is switched on in Settings
        _post(pg, {"experimental": True})
        pg.reload()
        pg.wait_for_function("!!window.__hubBoard?.active")
        pg.wait_for_selector(".hb-learning")
        assert "lit" not in pg.locator(".hb-learning").get_attribute("class")             # off by default
        assert "experimental" in pg.locator(".hb-learning").get_attribute("title").lower()
        grey = _light(pg)
        pg.evaluate("window.postMessage({hubShadow:true}, location.origin)")              # what the panel's switch sends
        pg.wait_for_function("document.querySelector('.hb-learning').classList.contains('lit')")
        assert _light(pg) == "rgb(0, 230, 118)" and grey != _light(pg)
        pg.evaluate("window.postMessage({hubShadow:false}, location.origin)")
        pg.wait_for_function("!document.querySelector('.hb-learning').classList.contains('lit')")
        pg.evaluate("window.postMessage({hubShadow:true}, 'https://elsewhere.example')")  # a message from another origin cannot light it
        pg.wait_for_timeout(200)
        assert "lit" not in pg.locator(".hb-learning").get_attribute("class")
        b.close()
    assert errors == []


def test_the_panel_says_experimental_and_its_switch_turns_shadow_mode_on_and_off(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block").new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/yard")
        assert "EXPERIMENTAL" in pg.inner_text("#topbar")
        pg.wait_for_function("document.getElementById('top-shadow').textContent.length>0")
        if pg.locator("#top-shadow").is_disabled():
            pytest.skip("the test run holds shadow mode off with an environment variable")
        assert pg.inner_text("#top-shadow") == "SHADOW MODE: OFF" and "Nothing is recorded" in pg.inner_text("#top-note")
        pg.click("#top-shadow")
        pg.wait_for_function("document.getElementById('top-shadow').textContent==='SHADOW MODE: ON'")
        assert "Observing" in pg.inner_text("#top-note")
        j = pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")
        assert j["shadow"]["on"] is True and j["learning"]["on"] is True                 # one switch sets both
        pg.click("[data-tab=teach]")
        pg.wait_for_function("!!document.getElementById('teachframe').src")
        fr = pg.frame_locator("#teachframe")
        fr.locator("#s-task").click()
        fr.locator("#card").get_by_text("No PC task has been kept yet").wait_for()
        assert "EXPERIMENTAL" in fr.locator("#count").inner_text() and fr.locator("p.sub").count() == 0           # no description paragraph
        pg.click("#top-shadow")
        pg.wait_for_function("document.getElementById('top-shadow').textContent==='SHADOW MODE: OFF'")
        assert pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")["shadow"]["on"] is False
        b.close()
    assert errors == []


def test_the_r_dot_is_the_size_of_the_pc_dot_and_its_click_turns_shadow_off_or_opens_the_panel(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        c = b.new_context(service_workers="block", viewport={"width": 1280, "height": 720})
        pg = c.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        api = lambda body: _post(pg, body)
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard?.active")
        api({"experimental": True, "shadow": False, "learning": False})
        pg.reload()
        pg.wait_for_function("!!window.__hubBoard?.active")
        pg.wait_for_selector(".hb-learning")
        dot = lambda s: pg.locator(s).evaluate("e=>{const x=getComputedStyle(e,'::after');return [x.width,x.height,x.top,x.right]}")
        assert dot(".hb-learning") == dot(".hb-pc") == ["4px", "4px", "4px", "4px"]          # as small as the PC-control dot
        assert pg.locator(".hb-glass-panel").count() == 0
        pg.click(".hb-learning")                                                         # light off: the click opens the panel
        pg.wait_for_selector(".hb-glass-panel")
        assert pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")["shadow"]["on"] is False
        pg.reload()
        pg.wait_for_function("!!window.__hubBoard?.active")
        pg.wait_for_selector(".hb-learning")
        if pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")["shadow"]["forced_off_by_environment"]:
            b.close()
            pytest.skip("the test run holds shadow mode off with an environment variable")
        api({"shadow": True, "learning": True})                                           # the panel's own switch
        pg.reload()
        pg.wait_for_function("!!window.__hubBoard?.active")
        pg.wait_for_function("document.querySelector('.hb-learning').classList.contains('lit')")
        pg.click(".hb-learning")                                                         # light on: this click only switches shadow off
        pg.wait_for_function("!document.querySelector('.hb-learning').classList.contains('lit')")
        assert pg.locator(".hb-glass-panel").count() == 0
        assert pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")["shadow"]["on"] is False
        pg.click(".hb-learning")                                                         # and the next click opens the panel
        pg.wait_for_selector(".hb-glass-panel")
        b.close()
    assert errors == []


def test_the_panel_has_scores_routines_with_a_fresh_start_and_smaller_type(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 900, "height": 700}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/yard")
        assert pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)") <= 13
        pg.click("[data-tab=scores]")
        pg.wait_for_function("document.querySelectorAll('#fitgrid .sc').length>=5")
        pg.wait_for_function("document.querySelectorAll('#chal tr').length>=7")           # tally, thompson and linucb behind two choices
        txt = pg.inner_text("#tab-scores")
        for word in ("Did the Hub understand what you meant?", "Task confidence", "Control (yard)", "RIVAL WAYS OF CHOOSING", "thompson", "linucb", "Gate for a new version", "report card"):
            assert word in txt, word
        pg.click("[data-tab=routines]")
        pg.wait_for_function("document.getElementById('freshnote').textContent.length>0")
        assert pg.is_visible("#fresh")
        b.close()
    assert errors == []
