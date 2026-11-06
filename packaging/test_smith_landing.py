"""Smith replaces the wake button on the landing page. His picture is the switch: visible while the wake word is off, faded out (still clickable) while it waits for his name.
His outline is drawn, line by line, only while you are talking with him; it lives outside the orb, has no filter, is built the first time it is needed and is hidden for good the
moment ENTER is pressed, so it cannot slow the move to the dashboard."""
import time

from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

FAKE_MIC = """navigator.mediaDevices.getUserMedia = async () => { const c = new AudioContext(), d = c.createMediaStreamDestination(), o = c.createOscillator(); o.connect(d); o.start(); return d.stream; };"""


def _landing(pw, hub, **ctx_args):
    b = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900}, **ctx_args)
    ctx.add_init_script(FAKE_MIC)
    pg = ctx.new_page()
    pg.goto(hub + "/offline.html")
    pg.wait_for_selector("#smith-slot", state="visible", timeout=20000)
    return b, pg


def _opacity(pg):
    return pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity)")


def test_his_picture_is_the_switch_and_his_outline_appears_only_while_you_talk_with_him(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.wait_for_function("window.__hubWake && window.__hubWake.smith().icon === true", timeout=10000)
        info = pg.evaluate("window.__hubWake.smith()")
        assert info["state"] == "off" and info["shown"] is False and info["built"] is False and info["strokes"] >= 60     # nothing is drawn, nothing is even built
        pg.wait_for_function("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity) > 0.9", timeout=4000)
        assert pg.get_attribute("#smith-slot", "aria-label").startswith("Smith")
        assert "smith-held" in pg.get_attribute("#wake-toggle", "class")                           # the old button is no longer on the page
        assert not pg.evaluate("!!document.querySelector('.globe-wrap .smith-draw, .globe-wrap svg.smith-draw')")
        pg.click("#smith-slot")                                                                    # his picture goes out: wake word on, ring lit
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.wait_for_function("document.getElementById('wake-ring').classList.contains('on')")
        pg.wait_for_function("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity) < 0.05", timeout=3000)
        after = pg.evaluate("window.__hubWake.smith()")
        assert after["icon"] is False and after["shown"] is False and after["built"] is False      # invisible while it waits for his name: no outline
        pg.evaluate("window.__hubWake._set('convo')")                                              # he is addressed: his outline is drawn
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        assert pg.evaluate("getComputedStyle(document.querySelector('.smith-draw')).display") == "block" and pg.evaluate("document.querySelector('.smith-draw').parentNode === document.body")
        pg.wait_for_function("(()=>{const p=document.querySelectorAll('.smith-draw .ln');return parseFloat(getComputedStyle(p[p.length-1]).strokeDashoffset)===0})()", timeout=6000)
        assert pg.evaluate("getComputedStyle(document.querySelector('.smith-draw .ln')).filter") == "none"      # no glow filter: that was the cost
        pg.evaluate("window.__hubWake._set('wake')")                                               # quiet again: gone
        pg.wait_for_function("window.__hubWake.smith().shown === false")
        pg.wait_for_function("getComputedStyle(document.querySelector('.smith-draw')).display === 'none'", timeout=3000)
        pg.click("#smith-slot")                                                                    # the invisible him: off, his picture returns
        pg.wait_for_function("window.__hubWake.state() === 'off'", timeout=10000)
        pg.wait_for_function("window.__hubWake.smith().icon === true && parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity) > 0.9", timeout=3000)
        assert not pg.evaluate("document.getElementById('wake-ring').classList.contains('on')")
        pg.evaluate("window.__hubWake._set('speak')")
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        pg.evaluate("window.__hubWake._leave()")                                                   # ENTER: his outline is out of the page at once
        assert pg.evaluate("window.__hubWake.smith().shown") is False and pg.evaluate("getComputedStyle(document.querySelector('.smith-draw')).display") == "none"
        b.close()
    assert errors == []


def test_the_hidden_wake_button_still_works_and_reduced_motion_draws_him_without_animation(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub, reduced_motion="reduce")
        pg.evaluate("document.getElementById('wake-toggle').click()")                              # the old switch is still the one holding the state
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._set('convo')")
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        assert pg.evaluate("document.querySelectorAll('.smith-draw .ln')[3].getAnimations().length") == 0
        assert pg.evaluate("parseFloat(getComputedStyle(document.querySelectorAll('.smith-draw .ln')[3]).strokeDashoffset)") == 0
        pg.evaluate("window.__hubWake._set('wake')")
        pg.wait_for_function("getComputedStyle(document.querySelector('.smith-draw')).display === 'none'", timeout=3000)
        b.close()


def _enter_ms(pw, hub, talking):
    b, pg = _landing(pw, hub)
    pg.wait_for_selector("#wake-btn[data-s=enter]", timeout=20000)
    if talking:
        pg.evaluate("window.__hubWake._set('convo')")
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        pg.wait_for_timeout(900)
    t0 = time.time()
    pg.click("#wake-btn")
    pg.wait_for_url("**enter=1**", timeout=30000)                                                  # the landing page's own leaving transition ends in this address
    ms = (time.time() - t0) * 1000
    b.close()
    return ms


def test_entering_the_dashboard_is_no_slower_when_he_was_on_screen(hub):
    with sync_playwright() as pw:
        plain = min(_enter_ms(pw, hub, False) for _ in range(2))
        talking = min(_enter_ms(pw, hub, True) for _ in range(2))
    assert talking < plain + 900, (plain, talking)                                                 # headless uses software graphics, so only a large gap would be real
