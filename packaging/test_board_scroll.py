"""The wheel scrolls the page inside a window, in 2D and in 3D (in 3D the browser's own scrolling stopped working under the tilt)."""
import os
import pytest
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub


@pytest.fixture
def page(hub):
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER', 'msedge'), headless=True)
        ctx = b.new_context(service_workers='block', viewport={'width': 1440, 'height': 900})
        ctx.request.put(hub + '/api/board/prefs', data='{}', headers={'Content-Type': 'application/json'})
        pg = ctx.new_page(); errors = []; pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(hub + '/?enter=1'); pg.wait_for_function('!!window.__hubBoard?.active'); pg.wait_for_timeout(1200)
        yield pg
        assert errors == []
        ctx.close(); b.close()


@pytest.mark.parametrize('mode', ['cad', '3d'])
def test_wheel_scrolls_the_page_inside_a_window_and_leaves_the_board_alone(page, mode):
    page.evaluate('(m)=>__hubBoard.active.view().setMode(m)', mode); page.wait_for_timeout(800)
    page.click(".hk[data-id='card:oc'] .hk-app"); page.wait_for_timeout(2200)
    page.click(".hk[data-id='card:oc'] .hk-tabs button:has-text('AGENCY')"); page.wait_for_timeout(2200)
    fr = page.locator(".hk[data-id='card:oc'] iframe").bounding_box()
    before = page.evaluate("JSON.stringify(__hubBoard.active.state().L['card:oc'])")
    page.mouse.move(fr['x'] + fr['width'] / 2, fr['y'] + fr['height'] / 2); page.mouse.wheel(0, 300); page.wait_for_timeout(700)
    top = page.evaluate(".hk[data-id='card:oc'] iframe") if False else page.evaluate("document.querySelector(\".hk[data-id='card:oc'] iframe\").contentDocument.scrollingElement.scrollTop")
    assert top > 100, (mode, top)                                       # the page moved
    fr2 = page.locator(".hk[data-id='card:oc'] iframe").bounding_box()
    assert (fr['x'], fr['y']) == (fr2['x'], fr2['y'])                    # and the board did not pan or zoom under it
    page.mouse.wheel(0, -300); page.wait_for_timeout(600)
    assert page.evaluate("document.querySelector(\".hk[data-id='card:oc'] iframe\").contentDocument.scrollingElement.scrollTop") < top
