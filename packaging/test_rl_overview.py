"""The OVERVIEW tab of the reinforcement-learning panel: one row per learner, closed explanations, and TEACH saying why it is empty."""
import json

from playwright.sync_api import sync_playwright

from hub.yard import overview as OV
from test_ui_lifecycle import hub  # noqa: F401


def test_the_overview_has_a_row_per_learner_with_a_state_and_what_it_still_needs():
    j = OV.overview()
    ids = [r["id"] for r in j["rows"]]
    assert ids == ["recording", "router", "bandits", "presets", "policy", "routines"]
    for r in j["rows"]:
        assert r["state"] in ("off", "recording", "practice", "shadow", "shadow-picks", "live") and r["from"] and r["changes"] and r["needs"], r
    assert j["next"]


def test_the_panel_opens_on_the_overview_as_one_terminal_table_that_fits_the_screen_with_only_the_real_levers_as_buttons(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1366, "height": 768}).new_page()
        pg.goto(hub + "/yard")
        pg.wait_for_selector("#ovlist .tr .tn", timeout=15000)
        got = pg.evaluate("""()=>{const e=document.getElementById('ovlist');return {tab:document.querySelector('.tabs .on').dataset.tab,rows:e.querySelectorAll('.tr:not(.th) .tn').length,btns:e.querySelectorAll('button').length-e.querySelectorAll('.lv button').length,levers:e.querySelectorAll('.lv button').length,
          fits:e.scrollHeight<=e.clientHeight+1,page:document.documentElement.scrollHeight<=innerHeight+1,mono:/mono|consolas|courier/i.test(getComputedStyle(e).fontFamily),details:e.querySelectorAll('.td').length,px:parseFloat(getComputedStyle(e).fontSize)}}""")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector("#rdata button", timeout=8000)
        data_open = pg.evaluate("[...document.querySelectorAll('#rdata .card')].filter(e=>!e.hidden).length")
        b.close()
    assert got["tab"] == "overview" and got["rows"] == 6 and got["btns"] == 0 and got["levers"] >= 8, got      # a table: the only buttons are the levers that really change something
    assert got["fits"] and got["page"] and got["mono"] and got["details"] >= 8 and 10 <= got["px"] <= 15, got      # one screen, monospace, the font picked to fit
    assert data_open == 0


def test_teach_says_why_it_is_empty(hub):
    import urllib.request
    j = json.loads(urllib.request.urlopen(hub + "/api/learning/teach").read())
    assert set(j["status"]) == {"logged", "since_fresh", "last", "fresh"}


def test_choosing_a_preset_mode_also_switches_shadow_mode_on_so_the_two_are_one_action(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1366, "height": 768}).new_page()
        pg.goto(hub + "/yard")
        pg.wait_for_selector("#ovlist .lv button", timeout=15000)
        pg.wait_for_function("document.getElementById('top-shadow').textContent.startsWith('SHADOW MODE')")
        if pg.inner_text("#top-shadow") != "SHADOW MODE: OFF":
            pg.click("#top-shadow")
            pg.wait_for_function("document.getElementById('top-shadow').textContent === 'SHADOW MODE: OFF'")
        pg.locator("#ovlist .lv button", has_text="APPLY").click()
        pg.wait_for_function("document.getElementById('top-shadow').textContent === 'SHADOW MODE: ON'", timeout=8000)        # one click, both done
        assert pg.evaluate("fetch('/api/yard/knobs').then(r=>r.json()).then(j=>JSON.stringify(j)).then(t=>t.includes('\"preset_mode\"') && /preset_mode[^}]*\"value\": ?\"apply\"/.test(t))")
        pg.locator("#ovlist .lv button", has_text="SHADOW").click()                          # put the presets back to the default
        pg.wait_for_timeout(600)
        pg.click("#top-shadow")
        pg.wait_for_function("document.getElementById('top-shadow').textContent === 'SHADOW MODE: OFF'")
        b.close()
