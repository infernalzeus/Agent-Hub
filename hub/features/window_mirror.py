"""A window of this PC as a panel on the dashboard, and a Claude Code session as a panel.

Windows (Claude Desktop, Edge, anything with a window): the Hub lists the windows that are open, takes a picture of one a few times a second and shows it in a panel. That is a live
picture, not the program itself: a native window cannot be embedded the way a web app the Hub fronts can. It is view-only until you switch CLICKS on in the panel; then a click in the
picture is a real click in that window, on this PC.

A panel opened on one device opens on the others too (the Hub keeps the list of open panels), and the picture can be watched from the phone. Whoever can open the Hub can see and use it, the same as PC control.

Sessions: the panel shows the recent turns of a Claude Code or Codex session and what it is waiting for, read from the session's own log, read-only.

No third-party package is needed: the picture is taken with the Windows API through ctypes. Pillow, when it is there, makes it a JPEG; without it the picture is a BMP, which every browser shows.
"""
from __future__ import annotations

import asyncio
import ctypes
import hashlib
import io
import json
import re
import struct
import sys
import time
from pathlib import Path

from aiohttp import web

routes = web.RouteTableDef()
WIN = sys.platform == "win32"
_SKIP_TITLES = {"Program Manager", "Settings", "Windows Input Experience", "Microsoft Text Input Application", "NVIDIA GeForce Overlay"}


def _local(request: web.Request) -> None:
    """Kept as the one place to tighten if the Hub ever gets per-device sign-in: today a panel is for every device that can open the Hub."""
    return None


# ---- the Windows API ----------------------------------------------------------------------------------------------------------------
def list_windows() -> "list[dict]":
    """The windows a person would call open: visible, titled, not a tool window, not hidden by the system, not tiny. Newest focus first is the order Windows gives them."""
    if not WIN:
        return []
    from ctypes import wintypes as wt
    user32, dwm, kernel32 = ctypes.windll.user32, ctypes.windll.dwmapi, ctypes.windll.kernel32
    out: "list[dict]" = []
    me = kernel32.GetCurrentProcessId()

    def exe_of(hwnd) -> str:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me:
            return ""
        h = kernel32.OpenProcessW(0x1000, False, pid.value) if hasattr(kernel32, "OpenProcessW") else kernel32.OpenProcess(0x1000, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            n = wt.DWORD(520)
            return Path(buf.value).name if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
        finally:
            kernel32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):                      # not visible, or owned by another window (a dialog)
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x80:                                              # a tool window
            return True
        cloaked = ctypes.c_int(0)
        if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4) == 0 and cloaked.value:  # hidden by the shell (a suspended store app)
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if not title or title in _SKIP_TITLES or w < 120 or h < 80:
            return True
        exe = exe_of(hwnd)
        if not exe:                                                                              # this Hub's own window, or one that cannot be read
            return True
        out.append({"id": int(hwnd), "title": title[:120], "exe": exe, "w": w, "h": h, "minimised": bool(user32.IsIconic(hwnd))})
        return True
    user32.EnumWindows(each, 0)
    return out


def find_window(query: str) -> "dict | None":
    """The open window that best matches what was said ("claude desktop", "edge", "notepad"): every word in its title or its program's name; a program name beats a title."""
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").casefold()) if w not in ("the", "a", "an", "my", "window", "app", "application", "desktop")] or \
            re.findall(r"[a-z0-9]+", (query or "").casefold())
    if not words:
        return None
    best, score = None, 0
    for w in list_windows():
        hay = (w["title"] + " " + w["exe"]).casefold()
        exe = w["exe"].casefold().replace(".exe", "")
        s = sum(1 for x in words if x in hay)
        if s == len(words):
            s += 2 * sum(1 for x in words if x in exe)
            if s > score:
                best, score = w, s
    return best


def window_rect(hwnd: int) -> "tuple[int, int, int, int] | None":
    """(x, y, width, height) of a window on the screen, or None."""
    if not WIN:
        return None
    from ctypes import wintypes as wt
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def capture(hwnd: int, max_w: int = 1000, quality: int = 80) -> "tuple[bytes, str] | None":
    """A picture of one window: (bytes, content type), or None when it is gone or minimised. Asks the window to draw itself (PrintWindow, full content), so another window in front of it
    does not matter; the picture is scaled down inside GDI before it is read."""
    if not WIN:
        return None
    from ctypes import wintypes as wt
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 20 or h < 20:
        return None
    try:
        import PIL  # noqa: F401
        grab = min(1.0, max_w * 1.5 / w)                                                   # a half again too big in GDI, then the exact size with a better filter
    except ImportError:
        grab = min(1.0, max_w / w)
    scale = grab
    tw, th = max(1, int(w * scale)), max(1, int(h * scale))
    screen = user32.GetDC(0)
    src, dst = gdi32.CreateCompatibleDC(screen), gdi32.CreateCompatibleDC(screen)
    bmp_src, bmp_dst = gdi32.CreateCompatibleBitmap(screen, w, h), gdi32.CreateCompatibleBitmap(screen, tw, th)
    old_src, old_dst = gdi32.SelectObject(src, bmp_src), gdi32.SelectObject(dst, bmp_dst)
    try:
        if not user32.PrintWindow(hwnd, src, 2):
            return None
        gdi32.SetStretchBltMode(dst, 4)                                                          # HALFTONE: a readable shrink
        gdi32.StretchBlt(dst, 0, 0, tw, th, src, 0, 0, w, h, 0x00CC0020)
        header = struct.pack("<IiiHHIIiiII", 40, tw, -th, 1, 32, 0, tw * th * 4, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(tw * th * 4)
        gdi32.GetDIBits(dst, bmp_dst, 0, th, buf, header, 0)
        raw = bytes(buf)
    finally:
        gdi32.SelectObject(src, old_src)
        gdi32.SelectObject(dst, old_dst)
        gdi32.DeleteObject(bmp_src)
        gdi32.DeleteObject(bmp_dst)
        gdi32.DeleteDC(src)
        gdi32.DeleteDC(dst)
        user32.ReleaseDC(0, screen)
    if not any(raw[:4096]) and not any(raw[-4096:]):                                             # a window that drew nothing
        return None
    try:
        from PIL import Image
        img = Image.frombuffer("RGBA", (tw, th), raw, "raw", "BGRA", 0, 1).convert("RGB")
        if tw > max_w:
            img = img.resize((max_w, max(1, round(th * max_w / tw))), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=max(30, min(97, int(quality))), subsampling=0 if quality >= 60 else 2, optimize=False)
        return out.getvalue(), "image/jpeg"
    except ImportError:
        file_header = b"BM" + struct.pack("<IHHI", 14 + 40 + len(raw), 0, 0, 14 + 40)
        return file_header + header + raw, "image/bmp"


def click(hwnd: int, fx: float, fy: float) -> bool:
    """A left click at a place in the window given as fractions of its width and height. Brings the window forward first."""
    if not WIN or not (0 <= fx <= 1 and 0 <= fy <= 1):
        return False
    from ctypes import wintypes as wt
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return False
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = int(r.left + fx * (r.right - r.left)), int(r.top + fy * (r.bottom - r.top))
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.06)
    user32.SetCursorPos(x, y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    return True


_KEYS = {"Enter": 0x0D, "Backspace": 0x08, "Tab": 0x09, "Escape": 0x1B, "ArrowLeft": 0x25, "ArrowUp": 0x26, "ArrowRight": 0x27, "ArrowDown": 0x28, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
         "PageUp": 0x21, "PageDown": 0x22}


def _send(inputs) -> None:
    from ctypes import wintypes as wt

    class KI(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    class MI(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    class U(ctypes.Union):
        _fields_ = [("ki", KI), ("mi", MI)]

    class IN(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", U)]
    arr = (IN * len(inputs))()
    for i, (vk, scan, flags) in enumerate(inputs):
        arr[i].type = 1
        arr[i].u.ki = KI(vk, scan, flags, 0, None)
    ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(IN))


def type_into(hwnd: int, text: str = "", key: str = "", ctrl: bool = False) -> bool:
    """Type text (as Unicode characters) or press one special key in a window, after bringing it forward. Used only from a panel with CLICKS switched on."""
    if not WIN or not ctypes.windll.user32.IsWindow(hwnd) or ctypes.windll.user32.IsIconic(hwnd):
        return False
    if not text and key not in _KEYS and not (ctrl and len(key) == 1):
        return False
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.04)
    seq = []
    if ctrl and len(key) == 1:                                                                  # Ctrl+C, Ctrl+V ...
        vk = ord(key.upper())
        seq += [(0x11, 0, 0), (vk, 0, 0), (vk, 0, 2), (0x11, 0, 2)]
    elif key in _KEYS:
        seq += [(_KEYS[key], 0, 0), (_KEYS[key], 0, 2)]
    for ch in text[:8000]:
        if ch == "\n":                                                                          # a line break inside a paragraph is Shift+Enter, so the chat box adds a line instead of sending
            seq += [(0x10, 0, 0), (0x0D, 0, 0), (0x0D, 0, 2), (0x10, 0, 2)]
        elif ch != "\r":
            seq += [(0, ord(ch), 4), (0, ord(ch), 4 | 2)]                                       # KEYEVENTF_UNICODE down, up
    for k in range(0, len(seq), 240):                                                            # in pieces: one big SendInput can drop keys, and a long text must arrive whole
        _send(seq[k:k + 240])
        if len(seq) > 240:
            time.sleep(0.02)
    return True


def wheel(hwnd: int, fx: float, fy: float, delta: int) -> bool:
    """Scroll the wheel over a place in the window (fractions of its size); positive delta scrolls up."""
    if not WIN or not (0 <= fx <= 1 and 0 <= fy <= 1):
        return False
    from ctypes import wintypes as wt
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return False
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(int(r.left + fx * (r.right - r.left)), int(r.top + fy * (r.bottom - r.top)))
    user32.mouse_event(0x0800, 0, 0, max(-1200, min(1200, int(delta))) & 0xFFFFFFFF, 0)
    return True


def foreground() -> int:
    """The window in front right now (0 when there is none, or not on Windows)."""
    return int(ctypes.windll.user32.GetForegroundWindow() or 0) if WIN else 0


def desktop_locked() -> bool:
    """True when the screen is locked or showing a secure screen: the desktop a program is allowed to read is then not the one a person sees, and every window reads as empty."""
    if not WIN:
        return False
    user32 = ctypes.windll.user32
    h = user32.OpenInputDesktop(0, False, 0x0100)                         # DESKTOP_SWITCHDESKTOP: refused while the secure desktop is up
    if not h:
        return True
    user32.CloseDesktop(h)
    return False


def focus(hwnd: int) -> bool:
    """Bring a window to the front and say whether it is there. Windows refuses a background program's request to take the front (the foreground lock): a synthetic Alt press and release,
    which is how any automation lifts that, is tried when the plain request did not work."""
    if not WIN:
        return False
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    if user32.GetForegroundWindow() == hwnd:
        return True
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    return user32.GetForegroundWindow() == hwnd


# ---- the routes ------------------------------------------------------------------------------------------------------------------------
@routes.get("/api/windows")
async def api_windows(request: web.Request) -> web.Response:
    _local(request)
    return web.json_response({"supported": WIN, "windows": await asyncio.to_thread(list_windows)})


@routes.get("/api/windows/find")
async def api_find(request: web.Request) -> web.Response:
    _local(request)
    w = await asyncio.to_thread(find_window, request.query.get("q", ""))
    return web.json_response({"window": w})


def _budget(request: web.Request, w: int, q: int, fps: int = 5) -> "tuple[int, int, int]":
    """A phone has a small memory budget for pictures (the first phone session pulled 340 KB pictures at 1800 px, five a second, and Safari gave up). Whatever page asks, a phone gets at most
    1400 px, quality 75 and 5 a second. This also covers a page the phone cached before the page learned its own budget."""
    if request.query.get("lite") == "1" or re.search(r"iPhone|iPad|iPod|Android", request.headers.get("User-Agent", "")):        # the page says so (touch is its main pointer, whatever the make), or the browser names itself
        return min(w, 1400), min(q, 75), min(fps, 5)
    return w, q, fps


@routes.get("/api/windows/{id}/frame")
async def api_frame(request: web.Request) -> web.Response:
    _local(request)
    w, q, _ = _budget(request, min(3000, max(300, int(request.query.get("w", "1000")))), int(request.query.get("q", "82")))
    got = await asyncio.to_thread(capture, int(request.match_info["id"]), w, q)
    if not got:
        raise web.HTTPNotFound(text="that window is gone, minimised, or drew nothing")
    headers = {"Cache-Control": "no-store"}
    if request.query.get("dedup") == "1":
        tag = '"' + hashlib.blake2s(got[0], digest_size=12).hexdigest() + '"'
        headers["ETag"] = tag
        if request.headers.get("If-None-Match") == tag:
            return web.Response(status=304, headers=headers)
    return web.Response(body=got[0], content_type=got[1], headers=headers)


@routes.get("/api/windows/{id}/stream")
async def api_stream(request: web.Request) -> web.StreamResponse:
    """A live picture of a window as one long response (multipart JPEG, which every browser plays in an <img>): ?fps=1..30 &w=pixels wide &q=JPEG quality. A frame that has not changed
    since the last one is not sent again, so a window that is only being typed in costs almost nothing at 1 or 2 a second. The rate is a ceiling: how fast the window can be drawn decides."""
    hwnd = int(request.match_info["id"])
    fps = max(1, min(30, int(request.query.get("fps", "5"))))
    w = min(3000, max(300, int(request.query.get("w", "1000"))))
    q = int(request.query.get("q", "82"))
    w, q, fps = _budget(request, w, q, fps)
    boundary = "hubframe"
    resp = web.StreamResponse(headers={"Content-Type": f"multipart/x-mixed-replace; boundary={boundary}", "Cache-Control": "no-store", "Connection": "close"})
    await resp.prepare(request)
    last, period, sent_at = None, 1.0 / fps, 0.0
    try:
        while True:
            t0 = time.time()
            got = await asyncio.to_thread(capture, hwnd, w, q)
            if got is None:
                if last is None:
                    break                                                                # never had a picture: the window is gone or minimised
            else:
                if got[0] != last or t0 - sent_at > 4:                                   # changed, or a keep-alive so the browser does not think it stalled
                    await resp.write(f"--{boundary}\r\nContent-Type: {got[1]}\r\nContent-Length: {len(got[0])}\r\n\r\n".encode() + got[0] + b"\r\n")
                    last, sent_at = got[0], t0
            await asyncio.sleep(max(0.0, period - (time.time() - t0)))
    except (ConnectionResetError, asyncio.CancelledError, RuntimeError):
        pass
    return resp


@routes.post("/api/windows/{id}/click")
async def api_click(request: web.Request) -> web.Response:
    _local(request)
    b = await request.json()
    ok = await asyncio.to_thread(click, int(request.match_info["id"]), float(b.get("x", -1)), float(b.get("y", -1)))
    if not ok:
        raise web.HTTPBadRequest(text="that click did not land on a window")
    return web.json_response({"ok": True})


@routes.post("/api/windows/{id}/keys")
async def api_keys(request: web.Request) -> web.Response:
    b = await request.json()
    ok = await asyncio.to_thread(type_into, int(request.match_info["id"]), str(b.get("text") or ""), str(b.get("key") or ""), bool(b.get("ctrl")))
    if not ok:
        raise web.HTTPBadRequest(text="nothing was typed")
    return web.json_response({"ok": True})


@routes.post("/api/windows/{id}/wheel")
async def api_wheel(request: web.Request) -> web.Response:
    b = await request.json()
    ok = await asyncio.to_thread(wheel, int(request.match_info["id"]), float(b.get("x", -1)), float(b.get("y", -1)), int(b.get("delta", 0)))
    return web.json_response({"ok": ok})


# The panels that are open, kept here so every device shows the same ones: open Claude on the PC and it is a panel on the phone too, close it anywhere and it goes everywhere.
PANELS: "dict[str, dict]" = {}


def add_panel(title: str, url: str) -> dict:
    p = {"key": url, "title": str(title)[:40], "url": url, "at": time.time()}
    PANELS[url] = p
    return p


@routes.get("/api/windows/panels")
async def api_panels(request: web.Request) -> web.Response:
    return web.json_response({"panels": list(PANELS.values())})


@routes.post("/api/windows/panels")
async def api_panel_add(request: web.Request) -> web.Response:
    b = await request.json()
    url = str(b.get("url") or "")
    if not re.fullmatch(r"/(?:mirror|session)\?id=[A-Za-z0-9]{1,20}", url):
        raise web.HTTPBadRequest(text="only a window or session panel can be opened this way")
    return web.json_response(add_panel(str(b.get("title") or "Window"), url))


@routes.delete("/api/windows/panels")
async def api_panel_close(request: web.Request) -> web.Response:
    PANELS.pop(request.query.get("url", ""), None)
    return web.json_response({"ok": True})


@routes.post("/api/windows/{id}/focus")
async def api_focus(request: web.Request) -> web.Response:
    _local(request)
    return web.json_response({"ok": await asyncio.to_thread(focus, int(request.match_info["id"]))})


# ---- a Claude Code or Codex session ---------------------------------------------------------------------------------------------------
def session_turns(sid: str, limit: int = 24) -> dict:
    """The recent turns of one session, read-only: who said it and what, trimmed. `sid` is the 12-character id the sessions list carries."""
    from . import agent_sessions as AS
    path = None
    for base, pat in ((AS.CLAUDE_DIR, "*/*.jsonl"), (AS.CODEX_DIR, "**/*.jsonl")):
        try:
            path = next((p for p in base.glob(pat) if p.stem[:12] == sid), None)
        except OSError:
            path = None
        if path:
            break
    if not path:
        return {"error": "that session is not there any more"}
    recs = AS._tail_records(path)
    turns = []
    for r in recs:
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        role = text = ""
        if r.get("type") == "user":
            role, text = "you", AS._text_of((r.get("message") or {}).get("content"))
        elif r.get("type") == "assistant":
            role, text = "agent", AS._text_of((r.get("message") or {}).get("content"))
        elif r.get("type") == "event_msg" and pl.get("type") == "user_message":
            role, text = "you", str(pl.get("message") or "")
        elif r.get("type") == "event_msg" and pl.get("type") == "agent_message":
            role, text = "agent", str(pl.get("message") or "")
        text = re.sub(r"<([A-Za-z_-]+)[^>]*>.*?</\1>", "", text or "", flags=re.S).strip()
        if role and text:
            turns.append({"who": role, "text": text[:1400]})
    row = next((x for x in AS.scan(time.time(), 30) if x["id"] == sid), {})
    return {"title": row.get("title") or path.stem[:12], "project": row.get("project", ""), "state": row.get("state", ""), "ask": row.get("ask", ""), "turns": turns[-limit:]}


@routes.get("/api/sessions/transcript")
async def api_transcript(request: web.Request) -> web.Response:
    _local(request)
    return web.json_response(await asyncio.to_thread(session_turns, request.query.get("id", "")[:12]))


_STYLE = """<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--accent:#00e676;--ink:#d9ffe9;--mute:rgba(0,230,118,.55)}*{box-sizing:border-box;font-family:Orbitron,monospace}
body{margin:0;background:transparent;color:var(--ink);font-size:12px;height:100vh;display:flex;flex-direction:column}
.bar{display:flex;gap:6px;align-items:center;padding:6px;border-bottom:1px solid rgba(0,230,118,.25);background:rgba(8,12,40,.55);flex-wrap:wrap}
select,button,label{background:rgba(6,10,36,.7);border:1px solid rgba(0,230,118,.35);border-radius:8px;color:var(--ink);padding:5px 8px;font-size:10px;letter-spacing:.5px}
#back{font:inherit;font-size:11px;letter-spacing:1px;color:var(--accent);border:1px solid var(--border,rgba(0,230,118,.35));border-radius:8px;padding:5px 9px;text-decoration:none}#back[hidden]{display:none}button{cursor:pointer}button:hover{border-color:var(--accent);box-shadow:0 0 8px rgba(0,230,118,.3)}.mute{color:var(--mute)}
.view{flex:1;min-height:0;overflow:auto;padding:6px}img{max-width:100%;display:block;border:1px solid rgba(0,230,118,.3);border-radius:8px}
.t{margin:6px 0;padding:7px 9px;border-radius:9px;border:1px solid rgba(0,230,118,.2);background:rgba(8,12,40,.6);white-space:pre-wrap;word-break:break-word;line-height:1.45}
.t.you{border-color:rgba(65,235,255,.45)}.t b{color:var(--accent);font-size:9px;letter-spacing:1px}
.grow{flex:1}.opts{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.opts label{display:flex;gap:4px;align-items:center;padding:3px 6px}.opts select{padding:3px 4px;font-size:9.5px}
.kb{display:flex;gap:4px;align-items:center;flex-wrap:wrap}#kbrow{flex:1 1 100%}#kbrow[hidden]{display:none}.kb textarea{flex:1 1 100%;background:rgba(6,10,36,.7);border:1px solid rgba(0,230,118,.35);border-radius:8px;color:var(--ink);padding:7px 9px;font:13px/1.45 Outfit,system-ui,sans-serif;min-height:64px;max-height:36vh;resize:vertical;white-space:pre-wrap;overflow-wrap:anywhere}
#vid{display:block;width:100%;max-height:100%;background:#000;object-fit:contain}#vid[hidden]{display:none}.mirror-inline #vid{margin-inline:auto;width:auto;max-width:100%;max-height:100%}#vidbtn.on{border-color:#00e676;color:#00e676}.note-row{display:flex;gap:10px;padding:3px 8px;font-size:9.5px;border-bottom:1px solid rgba(0,230,118,.12)}.view img{transition:none}
html:has(.mirror-inline){height:100%;background:#070d20}
body.mirror-inline{height:100%;overflow:hidden}
.mirror-settings{flex:0 0 auto;max-height:46%;overflow:auto;background:#0a1028}
.mirror-settings summary{padding:9px 10px;color:var(--accent);cursor:pointer;touch-action:manipulation}
.mirror-inline .note-row{flex:0 0 auto;overflow:hidden;white-space:nowrap}
.mirror-inline .view{padding:2px}
.mirror-inline .view img.fit{margin-inline:auto}
.mirror-inline .view img.fit{width:auto!important;height:auto;max-height:100%}
.mirror-inline .view:has(img.board-zoom.fit){position:relative;overflow:hidden}
.mirror-inline .view img.board-zoom.fit{position:absolute;left:calc(50% + var(--mirror-pan-x,0px));top:calc(50% + var(--mirror-pan-y,0px));transform:translate(-50%,-50%);width:var(--mirror-board-width)!important;max-width:none!important;max-height:none}
</style>"""

_MIRROR = _STYLE + """<title>Window</title><body>
<div class="bar">
 <select id="pick" aria-label="Window"></select><button id="focus" type="button">BRING FORWARD</button>
 <label><input type="checkbox" id="ctl"> CLICKS AND KEYS</label>
 <span class="kb" id="kbrow" hidden>
  <button type="button" data-key="Enter">ENTER</button><button type="button" data-key="Backspace">BACKSPACE</button><button type="button" data-key="Tab">TAB</button><button type="button" data-key="Escape">ESC</button>
  <button type="button" data-key="ArrowUp">UP</button><button type="button" data-key="ArrowDown">DOWN</button><button type="button" data-key="ArrowLeft">LEFT</button><button type="button" data-key="ArrowRight">RIGHT</button>
  <button type="button" id="kbclear">CLEAR</button>
  <textarea id="kb" rows="3" placeholder="Type or paste here: it goes to the window as you type. Enter sends Enter to the window; Shift+Enter is a new line." autocomplete="off" autocapitalize="sentences" spellcheck="true" aria-label="Type into the window"></textarea>
 </span>
 <span class="grow"></span>
 <span class="opts" role="group" aria-label="Stream quality">
  <label>RATE <select id="fps"><option value="1">1 / s</option><option value="2">2 / s</option><option value="5">5 / s</option><option value="10">10 / s</option><option value="15">15 / s</option><option value="30">30 / s</option></select></label>
  <label>DETAIL <select id="det"><option value="1">FIT</option><option value="1.5">SHARP</option><option value="2">VERY SHARP</option><option value="0">NATIVE</option></select></label>
  <label>QUALITY <select id="qual"><option value="65">NORMAL</option><option value="85">HIGH</option><option value="95">MAX</option></select></label>
  <label>ZOOM <select id="zoom"><option value="fit">FIT</option><option value="50">50 %</option><option value="75">75 %</option><option value="100">100 %</option><option value="150">150 %</option></select></label>
  <a id="back" href="/?enter=1" hidden>DASHBOARD</a><button id="vidbtn" type="button" hidden title="Watch this window as real video, up to 30 frames a second (no sound).">VIDEO</button><button id="close" type="button">CLOSE PANEL</button>
 </span>
</div>
<div class="note-row"><span class="mute" id="note">A live picture of the window, no sound.</span><span class="mute" id="stat"></span></div>
<div class="view" id="stage" tabindex="0"><img id="pic" alt="" draggable="false"><video id="vid" muted playsinline autoplay hidden></video></div>
<script>
const $=id=>document.getElementById(id),q=new URLSearchParams(location.search);let cur=q.get('id')||'',alive=true,sel=null;
const SKEY='hubMirror:'+(q.get('id')||'x'),defaults={fps:'5',det:'1.5',qual:'85',zoom:'fit'};
// A phone has a small memory budget for pictures. The log of the first phone session showed 340 KB pictures, 1800 px wide, five a second: Safari ran out of memory and the page died
// ('A problem repeatedly occurred'). So a phone gets a budget: at most 1400 px wide, quality 75, 5 pictures a second, one picture at a time, and the old one is released before the next shows.
const PHONE=matchMedia('(pointer:coarse)').matches||/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)||(navigator.maxTouchPoints>1&&/Macintosh/.test(navigator.userAgent));      // a phone or tablet of any make: touch is the main pointer
const MOBILE_PANEL=PHONE&&window!==top, SMALL_PHONE=MOBILE_PANEL&&/iPhone|iPod/i.test(navigator.userAgent);
const LITE=PHONE?'&lite=1':'';
if(PHONE)Object.assign(defaults,{fps:MOBILE_PANEL?'5':'2',det:'1',qual:'65'});
if(MOBILE_PANEL){
  document.body.classList.add('mirror-inline');
  const bar=document.querySelector('.bar'),settings=document.createElement('details'),summary=document.createElement('summary');
  settings.className='mirror-settings';summary.textContent='WINDOW SETTINGS';
  bar.before(settings);settings.append(summary,bar);
}
let cfg=Object.assign({},defaults);try{cfg=Object.assign(cfg,JSON.parse(localStorage.getItem('hubMirrorCfg')||'{}'));}catch(e){}
// a window remembers its own rate: Claude Desktop is for typing and needs one picture a second; a video needs ten or more
function cfgKey(){return sel?('hubMirror:'+sel.exe):'hubMirror:x';}
function loadCfg(){let c=Object.assign({},defaults);const saved=localStorage.getItem(cfgKey());try{c=Object.assign(c,JSON.parse(saved||'{}'));}catch(e){}
  if(!MOBILE_PANEL&&!saved&&innerWidth<700&&sel&&sel.w>900)c.zoom='100';        // a phone: fitting a wide window into the screen makes the text unreadable, so it opens at full size and you move around it
  cfg=c;['fps','det','qual','zoom'].forEach(k=>{$(k).value=cfg[k];});}
function saveCfg(){try{localStorage.setItem(cfgKey(),JSON.stringify(cfg));}catch(e){}}
async function list(){const j=await (await fetch('/api/windows')).json();const s=$('pick');s.replaceChildren();
  if(!j.supported){$('note').textContent='Windows can be shown on Windows only.';return;}
  j.windows.forEach(w=>{const o=document.createElement('option');o.value=w.id;o.textContent=w.title.slice(0,48)+'  ('+w.exe.replace('.exe','')+')'+(w.minimised?'  - minimised':'');s.append(o);});
  if(!cur&&q.get('q')){const f=await (await fetch('/api/windows/find?q='+encodeURIComponent(q.get('q')))).json();if(f.window)cur=String(f.window.id);}
  if(!cur&&j.windows.length)cur=String(j.windows[0].id);s.value=cur;
  const w=j.windows.find(x=>String(x.id)===cur);if(w&&(!sel||sel.exe!==w.exe)){sel=w;loadCfg();start();}}
$('pick').onchange=()=>{cur=$('pick').value;list().then(start);};
$('focus').onclick=()=>fetch('/api/windows/'+cur+'/focus',{method:'POST'});
['fps','det','qual','zoom'].forEach(k=>{$(k).onchange=()=>{cfg[k]=$(k).value;saveCfg();start();};});
// ---- the stream: one request, frames pushed at the chosen rate (the Hub skips a picture that has not changed)
const pic=$('pic');let sw=0;
let mobileTimer=0,mobileGen=0,mobileRequest=null,mobileURL='',mobileTag='',unchanged=0,moving=false;
let visible=!MOBILE_PANEL,active=true;
function gestureMode(){
  if(SMALL_PHONE)$('stage').style.touchAction=!$('ctl').checked&&cfg.zoom==='fit'?'none':'auto';
}
function clearMobile(keepPicture=false){
  mobileGen++;clearTimeout(mobileTimer);mobileRequest?.abort();mobileRequest=null;
  mobileTag='';unchanged=0;pic.onload=pic.onerror=null;if(!keepPicture)pic.removeAttribute('src');
  if(!keepPicture&&mobileURL){URL.revokeObjectURL(mobileURL);mobileURL='';}
}
async function mobileFrame(w,gen){
  if(gen!==mobileGen)return;
  const controller=new AbortController(),began=performance.now();
  mobileRequest=controller;
  const next=ms=>{if(gen===mobileGen)mobileTimer=setTimeout(()=>mobileFrame(w,gen),ms);};
  const delay=()=>Math.max(30,1000/fpsNow()-(performance.now()-began));
  function retry(){ $('note').textContent='That window is gone or minimised.';next(1500); }
  try{
    const headers=mobileTag?{'If-None-Match':mobileTag}:{};
    const r=await fetch('/api/windows/'+cur+'/frame?w='+w+'&q='+qualNow()+'&dedup=1'+LITE,{cache:'no-store',signal:controller.signal,headers});
    if(gen!==mobileGen)return;
    if(r.status===304){unchanged++;next(SMALL_PHONE&&unchanged>=3?Math.max(250,delay()):delay());return;}
    if(!r.ok)throw new Error('frame unavailable');
    const blob=await r.blob();
    if(gen!==mobileGen)return;
    const url=URL.createObjectURL(blob), decoded=new Image();
    decoded.src=url;
    try{await decoded.decode();}catch(e){URL.revokeObjectURL(url);if(gen===mobileGen)retry();return;}
    if(gen!==mobileGen){URL.revokeObjectURL(url);return;}
    const previous=mobileURL;
    mobileURL=url;pic.src=url;
    if(previous)URL.revokeObjectURL(previous);
    unchanged=0;mobileTag=r.headers.get('ETag')||'';
    $('note').textContent='A live picture of the window, no sound.';next(delay());
  }catch(e){if(gen===mobileGen)retry();}
  finally{if(mobileRequest===controller)mobileRequest=null;}
}
if(MOBILE_PANEL){
  if(SMALL_PHONE)window.setMirrorBoardZoom=(zoom,fit,x,y)=>{
    if(cfg.zoom!=='fit'||!pic.naturalWidth)return fit;
    const stage=$('stage'),aspect=pic.naturalWidth/pic.naturalHeight;
    if(!fit){
      if(stage.clientWidth<40||stage.clientHeight<40)return null;
      fit={zoom,width:Math.min(stage.clientWidth-4,(stage.clientHeight-4)*aspect)};
    }
    const width=Math.round(Math.min(1600,fit.width*zoom/fit.zoom));
    const offset=(value,space)=>Math.round(Math.max(-space,Math.min(space,value)));
    const panX=offset(x,Math.max(0,(width-stage.clientWidth)/2));
    const panY=offset(y,Math.max(0,(width/aspect-stage.clientHeight)/2));
    const style=width+'_'+panX+'_'+panY;
    if(pic.dataset.boardGeometry!==style){
      pic.dataset.boardGeometry=style;
      pic.style.setProperty('--mirror-board-width',width+'px');
      pic.style.setProperty('--mirror-pan-x',panX+'px');
      pic.style.setProperty('--mirror-pan-y',panY+'px');
    }
    pic.classList.add('board-zoom');
    if(phoneW()!==wNow){clearTimeout(zoomT);zoomT=setTimeout(()=>{if(!moving&&phoneW()!==wNow)start(true);},600);}      // zoomed to a new size: a picture with the pixels to match, once the zoom has settled
    return fit;
  };
  window.setMirrorMoving=value=>{if(moving!==value){moving=value;if(vidOn){const v=$('vid');if(value)v.pause();else v.play().catch(()=>{});}else start(true);}};
  window.setMirrorActive=value=>{if(active!==value){active=value;start();}};
  try{
    const frame=window.frameElement;
    active=frame.dataset.mirrorActive!=='false';
    const observer=new parent.IntersectionObserver(([entry])=>{
      const next=entry.isIntersecting&&entry.intersectionRatio>0;
      if(next!==visible){visible=next;start();}
    });
    observer.observe(frame);
    addEventListener('pagehide',()=>observer.disconnect());
    addEventListener('pageshow',e=>{if(e.persisted)observer.observe(frame);});
  }catch(e){visible=true;}
  document.addEventListener('visibilitychange',start);
  addEventListener('pageshow',e=>{if(e.persisted){alive=true;start();}});
}
// An iPhone's picture is asked for at the size it is SHOWN: its width on screen times the screen's pixel ratio, in steps of 160 px so a small change of zoom does not ask again. Never under 864 (it
// was a flat 864, which is soft at a 100 % or 150 % board zoom on a 3x screen) and never over the phone's budget of 1400, which the server enforces too.
let wNow=0,zoomT=0;
function phoneW(){const bw=parseFloat(pic.style.getPropertyValue('--mirror-board-width'))||0,css=pic.classList.contains('board-zoom')&&bw?bw:Math.max(300,$('stage').clientWidth),dpr=Math.min(3,devicePixelRatio||1);
  return Math.max(864,Math.min(1400,Math.ceil(css*dpr/160)*160));}
function start(keepPicture=false){if(!cur||!alive||(typeof vidOn!=='undefined'&&vidOn))return;
  const dpr=Math.min(2,devicePixelRatio||1),shown=cfg.zoom==='fit'?Math.max(300,$('stage').clientWidth):Math.round((sel?sel.w:1200)*Number(cfg.zoom)/100);
  const det=Number(cfg.det),w=SMALL_PHONE?phoneW():MOBILE_PANEL?Math.min(900,Math.round(shown*dpr*(det||1))):PHONE?Math.min(1400,Math.round(shown*dpr*(det||1))):(det===0?3000:Math.min(2600,Math.round(shown*dpr*det)));
  pic.classList.toggle('fit',cfg.zoom==='fit');pic.style.width=cfg.zoom==='fit'?'100%':shown+'px';pic.style.maxWidth=cfg.zoom==='fit'?'100%':'none';
  if(MOBILE_PANEL){
    clearMobile(keepPicture===true&&!moving);gestureMode();
    if(visible&&!moving&&active&&!document.hidden)mobileFrame(w,mobileGen);
    wNow=w;$('stat').textContent=fpsNow()+' / s, up to '+w+' px wide (single pictures)';
    return;
  }
  clearTimeout(streamT);mode=(PHONE||sessionStorage.getItem('hubMirrorPoll')==='1')?'poll':'stream';pic.onload=null;pollGen++;
  if(mode==='poll'){poll(w);}
  else{pic.src='/api/windows/'+cur+'/stream?fps='+fpsNow()+'&w='+w+'&q='+qualNow()+LITE+'&t='+Date.now();
    streamT=setTimeout(()=>{if(!(pic.naturalWidth>0)){try{sessionStorage.setItem('hubMirrorPoll','1');}catch(e){}mode='poll';poll(w);}},4500);}
  $('stat').textContent=fpsNow()+' / s, up to '+w+' px wide'+(mode==='poll'?' (single pictures)':'');}
const fpsNow=()=>PHONE?Math.min(SMALL_PHONE?(MOBILE_PANEL?8:3):5,Number(cfg.fps)):Number(cfg.fps),qualNow=()=>PHONE?Math.min(SMALL_PHONE?75:MOBILE_PANEL?65:75,Number(cfg.qual)):Number(cfg.qual);
let streamT=0,mode='stream';
let pollGen=0;
function poll(w){if(!alive||mode!=='poll')return;const gen=pollGen,t0=Date.now();
  if(document.hidden){setTimeout(()=>poll(w),800);return;}
  const next=ms=>setTimeout(()=>{if(gen===pollGen)poll(w);},ms);
  fetch('/api/windows/'+cur+'/frame?w='+Math.min(w,PHONE?1400:1800)+'&q='+qualNow()+LITE+'&t='+t0,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('gone');return r.blob();}).then(b=>{
    if(gen!==pollGen)return;const u=URL.createObjectURL(b),old=pic.dataset.blob;
    pic.onload=()=>{if(old)URL.revokeObjectURL(old);$('note').textContent='A live picture of the window, no sound.';next(Math.max(30,1000/fpsNow()-(Date.now()-t0)));};
    pic.onerror=()=>{URL.revokeObjectURL(u);next(1500);};
    pic.dataset.blob=u;pic.src=u;}).catch(()=>{$('note').textContent='That window is gone or minimised.';next(1500);});}
addEventListener('pagehide',()=>{alive=false;if(MOBILE_PANEL)clearMobile();pollGen++;const u=pic.dataset.blob;if(u)URL.revokeObjectURL(u);pic.removeAttribute('src');});
pic.onerror=()=>{$('note').textContent='That window is gone or minimised.';setTimeout(start,2000);};
addEventListener('resize',()=>{if(SMALL_PHONE&&cfg.zoom==='fit')return;clearTimeout(sw);sw=setTimeout(start,400);});
// ---- clicks, keys, wheel
const post=(p,b)=>fetch('/api/windows/'+cur+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
function on(){return $('ctl').checked&&cur;}
$('ctl').onchange=()=>{$('kbrow').hidden=!$('ctl').checked;gestureMode();};
// A phone raises its keyboard only for a focus that happens inside the tap itself, so the typing box is focused at once, before the click is sent.
function focusKb(){if($('ctl').checked)$('kb').focus({preventScroll:true});}
pic.addEventListener('pointerdown',focusKb);pic.addEventListener('touchstart',focusKb,{passive:true});
const tgt=()=>($('vid').hidden?pic:$('vid'));
// VIDEO: where the browser plays HLS itself (Safari, the iPhone), the window can be watched as real video instead of pictures. It is asked for, never automatic; a phone cannot hold pictures at that rate, but it decodes video in hardware.
var vidOn=false,beatTimer=0;
// What this page tells the Hub while it plays: alive every 4 s, and at once when it waits, stalls, errors or leaves (the Hub's log and /api/windows/video/report keep it; silence without a goodbye is how a crash shows).
function beat(kind){try{const v=$('vid'),q=v.getVideoPlaybackQuality?v.getVideoPlaybackQuality():{},view=(()=>{try{return parent.__hubBoard.active.view().mode();}catch(e){return window===top?'page':'';}})();
  navigator.sendBeacon('/api/windows/video/beat',new Blob([JSON.stringify({id:cur,kind,t:Math.round(v.currentTime*10)/10,ready:v.readyState,dropped:q.droppedVideoFrames,total:q.totalVideoFrames,view,moving:!!moving})],{type:'application/json'}));}catch(e){}}
['waiting','stalled','error'].forEach(n=>$('vid').addEventListener(n,()=>{if(vidOn)beat(n);}));
const canHls=!!document.createElement('video').canPlayType('application/vnd.apple.mpegurl');
if(canHls)$('vidbtn').hidden=false;
async function videoStart(){
  $('note').textContent='Starting the video...';
  let j;try{j=await (await fetch('/api/windows/'+cur+'/video/start?fps=30&w='+(SMALL_PHONE?960:1280),{method:'POST'})).json();}catch(e){j={ok:false,error:String(e)};}
  if(!j.ok){vidOn=false;$('vidbtn').classList.remove('on');$('note').textContent=j.error||'The video did not start.';return false;}
  vidOn=true;$('vidbtn').classList.add('on');$('vidbtn').textContent='PICTURES';
  if(typeof clearMobile==='function')clearMobile();pollGen++;clearTimeout(streamT);pic.removeAttribute('src');pic.hidden=true;
  const v=$('vid');v.hidden=false;v.src=j.playlist;v.play&&v.play().catch(()=>{});beat('start');beatTimer=setInterval(()=>beat('beat'),4000);
  $('note').textContent='Live video ('+j.encoder+', '+j.fps+' a second, no sound).';return true;}
async function videoStop(){
  clearInterval(beatTimer);beat('stop');vidOn=false;$('vidbtn').classList.remove('on');$('vidbtn').textContent='VIDEO';
  const v=$('vid');v.pause&&v.pause();v.removeAttribute('src');v.load&&v.load();v.hidden=true;pic.hidden=false;
  try{await fetch('/api/windows/'+cur+'/video/stop',{method:'POST'});}catch(e){}
  start();}
$('vidbtn').onclick=()=>vidOn?videoStop():videoStart();
$('vid').onclick=e=>pic.onclick(e);
addEventListener('pagehide',()=>{if(vidOn){beat('pagehide');try{navigator.sendBeacon('/api/windows/'+cur+'/video/stop');}catch(e){}}});
pic.onclick=async e=>{if(!on())return;focusKb();const r=tgt().getBoundingClientRect();
  const x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;const x2=await post('/click',{x,y});
  $('note').textContent=x2.ok?'Clicked. Type in the box above, the keyboard is for it.':'That click did not land.';focusKb();};
// What is typed in the box goes to the window as it is typed: the new characters, or Backspace for each one taken away (a phone's own keyboard, autocorrect and all, only ever tells us the box changed).
let kbLast='';
const sendText=s=>{for(let n=0;n<s.length;n+=300)post('/keys',{text:s.slice(n,n+300)});};
$('kb').addEventListener('input',()=>{if(!on())return;const v=$('kb').value;
  if(v.length>kbLast.length&&v.startsWith(kbLast))sendText(v.slice(kbLast.length));
  else if(v.length<kbLast.length&&kbLast.startsWith(v)){for(let n=kbLast.length-v.length;n>0;n--)post('/keys',{key:'Backspace'});}
  else if(v!==kbLast){for(let n=kbLast.length;n>0;n--)post('/keys',{key:'Backspace'});if(v)sendText(v);}
  kbLast=v;});
$('kb').addEventListener('keydown',e=>{if(!on())return;const k=e.key;
  if(k==='Enter'&&!e.shiftKey){e.preventDefault();post('/keys',{key:'Enter'});$('kb').value='';kbLast='';}
  else if(k==='Backspace'&&$('kb').value===''){e.preventDefault();post('/keys',{key:'Backspace'});}
  else if(k==='Tab'||k==='Escape'||(k.startsWith('Arrow')&&$('kb').value==='')||k==='Delete'&&$('kb').value===''){e.preventDefault();post('/keys',{key:k});}
  else if(e.ctrlKey&&k.length===1&&k.toLowerCase()!=='a'){e.preventDefault();post('/keys',{key:k,ctrl:true});}});
$('kbclear').onclick=()=>{$('kb').value='';kbLast='';};
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>{if(on()){post('/keys',{key:b.dataset.key});if(b.dataset.key==='Enter'){$('kb').value='';kbLast='';}}});
$('stage').addEventListener('keydown',e=>{if(!on()||e.target.id==='kb')return;
  if(e.key.length===1&&!e.ctrlKey&&!e.metaKey){e.preventDefault();post('/keys',{text:e.key});}
  else if(e.ctrlKey&&e.key.length===1){e.preventDefault();post('/keys',{key:e.key,ctrl:true});}
  else if(['Enter','Backspace','Tab','Escape','ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Delete','Home','End','PageUp','PageDown'].includes(e.key)){e.preventDefault();post('/keys',{key:e.key});}});
$('stage').addEventListener('wheel',e=>{if(!on())return;e.preventDefault();const r=tgt().getBoundingClientRect();post('/wheel',{x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height,delta:-Math.sign(e.deltaY)*120});},{passive:false});
if(window===top)$('back').hidden=false;      // on a page of its own (a phone opens it so), there is a way back
$('close').onclick=async()=>{await fetch('/api/windows/panels?url='+encodeURIComponent(location.pathname+location.search),{method:'DELETE'});try{parent.postMessage({hubWindowClose:location.pathname+location.search},'*');}catch(e){}if(window===top)location.href='/?enter=1';};
list().then(()=>setInterval(list,8000));
addEventListener('pagehide',()=>{alive=false;pic.removeAttribute('src');});
</script>
"""

_SESSION = _STYLE + """<title>Session</title><body>
<div class="bar"><b id="ttl">Session</b><span class="mute" id="meta"></span></div><div class="view" id="v"></div>
<script>
const id=new URLSearchParams(location.search).get('id')||'',v=document.getElementById('v');let stick=true;v.onscroll=()=>{stick=v.scrollTop+v.clientHeight>=v.scrollHeight-30;};
async function load(){try{const j=await (await fetch('/api/sessions/transcript?id='+encodeURIComponent(id))).json();
  if(j.error){v.textContent=j.error;return;}document.getElementById('ttl').textContent=j.title;document.getElementById('meta').textContent=j.project+' · '+j.state+(j.ask?' · waiting: '+j.ask:'');
  v.replaceChildren(...j.turns.map(t=>{const d=document.createElement('div');d.className='t '+t.who;const b=document.createElement('b');b.textContent=t.who.toUpperCase();d.append(b,document.createElement('br'),document.createTextNode(t.text));return d;}));
  if(stick)v.scrollTop=v.scrollHeight;}catch(e){}}
load();setInterval(load,3000);
</script>"""


@routes.get("/mirror")
async def page_mirror(request: web.Request) -> web.Response:
    return web.Response(text=_MIRROR, content_type="text/html")


@routes.get("/session")
async def page_session(request: web.Request) -> web.Response:
    return web.Response(text=_SESSION, content_type="text/html")
