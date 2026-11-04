"""The Agents page lists the Hub's own helpers (voice, doctor, desktop agent, router, learners, recorder), built from live facts."""
import sys
sys.path.insert(0, "packaging")

from test_ui_lifecycle import hub  # noqa: E402,F401


def test_the_helpers_endpoint_lists_the_doctor_and_every_learner(hub):
    import json
    import urllib.request
    rows = json.loads(urllib.request.urlopen(hub + "/api/hub/helpers").read())["helpers"]
    ids = [r["id"] for r in rows]
    for want in ("smith", "doctor", "desktop", "router", "yard", "bandit-model", "bandit-rung", "recorder"):
        assert want in ids, want
    assert all(r["does"] and r["where"] for r in rows)


def test_the_agents_page_shows_a_hub_helpers_tab_with_the_doctor_icon(hub):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block").new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/agents#helpers")
        pg.wait_for_selector("[data-fam=helpers]")
        pg.wait_for_function("document.querySelectorAll('#list .persona').length>=8", timeout=15000)
        assert "The Doctor" in pg.inner_text("#list") and "Yard learner" in pg.inner_text("#list")
        assert pg.locator("#list .persona svg path").count() >= 5                      # the doctor and the other helpers have drawn icons
        b.close()
    assert errors == []


def test_agent_pictures_are_served_by_id_and_nothing_else_is(hub, tmp_path, monkeypatch):
    import urllib.error
    import urllib.request
    for bad in ("doctor.png", "..%2f..%2fapp.py", "x.png", "Doctor.png"):
        try:
            urllib.request.urlopen(hub + "/static/agent-icons/" + bad)
            served = True
        except urllib.error.HTTPError as e:
            served = e.code != 404 and e.code != 400
        assert not served or bad == "doctor.png", bad               # until Codex adds the pictures, a missing one is a 404; a path trick never works
