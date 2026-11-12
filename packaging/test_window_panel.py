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
        pg.wait_for_selector(".hk[data-id^='extra:win-sized'] .hk-fr", timeout=10000)
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


GIF = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6.1 Mobile/15E148 Safari/604.1"


def test_a_phone_gets_small_single_pictures_one_at_a_time_and_each_old_picture_is_released(hub):
    """The first phone session pulled 340 KB pictures 1800 px wide, five a second, and Safari ran out of memory ('A problem repeatedly occurred'). A phone has a budget."""
    seen, revoked = [], []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True, user_agent=IPHONE)
        ctx.add_init_script("window.__rev=0;const r=URL.revokeObjectURL.bind(URL);URL.revokeObjectURL=u=>{window.__rev++;return r(u)}")
        pg = ctx.new_page()
        pg.route("**/api/windows/*/stream*", lambda r: (seen.append(r.request.url), r.fulfill(status=200, content_type="image/jpeg", body=b""))[1])
        pg.route("**/api/windows/*/frame*", lambda r: (seen.append(r.request.url), r.fulfill(status=200, content_type="image/gif", body=GIF))[1])
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
        pg.goto(hub + "/mirror?id=5")
        pg.wait_for_timeout(3500)
        revoked = pg.evaluate("window.__rev")
        b.close()
    frames = [u for u in seen if "/frame" in u]
    assert frames and not [u for u in seen if "/stream" in u]                                       # single pictures, never the endless stream
    import re
    assert all(int(re.search(r"w=(\d+)", u).group(1)) <= 1400 and int(re.search(r"q=(\d+)", u).group(1)) <= 75 for u in frames)
    assert len(frames) <= 12 and revoked >= len(frames) - 2                                         # about two a second, and each earlier picture released


def test_smiths_still_and_talk_button_picture_are_the_full_portrait_of_the_landing_vector(hub):
    import base64
    import urllib.request
    still = (Path(__file__).resolve().parent.parent / "hub" / "static" / "agent-art" / "smith-still.png").read_bytes()
    assert urllib.request.urlopen(hub + "/smith-icon.png", timeout=10).read() == still               # the Talk button
    page = urllib.request.urlopen(hub + "/offline.html", timeout=10).read().decode("utf-8", "replace")
    assert base64.b64encode(still).decode() in page                                                  # the picture the landing page swaps in at ENTER


def test_the_hub_itself_holds_a_phone_to_its_picture_budget_whatever_the_page_asks(fake, monkeypatch):
    seen = []
    monkeypatch.setattr(WM, "capture", lambda hwnd, max_w=1000, quality=80: (seen.append((max_w, quality)), (b"\xff\xd8x", "image/jpeg"))[1])
    async def go():
        app = web.Application()
        app.add_routes(WM.routes)
        async with TestClient(TestServer(app)) as c:
            await c.get("/api/windows/12/frame?w=1800&q=95", headers={"User-Agent": IPHONE})
            await c.get("/api/windows/12/frame?w=1800&q=95", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"})
    asyncio.run(go())
    assert seen == [(1400, 75), (1800, 95)]



ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"


def _board_with_mirror(pw, hub, ua, frames):
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True, user_agent=ua)
    pg = ctx.new_page()
    pg.route("**/api/windows/*/frame*", lambda r: (frames.append(r.request.url), r.fulfill(status=200, content_type="image/gif", body=GIF))[1])
    pg.route("**/api/windows/*/stream*", lambda r: (frames.append(r.request.url), r.fulfill(status=200, content_type="image/jpeg", body=b""))[1])
    pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
    pg.goto(hub + "/?enter=1")
    pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
    pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=5'}})")
    pg.wait_for_selector(".hk[data-id^='extra:win-claude'] iframe", timeout=10000)
    return b, pg


def test_every_touch_device_stops_the_live_window_while_the_board_moves_and_it_carries_on_after(hub):
    """Not only an iPhone: an Android phone's browser gets the same pause. The mirror asks for no picture while the board is being moved."""
    frames = []
    with sync_playwright() as pw:
        b, pg = _board_with_mirror(pw, hub, ANDROID, frames)
        pg.wait_for_function("(()=>{const f=document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\");try{return !!f.contentWindow.setMirrorMoving&&f.contentWindow.pic&&true}catch(e){return false}})()", timeout=15000)
        pg.wait_for_timeout(1500)
        asked_before = len(frames)
        assert asked_before > 0                                                                  # it was running
        state = "document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\").contentWindow.eval('moving')"
        pg.evaluate("document.querySelector('.hb').dispatchEvent(new WheelEvent('wheel',{deltaY:30,bubbles:true,cancelable:true}))")
        assert pg.evaluate(state) is True
        pg.wait_for_timeout(250)
        paused_at = len(frames)
        pg.evaluate("document.querySelector('.hb').dispatchEvent(new WheelEvent('wheel',{deltaY:30,bubbles:true,cancelable:true}))")    # keeps moving
        pg.wait_for_timeout(250)
        assert len(frames) == paused_at                                                           # nothing asked for while it moves
        pg.wait_for_function("document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\").contentWindow.eval('moving')===false", timeout=4000)
        pg.wait_for_timeout(1500)
        assert len(frames) > paused_at                                                            # and it carries on
        b.close()


def test_the_fit_button_sizes_a_window_to_the_shape_of_its_picture_and_any_other_page_to_its_content(hub):
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (800, 200), (20, 90, 60)).save(buf, "JPEG"); wide = buf.getvalue()           # a very wide window
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1300, "height": 900}, has_touch=True, is_mobile=True, user_agent=ANDROID).new_page()          # single pictures, as on a tablet
        pg.route("**/api/windows/*/stream*", lambda r: r.fulfill(status=200, content_type="image/jpeg", body=b""))
        pg.route("**/api/windows/*/frame*", lambda r: r.fulfill(status=200, content_type="image/jpeg", body=wide, headers={"ETag": '"x"'}))
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Wide", "exe": "w.exe", "w": 800, "h": 800, "minimised": False}]}))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Wide', url: '/mirror?id=5'}})")
        pg.wait_for_selector(".hk[data-id^='extra:win-wide'] iframe", timeout=10000)
        pg.wait_for_function("(()=>{const i=document.querySelector(\".hk[data-id^='extra:win-wide'] iframe\").contentDocument.getElementById('pic');return i&&i.naturalWidth>1})()", timeout=15000)
        sel = ".hk[data-id^='extra:win-wide']"
        before = pg.evaluate(f"(()=>{{const p=document.querySelector(\"{sel}\");return [p.offsetWidth,p.offsetHeight]}})()")     # sized for a square window
        pg.locator(sel + " [data-a=fit]").dispatch_event("click")
        pg.wait_for_timeout(600)
        after = pg.evaluate(f"(()=>{{const p=document.querySelector(\"{sel}\");return [p.offsetWidth,p.offsetHeight]}})()")
        b.close()
    assert after[1] < before[1] and abs((after[1] - 150) - after[0] / 4) < 40, (before, after)                  # 4 : 1 picture, plus the room above it


def test_the_auto_llm_card_with_its_reinforcement_learning_tab_fills_the_board_under_the_top_buttons(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1400, "height": 900}).new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        assert pg.evaluate("window.__hubBoard.open('/yard')") is True
        pg.wait_for_timeout(1200)
        got = pg.evaluate("""()=>{const st=window.__hubBoard.active.stage();const r=document.querySelector(".hk[data-id='card:oc']").getBoundingClientRect();
          return {stage:[st.left,st.top,st.right,st.bottom],box:[r.left,r.top,r.right,r.bottom],vw:innerWidth,vh:innerHeight}}""")
        b.close()
    sl, stp, sr, sb = got["stage"]
    l, t, r, bt = got["box"]
    assert l >= sl - 14 and t >= stp - 14 and r <= sr + 14 and bt <= sb + 14, got                           # inside the boundaries of the buttons around it
    assert (r - l) > 0.6 * (sr - sl) and (bt - t) > 0.6 * (sb - stp), got                                    # and large: it is read, not glanced at


def test_the_r_button_panel_takes_the_board_on_a_desktop_screen_and_stays_clear_of_the_buttons(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1700, "height": 950}).new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        got = pg.evaluate("""()=>{const q=document.querySelector('.hb-learning');q.hidden=false;const k=[...document.querySelectorAll('.hb-bar>*')].filter(e=>e.offsetParent).map(e=>e.getBoundingClientRect()),
          corner={right:Math.max(...k.map(e=>e.right)),bottom:Math.max(...k.map(e=>e.bottom))};q.click();return corner}""")
        pg.wait_for_selector(".hb-glass-panel", timeout=8000)
        pg.wait_for_timeout(700)
        got.update(pg.evaluate("""()=>{const p=document.querySelector('.hb-glass-panel').getBoundingClientRect();return {p:[p.left,p.top,p.right,p.bottom],vw:innerWidth,vh:innerHeight}}"""))
        b.close()
    l, t, r, bt = got["p"]
    assert l >= got["right"] + 12 - 3 and abs(t - (got["bottom"] + 12)) <= 10, got                       # its top-left corner is the bottom-right corner of the Talk / PC control / R buttons (further right only to leave the same space as on the right)
    assert abs(l - (got["vw"] - r)) <= 3, got                                                              # the same space on the right: it sits in the middle, not to one side
    assert (r - l) > 0.7 * got["vw"] and (bt - t) > 0.7 * got["vh"] - got["bottom"], got                  # and large: it is read


def test_opening_a_small_block_does_not_blow_it_up_to_more_than_a_readable_size(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 2000, "height": 1100}).new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Notes', url: '/mirror?id=3'}})")
        pg.wait_for_selector(".hk[data-id^='extra:win-notes'] iframe", timeout=10000)
        pg.wait_for_timeout(1500)
        k = pg.evaluate("window.__hubBoard.active.state().V.k")
        b.close()
    assert k <= 1.36, k                                                                                   # it used to be framed up to 2.4 times its size on a big screen


def test_the_dashboard_on_a_phone_starts_with_the_side_buttons_hidden_the_map_gone_and_a_readable_zoom(hub):
    with sync_playwright() as pw:
        d = pw.devices["iPhone 13"]
        b = pw.webkit.launch()
        pg = b.new_context(**d, service_workers="block").new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=30000)
        pg.wait_for_timeout(2000)
        got = pg.evaluate("""()=>({rail:getComputedStyle(document.querySelector('.hb-right-panel')).display!=='none'&&!document.querySelector('.hb-right-panel').hidden,
          map:(()=>{const m=document.querySelector('.hb-map');return !!m&&getComputedStyle(m).display!=='none'})(),k:window.__hubBoard.active.state().V.k})""")
        b.close()
    assert got["rail"] is False and got["map"] is False and got["k"] >= 0.6, got


def test_a_live_window_is_hidden_and_its_picture_let_go_while_the_board_moves_on_a_phone(hub):
    GIFB = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True, user_agent=ANDROID)
        pg = ctx.new_page()
        pg.route("**/api/windows/*/frame*", lambda r: r.fulfill(status=200, content_type="image/gif", body=GIFB))
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=5'}})")
        pg.wait_for_selector(".hk[data-id^='extra:win-claude'] iframe", timeout=10000)
        pg.wait_for_function("(()=>{const i=document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\").contentDocument.getElementById('pic');return !!i&&i.naturalWidth>0})()", timeout=15000)
        pg.wait_for_timeout(1500)                                                                         # the board has stopped moving
        pg.evaluate("document.querySelector('.hb').dispatchEvent(new WheelEvent('wheel',{deltaY:30,bubbles:true,cancelable:true}))")
        moving = pg.evaluate("""()=>{const f=document.querySelector(".hk[data-id^='extra:win-claude'] iframe");return {vis:getComputedStyle(f).visibility,src:f.contentDocument.getElementById('pic').getAttribute('src')}}""")
        pg.wait_for_function("getComputedStyle(document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\")).visibility==='visible'", timeout=4000)
        b.close()
    assert moving["vis"] == "hidden" and not moving["src"], moving                                         # not drawn, and no decoded picture held, while it moves


def test_no_two_buttons_lie_over_each_other_on_a_phone_dashboard_and_the_landing_goes_straight_to_it(hub):
    import time
    with sync_playwright() as pw:
        d = pw.devices["iPhone 13"]
        b = pw.webkit.launch()
        pg = b.new_context(**d, service_workers="block").new_page()
        pg.goto(hub + "/offline.html")
        pg.wait_for_selector("#wake-btn[data-s='enter']", timeout=30000)
        pg.wait_for_timeout(1500)
        t0 = time.time()
        pg.click("#wake-btn")
        pg.wait_for_url("**/?enter=1", timeout=8000)
        took = time.time() - t0
        assert pg.evaluate("document.querySelectorAll('iframe[data-dl-destination]').length") == 0 and took < 3          # no hidden second dashboard, no cube show: a fade and the dashboard
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=30000)
        pg.wait_for_timeout(2000)
        boxes = pg.evaluate("""()=>[...document.querySelectorAll('.hb-bar>*, .hb-tray>*, .hb-batch-controls, .hb-log-toggle, body>header button, .hb-right-panel>*')].filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>10&&r.height>10&&s.visibility!=='hidden'&&s.display!=='none'}).map(e=>{const r=e.getBoundingClientRect();return [(e.className||e.tagName).toString().slice(0,30),r.left,r.top,r.right,r.bottom]})""")
        b.close()
    clashes = []
    for i, a in enumerate(boxes):
        for c in boxes[i + 1:]:
            ox, oy = min(a[3], c[3]) - max(a[1], c[1]), min(a[4], c[4]) - max(a[2], c[2])
            if ox > 4 and oy > 4 and not (a[0].startswith("hb-batch") and c[0].startswith("hb-btn")) and not (c[0].startswith("hb-batch") and a[0].startswith("hb-btn")):
                clashes.append((a[0], c[0], round(ox), round(oy)))
    assert clashes == [], clashes


def test_the_phone_dashboard_runs_no_endless_animation_and_no_live_orb_while_nothing_is_happening(hub):
    """The dashboard held every frame at about 100 ms on a phone (25 ms with the animations off): the Smith button's two rings pulsed for as long as the page was open, and the header orb ran three
    live canvases, one of them WebGL, for a 30 px button. They run only while he listens."""
    with sync_playwright() as pw:
        b = pw.webkit.launch()
        pg = b.new_context(**pw.devices["iPhone 13"], service_workers="block").new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=30000)
        pg.wait_for_timeout(2500)
        got = pg.evaluate("""()=>({endless:document.getAnimations().filter(a=>a.effect&&a.effect.getComputedTiming().iterations===Infinity).map(a=>a.animationName||a.constructor.name),
          orb:document.querySelectorAll('#orb-host canvas').length,phone:document.documentElement.classList.contains('hub-phone')})""")
        b.close()
    assert got["phone"] and got["endless"] == [] and got["orb"] == 0, got


@pytest.mark.parametrize("name", ["iPhone 13", "iPhone 13 landscape"])
def test_a_phone_has_a_one_row_header_and_a_show_hide_button_for_the_view_buttons_either_way_up(hub, name):
    with sync_playwright() as pw:
        b = pw.webkit.launch()
        pg = b.new_context(**pw.devices[name], service_workers="block").new_page()
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=30000)
        pg.wait_for_timeout(1500)
        read = """()=>{const r=e=>{const b=e.getBoundingClientRect();return {w:b.width,h:b.height,x:b.x,y:b.y}},
          rail=document.querySelector('.hb-right-panel'),show=document.querySelector('.hb-panel-show'),hide=document.querySelector('.hb-panel-hide');
          return {header:r(document.querySelector('body>header')),railShown:!rail.hidden&&getComputedStyle(rail).display!=='none',show:getComputedStyle(show).display!=='none'&&!show.hidden?r(show):null,
          hide:getComputedStyle(hide).display!=='none'&&!hide.hidden?r(hide):null,vw:innerWidth}}"""
        first = pg.evaluate(read)
        pg.click(".hb-panel-show")
        pg.wait_for_timeout(500)
        second = pg.evaluate(read)
        pg.click(".hb-panel-hide")
        pg.wait_for_timeout(500)
        third = pg.evaluate(read)
        b.close()
    assert first["header"]["h"] <= 56, first                                                       # one row, not a block of three
    assert first["railShown"] is False and first["show"] and first["show"]["w"] >= 44 and first["show"]["h"] >= 30, first       # the view buttons start hidden, and there is a button to show them
    assert second["railShown"] is True and second["hide"] and second["show"] is None, second          # SHOW shows them and becomes HIDE
    assert third["railShown"] is False and third["show"], third                                         # and HIDE puts them away again


def test_an_iphone_picture_is_asked_for_at_the_size_it_is_shown_so_a_zoomed_window_stays_sharp(hub):
    """A flat 864 px picture was soft at a 100 % or 150 % zoom on a 3x screen. The width follows the picture's width on screen times the pixel ratio, in steps, never over the phone's budget."""
    import io
    import re
    from PIL import Image
    wide = io.BytesIO()
    Image.new("RGB", (190, 100), "#123").save(wide, "GIF")                                  # a window that is wider than tall, like the real one
    frames = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 390, "height": 760}, device_scale_factor=3, has_touch=True, is_mobile=True, user_agent=IPHONE)
        pg = ctx.new_page()
        pg.route("**/api/windows/*/frame*", lambda r: (frames.append(r.request.url), r.fulfill(status=200, content_type="image/gif", body=wide.getvalue()))[1])
        pg.route("**/api/windows", lambda r: r.fulfill(json={"supported": True, "windows": [{"id": 5, "title": "Claude", "exe": "claude.exe", "w": 1900, "h": 1000, "minimised": False}]}))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active", timeout=20000)
        pg.evaluate("window.__hubBoard.applyUi({window: {title: 'Claude', url: '/mirror?id=5'}})")
        pg.wait_for_selector(".hk[data-id^='extra:win-claude'] iframe", timeout=10000)
        frame = "document.querySelector(\".hk[data-id^='extra:win-claude'] iframe\").contentWindow"
        pg.wait_for_function("(()=>{try{const w=" + frame + ";return !!w.setMirrorBoardZoom&&w.pic.naturalWidth>0}catch(e){return false}})()", timeout=15000)
        pg.wait_for_timeout(800)
        small = [int(re.search(r"w=(\d+)", u).group(1)) for u in frames][-1]
        pg.evaluate("(()=>{const w=" + frame + ";w.pic.classList.add('board-zoom');w.pic.style.setProperty('--mirror-board-width','900px');w.eval('start(true)')})()")       # the picture shown 900 px wide (zoomed in)
        pg.wait_for_timeout(2500)
        big = [int(re.search(r"w=(\d+)", u).group(1)) for u in frames][-1]
        b.close()
    assert 864 <= small < big <= 1400, (small, big)                                                  # a zoomed picture is asked for with more pixels, within the budget
