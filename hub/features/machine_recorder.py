"""Teach a machine routine by doing it once.

`machine_routines.py` can already replay a surface sequence: match an anchor
image, click where it was found, judge its own confidence, refuse when the screen
changed. What it never had was a way to *get* that sequence. This is that half.

How it captures, and why this way:

* **Explicit RECORD only.** Hooks are installed when you press record and removed
  when you stop or the session times out. A hub that silently learns what you do
  on your own PC is a different and much worse product, so there is no
  always-on watcher and no way to start one by accident.

* **Keys are recorded as keys, never as text.** A routine for a game is mostly
  key presses, so they have to be captured — but each one is stored as its own
  step ("press A"), and nothing ever concatenates them into a string. That is a
  deliberate limit: this records *input*, and must not become something that
  assembles a typed password. Text you want typed is entered in the Hub, in the
  review screen, where you can see it.

* **Anchors, not coordinates.** Every click stores a small crop of the screen
  around the point, plus the point as a fraction of the window. Replay finds the
  crop again; the fraction is only the starting guess. That is what lets a
  routine survive the window moving.

* **Nothing is saved until you look at it.** A session lives in memory and is
  handed back as a list of steps in plain words. You name it, delete the steps
  you did not mean, and only then does it become a candidate routine.

Windows-only, like the rest of PC control: the hooks are `SetWindowsHookEx`.
Everywhere else this reports unavailable rather than half-working.
"""
from __future__ import annotations

import ctypes
import io
import threading
import time
from ctypes import wintypes

from aiohttp import web

from ..config import logger
from . import machine_routines as MR

routes = web.RouteTableDef()

# A session that outlives its purpose is a session nobody meant to leave running.
MAX_SESSION_S = 15 * 60
ANCHOR_PX = 96              # the crop stored around a click, in screen pixels
MAX_STEPS = 200

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_ESCAPE = 0x1B

# Only the names worth showing a human. Anything else is reported by code.
_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift", 0x11: "Ctrl",
    0x12: "Alt", 0x14: "CapsLock", 0x1B: "Esc", 0x20: "Space", 0x21: "PageUp",
    0x22: "PageDown", 0x23: "End", 0x24: "Home", 0x25: "Left", 0x26: "Up",
    0x27: "Right", 0x28: "Down", 0x2E: "Delete",
    **{0x70 + i: f"F{i + 1}" for i in range(24)},   # F1-F24, 0x70-0x87
}


def available() -> bool:
    """Can this machine record at all? Needs Windows and the imaging tools."""
    return hasattr(ctypes, "windll") and MR.inproc_ready()


def _vk_name(vk: int) -> str:
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    if 0x30 <= vk <= 0x5A:            # 0-9 and A-Z
        return chr(vk)
    return f"VK_{vk:02X}"


def _foreground() -> tuple[str, tuple[int, int, int, int]]:
    """The window in front, and its rectangle. ('', (0,0,0,0)) if unknown."""
    try:
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return "", (0, 0, 0, 0)
        length = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        u.GetWindowTextW(hwnd, buf, length + 1)
        rect = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rect))
        return buf.value, (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return "", (0, 0, 0, 0)


def _anchor_and_frac(x: int, y: int) -> tuple[bytes | None, list[float], str]:
    """A crop around the click, and where the click was inside its window.

    The crop is the thing replay actually matches on. The fraction is stored
    alongside as the first place to look, and as the fallback for a window with
    no distinguishing art at the click point.
    """
    title, (left, top, right, bottom) = _foreground()
    width, height = max(1, right - left), max(1, bottom - top)
    frac = [round((x - left) / width, 4), round((y - top) / height, 4)]
    try:
        frame = MR._grab()
        half = ANCHOR_PX // 2
        box = (max(0, x - half), max(0, y - half),
               min(frame.width, x + half), min(frame.height, y + half))
        out = io.BytesIO()
        frame.crop(box).save(out, format="PNG")
        return out.getvalue(), frac, title
    except Exception as exc:
        logger.warning("recorder: could not capture an anchor: %s", exc)
        return None, frac, title


class Session:
    """One recording. Holds its steps in memory and nowhere else until saved."""

    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.started = time.time()
        self.last_event = time.time()
        self.window = ""
        self.stopped_by = ""
        self._lock = threading.Lock()
        self._run = True
        self._thread: threading.Thread | None = None
        self._hooks: list = []

    # ── capture ───────────────────────────────────────────────────────────────
    def _add(self, step: dict) -> None:
        with self._lock:
            if len(self.steps) >= MAX_STEPS:
                self.stop("too many steps")
                return
            now = time.time()
            step["delay_ms"] = int((now - self.last_event) * 1000)
            step["ordinal"] = len(self.steps)
            self.last_event = now
            self.steps.append(step)

    def _on_click(self, x: int, y: int, button: str) -> None:
        png, frac, title = _anchor_and_frac(x, y)
        self.window = self.window or title
        self._add({
            "tool": "Click",
            "args": {"button": button},
            "frac": frac,
            "anchor_png": png,
            "note": f"{button}-click in “{title or 'the screen'}”",
        })

    def _on_key(self, vk: int) -> None:
        if vk == VK_ESCAPE:
            self.stop("Esc")
            return
        name = _vk_name(vk)
        self._add({
            "tool": "Shortcut",
            "args": {"keys": [name]},
            "frac": None,
            "anchor_png": None,
            "note": f"press {name}",
        })

    # ── the hook thread ───────────────────────────────────────────────────────
    def _pump(self) -> None:
        """Hooks must be installed on the thread that pumps their messages."""
        u = ctypes.windll.user32
        # Without these, ctypes guesses: it narrowed the 64-bit lparam to an int
        # and raised OverflowError on every event, so the rest of the hook chain
        # was never called. Declaring the signatures is not optional here.
        u.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                     wintypes.WPARAM, wintypes.LPARAM]
        u.CallNextHookEx.restype = ctypes.c_long
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                        wintypes.HINSTANCE, wintypes.DWORD]
        u.SetWindowsHookExW.restype = wintypes.HHOOK
        u.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        u.UnhookWindowsHookEx.restype = wintypes.BOOL
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int,
                                       wintypes.WPARAM, wintypes.LPARAM)

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        def mouse(code, wparam, lparam):
            # Always pass the event on: a recorder that swallows clicks would make
            # the machine unusable the moment it hung.
            try:
                if code >= 0 and wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    self._on_click(data.pt.x, data.pt.y,
                                   "left" if wparam == WM_LBUTTONDOWN else "right")
            except Exception as exc:
                logger.warning("recorder: mouse hook: %s", exc)
            return u.CallNextHookEx(None, code, wparam, lparam)

        def keyboard(code, wparam, lparam):
            try:
                if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    self._on_key(int(data.vkCode))
            except Exception as exc:
                logger.warning("recorder: keyboard hook: %s", exc)
            return u.CallNextHookEx(None, code, wparam, lparam)

        # Keep references alive; a garbage-collected callback crashes the process.
        self._cbs = [proc_type(mouse), proc_type(keyboard)]
        self._hooks = [u.SetWindowsHookExW(WH_MOUSE_LL, self._cbs[0], None, 0),
                       u.SetWindowsHookExW(WH_KEYBOARD_LL, self._cbs[1], None, 0)]
        if not all(self._hooks):
            logger.error("recorder: could not install hooks")
            self._run = False

        msg = wintypes.MSG()
        while self._run:
            if time.time() - self.started > MAX_SESSION_S:
                self.stopped_by = self.stopped_by or "timed out"
                break
            # PeekMessage rather than GetMessage: GetMessage blocks forever and
            # would leave the hooks installed when the session is stopped from
            # the web UI instead of from the keyboard.
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)

        for hook in self._hooks:
            if hook:
                u.UnhookWindowsHookEx(hook)
        self._hooks = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._pump, name="machine-recorder",
                                        daemon=True)
        self._thread.start()

    def stop(self, why: str = "stopped", wait: float = 2.0) -> None:
        """Ask the hook thread to finish, and wait for it to actually do so.

        Returning early here meant the hooks were still installed for a moment
        after the session said it was over. For an input hook that window is the
        whole safety property, so stop() blocks until the thread has unhooked.
        """
        self.stopped_by = self.stopped_by or why
        self._run = False
        thread = self._thread
        # Never join from inside the hook thread itself (Esc arrives there).
        if wait and thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(wait)
            if thread.is_alive():
                logger.warning("recorder: hook thread did not stop within %.1fs", wait)

    @property
    def running(self) -> bool:
        """Answered by the thread, not by the flag: while it is alive the hooks
        may still be installed, and that is what 'running' has to mean."""
        return bool(self._thread and self._thread.is_alive())

    def view(self) -> dict:
        """What the panel shows. Anchors are reported by size, never inlined."""
        with self._lock:
            steps = [{
                "ordinal": s["ordinal"], "tool": s["tool"], "note": s["note"],
                "delay_ms": s["delay_ms"], "frac": s["frac"],
                "has_anchor": bool(s.get("anchor_png")),
            } for s in self.steps]
        return {"running": self.running, "window": self.window,
                "seconds": int(time.time() - self.started),
                "stopped_by": self.stopped_by, "steps": steps,
                "max_seconds": MAX_SESSION_S}


_session: Session | None = None
_guard = threading.Lock()


def current() -> Session | None:
    return _session


# ── api ───────────────────────────────────────────────────────────────────────
@routes.get("/api/pc/record")
async def api_state(request: web.Request) -> web.Response:
    if not available():
        return web.json_response({"available": False, "running": False, "steps": [],
                                  "why": "Recording needs Windows and the imaging tools "
                                         "(set up Screen recording first)."})
    s = current()
    return web.json_response({"available": True, **(s.view() if s else
                              {"running": False, "steps": [], "seconds": 0})})


@routes.post("/api/pc/record/start")
async def api_start(request: web.Request) -> web.Response:
    global _session
    if not available():
        raise web.HTTPPreconditionRequired(text="recording is not available on this machine")
    with _guard:
        if _session and _session.running:
            raise web.HTTPConflict(text="a recording is already running")
        _session = Session()
        _session.start()
    logger.info("recorder: started")
    return web.json_response(_session.view())


@routes.post("/api/pc/record/stop")
async def api_stop(request: web.Request) -> web.Response:
    s = current()
    if not s:
        raise web.HTTPNotFound(text="nothing is being recorded")
    await __import__("asyncio").to_thread(s.stop, "you")
    logger.info("recorder: stopped after %d step(s)", len(s.steps))
    return web.json_response(s.view())


@routes.post("/api/pc/record/save")
async def api_save(request: web.Request) -> web.Response:
    """Turn the captured steps into a candidate routine."""
    s = current()
    if not s:
        raise web.HTTPNotFound(text="nothing to save")
    if s.running:
        raise web.HTTPConflict(text="stop the recording first")
    body = await request.json()
    intent = str(body.get("intent") or "").strip()
    title = str(body.get("title") or intent).strip()
    profile = str(body.get("profile") or "balanced")
    drop = {int(i) for i in (body.get("drop") or [])}
    if not intent:
        raise web.HTTPBadRequest(text="give the routine something to be called by")
    steps = [st for st in s.steps if st["ordinal"] not in drop]
    if not steps:
        raise web.HTTPBadRequest(text="every step was dropped — nothing to save")
    routine = MR.save_machine_routine(intent, title, s.window, profile, steps)
    logger.info("recorder: saved %s (%d step(s))", intent, len(steps))
    return web.json_response({"ok": True, "routine": routine})


@routes.post("/api/pc/record/discard")
async def api_discard(request: web.Request) -> web.Response:
    global _session
    s = current()
    if s:
        s.stop("discarded")
    with _guard:
        _session = None
    return web.json_response({"ok": True})
