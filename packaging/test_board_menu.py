"""The BLOCKS list can always be left: its button stays reachable, there is a close button, a click elsewhere closes it, and Escape still does."""
import os
import sys

import pytest

sys.path.insert(0, "packaging")
from playwright.sync_api import sync_playwright  # noqa: E402
from test_ui_lifecycle import hub  # noqa: E402,F401


@pytest.fixture
def board(hub):
    with sync_playwright() as p:
        opts = {'headless': os.environ.get('AGENTHUB_TEST_HEADED') != '1'}
        if os.environ.get('AGENTHUB_TEST_BROWSER'):
            opts['channel'] = os.environ['AGENTHUB_TEST_BROWSER']
        b = p.chromium.launch(**opts)
        pg = b.new_context(service_workers="block", viewport={"width": 1400, "height": 900}).new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!(window.__hubBoard && __hubBoard.active)")
        pg.wait_for_timeout(700)
        yield pg
        b.close()


def open_blocks(pg):
    pg.get_by_role('button',name='MORE',exact=True).click()
    pg.get_by_role('button',name='BLOCKS',exact=True).click()


def shown(pg):
    return not pg.evaluate("document.querySelector('.hb-jump').hidden")


def test_the_list_never_covers_the_button_that_opens_it(board):
    open_blocks(board)
    assert shown(board)
    btn = board.evaluate("(() => { const r = [...document.querySelectorAll('.hb-btn')].find(b => b.textContent === 'MORE').getBoundingClientRect(); return r.bottom; })()")
    top = board.evaluate("document.querySelector('.hb-jump').getBoundingClientRect().top")
    assert top > btn
    board.get_by_role('button',name='MORE',exact=True).click()              # return to the picker without the list covering it
    board.wait_for_timeout(300)
    assert not shown(board)


@pytest.mark.parametrize("how", ["x", "outside", "escape"])
def test_every_way_out_works(board, how):
    open_blocks(board)
    assert shown(board)
    if how == "x":
        board.click(".hb-jump-x")
    elif how == "outside":
        board.mouse.click(60, 880)
    else:
        board.keyboard.press("Escape")
    board.wait_for_timeout(350)
    assert not shown(board)


def test_choosing_a_block_closes_the_list(board):
    open_blocks(board)
    board.locator(".hb-jump button:not(.hb-jump-x)").first.click()
    board.wait_for_timeout(350)
    assert not shown(board)
