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


def test_the_panel_opens_on_the_overview_with_every_explanation_closed_and_a_button_for_each(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 900}).new_page()
        pg.goto(hub + "/yard")
        pg.wait_for_selector(".ovgrid .ovc", timeout=15000)
        got = pg.evaluate("""()=>({tab:document.querySelector('.tabs .on').dataset.tab,rows:document.querySelectorAll('.ovgrid .ovc b').length,open:[...document.querySelectorAll('.ovd')].filter(e=>!e.hidden).length,btns:document.querySelectorAll('.ovgrid button').length})""")
        pg.click(".ovgrid button")
        opened = pg.evaluate("[...document.querySelectorAll('.ovd')].filter(e=>!e.hidden).length")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector("#rdata button", timeout=8000)
        data_open = pg.evaluate("[...document.querySelectorAll('#rdata .card')].filter(e=>!e.hidden).length")
        cards_open = pg.evaluate("document.querySelectorAll('.rc.open').length")
        b.close()
    assert got == {"tab": "overview", "rows": 6, "open": 0, "btns": 6}, got
    assert opened == 1 and data_open == 0 and cards_open == 0                       # a button opens one; nothing else opens by itself


def test_teach_says_why_it_is_empty(hub):
    import urllib.request
    j = json.loads(urllib.request.urlopen(hub + "/api/learning/teach").read())
    assert set(j["status"]) == {"logged", "since_fresh", "last", "fresh"}
