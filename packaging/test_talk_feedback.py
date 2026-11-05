"""A plain click on TALK opens no window, so the button and a note under it must say what happened: listening, stopped, or why not."""
import os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub

TALK = '.hb-bar .talk-btn'


def press(pg, sel):
    r = pg.locator(sel).bounding_box()
    pg.mouse.move(r['x'] + r['width'] / 2, r['y'] + r['height'] / 2); pg.mouse.down(); pg.wait_for_timeout(100); pg.mouse.up(); pg.wait_for_timeout(900)


def make(p, hub, fake):
    args = ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] if fake else []
    b = p.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER', 'msedge'), headless=True, args=args)
    ctx = b.new_context(service_workers='block', viewport={'width': 1280, 'height': 800}, permissions=['microphone'] if fake else [])
    pg = ctx.new_page(); pg.goto(hub + '/?enter=1'); pg.wait_for_function('!!window.__hubBoard?.active'); pg.wait_for_timeout(1000)
    return b, pg


def test_click_with_a_working_microphone_shows_listening_on_the_button_and_a_note(hub):
    with sync_playwright() as p:
        b, pg = make(p, hub, True)
        press(pg, TALK)
        assert pg.locator('#voice').is_hidden()
        assert 'on' in pg.get_attribute(TALK, 'class').split()
        assert pg.locator('.v-bubble').is_visible() and 'Listening' in pg.inner_text('.v-bubble')
        press(pg, TALK)                                                        # second click stops, still no window
        assert 'on' not in pg.get_attribute(TALK, 'class').split() and pg.locator('#voice').is_hidden()
        assert 'Stopped' in pg.inner_text('.v-bubble')
        log = pg.evaluate("sessionStorage.getItem('agenthub:log')"); assert 'Listening on' in log and 'Listening off' in log
        b.close()


def test_click_without_a_microphone_says_why_next_to_the_button(hub):
    with sync_playwright() as p:
        b, pg = make(p, hub, False)
        press(pg, TALK)
        assert pg.locator('#voice').is_hidden()
        pg.wait_for_function("document.querySelector('.v-bubble') && !document.querySelector('.v-bubble').hidden && /microphone/i.test(document.querySelector('.v-bubble').textContent)", timeout=6000)
        pg.locator('.v-bubble').click(); pg.wait_for_timeout(400)               # the note opens the chat so the person can type instead
        assert pg.locator('#voice').is_visible()
        b.close()
