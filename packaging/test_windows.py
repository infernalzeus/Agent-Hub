"""Several windows of one tool: another block of the same tool, offset, allowed to overlap, at stepped depths in 3D, closable, five at most."""
import sys

import pytest

sys.path.insert(0, "packaging")
from playwright.sync_api import sync_playwright  # noqa: E402
from test_ui_lifecycle import hub  # noqa: E402,F401


@pytest.fixture
def board(hub):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1600, "height": 1000}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!(window.__hubBoard && __hubBoard.active)")
        pg.wait_for_timeout(700)
        assert pg.evaluate("__hubBoard.open('/missions')")
        pg.wait_for_selector(".hk[data-id='card:oc'].exp .hk-fr", timeout=8000)
        yield pg
        assert errors == []
        b.close()


def ids(pg):
    return pg.evaluate("[...document.querySelectorAll('.hk.exp')].map(e => e.dataset.id).filter(i => i.startsWith('card:oc'))")


def test_a_new_window_of_the_tool_stacks_in_front_and_overlaps_the_first(board):
    assert board.locator(".hk[data-id='card:oc'] [data-a=dup]").is_visible()          # only an open tool offers it
    board.click(".hk[data-id='card:oc'] [data-a=dup]")
    board.wait_for_selector(".hk[data-id='card:oc#2'].exp .hk-fr", timeout=8000)
    assert ids(board) == ["card:oc", "card:oc#2"]
    assert board.evaluate("document.querySelector(\".hk[data-id='card:oc#2'] .hk-h .t\").textContent") == "AUTO-LLM 2"
    a = board.evaluate("(() => { const r = document.querySelector(\".hk[data-id='card:oc']\").getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })()")
    b = board.evaluate("(() => { const r = document.querySelector(\".hk[data-id='card:oc#2']\").getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })()")
    assert b[0] < a[2] and b[1] < a[3] and b[0] > a[0] - 1                               # they overlap: a stack, not a row
    assert board.evaluate("__hubBoard.active.state().L['card:oc#2'].z > __hubBoard.active.state().L['card:oc'].z")


def test_in_3d_the_windows_sit_at_stepped_depths_and_pressing_one_brings_it_forward(board):
    board.click(".hk[data-id='card:oc'] [data-a=dup]")
    board.click(".hk[data-id='card:oc#2'] [data-a=dup]")
    board.wait_for_selector(".hk[data-id='card:oc#3'].exp .hk-fr", timeout=8000)
    board.click(".hb-btn:has-text('VIEW')")                                               # 3D
    board.wait_for_timeout(600)
    dz = lambda i: float(board.evaluate("document.querySelector(\".hk[data-id='%s']\").style.getPropertyValue('--hb-dz')" % i).replace("px", ""))
    assert dz("card:oc#3") == 170 and dz("card:oc#2") == 80 and dz("card:oc") == -10      # last made is in front, the first at the back
    board.locator(".hk[data-id='card:oc'] .hk-h").dispatch_event("pointerdown", {"button": 0, "pointerId": 1, "bubbles": True, "clientX": 400, "clientY": 100})   # press the one at the back
    board.evaluate("dispatchEvent(new PointerEvent('pointerup', {pointerId: 1}))")
    assert dz("card:oc") == 170 and dz("card:oc#3") == 80


def test_a_window_can_be_closed_and_the_first_one_stays(board):
    board.click(".hk[data-id='card:oc'] [data-a=dup]")
    board.wait_for_selector(".hk[data-id='card:oc#2'].exp", timeout=8000)
    board.click(".hk[data-id='card:oc#2'] [data-a=col]")
    board.wait_for_timeout(300)
    assert board.locator(".hk[data-id='card:oc#2']").count() == 0 and ids(board) == ["card:oc"]
    assert board.evaluate("document.querySelector(\".hk[data-id='card:oc']\").style.getPropertyValue('--hb-dz')") == ""    # alone again: no stepped depth


def test_five_windows_at_most(board):
    for _ in range(6):
        board.click(".hk[data-id='card:oc'] [data-a=dup]")
        board.wait_for_timeout(150)
    assert len(ids(board)) == 5
