"""Neo designs agents; Agent Smith is only the voice. Pictures on the Agents page are one big size."""
import sys
sys.path.insert(0, "packaging")

from test_ui_lifecycle import hub  # noqa: E402,F401


def test_the_agent_creator_is_neo_and_smith_is_not_a_persona_any_more():
    from hub import agent_knowledge as AK
    assert "neo" in AK.UTILITY_AGENTS and "agent-smith" not in AK.UTILITY_AGENTS
    persona = AK._load_persona("neo")
    assert persona and "Neo" in persona["body"] and "Agent Smith" not in persona["body"]


def test_the_agents_page_shows_neo_with_his_picture_and_every_picture_is_big(hub):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1000, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/agents")
        pg.wait_for_function("document.querySelectorAll('#list .persona').length>=3", timeout=15000)
        txt = pg.inner_text("body")
        assert "NEO" in txt and "AGENT SMITH" not in txt.upper().replace("SMITH IS THE VOICE", "")
        assert "EDIT WITH NEO" in txt
        assert pg.locator("#btn-create img").get_attribute("src") == "/static/agent-icons/neo.png"
        pg.wait_for_function("[...document.querySelectorAll('#list .persona .smith-a')].every(i=>i.complete)", timeout=8000)
        sizes = pg.evaluate("[...document.querySelectorAll('#list .persona .smith-a')].map(i=>Math.round(i.getBoundingClientRect().width))")
        assert sizes and all(w >= 64 for w in sizes), sizes
        pg.goto(hub + "/agents#helpers")
        pg.wait_for_function("document.querySelectorAll('#list .persona').length>=9", timeout=15000)
        pg.wait_for_function("[...document.querySelectorAll('#list .hic img, #list .smith-a')].every(i=>i.complete&&i.naturalWidth>0)", timeout=8000)
        sizes = pg.evaluate("[...document.querySelectorAll('#list .hic img, #list .smith-a')].map(i=>Math.round(i.getBoundingClientRect().width))")
        assert sizes and all(w >= 64 for w in sizes), sizes
        assert "Neo" in pg.inner_text("#list")
        b.close()
    assert errors == []


def test_the_doctor_is_told_how_to_call_neo_and_where_the_hub_is():
    from hub.features import support
    b = support.brief_for("the Agents page is empty")
    assert "Neo" in b and "/api/agents/draft" in b and "THE RUNNING HUB: http://127.0.0.1:" in b
    assert "nothing is saved" in b.lower() or "Nothing is saved" in b
