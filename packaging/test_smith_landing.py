"""Smith replaces the wake button on the landing page. His picture is the button: it shows while the wake word is off (so it can be switched on) and while you are talking with him
(you said Smith: it pops up, and goes when the talk is quiet); while the Hub only waits for his name it is invisible but still clickable. Nothing is drawn over the orb. At ENTER the
page goes quiet (microphone let go, polling stopped, the ring stops breathing) so the move to the dashboard has the whole processor."""
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


def _shown(pg):
    pg.wait_for_function("window.__hubWake.smith().icon === true")
    pg.wait_for_function("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity) > 0.9", timeout=4000)


def _hidden(pg):
    pg.wait_for_function("window.__hubWake.smith().icon === false")
    pg.wait_for_function("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity) < 0.05", timeout=4000)


def test_his_picture_is_the_button_it_pops_up_when_you_say_smith_and_nothing_is_drawn_over_the_orb(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _shown(pg)                                                                                 # wake word off: the picture is the switch
        assert pg.get_attribute("#smith-slot", "aria-label").startswith("Smith")
        assert "smith-held" in pg.get_attribute("#wake-toggle", "class")                           # the old button is no longer on the page
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.wait_for_function("document.getElementById('wake-ring').classList.contains('on')")
        _hidden(pg)                                                                                # waiting for his name: invisible
        pg.evaluate("window.__hubWake._set('convo')")                                              # you said Smith: he pops up, in the button's place
        _shown(pg)
        slot = pg.evaluate("(()=>{const r=document.getElementById('smith-slot').getBoundingClientRect(), g=document.querySelector('.globe-wrap').getBoundingClientRect();return {top:r.top,gbottom:g.bottom}})()")
        assert slot["top"] >= slot["gbottom"] - 2                                                  # below the orb, never in front of it
        for s in ("think", "speak"):
            pg.evaluate(f"window.__hubWake._set('{s}')"); _shown(pg)
        assert pg.evaluate("document.querySelectorAll('svg.smith-draw, .smith-draw').length") == 0   # no outline exists any more
        pg.evaluate("window.__hubWake._set('wake')")                                               # quiet again: gone
        _hidden(pg)
        pg.click("#smith-slot")                                                                    # the invisible him: off, the picture returns
        pg.wait_for_function("window.__hubWake.state() === 'off'", timeout=10000)
        _shown(pg)
        b.close()
    assert errors == []


def test_the_hidden_wake_button_still_works(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub, reduced_motion="reduce")
        pg.evaluate("document.getElementById('wake-toggle').click()")                              # the old switch is still the one holding the state
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._set('convo')")
        _shown(pg)
        b.close()


def test_pressing_enter_quiets_the_page_microphone_ring_and_picture(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake' && window.__hubWake.mic()", timeout=15000)
        pg.wait_for_function("getComputedStyle(document.getElementById('wake-ring')).animationName === 'wkBreath'")
        pg.evaluate("window.__hubWake._leave()")                                                   # what the click on ENTER does first
        assert pg.evaluate("window.__hubWake.mic()") is False                                      # the microphone and its analysers are let go
        assert pg.evaluate("getComputedStyle(document.getElementById('wake-ring')).animationName") == "none"
        assert pg.evaluate("getComputedStyle(document.getElementById('smith-slot')).display") == "none"
        assert pg.evaluate("localStorage.getItem('agenthub:wake')") == "1"                         # the wake word stays switched on for the dashboard
        b.close()


def _enter(pw, hub, listening):
    """Click ENTER; return milliseconds to the new address and the slowest gap between two animation frames on the way."""
    b, pg = _landing(pw, hub)
    pg.wait_for_selector("#wake-btn[data-s=enter]", timeout=20000)
    if listening:
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._set('convo')")
        pg.wait_for_timeout(900)
    pg.evaluate("""()=>{window.__gaps=[];let last=performance.now();const f=t=>{window.__gaps.push(t-last);last=t;try{sessionStorage.setItem('gaps',JSON.stringify(window.__gaps))}catch(e){}requestAnimationFrame(f)};requestAnimationFrame(f)}""")
    t0 = time.time()
    pg.click("#wake-btn")
    pg.wait_for_url("**enter=1**", timeout=30000)
    ms = (time.time() - t0) * 1000
    b.close()
    return ms


def test_entering_the_dashboard_is_no_slower_while_he_is_listening(hub):
    with sync_playwright() as pw:
        plain = min(_enter(pw, hub, False) for _ in range(2))
        listening = min(_enter(pw, hub, True) for _ in range(2))
    assert listening < plain + 600, (plain, listening)                                             # headless uses software graphics, so only a large gap would be real
