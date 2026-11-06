"""Smith on the landing page is the wake switch: drawn line by line while the wake word is off or while he listens, gone while it waits for his name, and a click on him toggles it."""
import pytest
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

FAKE_MIC = """navigator.mediaDevices.getUserMedia = async () => { const c = new AudioContext(), d = c.createMediaStreamDestination(), o = c.createOscillator(); o.connect(d); o.start(); return d.stream; };"""


def _offset(pg, i):
    return pg.evaluate("i=>parseFloat(getComputedStyle(document.querySelectorAll('.smith-draw .ln')[i]).strokeDashoffset)", i)


def test_smith_is_drawn_when_the_wake_word_is_off_and_a_click_on_him_switches_it_on_and_off(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900})
        ctx.add_init_script(FAKE_MIC)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/offline.html")
        pg.wait_for_selector("#wake-toggle", state="visible", timeout=20000)
        pg.wait_for_function("window.__hubWake && window.__hubWake.smith().shown === true", timeout=10000)
        info = pg.evaluate("window.__hubWake.smith()")
        assert info["state"] == "off" and info["drawn"] >= 60                                       # the traced strokes are there
        pg.wait_for_function("(()=>{const p=document.querySelectorAll('.smith-draw .ln');return p.length&&parseFloat(getComputedStyle(p[p.length-1]).strokeDashoffset)===0})()", timeout=8000)
        assert _offset(pg, 0) == 0                                                                  # drawn in, every line
        assert pg.get_attribute("#smith-hit", "aria-label").startswith("Smith") and "on" in pg.get_attribute("#smith-hit", "title")
        pg.click("#smith-hit")                                                                      # click him: he draws out and the ring lights
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.wait_for_function("window.__hubWake.smith().shown === false")
        pg.wait_for_function("document.getElementById('wake-ring').classList.contains('on')")
        pg.wait_for_function("parseFloat(getComputedStyle(document.querySelectorAll('.smith-draw .ln')[0]).strokeDashoffset)===1", timeout=8000)      # fully drawn out
        assert "off" in pg.get_attribute("#smith-hit", "title")
        pg.evaluate("window.__hubWake._set('convo')")                                                 # he is addressed: he comes back and breathes while it listens
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        assert "live" in pg.get_attribute(".smith-draw", "class")
        pg.evaluate("window.__hubWake._set('wake')")                                                  # quiet again: he leaves, the ring stays lit
        pg.wait_for_function("window.__hubWake.smith().shown === false")
        pg.click("#smith-hit")                                                                      # click the invisible him: wake word off, he draws in
        pg.wait_for_function("window.__hubWake.state() === 'off'", timeout=10000)
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        assert not pg.evaluate("document.getElementById('wake-ring').classList.contains('on')")
        b.close()
    assert errors == []


def test_the_old_wake_button_and_smith_stay_in_step_and_reduced_motion_shows_him_without_animation(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900}, reduced_motion="reduce")
        ctx.add_init_script(FAKE_MIC)
        pg = ctx.new_page()
        pg.goto(hub + "/offline.html")
        pg.wait_for_selector("#wake-toggle", state="visible", timeout=20000)
        pg.wait_for_function("window.__hubWake.smith().shown === true")
        assert _offset(pg, 3) == 0 and pg.evaluate("document.querySelectorAll('.smith-draw .ln')[3].getAnimations().length") == 0       # no animation, just shown
        pg.click("#wake-toggle")                                                                    # the button under the ring is the same switch
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.wait_for_function("window.__hubWake.smith().shown === false")
        assert _offset(pg, 3) == 1
        pg.click("#wake-toggle")
        pg.wait_for_function("window.__hubWake.state() === 'off' && window.__hubWake.smith().shown === true", timeout=10000)
        b.close()
