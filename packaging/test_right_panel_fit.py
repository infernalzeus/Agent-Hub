"""The view controls on the right of the board (zoom, FIT, TIDY, BLOCKS, the 3D axis and its buttons) are an overlay: never a scrolled box. On a short screen they are drawn smaller until all of them fit."""
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401


def test_the_right_hand_view_controls_never_scroll_and_shrink_to_fit_a_short_screen(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        out = {}
        for size in ((1920, 1080), (1180, 430), (1024, 380)):
            pg = b.new_context(service_workers="block", viewport={"width": size[0], "height": size[1]}).new_page()
            pg.goto(hub + "/?enter=1")
            pg.wait_for_function("!!window.__hubBoard", timeout=25000)
            pg.wait_for_timeout(1200)
            pg.evaluate("__hubBoard.active.view().setMode('3d')")
            pg.wait_for_timeout(700)
            pg.evaluate("window.__hubFitRight()")
            pg.wait_for_timeout(300)
            out[size] = pg.evaluate("""(()=>{const s=document.querySelector('.hb-right-scroll'),r=s.getBoundingClientRect(),last=[...s.children].pop().getBoundingClientRect();return {overflow:getComputedStyle(s).overflowY,fit:+(s.dataset.fit||1),gap:Math.round(r.bottom-last.bottom)}})()""")
            pg.close()
        b.close()
    for size, r in out.items():
        assert r["overflow"] == "visible", (size, r)                      # no scroll bar to cut anything off
        assert r["gap"] >= -2, (size, r)                                  # the last control ends inside the panel
    assert out[(1920, 1080)]["fit"] == 1 and out[(1024, 380)]["fit"] < 1  # a tall screen is left as it is; a short one is scaled down
