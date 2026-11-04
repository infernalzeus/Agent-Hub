"""/chats: Talk history, quick OpenCode chat and agent sessions in one page; Auto-LLM tabs are Missions, Graph, R learning, Agency, Chats."""
import json, os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub


def test_chats_page_shows_the_talk_lines_the_quick_chat_button_and_sessions(hub):
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
        pg = b.new_page()
        pg.goto(hub + "/chats")
        pg.evaluate("""() => sessionStorage.setItem('agenthub:log', JSON.stringify([
            {at: Date.now(), kind: 'chat', t: 'Smith: opening missions'},
            {at: Date.now() - 5000, kind: 'chat', t: 'You: open missions'},
            {at: Date.now() - 9000, kind: 'hands', t: 'TAP'}]))""")
        pg.reload()
        pg.wait_for_selector("#talk .row")
        txt = pg.inner_text("#talk")
        assert "open missions" in txt and "opening missions" in txt and "TAP" not in txt      # only chat lines, not hand lines
        assert pg.locator("#quick").is_visible() and pg.locator("#open-chat").is_visible()
        pg.wait_for_function("document.querySelector('#sessions .row')||/No agent sessions|Could not/.test(document.getElementById('sessions').innerText)")
        b.close()


def test_auto_llm_tabs_are_named_in_the_new_order():
    src = (os.path.join(os.path.dirname(__file__), "..", "hub", "static", "home-board.js"))
    s = open(src, encoding="utf-8").read()
    want = "[['MISSIONS', '/missions'], ['GRAPH', '/graph'], ['R LEARNING', '/yard'], ['AGENCY', '/agents'], ['CHATS', '/chats']]"
    assert want in s and "QUICK CHAT" not in s
