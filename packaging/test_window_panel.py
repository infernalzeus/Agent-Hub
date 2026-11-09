"""A window of this PC (or a Claude Code session) as a panel on the dashboard. The Windows calls are replaced by fakes: no real window is opened, shown or clicked by a test."""
import asyncio
import json
import urllib.parse
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from playwright.sync_api import sync_playwright

from hub.features import agent_sessions as AS, home_state as HS, voice as V, window_mirror as WM
from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

WINDOWS = [{"id": 11, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False},
           {"id": 12, "title": "Agent Hub - Microsoft Edge", "exe": "msedge.exe", "w": 1200, "h": 800, "minimised": False},
           {"id": 13, "title": "Untitled - Notepad", "exe": "notepad.exe", "w": 700, "h": 500, "minimised": False}]


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(WM, "list_windows", lambda: list(WINDOWS))
    clicks = []
    monkeypatch.setattr(WM, "capture", lambda hwnd, max_w=1000, quality=80: (b"\xff\xd8fakejpeg", "image/jpeg") if hwnd in (11, 12, 13) else None)
    monkeypatch.setattr(WM, "click", lambda hwnd, x, y: clicks.append((hwnd, x, y)) or True)
    return clicks


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.mark.parametrize("said,want", [("claude desktop", 11), ("Edge", 12), ("microsoft edge", 12), ("notepad", 13), ("the claude app", 11)])
def test_a_window_is_found_from_what_was_said(fake, said, want):
    assert WM.find_window(said)["id"] == want


def test_nothing_is_found_for_a_window_that_is_not_open(fake):
    assert WM.find_window("spotify") is None and WM.find_window("") is None


def test_the_endpoints_list_show_and_click_and_refuse_a_window_that_is_gone(fake):
    async def go():
        app = web.Application()
        app.add_routes(WM.routes)
        async with TestClient(TestServer(app)) as c:
            j = await (await c.get("/api/windows")).json()
            assert [w["id"] for w in j["windows"]] == [11, 12, 13]
            r = await c.get("/api/windows/12/frame?w=800")
            assert r.status == 200 and r.content_type == "image/jpeg" and r.headers["Cache-Control"] == "no-store"
            assert (await c.get("/api/windows/99/frame")).status == 404
            assert (await c.post("/api/windows/12/click", json={"x": 0.5, "y": 0.25})).status == 200 and fake == [(12, 0.5, 0.25)]
            assert (await c.get("/api/windows/find?q=edge")).status == 200
            assert "Orbitron" in await (await c.get("/mirror")).text()
    _run(go())


@pytest.mark.parametrize("said", ["open Claude Desktop in the dashboard", "show Edge as a panel", "put Notepad on the board", "open the Hub session in the dashboard",
                                  "open Claude Desktop in the dashboard for me as a separate window or a panel", "Open Claude Desktop for me in the dashboard", "show me Edge in a separate window on the dashboard"])
def test_the_spoken_phrase_is_a_window_request_and_the_screens_are_not(said):
    q = HS.ui_for(said, "")["window_query"]
    assert q and not q.lower().endswith(("for me", "window", "panel"))
    for other in ("open the dashboard", "show the dashboard", "open home", "clear the dashboard", "tidy the dashboard"):
        assert not HS.ui_for(other, "")["window_query"]


def test_saying_it_answers_with_a_panel_for_the_window_or_for_the_session(fake, monkeypatch):
    got = _run(V._window_command("Claude Desktop"))
    assert got["window"] == {"title": "Claude", "url": "/mirror?id=11"}
    monkeypatch.setattr(AS, "scan", lambda now=None, limit=10: [{"id": "abc123def456", "title": "Agent Hub development and bug fixes", "project": "Agent Hub", "agent": "claude"}])
    got = _run(V._window_command("the Agent Hub development session"))
    assert got["window"]["url"] == "/session?id=abc123def456" and "development" in got["say"]


def test_a_session_panel_reads_the_turns_and_the_title_of_the_session(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "abc123def456-0000.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in [{"type": "custom-title", "customTitle": "My named session"}, {"type": "user", "message": {"content": "fix the button"}},
                                                  {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, the button works."}]}}]) + "\n", encoding="utf-8")
    monkeypatch.setattr(AS, "CLAUDE_DIR", tmp_path)
    monkeypatch.setattr(AS, "CODEX_DIR", tmp_path / "nocodex")
    j = WM.session_turns("abc123def456")
    assert [t["who"] for t in j["turns"]] == ["you", "agent"] and j["turns"][1]["text"].startswith("Done")
    assert WM.session_turns("nope")["error"]


def test_the_board_opens_a_window_as_a_panel_of_its_own(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1300, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        assert pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=11'}})") is True
        pg.wait_for_selector(".hk[data-id^='extra:win-claude'] iframe", timeout=10000)
        assert "/mirror?id=11" in pg.evaluate("document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\").src")
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=11'}})")             # the same window again is the same panel, not a copy
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=12'}})")             # another window with the same title is another panel
        assert pg.locator(".hk[data-id^='extra:win-claude']").count() == 2
        b.close()
    assert errors == []


def test_a_panel_opened_on_one_device_opens_on_the_other_and_closing_it_closes_both(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pc = b.new_context(service_workers="block", viewport={"width": 1300, "height": 900}).new_page()
        phone = b.new_context(service_workers="block", viewport={"width": 390, "height": 800}).new_page()
        for pg in (pc, phone):
            pg.goto(hub + "/?enter=1")
            pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pc.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=4321'}})")
        phone.wait_for_selector(".hk[data-id^='extra:win-claude'] iframe[src*='id=4321']", timeout=12000)                 # the phone shows it without being asked
        assert phone.locator("iframe[src*='id=4321']").count() == 1
        phone.evaluate("fetch('/api/windows/panels?url=' + encodeURIComponent('/mirror?id=4321'), {method: 'DELETE'})")
        pc.wait_for_function("!document.querySelector(\"iframe[src*='id=4321']\")", timeout=12000)  # closed on the Hub: gone from the PC
        b.close()


def test_the_panel_can_type_and_scroll_when_clicks_and_keys_are_on(fake, monkeypatch):
    sent = []
    monkeypatch.setattr(WM, "type_into", lambda hwnd, text="", key="", ctrl=False: sent.append((hwnd, text, key, ctrl)) or True)
    monkeypatch.setattr(WM, "wheel", lambda hwnd, x, y, d: sent.append((hwnd, "wheel", d)) or True)

    async def go():
        app = web.Application()
        app.add_routes(WM.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/windows/11/keys", json={"text": "hi"})).status == 200
            assert (await c.post("/api/windows/11/keys", json={"key": "Enter"})).status == 200
            assert (await c.post("/api/windows/11/wheel", json={"x": 0.5, "y": 0.5, "delta": -120})).status == 200
            assert (await c.post("/api/windows/panels", json={"title": "Claude", "url": "/mirror?id=11"})).status == 200
            assert (await c.post("/api/windows/panels", json={"title": "x", "url": "https://evil.example/"})).status == 400
            assert [p["url"] for p in (await (await c.get("/api/windows/panels")).json())["panels"]] == ["/mirror?id=11"]
    _run(go())
    assert sent == [(11, "hi", "", False), (11, "", "Enter", False), (11, "wheel", -120)]


def test_the_stream_pushes_frames_at_the_chosen_rate_and_skips_an_unchanged_picture(fake, monkeypatch):
    frames = iter([b"\xff\xd8A", b"\xff\xd8A", b"\xff\xd8B"] + [b"\xff\xd8B"] * 50)
    monkeypatch.setattr(WM, "capture", lambda hwnd, max_w=1000, quality=80: (next(frames), "image/jpeg"))

    async def go():
        app = web.Application()
        app.add_routes(WM.routes)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/windows/11/stream?fps=30&w=800&q=85")
            assert r.status == 200 and r.headers["Content-Type"].startswith("multipart/x-mixed-replace")
            body = b""
            while body.count(b"--hubframe") < 2:
                body += await asyncio.wait_for(r.content.readany(), 3)
            r.close()
            return body
    body = _run(go())
    assert body.count(b"\xff\xd8A") == 1 and b"\xff\xd8B" in body                            # the repeated picture was sent once


def test_the_page_offers_rate_detail_quality_and_zoom_and_a_typing_box_for_a_phone():
    page = WM._MIRROR
    for needle in ('id="fps"', 'id="det"', 'id="qual"', 'id="zoom"', 'id="kb"', "/stream?fps=", 'data-key="Enter"', "focusKb", "kbLast"):
        assert needle in page


def test_the_bottom_left_tray_has_a_windows_button_that_opens_a_window_as_a_panel(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1300, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_selector(".hb-tray-count[data-tray='windows']", timeout=20000)
        pg.click(".hb-tray-count[data-tray='windows']")
        pg.wait_for_selector(".hb-tray-list:not([hidden]) button", timeout=10000)
        before = pg.locator(".hk[data-id^='extra:win-']").count()
        pg.click(".hb-tray-list:not([hidden]) button >> nth=0")
        pg.wait_for_function("n=>document.querySelectorAll(\".hk[data-id^='extra:win-']\").length>n", arg=before, timeout=10000)
        assert pg.locator(".hk[data-id^='extra:win-'] iframe[loading='eager']").count() >= 1             # a window panel loads at once, not when it scrolls into view
        b.close()
    assert errors == []


def test_the_page_falls_back_to_single_pictures_when_a_stream_never_arrives():
    page = WM._MIRROR
    assert "hubMirrorPoll" in page and "/frame?w=" in page and "poll(w)" in page


def test_what_is_typed_in_the_box_reaches_the_window_and_a_tap_on_the_picture_focuses_it(hub):
    sent = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True).new_page()
        pg.route("**/api/windows/*/stream*", lambda r: r.fulfill(status=200, content_type="image/jpeg", body=b""))
        pg.route("**/api/windows/*/frame*", lambda r: r.fulfill(status=200, content_type="image/gif", body=bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")))
        pg.route("**/api/windows/*/click", lambda r: r.fulfill(json={"ok": True}))
        pg.route("**/api/windows/*/keys", lambda r: (sent.append(r.request.post_data_json), r.fulfill(json={"ok": True}))[1])
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
        pg.goto(hub + "/mirror?id=5")
        pg.wait_for_selector("#pic")
        pg.check("#ctl")
        pg.tap("#pic")                                                                              # a tap on the picture: the click is sent and the typing box has the focus
        pg.wait_for_function("document.activeElement && document.activeElement.id === 'kb'")
        pg.keyboard.type("hi")
        pg.keyboard.press("Backspace")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        b.close()
    assert sent == [{"text": "h"}, {"text": "i"}, {"key": "Backspace"}, {"key": "Enter"}], sent


def test_a_paragraph_stays_readable_in_the_box_and_arrives_whole_with_its_line_breaks(hub, monkeypatch):
    sent = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True).new_page()
        pg.route("**/api/windows/*/stream*", lambda r: r.fulfill(status=200, content_type="image/jpeg", body=b""))
        pg.route("**/api/windows/*/frame*", lambda r: r.fulfill(status=200, content_type="image/gif", body=bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")))
        pg.route("**/api/windows/*/keys", lambda r: (sent.append(r.request.post_data_json), r.fulfill(json={"ok": True}))[1])
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
        pg.goto(hub + "/mirror?id=5")
        pg.wait_for_selector("#pic")
        pg.check("#ctl")
        pg.focus("#kb")
        pg.keyboard.type("ab")
        pg.keyboard.press("Shift+Enter")
        pg.keyboard.type("cd")
        long = "x" * 700
        pg.evaluate("t=>{const k=document.getElementById('kb');k.value+=t;k.dispatchEvent(new Event('input'))}", long)            # a pasted paragraph
        pg.wait_for_timeout(300)
        shown = pg.evaluate("document.getElementById('kb').value")
        b.close()
    assert "".join(s.get("text", "") for s in sent) == "ab\ncd" + long and all(len(s.get("text", "")) <= 300 for s in sent)
    assert shown == "ab\ncd" + long                                                              # nothing was cleared or cut: it can be read back


def test_a_line_break_in_typed_text_is_shift_enter_and_a_long_text_is_sent_in_pieces(monkeypatch):
    calls = []
    monkeypatch.setattr(WM, "WIN", True)
    monkeypatch.setattr(WM, "_send", lambda seq: calls.append(list(seq)))
    import ctypes
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"user32": type("U", (), {"IsWindow": staticmethod(lambda h: 1), "IsIconic": staticmethod(lambda h: 0), "SetForegroundWindow": staticmethod(lambda h: 1)})}), raising=False)
    assert WM.type_into(7, "a\nb")
    flat = [x for c in calls for x in c]
    assert (0x10, 0, 0) in flat and (0x0D, 0, 0) in flat and (0, ord("a"), 4) in flat and (0, ord("b"), 4) in flat
    calls.clear()
    assert WM.type_into(7, "y" * 2000) and len(calls) > 1 and sum(len(c) for c in calls) == 4000


def _open_panel_sized(hub, viewport, mobile, win_w, win_h):
    import urllib.request
    for p in json.load(urllib.request.urlopen(hub + "/api/windows/panels", timeout=10))["panels"]:            # panels left by earlier tests are not part of this one
        urllib.request.urlopen(urllib.request.Request(hub + "/api/windows/panels?url=" + urllib.parse.quote(p["url"], safe=""), method="DELETE", headers={"Origin": hub}), timeout=10)
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport=viewport, has_touch=mobile, is_mobile=mobile)
        pg = ctx.new_page()
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 77, "title": "Sized", "exe": "x.exe", "w": win_w, "h": win_h, "minimised": False}]}))
        pg.route("**/mirror?id=77*", lambda r: r.fulfill(content_type="text/html", body="<body style='background:#111'>x</body>"))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Sized', url: '/mirror?id=77'}})")
        pg.wait_for_selector(".hk[data-id^='extra:win-sized'] iframe", timeout=10000)
        pg.wait_for_timeout(1500)
        res = pg.evaluate("""()=>{const sel=".hk[data-id^='extra:win-sized']",p=document.querySelector(sel);const r=p.getBoundingClientRect();
          const o=[...document.querySelectorAll('.hk')].filter(n=>n!==p&&!n.hidden&&getComputedStyle(n).display!=='none'&&getComputedStyle(n).visibility!=='hidden'&&getComputedStyle(n).opacity!=='0').map(n=>{const q=n.getBoundingClientRect();return {id:n.dataset.id,left:q.left,right:q.right,top:q.top,bottom:q.bottom,width:q.width,height:q.height};})
            .filter(q=>q.width>0&&q.height>0&&q.left<r.right-2&&q.right>r.left+2&&q.top<r.bottom-2&&q.bottom>r.top+2).map(q=>q.id);
          return {w:r.width,h:r.height,overlaps:o.length,who:o,vw:innerWidth,vh:innerHeight,k:p.offsetWidth?r.width/p.offsetWidth:1,ow:p.offsetWidth,oh:p.offsetHeight}}""")
        b.close()
    return res


def test_a_computer_panel_is_about_the_shape_of_the_window_it_shows_not_a_fixed_large_box(hub):
    small = _open_panel_sized(hub, {"width": 1300, "height": 900}, False, 520, 420)
    wide = _open_panel_sized(hub, {"width": 1300, "height": 900}, False, 1920, 1000)
    assert 380 <= small["ow"] <= 560 and small["oh"] <= small["ow"] / (520 / 420) + 160           # a small window: a small panel
    assert wide["ow"] >= 650 and wide["oh"] <= wide["ow"] / (1920 / 1000) + 160                    # a wide one: wide, and not taller than its picture needs
    assert small["oh"] < wide["ow"]


def test_a_phone_panel_fits_the_screen_and_leaves_nothing_of_the_board_under_it(hub):
    r = _open_panel_sized(hub, {"width": 390, "height": 760}, True, 1900, 1000)
    assert r["w"] <= r["vw"] and r["h"] <= r["vh"] and r["overlaps"] == 0, r


def test_the_board_header_and_button_bar_start_below_an_iphone_notch():
    css = (Path(__file__).resolve().parent.parent / "hub" / "static" / "hub-blocks.css").read_text(encoding="utf-8")
    assert "body>header{top:max(8px,env(safe-area-inset-top))!important}" in css
    assert "@media(min-width:1101px){.hb .hb-bar{top:max(8px,env(safe-area-inset-top))}}" in css
