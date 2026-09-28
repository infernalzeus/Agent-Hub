"""The recorder: what it captures, what it refuses to capture, and what it leaks.

The hooks themselves need a real Windows desktop, so the tests drive the session
object directly. That is the honest boundary: everything above the hook - step
accumulation, timing, the anchor, the review view, saving, and the refusals - is
covered here, and the hook is left to the live check in the test list.

The security-shaped tests are the point of the file. A recorder is the one
feature in the hub that watches the keyboard, so the properties that keep it from
being a keylogger are pinned, not assumed.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from hub.features import machine_recorder as REC  # noqa: E402


class FakeImage:
    """Just enough Pillow for the anchor crop."""
    width, height = 1920, 1080

    def crop(self, box):
        self.box = box
        return self

    def save(self, fh, format="PNG"):
        fh.write(b"\x89PNG\r\n\x1a\n" + bytes(16))


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(REC.MR, "_grab", lambda: FakeImage())
    monkeypatch.setattr(REC, "_foreground", lambda: ("Notepad", (100, 50, 1100, 850)))
    return REC.Session()


# ── what it captures ──────────────────────────────────────────────────────────
def test_a_click_stores_an_anchor_and_a_window_fraction(session):
    session._on_click(600, 450, "left")
    step = session.steps[0]
    assert step["tool"] == "Click"
    assert step["anchor_png"].startswith(b"\x89PNG"), "replay matches the crop, so it must exist"
    # (600-100)/1000 across, (450-50)/800 down
    assert step["frac"] == [0.5, 0.5]
    assert "Notepad" in step["note"], "the review screen has to read as English"


def test_the_crop_is_clamped_at_the_screen_edge(session):
    """A click near the corner must not ask for pixels that are not there."""
    session._on_click(5, 5, "left")
    assert session.steps, "a corner click is still a click"
    assert session.steps[0]["anchor_png"]


def test_delays_are_measured_between_steps(session):
    session._on_click(600, 450, "left")
    session.last_event -= 0.4                     # pretend 400ms passed
    session._on_click(700, 450, "left")
    assert session.steps[0]["delay_ms"] < 100
    assert 350 <= session.steps[1]["delay_ms"] <= 500


def test_ordinals_are_dense_and_in_order(session):
    for i in range(5):
        session._on_click(600 + i, 450, "left")
    assert [s["ordinal"] for s in session.steps] == [0, 1, 2, 3, 4]


# ── what it refuses to capture ────────────────────────────────────────────────
def test_keys_are_separate_steps_and_never_a_string(session):
    """The property that keeps this from being a keylogger.

    A routine for a game is mostly key presses, so keys must be captured. But
    nothing may ever concatenate them: a recorder that builds up "hunter2" from
    eight keystrokes has become something else.
    """
    for vk in (0x50, 0x41, 0x53, 0x53):           # P A S S
        session._on_key(vk)
    assert len(session.steps) == 4
    assert [s["args"]["keys"] for s in session.steps] == [["P"], ["A"], ["S"], ["S"]]
    for step in session.steps:
        assert "text" not in step and "text" not in step["args"]
    joined = "".join(s["args"]["keys"][0] for s in session.steps)
    assert not any(joined in str(v) for s in session.steps for v in s.values()), \
        "no step may hold the keys as one run of text"


def test_escape_stops_instead_of_being_recorded(session):
    session._on_key(REC.VK_ESCAPE)
    assert session.steps == [], "the stop key is not part of the routine"
    assert session.stopped_by == "Esc"


def test_a_session_cannot_grow_without_bound(session, monkeypatch):
    monkeypatch.setattr(REC, "MAX_STEPS", 5)
    for i in range(20):
        session._on_click(600, 450, "left")
    assert len(session.steps) <= 5
    assert session.stopped_by, "hitting the cap must end the session, not silently drop input"


def test_the_session_has_a_deadline():
    assert 0 < REC.MAX_SESSION_S <= 30 * 60, \
        "an input hook with no deadline is one nobody remembers to turn off"


# ── what it shows ─────────────────────────────────────────────────────────────
def test_the_view_never_carries_image_bytes(session):
    session._on_click(600, 450, "left")
    view = session.view()
    assert view["steps"][0]["has_anchor"] is True
    assert "anchor_png" not in view["steps"][0], "screenshots must not ride along in JSON"
    assert b"PNG" not in repr(view).encode()


def test_the_view_reads_as_words(session):
    session._on_click(600, 450, "left")
    session._on_key(0x41)
    notes = [s["note"] for s in session.view()["steps"]]
    assert notes == ["left-click in “Notepad”", "press A"]


# ── saving ────────────────────────────────────────────────────────────────────
def test_saving_drops_the_steps_you_dropped(session, monkeypatch, tmp_path):
    saved = {}

    def fake_save(intent, title, window, profile, steps):
        saved.update(intent=intent, steps=steps, window=window, profile=profile)
        return {"id": "r1", "status": "candidate"}

    monkeypatch.setattr(REC.MR, "save_machine_routine", fake_save)
    for i in range(3):
        session._on_click(600 + i, 450, "left")

    keep = [st for st in session.steps if st["ordinal"] not in {1}]
    REC.MR.save_machine_routine("open the thing", "Open the thing",
                                session.window, "balanced", keep)
    assert len(saved["steps"]) == 2
    assert [s["ordinal"] for s in saved["steps"]] == [0, 2]


def test_a_new_session_starts_empty():
    """Nothing may survive from a previous recording."""
    a = REC.Session()
    a.steps.append({"ordinal": 0, "tool": "Click", "note": "x",
                    "delay_ms": 0, "frac": None})
    assert REC.Session().steps == []


def test_available_is_honest_about_this_machine():
    """It must never claim it can record when it cannot."""
    import ctypes
    from hub.features import machine_routines as MR
    assert REC.available() == (hasattr(ctypes, "windll") and MR.inproc_ready())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── the property that matters most ────────────────────────────────────────────
# Found live: stop() returned while the hook thread was still unwinding, so the
# hooks were briefly still installed after the session claimed to be over. For an
# input hook, that window IS the safety property.

def test_running_is_answered_by_the_thread_not_a_flag():
    s = REC.Session()
    assert not s.running, "a session with no thread is not running"
    s._run = False
    assert not s.running


def test_stop_waits_for_the_thread(monkeypatch):
    import threading
    s = REC.Session()
    released = threading.Event()

    def slow_pump():
        while s._run:
            time.sleep(0.01)
        time.sleep(0.15)          # unwinding: unhooking happens in here
        s._hooks = []
        released.set()

    s._thread = threading.Thread(target=slow_pump, daemon=True)
    s._hooks = [1, 2]
    s._thread.start()
    time.sleep(0.05)
    s.stop("test")
    assert released.is_set(), "stop() returned before the hooks were released"
    assert s._hooks == []
    assert not s.running


def test_stop_from_inside_the_hook_thread_does_not_deadlock():
    """Esc arrives on the hook thread; joining itself there would hang forever."""
    import threading
    s = REC.Session()
    done = threading.Event()

    def pump():
        s.stop("Esc")             # stopping itself
        done.set()

    s._thread = threading.Thread(target=pump, daemon=True)
    s._thread.start()
    assert done.wait(2.0), "stop() deadlocked when called from the hook thread"


def test_function_keys_go_up_to_24():
    assert REC._vk_name(0x70) == "F1"
    assert REC._vk_name(0x87) == "F24", "Windows has 24 function keys"
