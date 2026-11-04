"""Weak evidence: what the person did next hints at whether a choice worked, and is counted apart from exact labels."""
from hub.features import learning as L


def mk(text, at, ok=None):
    return ({"kind": "route", "context": "bin", "chosen": "app_task", "options": [], "by": "rules", "ok": ok, "at": at}, text, at)


def test_a_repeat_or_a_correction_soon_after_is_a_likely_failure_and_a_different_request_a_hint_of_success():
    rows = [mk("open apple music", 100), mk("open apple music", 130), mk("no, I meant the playlist", 150), mk("what time is it", 400), mk("play jazz", 430)]
    L.weak_labels(rows)
    got = [r[0].get("weak") for r in rows]
    assert got == [False, False, None, True, None]            # the last has nothing after it; 150 -> 400 is too far apart to say anything


def test_an_exact_label_is_never_touched_and_weak_never_fills_ok():
    rows = [mk("open notepad", 10, ok=True), mk("open notepad", 20)]
    L.weak_labels(rows)
    assert rows[0][0]["ok"] is True and "weak" not in rows[0][0]
    assert all(r[0]["ok"] in (True, None) for r in rows)


def test_counters_keep_weak_evidence_apart_from_exact_labels():
    a, _, _ = mk("x", 1)
    a["weak"] = False
    b, _, _ = mk("y", 2)
    b["weak"] = True
    c, _, _ = mk("z", 3, ok=True)
    t = L.counters([a, b, c])["route"]["bin"]["app_task"]
    assert (t["ok"], t["failed"], t["unknown"], t["weak_ok"], t["weak_failed"]) == (1, 0, 2, 1, 1)
