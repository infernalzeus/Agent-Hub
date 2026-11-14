"""NEEDS ATTENTION says how old each item is, lists the old ones last and greyed, and offers a way to clear them (13 Nov: a review from 4 Nov and two proposals from 15 Oct still read as 'needs you')."""
import time
from types import SimpleNamespace

from hub.features import home_state as H, missions as M, proposals as P


def _mission(mid, status, created):
    return SimpleNamespace(id=mid, project_name="Agent Hub", brief="Doctor: look at it", status=status, agent="doctor", runtime="claude-code", model=None, created=created, error="", ended=created, changed_files=[], questions=[])


def test_old_items_are_marked_old_sorted_last_and_can_be_cleared(monkeypatch):
    now = time.time()
    monkeypatch.setattr(P, "load", lambda: [{"id": "old1", "kind": "action_app", "name": "Old thing", "why": "x", "created": now - 30 * 86400},
                                            {"id": "new1", "kind": "action_app", "name": "New thing", "why": "y", "created": now - 120}])
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _mission("a", "awaiting_review", now - 10 * 86400), "b": _mission("b", "awaiting_review", now - 3600)}))
    att = [a for a in H.state()["attention"] if a["kind"] in ("proposal", "mission")]
    by = {a["id"]: a for a in att}
    assert not by["new1"]["old"] and by["new1"]["level"] == "amber" and by["b"]["old"] is False
    assert by["old1"]["old"] and by["old1"]["level"] == "" and by["old1"]["dismiss"] == {"method": "DELETE", "url": "/api/proposals/old1", "label": "DISMISS"}
    assert by["a"]["old"] and by["a"]["dismiss"]["url"] == "/api/missions/a/discard" and by["a"]["age_s"] >= 10 * 86400
    assert [a["old"] for a in att] == sorted(a["old"] for a in att)                       # fresh first, old last
